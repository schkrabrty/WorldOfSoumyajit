"""Shared section definitions for the manager and production validation."""
import hashlib
import json
import re

SECTIONS_FILE = "_data/sections.json"
TILES_FILE = "_data/tiles.json"
MAIN_PAGES = {
    "index.html": {"url": "/", "title": "My Works", "category": "works"},
    "blog.html": {"url": "/blog.html", "title": "My Photography", "category": "photography"},
    "my-creativity.html": {"url": "/my-creativity.html", "title": "My Creativity", "category": "creativity"},
    "about.html": {"url": "/about.html", "title": "About Me", "category": "about"},
}
RESERVED_IDS = {"header", "menu", "main", "footer", "wrapper"}


def main_pages(catalog):
    """Read the main-page registry, with defaults for the original site pages."""
    defaults = {details["url"]: details for details in MAIN_PAGES.values()}
    return {"index.html" if url == "/" else url.lstrip("/"): {
        "url": url, "title": settings.get("title", defaults.get(url, {}).get("title")),
        "category": settings.get("category", defaults.get(url, {}).get("category"))}
        for url, settings in catalog.items()}


def validate_sections(catalog, tiles):
    if not isinstance(catalog, dict) or "/" not in catalog:
        raise ValueError("The main-page list must include the homepage.")
    categories = set()
    used = set()
    for url, settings in catalog.items():
        if url != "/" and (not re.fullmatch(r"/[a-z0-9]+(?:-[a-z0-9]+)*\.html", url) or url in {"/index.html", "/404.html", "/elements.html"}):
            raise ValueError("Main pages need a valid local page address.")
        if not isinstance(settings, dict) or not isinstance(settings.get("navigation"), bool) or not isinstance(settings.get("sections"), list):
            raise ValueError("Each main page needs a section list and navigation setting.")
    for page in main_pages(catalog).values():
        if not isinstance(page["title"], str) or not page["title"].strip() or len(page["title"]) > 120:
            raise ValueError("Each main page needs a title between 1 and 120 characters.")
        category = page["category"]
        if not isinstance(category, str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", category) or category in categories or category == "main":
            raise ValueError("Main-page categories must be valid and unique.")
        categories.add(category)
    for settings in catalog.values():
        anchors = set(RESERVED_IDS)
        for section in settings["sections"]:
            if not isinstance(section, dict): raise ValueError("Each section needs a title and an ID.")
            identifier, title = section.get("id"), section.get("title")
            if not isinstance(identifier, str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", identifier):
                raise ValueError("Section IDs must start with a letter and use lowercase letters, numbers, and hyphens.")
            if identifier in used or identifier in anchors or identifier + "-heading" in anchors:
                raise ValueError("Section IDs and heading anchors must be unique: " + identifier)
            if not isinstance(title, str) or not title.strip() or len(title) > 120:
                raise ValueError("Enter a section title between 1 and 120 characters.")
            if not isinstance(section.get("show_heading"), bool): raise ValueError("Choose whether the section heading is shown.")
            used.add(identifier);anchors.update({identifier, identifier + "-heading"})
    if not isinstance(tiles, dict) or set(tiles) != used or any(not isinstance(entries, list) for entries in tiles.values()):
        raise ValueError("The tile groups must match the configured sections.")


def section_groups(catalog):
    return {section["id"]: section["title"] for settings in catalog.values() for section in settings["sections"]}


def sections_revision(files):
    return hashlib.sha256(files[SECTIONS_FILE] + b"\0" + files[TILES_FILE]).hexdigest()


def load_sections(files):
    catalog, tiles = json.loads(files[SECTIONS_FILE]), json.loads(files[TILES_FILE])
    validate_sections(catalog, tiles)
    return catalog, tiles
