#!/usr/bin/env python3
"""Exercise content operations in temporary copies, never in the live workspace."""
import base64
import importlib.util
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
from threading import Thread
import unittest
from urllib.request import urlopen

spec = importlib.util.spec_from_file_location("manage_site", Path(__file__).with_name("manage_site.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SOURCE = Path(__file__).resolve().parents[1]


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="website-manager-test-")
        self.root = Path(self.temp.name) / "site"
        self.root.mkdir()
        for path in (SOURCE / "pages").glob("*.html"):
            shutil.copy2(path, self.root / path.name)
        for name in ["_config.yml", ".gitignore"]:
            shutil.copy2(SOURCE / name, self.root / name)
        shutil.copytree(SOURCE / "_data", self.root / "_data")
        self.manager = module.SiteManager(self.root, "http://127.0.0.1:4111")
        self.manager.start_build = lambda: {"message": "Test preview"}

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, name=None):
        if not name:
            return {"title": "A new story", "heading": "A new story", "slug": "new-story", "description": "A Bengali story.",
                    "section": "creativity", "type": "creativity", "body": "<p>বাংলায় নতুন গল্প।</p>", "image": "",
                    "tile": {"enabled": True, "group": "creativity", "title": "New story", "caption": "In Bengali",
                             "image": "https://example.com/photo.jpg", "alt": "Story illustration", "position": 0}}
        page = self.manager.page(name)
        meta = page["meta"]
        return {"id": name, "revision": page["revision"], "title": meta["title"], "heading": page["heading"], "slug": name.removesuffix(".html"),
                "description": meta["description"], "section": meta.get("section", "main"), "type": "general", "body": page["body"],
                "image": meta.get("image", ""), "metadata": meta, "tile": {"enabled": bool(page["tile"]), **(page["tile"] or {})}}

    def test_create_page_tile_and_undo(self):
        self.manager.save(self.payload())
        page = self.manager.page("new-story.html")
        self.assertIn("বাংলায়", page["body"])
        self.assertEqual(page["tile"]["position"], 0)
        self.assertEqual(page["meta"]["permalink"], "/new-story.html")
        entry = self.manager.history()[0]
        self.manager.undo({"id": entry["id"]})
        self.assertFalse((self.root / "new-story.html").exists())
        self.assertNotIn("/new-story.html", (self.root / "_data/tiles.json").read_text())

    def test_pages_folder_keeps_stable_ids_and_urls_through_save_delete_undo(self):
        folder = self.root / "pages";folder.mkdir()
        for source in self.root.glob("*.html"): source.rename(folder / source.name)
        self.assertTrue(self.manager.page("about.html")["protected"])
        self.manager.save(self.payload())
        self.assertTrue((folder / "new-story.html").is_file())
        self.assertFalse((self.root / "new-story.html").exists())
        page = self.manager.page("new-story.html")
        self.assertEqual(page["url"], "/new-story.html")
        self.manager.delete({"pages": [{"id":page["id"],"revision":page["revision"],"replacement":""}]})
        self.assertFalse((folder / "new-story.html").exists())
        self.manager.undo({"id":self.manager.history()[0]["id"]})
        self.assertTrue((folder / "new-story.html").is_file())

    def test_accessible_new_content_validation_and_single_main_heading(self):
        for body in ['<img src="https://example.org/photo.jpg">','<iframe src="https://example.org/video"></iframe>']:
            payload=self.payload();payload["body"]=body
            with self.assertRaisesRegex(module.Problem,"Accessibility"):
                self.manager.save(payload)
        payload=self.payload();payload["body"]='<h1>Draft heading</h1><p>Story.</p><img src="https://example.org/photo.jpg" alt="">'
        self.manager.save(payload)
        body=self.manager.page("new-story.html")["body"]
        self.assertEqual(body.count('<h1'),1)
        self.assertIn('<h1>A new story</h1>',body)

    def test_rename_updates_old_aliases_and_links(self):
        payload = self.payload("deepaboli-2025.html")
        original = (self.root / "about.html").read_text()
        (self.root / "about.html").write_text(original + '<a href="deepaboli-2025.html#photos">More</a>')
        payload["slug"] = "autumn-lights"
        self.manager.save(payload)
        redirects = json.loads((self.root / "_data/redirects.json").read_text())
        self.assertEqual(redirects["/Deepaboli_2025.html"], "/autumn-lights.html")
        self.assertEqual(redirects["/deepaboli-2025.html"], "/autumn-lights.html")
        self.assertFalse((self.root / "deepaboli-2025.html").exists())
        self.assertIn('href="/autumn-lights.html#photos"', (self.root / "about.html").read_text())

    def test_custom_tile_artwork_is_preserved(self):
        catalog = json.loads((self.root / "_data/tiles.json").read_text())
        before = next(t["html"] for t in catalog["research-projects"] if t["page"] == "/collaborative-navigation-spatial-learning.html")
        payload = self.payload("collaborative-navigation-spatial-learning.html")
        payload["description"] += " Updated."
        self.manager.save(payload)
        after = json.loads((self.root / "_data/tiles.json").read_text())
        tile = next(t["html"] for t in after["research-projects"] if t["page"] == "/collaborative-navigation-spatial-learning.html")
        self.assertEqual(tile, before)

    def test_stale_editor_cannot_overwrite_external_changes(self):
        payload = self.payload("deepaboli-2025.html")
        path = self.root / "deepaboli-2025.html"
        path.write_text(path.read_text() + "\n<p>External change</p>")
        with self.assertRaises(module.Problem):
            self.manager.save(payload)
        self.assertIn("External change", path.read_text())

    def test_partial_write_failure_restores_already_written_files(self):
        catalog = (self.root / "_data/tiles.json").read_bytes()
        original_write = self.manager.write
        failed = False
        def interrupted_write(name, data):
            nonlocal failed
            if name == "_data/tiles.json" and not failed:
                failed = True
                raise OSError("Simulated disk error")
            original_write(name, data)
        self.manager.write = interrupted_write
        with self.assertRaises(OSError):
            self.manager.commit("Interrupted save", {"new-story.html": b"New content", "_data/tiles.json": b"{}"}, {"_data/tiles.json": catalog})
        self.assertFalse((self.root / "new-story.html").exists())
        self.assertEqual((self.root / "_data/tiles.json").read_bytes(), catalog)
        self.assertEqual(self.manager.history(), [])

    def test_reserved_old_address_cannot_be_reused(self):
        payload = self.payload()
        payload["slug"] = "deepaboli-2025"
        with self.assertRaises(module.Problem):
            self.manager.save(payload)

    def test_bulk_delete_and_undo(self):
        names = ["deepaboli-2024.html", "deepaboli-2025.html"]
        originals = {name: (self.root / name).read_bytes() for name in names}
        choices = [{"id": name, "revision": self.manager.page(name)["revision"], "replacement": "/deepaboli-2023.html"} for name in names]
        self.manager.delete({"pages": choices})
        self.assertTrue(all(not (self.root / name).exists() for name in names))
        redirects = json.loads((self.root / "_data/redirects.json").read_text())
        self.assertEqual(redirects["/Deepaboli_2025.html"], "/deepaboli-2023.html")
        self.manager.undo({"id": self.manager.history()[0]["id"]})
        for name in names:
            self.assertEqual((self.root / name).read_bytes(), originals[name])

    def test_delete_without_replacement_cleans_legacy_aliases(self):
        page = self.manager.page("deepaboli-2025.html")
        self.manager.delete({"pages": [{"id": page["id"], "revision": page["revision"], "replacement": ""}]})
        self.assertNotIn("deepaboli-2025.html", (self.root / "_data/redirects.json").read_text())

    def test_delete_requires_a_replacement_for_incoming_links(self):
        path = self.root / "about.html"
        path.write_text(path.read_text() + '<a href="deepaboli-2025.html">Festival</a>')
        page = self.manager.page("deepaboli-2025.html")
        with self.assertRaises(module.Problem):
            self.manager.delete({"pages": [{"id": page["id"], "revision": page["revision"]}]})
        self.assertTrue((self.root / page["id"]).exists())

    def test_main_pages_are_protected(self):
        page = self.manager.page("index.html")
        with self.assertRaises(module.Problem):
            self.manager.delete({"pages": [{"id": page["id"], "revision": page["revision"]}]})

    def test_uploaded_media_is_committed_with_page_and_undoable(self):
        upload = self.manager.upload({"name": "drawing.svg", "content": base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg"/>').decode()})
        asset = self.root / upload["url"].lstrip("/")
        self.assertFalse(asset.exists())
        payload = self.payload()
        payload["body"] = '<img src="' + upload["url"] + '" alt="A drawing">'
        payload["uploads"] = [upload["id"]]
        payload["tile"]["image"] = upload["url"]
        self.manager.save(payload)
        self.assertTrue(asset.exists())
        self.manager.undo({"id": self.manager.history()[0]["id"]})
        self.assertFalse(asset.exists())

    def test_saved_uploads_are_visible_before_preview_build_finishes(self):
        directory = self.root / "assets/uploads"
        directory.mkdir(parents=True)
        content = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>'
        (directory / "new-photo.svg").write_bytes(content)
        server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
        server.manager = self.manager
        server.token = "test-token"
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/assets/uploads/new-photo.svg", timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), content)
                self.assertEqual(response.headers["Content-Type"], "image/svg+xml")
        finally:
            server.shutdown()
            server.server_close()

    def test_undo_refuses_to_overwrite_later_manual_edits(self):
        self.manager.save(self.payload())
        path = self.root / "new-story.html"
        path.write_text(path.read_text() + "\n<p>Keep this</p>")
        with self.assertRaises(module.Problem):
            self.manager.undo({"id": self.manager.history()[0]["id"]})
        self.assertTrue(path.exists())

    def test_profile_updates_and_favicon_version(self):
        self.manager.person({"id": "amanda_kane", "name": "Amanda Kane", "url": "https://example.com/amanda", "aliases": ["Amanda"]})
        self.assertEqual(json.loads((self.root / "_data/people.json").read_text())["amanda_kane"]["url"], "https://example.com/amanda")
        settings = self.manager.state()["settings"]
        settings["profile_image"] = "https://example.com/new-photo.png"
        old_version = self.manager.snapshot()[2]["favicon_version"]
        self.manager.settings(settings)
        self.assertEqual(self.manager.snapshot()[2]["favicon_version"], old_version + 1)

    def test_reordering_rejects_a_missing_tile(self):
        tiles = self.manager.state()["tiles"]["creativity"]
        with self.assertRaises(module.Problem):
            self.manager.reorder({"group": "creativity", "order": [t["page"] for t in tiles[:-1]]})
        order = list(reversed([t["page"] for t in tiles]))
        self.manager.reorder({"group": "creativity", "order": order})
        self.assertEqual([t["page"] for t in self.manager.state()["tiles"]["creativity"]], order)

    def test_video_dates_need_real_calendar_dates_and_timezones(self):
        base = {"@type": "VideoObject", "embedUrl": "https://www.youtube.com/embed/OKNmkjQb4D8"}
        for value in ["2024-08-30", "2024-08-30T07:30:40", "2024-02-30T07:30:40-07:00"]:
            with self.assertRaises(module.Problem):
                self.manager.validate_video({**base, "uploadDate": value})
        self.manager.validate_video({**base, "uploadDate": "2024-08-30T07:30:40-07:00"})

    def test_gallery_keeps_distinct_small_and_full_size_urls(self):
        payload = self.payload()
        payload["body"] = '<section class="gallery"><a href="https://example.com/full.jpg" data-lightbox="mygallery"><img src="https://example.com/small.jpg" alt="A photo"></a></section>'
        self.manager.save(payload)
        body = self.manager.page("new-story.html")["body"]
        self.assertIn('href="https://example.com/full.jpg"', body)
        self.assertIn('src="https://example.com/small.jpg"', body)

    def test_gallery_save_removes_empty_editor_links_and_preserves_real_content(self):
        payload = self.payload()
        photo = '<a href="https://example.com/full.jpg" data-lightbox="mygallery" data-title="Caption"><img src="https://example.com/small.jpg" alt="A photo"></a>'
        text_link = '<a href="https://example.com/full.jpg" data-lightbox="mygallery">View photo</a>'
        named_anchor = '<a id="notes"></a>'
        payload["body"] = ('<p>বাংলায় গল্প।</p><section class="gallery">'
                           '<a href="https://example.com/empty.jpg" data-lightbox="mygallery"><br> &nbsp;\u200b<span></span></a>'
                           + photo + text_link + named_anchor + '</section>')
        self.manager.save(payload)
        body = self.manager.page("new-story.html")["body"]
        self.assertNotIn("empty.jpg", body)
        for expected in [photo, text_link, named_anchor, "বাংলায় গল্প।"]:
            self.assertIn(expected, body)

    def test_replacing_and_removing_video_updates_its_metadata(self):
        name = "omnidirectional-treadmill-vs-natural-walking.html"
        payload = self.payload(name)
        old = "https://www.youtube.com/embed/OKNmkjQb4D8"
        new = "https://www.youtube.com/embed/VpbjKTbEevU"
        payload["body"] = payload["body"].replace(old, new)
        payload["videos"] = [{"@context": "https://schema.org", "@type": "VideoObject", "name": "Replacement video",
                              "description": "Updated video description", "embedUrl": new,
                              "thumbnailUrl": "https://img.youtube.com/vi/VpbjKTbEevU/hqdefault.jpg",
                              "uploadDate": "2025-12-18T07:26:18-08:00"}]
        self.manager.save(payload)
        meta = self.manager.page(name)["meta"]["structured_data"]
        schemas = meta if isinstance(meta, list) else [meta]
        self.assertEqual([s["embedUrl"] for s in schemas if s.get("@type") == "VideoObject"], [new])
        payload = self.payload(name)
        payload["body"] = re.sub(r"<iframe\b[^>]*>.*?</iframe>", "", payload["body"], flags=re.S)
        self.manager.save(payload)
        meta = self.manager.page(name)["meta"].get("structured_data", [])
        schemas = meta if isinstance(meta, list) else [meta]
        self.assertFalse(any(s.get("@type") == "VideoObject" for s in schemas))

    def test_publish_only_after_current_review_using_a_local_git_remote(self):
        def git(*args):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)
        git("init", "-b", "main")
        git("config", "user.name", "Website manager test")
        git("config", "user.email", "test@example.invalid")
        git("add", ".")
        git("commit", "-m", "Fixture")
        remote = Path(self.temp.name) / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        git("remote", "add", "origin", str(remote))
        self.manager.build = lambda production=False: (self.root, "Test build")
        self.manager.save(self.payload())
        review = self.manager.review_changes()
        path = self.root / "new-story.html"
        path.write_text(path.read_text() + "\n<p>Changed after review</p>")
        with self.assertRaises(module.Problem):
            self.manager.publish({"review": review["id"], "message": "Content update"})
        review = self.manager.review_changes()
        self.manager.publish({"review": review["id"], "message": "Content update"})
        published = subprocess.check_output(["git", "--git-dir", str(remote), "show", "main:new-story.html"], text=True)
        self.assertIn("Changed after review", published)


if __name__ == "__main__":
    unittest.main()
