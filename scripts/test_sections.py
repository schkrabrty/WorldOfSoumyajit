#!/usr/bin/env python3
"""Test section operations on temporary website copies, never on the user's pages."""
import copy
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import tempfile
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from manage_site import Handler, Problem, SiteManager
from site_sections import MAIN_PAGES, SECTIONS_FILE, TILES_FILE, validate_sections

SOURCE = Path(__file__).resolve().parents[1]


class SectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="section-manager-test-")
        self.root = Path(self.temp.name)
        for path in SOURCE.glob("*.html"): shutil.copy2(path, self.root / path.name)
        for name in ["_config.yml", ".gitignore"]: shutil.copy2(SOURCE / name, self.root / name)
        shutil.copytree(SOURCE / "_data", self.root / "_data")
        self.manager = SiteManager(self.root, "http://127.0.0.1:4111")
        self.manager.start_build = lambda: None
        self.original_pages = {path.name: path.read_bytes() for path in self.root.glob("*.html")}

    def tearDown(self): self.temp.cleanup()

    def catalog(self): return json.loads((self.root / SECTIONS_FILE).read_text())
    def tiles(self): return json.loads((self.root / TILES_FILE).read_text())
    def change(self, action, page="index.html", **data):
        return self.manager.manage_sections({"action": action, "page": page, "revision": self.manager.state()["sections_revision"], **data})

    def payload(self, group, slug="new-section-page"):
        return {"title": "A new page", "heading": "A new page", "slug": slug, "description": "A page in a new section.",
                "section": "works", "type": "research", "body": "<p>Content</p>", "image": "https://example.com/full.jpg",
                "tile": {"enabled": True, "group": group, "title": "New tile", "image": "https://example.com/small.jpg", "position": 0}}

    def assert_pages_unchanged(self):
        self.assertEqual({path.name: path.read_bytes() for path in self.root.glob("*.html")}, self.original_pages)

    def test_existing_sections_keep_their_order_and_tile_counts(self):
        state = self.manager.state()
        main = next(page for page in state["section_pages"] if page["id"] == "index.html")
        self.assertEqual([section["id"] for section in main["sections"]], ["research-projects", "teaching-tutorials", "academic-service"])
        self.assertEqual(main["sections"][0]["count"], len(self.tiles()["research-projects"]))
        self.assertEqual(set(state["groups"]), set(self.tiles()))

    def test_new_sections_work_on_every_main_page_and_appear_first(self):
        for page in MAIN_PAGES:
            with self.subTest(page=page):
                identifier = self.change("create", page=page, title="New section")["id"]
                settings = self.catalog()[MAIN_PAGES[page]["url"]]
                self.assertEqual(settings["sections"][0]["id"], identifier)
                self.assertEqual(self.tiles()[identifier], [])
                self.assertIn(identifier, self.manager.state()["groups"])
        self.assert_pages_unchanged()

    def test_new_pages_can_use_new_sections_and_new_tiles_start_first(self):
        identifier = self.change("create", title="Recent work")["id"]
        self.manager.save(self.payload(identifier))
        self.manager.save(self.payload(identifier, "another-new-page"))
        self.assertEqual([tile["page"] for tile in self.tiles()[identifier]], ["/another-new-page.html", "/new-section-page.html"])
        self.assertEqual(self.manager.page("new-section-page.html")["tile"]["group"], identifier)

    def test_rename_preserves_anchor_and_all_custom_tile_markup(self):
        before = self.tiles()
        self.change("edit", id="research-projects", title="Research & <Projects>", show_heading=False)
        section = self.catalog()["/"]["sections"][0]
        self.assertEqual(section, {"id": "research-projects", "title": "Research & <Projects>", "show_heading": False})
        self.assertEqual(self.tiles(), before)
        self.assert_pages_unchanged()

    def test_section_reorder_navigation_and_undo(self):
        before = self.catalog()
        order = list(reversed([section["id"] for section in before["/"]["sections"]]))
        self.change("reorder", order=order)
        self.assertEqual([section["id"] for section in self.catalog()["/"]["sections"]], order)
        self.manager.undo({"id": self.manager.history()[0]["id"]})
        self.assertEqual(self.catalog(), before)
        self.change("navigation", page="blog.html", navigation=True)
        self.assertTrue(self.catalog()["/blog.html"]["navigation"])

    def test_move_tiles_keeps_source_order_and_artwork_and_never_deletes_pages(self):
        before, sections = self.tiles(), self.catalog()
        self.change("delete", id="teaching-tutorials", tile_action="move", destination="research-projects")
        self.assertEqual(self.tiles()["research-projects"], before["teaching-tutorials"] + before["research-projects"])
        self.assertNotIn("teaching-tutorials", self.tiles())
        self.assert_pages_unchanged()
        self.manager.undo({"id": self.manager.history()[0]["id"]})
        self.assertEqual(self.tiles(), before)
        self.assertEqual(self.catalog(), sections)

    def test_move_can_target_another_main_page_without_losing_tiles(self):
        before = self.tiles()
        self.change("delete", id="academic-service", tile_action="move", destination="photography")
        self.assertEqual(self.tiles()["photography"], before["academic-service"] + before["photography"])
        self.assert_pages_unchanged()

    def test_duplicate_destination_pages_keep_the_existing_destination_tile(self):
        tiles = self.tiles()
        source = copy.deepcopy(tiles["teaching-tutorials"][0])
        existing = {"page": source["page"], "html": source["html"] + "<!-- destination crop -->"}
        tiles["research-projects"].append(existing)
        (self.root / TILES_FILE).write_bytes(self.manager.json_bytes(tiles))
        self.change("delete", id="teaching-tutorials", tile_action="move", destination="research-projects")
        matches = [tile for tile in self.tiles()["research-projects"] if tile["page"] == source["page"]]
        self.assertEqual(matches, [existing])

    def test_removing_tiles_keeps_pages_and_allows_them_to_be_added_again(self):
        self.change("delete", id="academic-service", tile_action="hide")
        self.assertNotIn("academic-service", self.manager.state()["groups"])
        self.assertIsNone(self.manager.page("voluntary-service.html")["tile"])
        self.assert_pages_unchanged()

    def test_empty_sections_and_pages_with_no_sections_are_supported(self):
        for page, details in MAIN_PAGES.items():
            for section in list(self.catalog()[details["url"]]["sections"]):
                self.change("delete", page=page, id=section["id"], tile_action="hide")
        self.assertEqual(self.manager.state()["groups"], {})
        self.assertEqual(self.tiles(), {})
        identifier = self.change("create", title="Start again")["id"]
        self.assertIn(identifier, self.manager.state()["groups"])
        self.change("delete", id=identifier)
        self.assertEqual(self.manager.state()["groups"], {})
        self.assert_pages_unchanged()

    def test_nonempty_sections_require_an_explicit_tile_disposition(self):
        before = self.tiles()
        for data in [{}, {"tile_action": "move", "destination": "academic-service"}, {"tile_action": "move", "destination": "missing"}]:
            with self.subTest(data=data), self.assertRaises(Problem): self.change("delete", id="academic-service", **data)
        self.assertEqual(self.tiles(), before)
        self.assertEqual(self.manager.history(), [])

    def test_stale_requests_and_invalid_orders_cannot_overwrite_new_changes(self):
        revision = self.manager.state()["sections_revision"]
        self.change("create", title="A section added in another window")
        with self.assertRaisesRegex(Problem, "changed after"):
            self.manager.manage_sections({"action": "delete", "page": "index.html", "id": "research-projects", "tile_action": "hide", "revision": revision})
        for order in [[], ["research-projects"] * 4, "not a list", [None]]:
            with self.subTest(order=order), self.assertRaises(Problem): self.change("reorder", order=order)
        self.assertIn("research-projects", self.tiles())

    def test_a_new_tile_invalidates_a_section_deletion_form(self):
        revision = self.manager.state()["sections_revision"]
        self.manager.save(self.payload("research-projects"))
        with self.assertRaises(Problem):
            self.manager.manage_sections({"action": "delete", "page": "index.html", "id": "research-projects", "tile_action": "hide", "revision": revision})
        self.assertTrue((self.root / "new-section-page.html").is_file())

    def test_section_ids_avoid_reserved_anchors_and_collisions(self):
        for title in ["Header", "Research projects", "Research projects heading", "123 projects", "বাংলা"]:
            identifier = self.change("create", title=title)["id"]
            self.assertNotEqual(identifier, "header")
            self.assertNotEqual(identifier, "research-projects-heading")
        validate_sections(self.catalog(), self.tiles())

    def test_invalid_forms_do_not_modify_the_catalog(self):
        before = self.catalog()
        for data in [{"action": "create", "title": " "}, {"action": "create", "title": "x" * 121}, {"action": "create", "title": "Title", "show_heading": "yes"}, {"action": "navigation", "navigation": "yes"}, {"action": "edit", "id": "missing", "title": "Title"}, {"action": "create", "page": "../../elsewhere", "title": "Title"}, {"action": "unknown"}]:
            with self.subTest(data=data), self.assertRaises(Problem):
                self.manager.manage_sections({"page": "index.html", "revision": self.manager.state()["sections_revision"], **data})
        self.assertEqual(self.catalog(), before)

    def test_partial_write_failure_rolls_back_both_catalogs(self):
        before = {name: (self.root / name).read_bytes() for name in [SECTIONS_FILE, TILES_FILE]}
        write = self.manager.write
        failed = False
        def interrupted(name, data):
            nonlocal failed
            if name == TILES_FILE and not failed: failed = True;raise OSError("Simulated write failure")
            write(name, data)
        self.manager.write = interrupted
        with self.assertRaises(OSError): self.change("create", title="Interrupted section")
        for name, content in before.items(): self.assertEqual((self.root / name).read_bytes(), content)
        self.assertEqual(self.manager.history(), [])

    def test_schema_rejects_orphan_groups_and_duplicate_section_anchors(self):
        catalog, tiles = self.catalog(), self.tiles()
        tiles["orphan"] = []
        with self.assertRaises(ValueError): validate_sections(catalog, tiles)
        tiles.pop("orphan")
        catalog["/"]["sections"].append({"id": "research-projects-heading", "title": "Clash", "show_heading": True})
        tiles["research-projects-heading"] = []
        with self.assertRaises(ValueError): validate_sections(catalog, tiles)

    def test_sections_http_route_checks_token_and_origin(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.manager = self.manager;server.token = "section-test-token"
        origin = "http://127.0.0.1:" + str(server.server_port);self.manager.origin = origin
        thread = Thread(target=server.serve_forever, daemon=True);thread.start()
        def request(token=server.token):
            payload = {"action": "create", "page": "index.html", "title": "HTTP section", "revision": self.manager.state()["sections_revision"]}
            return Request(origin + "/api/sections", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "X-Manager-Token": token, "Origin": origin})
        try:
            with self.assertRaises(HTTPError) as error: urlopen(request("wrong"))
            self.assertEqual(error.exception.code, 403);error.exception.close()
            with urlopen(request()) as response: identifier = json.load(response)["id"]
            self.assertIn(identifier, self.tiles())
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)


if __name__ == "__main__": unittest.main()
