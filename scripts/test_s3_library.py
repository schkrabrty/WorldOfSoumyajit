#!/usr/bin/env python3
"""Test URL accounting and S3 selection without an AWS connection."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from s3_library import DEFAULTS, S3Library, collect_references, object_keys


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "_data").mkdir()
        (self.root / "_config.yml").write_text("name: Test\n")
        self.library = S3Library(self.root)
        self.prefix = DEFAULTS["prefix"]
    def tearDown(self): self.temp.cleanup()
    def test_legacy_spaces_literal_plus_and_query_versions(self):
        url = "https://worldofsoumyajit.s3.amazonaws.com/My+Website+related+Stuffs/A%2BB.png?favicon=2"
        self.assertIn("My Website related Stuffs/A+B.png", object_keys(url))
        self.assertNotIn("My Website related Stuffs/A B.png", object_keys(url))
        self.assertEqual(object_keys("https://worldofsoumyajit.s3.attacker.example/test.jpg"), set())
    def test_html_and_json_references_preserve_both_gallery_sizes_and_apostrophes(self):
        full = "https://worldofsoumyajit.s3.amazonaws.com/My+Website+related+Stuffs/Frank's+full.jpg"
        small = "https://worldofsoumyajit.s3.amazonaws.com/My+Website+related+Stuffs/small.jpg"
        html = '<a href="' + full + '"><img src="' + small + '"></a>'
        (self.root / "index.html").write_text(html)
        (self.root / "_data/tiles.json").write_text(json.dumps({"tiles": [{"html": html}]}))
        result = collect_references(self.root)
        self.assertIn(self.prefix + "Frank's full.jpg", result["keys"])
        self.assertIn(self.prefix + "small.jpg", result["keys"])
        self.assertIn({"full": full, "small": small}, result["pairs"])
    def test_browse_filters_types_and_pairs_existing_objects_with_case_differences(self):
        objects = [{"Key": self.prefix + name, "Size": 100} for name in ["Photo.JPG", "Photo_800x600.jpg", "Paper.pdf", "Unpaired_800x600.jpg"]]
        self.library.command = MagicMock(return_value={"Contents": objects, "CommonPrefixes": [{"Prefix": self.prefix + "folder/"}]})
        result = self.library.browse(kind="image")
        self.assertEqual(len(result["files"]), 3)
        photo = next(item for item in result["files"] if item["name"] == "Photo.JPG")
        self.assertTrue(photo["pair"]["full_url"].endswith("Photo.JPG"))
        self.assertTrue(photo["pair"]["small_url"].endswith("Photo_800x600.jpg"))
        self.assertIsNone(next(item for item in result["files"] if item["name"].startswith("Unpaired"))["pair"])
        self.assertEqual(len(self.library.browse(kind="pdf")["files"]), 1)
    def test_explicit_website_pairs_take_precedence_over_filename_suggestions(self):
        full, small = self.prefix + "drawing.jpg", self.prefix + "drawing-small.jpg"
        (self.root / "index.html").write_text('<a href="' + self.library.public_url(full) + '"><img src="' + self.library.public_url(small) + '"></a>')
        self.library.command = MagicMock(return_value={"Contents": [{"Key": full, "Size": 100}, {"Key": small, "Size": 20}]})
        result = self.library.browse(kind="image")
        self.assertTrue(all(file["pair"]["small_url"] == self.library.public_url(small) for file in result["files"]))
    def test_pair_cache_refreshes_when_page_content_changes(self):
        full, first, second = [self.prefix + name for name in ["full.jpg", "small-first.jpg", "small-second.jpg"]]
        page = self.root / "index.html"
        def content(small): return '<a href="' + self.library.public_url(full) + '"><img src="' + self.library.public_url(small) + '"></a>'
        page.write_text(content(first))
        self.library.command = MagicMock(return_value={"Contents": [{"Key": key, "Size": 100} for key in [full, first, second]]})
        before = self.library.browse()["files"][0]["pair"]
        page.write_text(content(second))
        after = self.library.browse()["files"][0]["pair"]
        self.assertEqual(before["small_url"], self.library.public_url(first))
        self.assertEqual(after["small_url"], self.library.public_url(second))
    def test_browse_never_escapes_the_configured_website_folder(self):
        self.library.command = MagicMock()
        with self.assertRaises(ValueError): self.library.browse(prefix="unrelated-private-folder/")
        self.library.command.assert_not_called()
    def test_public_urls_quote_spaces_plus_signs_and_unicode(self):
        url = self.library.public_url(self.prefix + "A+B ছবি.jpg")
        self.assertIn("My%20Website%20related%20Stuffs/", url)
        self.assertIn("A%2BB%20", url)
        self.assertNotIn(" ", url)
    def test_selection_verifies_public_access_before_inserting_links(self):
        response = MagicMock();response.status = 200
        response.__enter__.return_value = response
        key = self.prefix + "Photo.JPG"
        with patch("s3_library.urlopen", return_value=response) as opened:
            result = self.library.resolve({"keys": [key]})
        self.assertEqual(result["files"][0]["key"], key)
        self.assertEqual(opened.call_args.args[0].method, "HEAD")
    def test_selection_rejects_private_files_and_out_of_scope_keys(self):
        with patch("s3_library.urlopen", side_effect=ValueError("403")):
            with self.assertRaises(ValueError): self.library.resolve({"keys": [self.prefix + "Private.jpg"]})
        with self.assertRaises(ValueError): self.library.resolve({"keys": ["another-folder/file.jpg"]})

    def test_install_reuses_existing_aws_support_without_running_setup(self):
        with patch.object(self.library,"executable",return_value="/local/aws"),patch("s3_library.subprocess.run") as setup:
            self.assertIn("already installed",self.library.install()["message"])
            setup.assert_not_called()

    def test_install_from_an_incomplete_copy_explains_how_to_open_the_working_manager(self):
        with patch.object(self.library,"executable",side_effect=ValueError("Missing")),patch("s3_library.subprocess.run") as setup:
            with self.assertRaisesRegex(ValueError,"Manage Website.command"):
                self.library.install()
            setup.assert_not_called()


if __name__ == "__main__": unittest.main()
