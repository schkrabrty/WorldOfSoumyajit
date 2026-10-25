#!/usr/bin/env python3
"""Exercise image preparation against an in-memory S3, without cloud writes."""
import hashlib
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from manage_site import Handler
from s3_library import AWSProblem, DEFAULTS, MAX_PHOTO_BYTES, S3Library, THUMBNAIL_FOLDER


class ThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "_data").mkdir()
        (self.root / "_config.yml").write_text("name: Test\n")
        self.library = S3Library(self.root)
        self.key = DEFAULTS["prefix"] + "Gallery/Portrait + ছবি.JPG"
        self.objects = {}
        self.add(self.key, b"original photo")
        self.library.command = Mock(side_effect=self.command)
        self.library._public = Mock(side_effect=lambda key: {"key": key, "url": self.library.public_url(key)})
        self.library.render_thumbnail = Mock(side_effect=lambda source, target: target.write_bytes(b"small webp"))

    def tearDown(self):
        self.temp.cleanup()

    def add(self, key, content):
        self.objects[key] = {"data": content, "ETag": '"' + hashlib.md5(content).hexdigest() + '"', "ContentLength": len(content)}

    def command(self, *args, **kwargs):
        operation = args[1]
        value = lambda name: args[args.index(name) + 1]
        if operation == "list-objects-v2":
            prefix = value("--prefix")
            contents, folders = [], set()
            for key, obj in self.objects.items():
                if not key.startswith(prefix): continue
                rest = key[len(prefix):]
                if "/" in rest:
                    folders.add(prefix + rest.split("/")[0] + "/")
                else:
                    contents.append({"Key": key, "Size": obj["ContentLength"], "ETag": obj["ETag"]})
            return {"Contents": contents, "CommonPrefixes": [{"Prefix": folder} for folder in sorted(folders)]}
        key = value("--key")
        if operation == "head-object":
            if key not in self.objects: raise AWSProblem("An error occurred (404) when calling HeadObject: Not Found")
            return {k: v for k, v in self.objects[key].items() if k != "data"}
        if operation == "get-object":
            self.assertEqual(value("--if-match"), self.objects[key]["ETag"])
            Path(args[-1]).write_bytes(self.objects[key]["data"])
            return {}
        if operation == "put-object":
            self.assertEqual(value("--if-none-match"), "*")
            self.assertNotEqual(key, self.key)
            if key in self.objects: raise AWSProblem("An error occurred (PreconditionFailed) when calling PutObject")
            self.add(key, Path(value("--body")).read_bytes())
            self.objects[key]["Metadata"] = json.loads(value("--metadata"))
            return {"ETag": self.objects[key]["ETag"]}
        raise AssertionError("Unexpected S3 mutation: " + operation)

    def prepare(self, keys=None):
        return self.library.prepare_images({"keys": keys or [self.key]})["files"][0]

    def test_creates_public_thumbnail_and_reuses_it_without_downloading_again(self):
        original = dict(self.objects[self.key])
        first = self.prepare()
        self.assertEqual(first["thumbnail_status"], "created")
        small = first["pair"]["small_key"]
        self.assertIn("/_thumbnails/", small)
        self.assertTrue(small.endswith(".webp"))
        self.assertEqual(first["pair"]["full_url"], self.library.public_url(self.key))
        self.assertEqual(self.objects[self.key], original)
        self.assertEqual(self.prepare()["thumbnail_status"], "reused")
        self.library.render_thumbnail.assert_called_once()
        uploads = [call.args for call in self.library.command.call_args_list if call.args[1] == "put-object"]
        self.assertEqual(len(uploads), 1)
        self.assertIn("image/webp", uploads[0])
        self.assertIn("public, max-age=31536000, immutable", uploads[0])
        self.assertEqual(list(self.library.cache.glob("site-photo-*")), [])

    def test_new_source_version_gets_new_thumbnail_without_overwriting_old_one(self):
        old = self.prepare()["pair"]["small_key"]
        self.add(self.key, b"replacement original")
        new = self.prepare()["pair"]["small_key"]
        self.assertNotEqual(old, new)
        self.assertIn(old, self.objects)
        self.assertIn(new, self.objects)
        listing = self.library.browse(prefix=self.key.rpartition("/")[0] + "/")
        self.assertEqual(listing["files"][0]["pair"]["small_key"], new)
        self.assertFalse(any(folder.endswith("/_thumbnails/") for folder in listing["folders"]))

    def test_reuses_legacy_pair_even_when_selecting_small_image(self):
        small = self.key.removesuffix(".JPG") + "_800x600.jpg"
        self.add(small, b"existing resized picture")
        file = self.prepare([small])
        self.assertEqual(file["pair"]["full_key"], self.key)
        self.assertEqual(file["pair"]["small_key"], small)
        self.library.render_thumbnail.assert_not_called()

    def test_explicit_pair_takes_precedence_and_identical_urls_are_not_a_pair(self):
        url = self.library.public_url(self.key)
        (self.root / "page.html").write_text('<a href="' + url + '"><img src="' + url + '"></a>')
        self.assertEqual(self.prepare()["thumbnail_status"], "created")
        small = self.key.rpartition("/")[0] + "/custom-crop.png"
        self.add(small, b"custom crop")
        (self.root / "page.html").write_text('<a href="' + url + '"><img src="' + self.library.public_url(small) + '"></a>')
        self.assertEqual(self.prepare()["pair"]["small_key"], small)

    def test_private_source_aborts_before_creating_any_object(self):
        self.library._public.side_effect = ValueError("not public")
        with self.assertRaisesRegex(ValueError, "not public"): self.prepare()
        self.library.render_thumbnail.assert_not_called()
        self.assertEqual(len(self.objects), 1)

    def test_access_denied_is_not_treated_as_a_missing_thumbnail(self):
        real = self.command
        def denied(*args, **kwargs):
            if args[1] == "head-object" and THUMBNAIL_FOLDER in args[args.index("--key") + 1]:
                raise AWSProblem("An error occurred (403) when calling HeadObject: Access Denied")
            return real(*args, **kwargs)
        self.library.command.side_effect = denied
        with self.assertRaises(AWSProblem): self.prepare()
        self.library.render_thumbnail.assert_not_called()

    def test_conditional_write_race_reuses_the_other_writers_thumbnail(self):
        real = self.command
        def race(*args, **kwargs):
            if args[1] == "put-object":
                key = args[args.index("--key") + 1]
                self.add(key, b"another manager prepared this")
            return real(*args, **kwargs)
        self.library.command.side_effect = race
        self.assertEqual(self.prepare()["thumbnail_status"], "reused")

    def test_upload_failure_never_returns_a_broken_pair_and_cleans_downloads(self):
        real = self.command
        def denied(*args, **kwargs):
            if args[1] == "put-object": raise AWSProblem("An error occurred (AccessDenied) when calling PutObject")
            return real(*args, **kwargs)
        self.library.command.side_effect = denied
        with self.assertRaises(AWSProblem): self.prepare()
        self.assertEqual(len(self.objects), 1)
        self.assertEqual(list(self.library.cache.glob("site-photo-*")), [])

    def test_source_replacement_during_preparation_requires_a_retry(self):
        render = self.library.render_thumbnail.side_effect
        def replaced(source, target):
            render(source, target)
            self.add(self.key, b"changed while preparing")
        self.library.render_thumbnail.side_effect = replaced
        with self.assertRaisesRegex(ValueError, "changed while"): self.prepare()

    def test_scope_and_type_checks_happen_before_any_aws_calls(self):
        for keys in [["other/photo.jpg"], [DEFAULTS["prefix"] + "paper.pdf"], [DEFAULTS["prefix"] + "_thumbnails/file.webp"], [None], [], "not an array"]:
            with self.subTest(keys=keys), self.assertRaises(ValueError): self.library.prepare_images({"keys": keys})
        self.library.command.assert_not_called()

    def test_large_photos_are_rejected_before_download(self):
        self.objects[self.key]["ContentLength"] = MAX_PHOTO_BYTES + 1
        with self.assertRaisesRegex(ValueError, "50 MB"): self.prepare()
        self.library.render_thumbnail.assert_not_called()

    def test_svg_is_reused_without_rasterization(self):
        svg = DEFAULTS["prefix"] + "Gallery/art.svg"
        self.add(svg, b"<svg/>")
        self.assertEqual(self.prepare([svg])["thumbnail_status"], "vector")
        self.library.render_thumbnail.assert_not_called()

    def test_pasted_urls_handle_unicode_literal_plus_and_legacy_spaces(self):
        url = self.library.public_url(self.key)
        result = self.library.prepare_image_urls({"urls": [url, "https://example.com/unrelated.jpg", "/assets/uploads/local.jpg"]})
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["input_url"], url)
        self.assertEqual(result["files"][0]["pair"]["full_key"], self.key)
        legacy = self.library.public_url(DEFAULTS["prefix"] + "Gallery/space photo.jpg").replace("%20", "+")
        self.add(DEFAULTS["prefix"] + "Gallery/space photo.jpg", b"legacy picture")
        self.assertEqual(self.library.prepare_image_urls({"urls": [legacy]})["files"][0]["input_url"], legacy)

    def test_pasted_generated_url_is_not_resized_again(self):
        url = self.prepare()["pair"]["small_url"]
        self.assertEqual(self.library.prepare_image_urls({"urls": [url]}), {"files": []})

    def test_public_acl_is_only_mirrored_onto_our_derivative(self):
        small = self.library.thumbnail_key(self.key, self.objects[self.key]["ETag"])
        self.library._public.side_effect = [ValueError("private"), {"key": small}]
        self.library.command.side_effect = None
        self.library.command.return_value = {"Grants": [{"Grantee": {"URI": "http://acs.amazonaws.com/groups/global/AllUsers"}, "Permission": "READ"}]}
        self.library._public_thumbnail(small, self.key)
        writes = [call.args for call in self.library.command.call_args_list if call.args[1] == "put-object-acl"]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][writes[0].index("--key") + 1], small)

    def test_private_derivative_without_public_source_acl_reports_actionable_error(self):
        self.library._public.side_effect = ValueError("private")
        self.library.command.side_effect = None
        self.library.command.return_value = {"Grants": []}
        with self.assertRaisesRegex(ValueError, "Allow public read"):
            self.library._public_thumbnail("small.webp", self.key)
        self.assertFalse(any(call.args[1] == "put-object-acl" for call in self.library.command.call_args_list))

    def test_http_preparation_routes_return_pairs_and_require_manager_origin_and_token(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        origin = "http://127.0.0.1:" + str(server.server_port)
        server.manager = Mock(origin=origin, storage=self.library)
        server.token = "test-manager-token"
        thread = Thread(target=server.serve_forever, daemon=True);thread.start()
        def request(route, data, token=server.token, source=origin):
            return Request(origin + "/api/s3/" + route, data=json.dumps(data).encode(),
                           headers={"Content-Type": "application/json", "X-Manager-Token": token, "Origin": source})
        try:
            for token, source in [("bad-token", origin), (server.token, "https://unrelated.example")]:
                with self.assertRaises(HTTPError) as error: urlopen(request("prepare-images", {"keys": [self.key]}, token, source))
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
            self.library.command.assert_not_called()
            with urlopen(request("prepare-images", {"keys": [self.key]})) as response:
                file = json.load(response)["files"][0]
            self.assertEqual(file["pair"]["full_key"], self.key)
            with urlopen(request("prepare-image-urls", {"urls": [self.library.public_url(self.key)]})) as response:
                self.assertEqual(json.load(response)["files"][0]["pair"], file["pair"])
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)


if __name__ == "__main__": unittest.main()
