"""Main-page lifecycle tests use disposable site copies."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from manage_site import Problem, SiteManager
from site_sections import SECTIONS_FILE, TILES_FILE, main_pages, validate_sections

SOURCE = Path(__file__).resolve().parents[1]


class MainPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="main-pages-test-")
        self.root = Path(self.temp.name)
        for item in (SOURCE / "pages").glob("*.html"): shutil.copy2(item, self.root / item.name)
        for name in ["_config.yml", ".gitignore"]: shutil.copy2(SOURCE / name, self.root / name)
        shutil.copytree(SOURCE / "_data", self.root / "_data")
        self.manager = SiteManager(self.root, "http://127.0.0.1:4111")
        self.manager.start_build = lambda: None

    def tearDown(self): self.temp.cleanup()

    def change(self, action="create", **data):
        values = {"title": "My Adventures", "slug": "my-adventures", "description": "Trips and memories.", "section_title": "Recent trips"}
        return self.manager.manage_main_pages({**values, "action": action, "revision": self.manager.state()["main_pages_revision"], **data})

    def navigation(self):
        return self.manager.yaml("load", documents=[(self.root / "_data/navigation.yml").read_text()])[0]

    def test_create_updates_page_menu_sections_categories_and_can_be_undone(self):
        before = self.manager.snapshot()[0]
        self.change()
        page = self.manager.page("my-adventures.html")
        self.assertTrue(page["main_page"] and page["protected"])
        self.assertEqual(page["meta"]["layout"], "default")
        self.assertIn("Trips and memories.", page["body"])
        item = next(item for item in self.navigation() if item["url"] == "/my-adventures.html")
        state = self.manager.state()
        main = next(item for item in state["section_pages"] if item["id"] == "my-adventures.html")
        self.assertEqual(main["category"], item["key"])
        self.assertEqual(state["group_categories"][main["sections"][0]["id"]], item["key"])
        self.manager.undo({"id": self.manager.history()[0]["id"]})
        self.assertEqual(self.manager.snapshot()[0], before)

    def test_new_main_page_accepts_sections_and_detail_pages(self):
        self.change()
        page = self.manager.page("my-adventures.html")
        self.manager.save({"id": page["id"], "revision": page["revision"], "title": page["meta"]["title"],
                           "description": page["meta"]["description"], "heading": "Adventures and memories", "section": "main",
                           "body": page["body"], "metadata": page["meta"], "tile": {"enabled": False}})
        edited = self.manager.page("my-adventures.html")
        self.assertEqual(edited["meta"]["layout"], "default")
        self.assertEqual(edited["meta"]["permalink"], "/my-adventures.html")
        self.assertIn("Adventures and memories", edited["body"])
        state = self.manager.state()
        result = self.manager.manage_sections({"action": "create", "page": "my-adventures.html", "title": "Older trips", "revision": state["sections_revision"]})
        category = next(page["category"] for page in state["section_pages"] if page["id"] == "my-adventures.html")
        self.manager.save({"title": "A trip", "slug": "a-test-trip", "heading": "A trip", "description": "A trip.", "section": category,
                           "body": "<p>A memory.</p>", "tile": {"enabled": True, "group": result["id"], "title": "A trip", "image": "https://example.com/a.jpg"}})
        self.assertEqual(self.manager.page("a-test-trip.html")["meta"]["section"], category)
        self.assertEqual(self.manager.page("a-test-trip.html")["tile"]["group"], result["id"])

    def test_deleting_existing_main_moves_sections_and_rewrites_links_backlinks_and_redirects(self):
        before = self.manager.snapshot()[0]
        tiles = json.loads(before[TILES_FILE])
        self.change("delete", page="blog.html", replacement="index.html", tile_action="move")
        self.assertFalse((self.root / "blog.html").exists())
        self.assertFalse(any(item["url"] == "/blog.html" for item in self.navigation()))
        catalog = json.loads((self.root / SECTIONS_FILE).read_text())
        self.assertNotIn("/blog.html", catalog)
        self.assertEqual(catalog["/"]["sections"][0]["id"], "photography")
        self.assertEqual(json.loads((self.root / TILES_FILE).read_text())["photography"], tiles["photography"])
        self.assertEqual(self.manager.page("grandfather-mountain.html")["meta"]["section"], "works")
        self.assertIn('href="/"', self.manager.page("about.html")["body"])
        redirects = json.loads((self.root / "_data/redirects.json").read_text())
        self.assertEqual(redirects["/blog.html"], "/")
        self.assertNotIn("/blog.html", redirects.values())
        self.manager.undo({"id": self.manager.history()[0]["id"]})
        self.assertEqual(self.manager.snapshot()[0], before)

    def test_hide_keeps_detail_pages_and_removes_only_the_main_page_sections(self):
        detail = self.manager.page("deepaboli-2025.html")
        self.change("delete", page="my-creativity.html", replacement="about.html", tile_action="hide")
        after = self.manager.page("deepaboli-2025.html")
        self.assertEqual(after["body"], detail["body"])
        self.assertEqual(after["meta"]["section"], "about")
        self.assertIsNone(after["tile"])
        self.assertNotIn("creativity", self.manager.state()["groups"])

    def test_deletion_preserves_moved_section_links_and_drops_removed_fragment_links(self):
        source = self.root / "about.html"
        source.write_text(source.read_text() + '<a href="/blog.html#photography">Pictures</a><a href="/blog.html#missing">Other</a>')
        self.change("delete", page="blog.html", replacement="index.html", tile_action="move")
        body = self.manager.page("about.html")["body"]
        self.assertIn('href="/#photography"', body)
        self.assertIn('href="/">Other', body)

    def test_homepage_self_replacement_and_missing_disposition_are_rejected(self):
        before = self.manager.snapshot()[0]
        for values in [{"page": "index.html", "replacement": "blog.html", "tile_action": "move"},
                       {"page": "blog.html", "replacement": "blog.html", "tile_action": "move"},
                       {"page": "blog.html", "replacement": "index.html"}]:
            with self.subTest(values=values), self.assertRaises(Problem): self.change("delete", **values)
        self.assertEqual(self.manager.snapshot()[0], before)

    def test_bad_create_addresses_and_duplicate_historical_addresses_are_rejected(self):
        before = self.manager.snapshot()[0]
        for slug in ["../outside", "About", "about", "index", "deepaboli-2025", "Deepaboli_2025", ""]:
            with self.subTest(slug=slug), self.assertRaises(Problem): self.change(slug=slug)
        self.assertEqual(self.manager.snapshot()[0], before)

    def test_stale_main_page_forms_cannot_discard_new_page_edits(self):
        revision = self.manager.state()["main_pages_revision"]
        path = self.root / "blog.html";path.write_text(path.read_text() + "\n<p>New writing</p>")
        with self.assertRaisesRegex(Problem, "changed after"):
            self.manager.manage_main_pages({"action": "delete", "page": "blog.html", "replacement": "index.html", "tile_action": "move", "revision": revision})
        self.assertTrue(path.exists())

    def test_shared_delete_removes_multiple_main_and_detail_pages_in_one_undoable_change(self):
        before = self.manager.snapshot()[0]
        choices = []
        for name, replacement in [("blog.html", "/"), ("my-creativity.html", "/"), ("deepaboli-2025.html", "/deepaboli-2024.html")]:
            page = self.manager.page(name)
            choices.append({"id": name, "revision": page["revision"], "replacement": replacement, "tile_action": "move"})
        self.manager.delete({"pages": choices, "main_pages_revision": self.manager.state()["main_pages_revision"]})
        self.assertFalse(any((self.root / item["id"]).exists() for item in choices))
        self.assertEqual(len(self.manager.history()), 1)
        self.assertEqual(self.manager.page("grandfather-mountain.html")["meta"]["section"], "works")
        self.assertEqual(self.manager.page("deepaboli-2024.html")["meta"]["section"], "works")
        tiles = json.loads((self.root / TILES_FILE).read_text())
        self.assertFalse(any(tile["page"] == "/deepaboli-2025.html" for group in tiles.values() for tile in group))
        self.manager.undo({"id": self.manager.history()[0]["id"]})
        self.assertEqual(self.manager.snapshot()[0], before)

    def test_shared_delete_rejects_replacements_that_are_selected_and_stale_catalogs(self):
        before = self.manager.snapshot()[0]
        choices = [{"id": name, "revision": self.manager.page(name)["revision"], "replacement": "/blog.html", "tile_action": "move"}
                   for name in ["blog.html", "my-creativity.html"]]
        with self.assertRaises(Problem):
            self.manager.delete({"pages": choices, "main_pages_revision": self.manager.state()["main_pages_revision"]})
        self.assertEqual(self.manager.snapshot()[0], before)
        revision = self.manager.state()["main_pages_revision"]
        self.change()
        choices[0]["replacement"] = "/"
        with self.assertRaisesRegex(Problem, "changed after"):
            self.manager.delete({"pages": choices[:1], "main_pages_revision": revision})
        self.assertTrue((self.root / "blog.html").exists())

    def test_partial_write_failure_restores_page_navigation_and_catalogs(self):
        before = self.manager.snapshot()[0]
        write = self.manager.write
        for action in ["create", "delete"]:
            failed = False
            def interrupted(name, data):
                nonlocal failed
                if name == SECTIONS_FILE and not failed: failed = True;raise OSError("Disk error")
                write(name, data)
            self.manager.write = interrupted
            with self.subTest(action=action), self.assertRaises(OSError):
                self.change(action, page="blog.html", replacement="index.html", tile_action="move")
            self.assertEqual(self.manager.snapshot()[0], before)
            self.assertEqual(self.manager.history(), [])
        self.manager.write = write

    def test_registry_requires_homepage_valid_metadata_and_unique_categories(self):
        files = self.manager.snapshot()[0]
        catalog, tiles = json.loads(files[SECTIONS_FILE]), json.loads(files[TILES_FILE])
        catalog.pop("/")
        with self.assertRaises(ValueError): validate_sections(catalog, tiles)
        catalog = json.loads(files[SECTIONS_FILE]);catalog["/custom.html"] = {"title": "Custom", "category": "works", "navigation": False, "sections": []}
        with self.assertRaises(ValueError): validate_sections(catalog, tiles)
        catalog["/custom.html"]["category"] = "custom"
        validate_sections(catalog, tiles)
        self.assertIn("custom.html", main_pages(catalog))


if __name__ == "__main__": unittest.main()
