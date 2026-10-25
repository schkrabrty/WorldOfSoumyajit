#!/usr/bin/env python3
"""Run the local, form-based website manager. No Python packages are required."""

import argparse
import base64
import copy
from datetime import datetime, timezone
import glob
import hashlib
from html import escape, unescape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import threading
import unicodedata
from urllib.parse import parse_qs, quote, unquote, urljoin, urlsplit
from urllib.request import Request, urlopen
import webbrowser

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from s3_library import S3Library
from site_sections import MAIN_PAGES, RESERVED_IDS, SECTIONS_FILE, TILES_FILE, load_sections, section_groups, sections_revision, validate_sections


PROTECTED = {"index.html", "blog.html", "my-creativity.html", "about.html", "404.html", "elements.html"}
FRONT = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.S)


class Problem(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def plain(text):
    return " ".join(unescape(re.sub(r"<[^>]*>", " ", text)).split())


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "new-page"


def valid_url(value, required=False):
    value = str(value or "").strip()
    if not value and not required:
        return ""
    parts = urlsplit(value)
    if parts.scheme in {"https", "http"} and parts.netloc:
        return value
    if value.startswith("/assets/") and ".." not in value.split("/"):
        return value
    raise Problem("Use a complete https:// URL or an /assets/ path.")


def ruby_executable():
    candidates = [shutil.which("ruby"), "/opt/homebrew/opt/ruby@3.4/bin/ruby", "/usr/local/opt/ruby@3.4/bin/ruby"]
    candidates += glob.glob("/opt/homebrew/Library/Homebrew/vendor/portable-ruby/3.4.*/bin/ruby")
    candidates += glob.glob("/usr/local/Homebrew/Library/Homebrew/vendor/portable-ruby/3.4.*/bin/ruby")
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            result = subprocess.run([candidate, "-e", 'exit(RUBY_VERSION.start_with?("3.4.") ? 0 : 1)'], capture_output=True)
            if result.returncode == 0:
                return candidate
    raise Problem("Ruby 3.4 is required. Install it with: brew install ruby@3.4")


def attr_change(tag, key, value):
    pattern = re.compile(r"(\b" + re.escape(key) + r"\s*=\s*)([\"'])(.*?)\2", re.S | re.I)
    if pattern.search(tag):
        return pattern.sub(lambda m: m[1] + '"' + escape(value, quote=True) + '"', tag, count=1)
    return tag[:-1] + ' ' + key + '="' + escape(value, quote=True) + '">'


def tile_fields(record):
    if not record:
        return None
    text = record["html"]
    image = re.search(r"<img\b[^>]*>", text, re.I)
    def attribute(key):
        match = re.search(r"\b" + key + r"\s*=\s*([\"'])(.*?)\1", image[0] if image else "", re.S | re.I)
        return unescape(match[2]) if match else ""
    heading = re.search(r"<h[1-6]\b[^>]*>(.*?)</h[1-6]>", text, re.S | re.I)
    caption = re.search(r'<div\s+class="content"[^>]*>\s*<p[^>]*>(.*?)</p>', text, re.S | re.I)
    return {"title": plain(heading[1]) if heading else "", "caption": plain(caption[1]) if caption else "",
            "image": attribute("src"), "alt": attribute("alt")}


def make_tile(page_url, fields, existing=None, old_url=None):
    title = str(fields.get("title", "")).strip()
    image = valid_url(fields.get("image"), True)
    alt = str(fields.get("alt") or title).strip()
    caption = str(fields.get("caption", "")).strip()
    if not title:
        raise Problem("A tile title is required.")
    if existing:
        text = existing["html"]
        previous = tile_fields(existing)
        if title != previous["title"]:
            text = re.sub(r"(<h[1-6]\b[^>]*>).*?(</h[1-6]>)", lambda m: m[1] + escape(title) + m[2], text, count=1, flags=re.S | re.I)
        if caption != previous["caption"]:
            text = re.sub(r'(<div\s+class="content"[^>]*>\s*<p[^>]*>).*?(</p>)', lambda m: m[1] + escape(caption) + m[2], text, count=1, flags=re.S | re.I)
        if image != previous["image"] or alt != previous["alt"]:
            text = re.sub(r"<img\b[^>]*>", lambda m: attr_change(attr_change(m[0], "src", image), "alt", alt), text, count=1, flags=re.I)
        if old_url != page_url:
            text = re.sub(r"<a\b[^>]*>", lambda m: attr_change(m[0], "href", page_url), text, count=1, flags=re.I)
    else:
        text = ('<article class="style1 caption-bottom">\n  <span class="image"><img src="' + escape(image, quote=True)
                + '" loading="lazy" alt="' + escape(alt, quote=True) + '" decoding="async" /></span>\n'
                + '  <a href="' + escape(page_url, quote=True) + '"><div class="tile-caption"><h2>' + escape(title)
                + '</h2><div class="content"><p>' + escape(caption) + '</p></div></div></a>\n</article>')
    return {"page": page_url, "html": text}


def rewrite_links(text, old_url, new_url, source_url):
    pattern = re.compile(r"(<a\b[^>]*?\bhref\s*=\s*)([\"'])(.*?)\2", re.S | re.I)
    def replace(match):
        resolved = urlsplit(urljoin("https://worldofsoumyajit.com" + source_url, unescape(match[3])))
        if resolved.netloc not in {"worldofsoumyajit.com", "www.worldofsoumyajit.com"} or resolved.path != old_url:
            return match[0]
        suffix = ("?" + resolved.query if resolved.query else "") + ("#" + resolved.fragment if resolved.fragment else "")
        return match[1] + '"' + escape(new_url + suffix, quote=True) + '"'
    return pattern.sub(replace, text).replace("https://worldofsoumyajit.com" + old_url, "https://worldofsoumyajit.com" + new_url)


class SiteManager:
    def __init__(self, root, origin):
        self.root = Path(root).resolve()
        self.origin = origin
        self.ruby = ruby_executable()
        self.cache = self.root / ".site-manager"
        (self.cache / "history").mkdir(parents=True, exist_ok=True)
        (self.cache / "uploads").mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.build_status = {"running": False, "ready": False, "error": "", "log": ""}
        self.preview = None
        self.review = None
        self.storage = S3Library(self.root)

    def yaml(self, action, **payload):
        result = subprocess.run([self.ruby, str(Path(__file__).parent / "site_manager/yaml_bridge.rb")],
                                input=json.dumps({"action": action, **payload}, ensure_ascii=False), text=True, capture_output=True)
        if result.returncode:
            raise Problem("Could not read page metadata: " + result.stderr.splitlines()[0])
        return json.loads(result.stdout) if action == "load" else result.stdout

    def snapshot(self):
        with self.lock:
            files = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.glob("*.html") if FRONT.match(p.read_text())}
            for name in [TILES_FILE, SECTIONS_FILE, "_data/people.json", "_data/redirects.json", "_data/navigation.yml", "_config.yml"]:
                files[name] = (self.root / name).read_bytes()
            pages = {}
            entries = [(name, data.decode()) for name, data in files.items() if name.endswith(".html")]
            documents = [FRONT.match(text)[1] for _, text in entries]
            metadata = self.yaml("load", documents=documents + [files["_config.yml"].decode()])
            for (name, text), meta in zip(entries, metadata):
                match = FRONT.match(text)
                pages[name] = {"id": name, "url": meta.get("permalink", "/" if name == "index.html" else "/" + name),
                               "meta": meta, "body": text[match.end():], "text": text, "revision": digest(files[name])}
            return files, pages, metadata[-1]

    def state(self):
        files, pages, config = self.snapshot()
        catalog, tiles = load_sections(files)
        section_pages = [{"id": name, **details, **catalog[details["url"]],
                          "sections": [{**section, "count": len(tiles[section["id"]])} for section in catalog[details["url"]]["sections"]]}
                         for name, details in MAIN_PAGES.items()]
        groups = {section["id"]: page["title"] + " / " + section["title"] for page in section_pages for section in page["sections"]}
        result = []
        for name, page in pages.items():
            if name in {"404.html", "elements.html"}:
                continue
            placements = [group for group, entries in tiles.items() if any(tile["page"] == page["url"] for tile in entries)]
            result.append({"id": name, "title": page["meta"].get("title", name), "url": page["url"],
                           "section": page["meta"].get("section", "main"), "protected": name in PROTECTED,
                           "groups": placements, "description": page["meta"].get("description", "")})
        return {"pages": sorted(result, key=lambda p: (not p["protected"], p["title"].casefold())), "groups": groups,
                "section_pages": section_pages, "sections_revision": sections_revision(files),
                "group_categories": {section["id"]: page["category"] for page in section_pages for section in page["sections"]},
                "people": json.loads(files["_data/people.json"]), "tiles": {group: [{"page": t["page"], **tile_fields(t)} for t in entries] for group, entries in tiles.items()},
                "storage": self.storage.status(), "settings": {"profile_image": config.get("profile_image", ""), "email": config.get("email", ""),
                             "cv": config.get("cv", {}), "social": config.get("social", {})}, "history": self.history(), "build": self.build_status}

    def page(self, name):
        files, pages, _ = self.snapshot()
        if name not in pages:
            raise Problem("That page no longer exists. Refresh the page list.")
        page = copy.deepcopy(pages[name])
        tiles = json.loads(files["_data/tiles.json"])
        page["tile"] = None
        for group, entries in tiles.items():
            for position, tile in enumerate(entries):
                if tile["page"] == page["url"]:
                    page["tile"] = {**tile_fields(tile), "group": group, "position": position}
        heading = re.search(r"<h1\b[^>]*>(.*?)</h1>", page["body"], re.S | re.I)
        page["heading"] = plain(heading[1]) if heading else page["meta"].get("title", "")
        page["protected"] = name in PROTECTED
        page.pop("text")
        return page

    def commit(self, label, writes, before):
        """Archive a reversible change and reject concurrent external edits."""
        changed = {name: data for name, data in writes.items() if data != before.get(name)}
        if not changed:
            return None
        for name in changed:
            path = self.root / name
            if not path.resolve().is_relative_to(self.root):
                raise Problem("Invalid file path.")
            actual = path.read_bytes() if path.exists() else None
            if actual != before.get(name):
                raise Problem("A file changed outside the manager. Reload the form before saving: " + name)
        identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + "-" + secrets.token_hex(3)
        entry = {"id": identifier, "label": label, "time": datetime.now(timezone.utc).isoformat(), "undone": False,
                 "files": {name: {"before": base64.b64encode(before[name]).decode() if before.get(name) is not None else None,
                                   "after": digest(data)} for name, data in changed.items()}}
        journal = self.cache / "history" / (identifier + ".json")
        journal.write_text(json.dumps(entry, ensure_ascii=False))
        applied = []
        try:
            for name, data in changed.items():
                self.write(name, data)
                applied.append(name)
        except Exception:
            for name in reversed(applied):
                self.write(name, before.get(name))
            journal.unlink()
            raise
        self.review = None
        return identifier

    def write(self, name, data):
        path = self.root / name
        if data is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".manager-tmp")
            temporary.write_bytes(data)
            os.replace(temporary, path)

    def history(self):
        entries = []
        for path in sorted((self.cache / "history").glob("*.json"), reverse=True):
            entry = json.loads(path.read_text())
            entries.append({key: entry[key] for key in ["id", "label", "time", "undone"]})
        active = next((entry["id"] for entry in entries if not entry["undone"]), None)
        for entry in entries:
            entry["canUndo"] = entry["id"] == active
        return entries[:20]

    def undo(self, data):
        with self.lock:
            entry_id = data.get("id")
            if not any(e["id"] == entry_id and e["canUndo"] for e in self.history()):
                raise Problem("Only the most recent active change can be undone.")
            path = self.cache / "history" / (entry_id + ".json")
            entry = json.loads(path.read_text())
            current_versions = {}
            for name, version in entry["files"].items():
                current = self.root / name
                actual = current.read_bytes() if current.exists() else None
                if digest(actual) != version["after"]:
                    raise Problem("This file changed after that operation. Undo would overwrite it: " + name)
                current_versions[name] = actual
            restored = []
            try:
                for name, version in entry["files"].items():
                    self.write(name, base64.b64decode(version["before"]) if version["before"] is not None else None)
                    restored.append(name)
            except Exception:
                for name in reversed(restored):
                    self.write(name, current_versions[name])
                raise
            entry["undone"] = True
            path.write_text(json.dumps(entry, ensure_ascii=False))
            self.review = None
        self.start_build()
        return {"message": "Change undone."}

    def save(self, data):
        with self.lock:
            before, pages, _ = self.snapshot()
            name = data.get("id")
            existing = pages.get(name)
            if name and not existing:
                raise Problem("This page no longer exists.")
            if existing and data.get("revision") != existing["revision"]:
                raise Problem("This page changed after you opened it. Reload it before saving.")
            title = str(data.get("title", "")).strip()
            description = str(data.get("description", "")).strip()
            if not title or not description:
                raise Problem("Enter a page title and a search description.")
            slug = str(data.get("slug", "")).strip()
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) and name not in PROTECTED:
                raise Problem("The page address must use lowercase English letters, numbers, and hyphens.")
            filename = name if name in PROTECTED else slug + ".html"
            target_url = existing["url"] if name in PROTECTED else "/" + filename
            redirects = json.loads(before["_data/redirects.json"])
            if filename != name:
                occupied = {path.name.casefold() for path in self.root.glob("*.html")}
                occupied.update(path.lstrip("/").casefold() for path in redirects)
                if filename.casefold() in occupied:
                    raise Problem("That address is already used by a page or a historical redirect.")
            section = data.get("section", "works")
            if section not in {"works", "photography", "creativity", "about", "main"}:
                raise Problem("Choose a valid page section.")
            meta = copy.deepcopy(data.get("metadata") if isinstance(data.get("metadata"), dict) else existing["meta"] if existing else {})
            meta.update({"title": title, "description": description, "permalink": target_url})
            if name not in PROTECTED:
                meta.update({"layout": "detail", "section": section, "content_type": data.get("type", "general")})
            image = valid_url(data.get("image"))
            if image:
                meta["image"] = image
            else:
                meta.pop("image", None)
            body = str(data.get("body", ""))
            if not plain(body) and not re.search(r"<(?:img|iframe)\b", body, re.I):
                raise Problem("Add some page content.")
            if re.search(r"<script\b|\son\w+\s*=", body, re.I):
                raise Problem("Use static page content; scripts and inline event handlers are not supported by the editor.")
            heading = str(data.get("heading") or title).strip()
            old_heading = re.search(r"<h1\b[^>]*>(.*?)</h1>", existing["body"] if existing else "", re.S | re.I)
            if not existing:
                body = '<h1 align="center">' + escape(heading) + '</h1>\n' + body
            elif old_heading and heading != plain(old_heading[1]):
                body = re.sub(r"(<h1\b[^>]*>).*?(</h1>)", lambda m: m[1] + escape(heading) + m[2], body, count=1, flags=re.S | re.I)
            schemas = meta.get("structured_data", [])
            schemas = schemas if isinstance(schemas, list) else [schemas]
            schemas = [s for s in schemas if not isinstance(s, dict) or s.get("@type") != "VideoObject" or s.get("embedUrl", "") in body]
            for schema in schemas:
                if isinstance(schema, dict) and schema.get("@type") == "ScholarlyArticle":
                    schema.update({"name": title, "description": description, "url": "https://worldofsoumyajit.com" + target_url})
            for schema in data.get("videos", []):
                self.validate_video(schema)
                if schema["embedUrl"] not in body:
                    continue
                schemas = [s for s in schemas if s.get("embedUrl") != schema["embedUrl"]] + [schema]
            if schemas:
                meta["structured_data"] = schemas[0] if len(schemas) == 1 else schemas
            else:
                meta.pop("structured_data", None)
            writes = {}
            old_url = existing["url"] if existing else target_url
            if existing and old_url != target_url:
                body = rewrite_links(body, old_url, target_url, old_url)
                redirects = {old: target_url if target == old_url else target for old, target in redirects.items()}
                redirects[old_url] = target_url
                writes[name] = None
                for other in pages.values():
                    if other["id"] != name:
                        updated = rewrite_links(other["text"], old_url, target_url, other["url"])
                        if updated != other["text"]:
                            writes[other["id"]] = updated.encode()
                writes["_data/redirects.json"] = self.json_bytes(redirects)
            catalog, tiles = load_sections(before)
            prior = next((tile for entries in tiles.values() for tile in entries if tile["page"] == old_url), None)
            for group in tiles:
                tiles[group] = [t for t in tiles[group] if t["page"] not in {old_url, target_url}]
                for tile in tiles[group]:
                    if old_url != target_url:
                        tile["html"] = rewrite_links(tile["html"], old_url, target_url, "/")
            settings = data.get("tile") or {}
            if settings.get("enabled"):
                group = settings.get("group")
                if group not in section_groups(catalog):
                    raise Problem("Choose the section where the tile should appear.")
                position = max(0, min(int(settings.get("position", 0)), len(tiles[group])))
                tiles[group].insert(position, make_tile(target_url, settings, prior, old_url))
            writes["_data/tiles.json"] = self.json_bytes(tiles)
            for upload_id in data.get("uploads", []):
                if not re.fullmatch(r"[a-f0-9]{24}", upload_id):
                    raise Problem("Invalid uploaded file.")
                upload = self.cache / "uploads" / (upload_id + ".json")
                info = json.loads(upload.read_text())
                if info["url"] in body or info["url"] == image or info["url"] == settings.get("image"):
                    asset = info["url"].lstrip("/")
                    before[asset] = None
                    writes[asset] = (self.cache / "uploads" / upload_id).read_bytes()
            # Preserve the original front matter exactly when no metadata changed.
            if existing and meta == existing["meta"]:
                front = FRONT.match(existing["text"])[0]
            else:
                front = self.yaml("dump", data=meta).rstrip() + "\n---\n"
            writes[filename] = (front + body).encode()
            self.commit(("Update " if existing else "Create ") + title, writes, before)
        self.start_build()
        return {"message": "Page saved. Its tile, links, and metadata are updated.", "id": filename}

    @staticmethod
    def json_bytes(value):
        return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()

    def delete(self, data):
        with self.lock:
            before, pages, _ = self.snapshot()
            choices = data.get("pages", [])
            selected = {entry.get("id") for entry in choices}
            if not selected or selected & PROTECTED or not selected <= pages.keys():
                raise Problem("Choose existing detail pages. Main index pages cannot be deleted.")
            replacements = {}
            for choice in choices:
                page = pages[choice["id"]]
                if choice.get("revision") != page["revision"]:
                    raise Problem("A selected page changed. Reload the selection before deleting.")
                replacement = choice.get("replacement", "")
                if replacement and not any(p["url"] == replacement and p["id"] not in selected for p in pages.values()):
                    raise Problem("Choose a replacement page that is not also being deleted.")
                replacements[page["url"]] = replacement
            writes = {name: None for name in selected}
            for page in pages.values():
                if page["id"] in selected:
                    continue
                text = page["text"]
                for old, new in replacements.items():
                    if new:
                        text = rewrite_links(text, old, new, page["url"])
                    elif rewrite_links(text, old, "/__removed__", page["url"]) != text:
                        raise Problem(page["meta"].get("title", page["id"]) + " still links to the deleted page. Choose a replacement or edit that link first.")
                if text != page["text"]:
                    writes[page["id"]] = text.encode()
            tiles = json.loads(before["_data/tiles.json"])
            for group in tiles:
                tiles[group] = [t for t in tiles[group] if t["page"] not in replacements]
            redirects = json.loads(before["_data/redirects.json"])
            redirects = {old: replacements.get(target, target) for old, target in redirects.items() if target not in replacements or replacements[target]}
            redirects.update({old: new for old, new in replacements.items() if new})
            writes.update({"_data/tiles.json": self.json_bytes(tiles), "_data/redirects.json": self.json_bytes(redirects)})
            self.commit("Delete " + ", ".join(pages[name]["meta"].get("title", name) for name in sorted(selected)), writes, before)
        self.start_build()
        return {"message": "Selected pages removed. You can restore them from Recent changes."}

    def reorder(self, data):
        with self.lock:
            path = self.root / "_data/tiles.json"
            before = path.read_bytes()
            catalog, tiles = load_sections({SECTIONS_FILE: (self.root / SECTIONS_FILE).read_bytes(), TILES_FILE: before})
            group = data.get("group")
            order = data.get("order", [])
            if group not in tiles or sorted(order) != sorted(t["page"] for t in tiles[group]):
                raise Problem("The tile list changed. Reload it before arranging the tiles.")
            lookup = {tile["page"]: tile for tile in tiles[group]}
            tiles[group] = [lookup[url] for url in order]
            self.commit("Arrange " + section_groups(catalog)[group] + " tiles", {TILES_FILE: self.json_bytes(tiles)}, {TILES_FILE: before})
        self.start_build()
        return {"message": "Tile order saved."}

    def manage_sections(self, data):
        with self.lock:
            before, pages, _ = self.snapshot()
            catalog, tiles = load_sections(before)
            if data.get("revision") != sections_revision(before):
                raise Problem("Sections or tiles changed after you opened this screen. Reload Sections before saving.")
            page = data.get("page")
            if page not in MAIN_PAGES: raise Problem("Choose a main page for these sections.")
            settings = catalog[MAIN_PAGES[page]["url"]]
            action = data.get("action")
            identifier = data.get("id")
            section = next((item for item in settings["sections"] if item["id"] == identifier), None)
            if action in {"edit", "delete"} and section is None: raise Problem("That section no longer exists on this page.")
            if action in {"create", "edit"}:
                title = str(data.get("title", "")).strip()
                if not title or len(title) > 120: raise Problem("Enter a section title between 1 and 120 characters.")
                show_heading = data.get("show_heading", True)
                if not isinstance(show_heading, bool): raise Problem("Choose whether the section heading is shown.")
                if action == "create":
                    base = slugify(title)
                    if not base[0].isalpha(): base = "section-" + base
                    used = set(RESERVED_IDS)
                    used.update(re.findall(r'''\bid\s*=\s*["']([^"']+)''', pages[page]["body"], re.I))
                    for item in section_groups(catalog): used.update({item, item + "-heading"})
                    identifier, suffix = base, 2
                    while identifier in used or identifier + "-heading" in used:
                        identifier = base + "-" + str(suffix);suffix += 1
                    settings["sections"].insert(0, {"id": identifier, "title": title, "show_heading": show_heading})
                    tiles[identifier] = []
                    label = "Add section " + title
                else:
                    section.update({"title": title, "show_heading": show_heading})
                    label = "Edit section " + title
            elif action == "reorder":
                order = data.get("order")
                expected = [item["id"] for item in settings["sections"]]
                if not isinstance(order, list) or any(not isinstance(item, str) for item in order) or sorted(order) != sorted(expected):
                    raise Problem("The section order must contain every section exactly once.")
                lookup = {item["id"]: item for item in settings["sections"]}
                settings["sections"] = [lookup[item] for item in order]
                label = "Arrange sections on " + MAIN_PAGES[page]["title"]
            elif action == "navigation":
                if not isinstance(data.get("navigation"), bool): raise Problem("Choose whether section links are shown.")
                settings["navigation"] = data["navigation"]
                label = "Update section links on " + MAIN_PAGES[page]["title"]
            elif action == "delete":
                if tiles[identifier]:
                    disposition = data.get("tile_action")
                    if disposition not in {"move", "hide"}: raise Problem("Choose where the section's tiles should go.")
                    if disposition == "move":
                        destination = data.get("destination")
                        if destination not in tiles or destination == identifier: raise Problem("Choose another section for these tiles.")
                        existing_pages = {tile["page"] for tile in tiles[destination]}
                        tiles[destination] = [tile for tile in tiles[identifier] if tile["page"] not in existing_pages] + tiles[destination]
                settings["sections"] = [item for item in settings["sections"] if item["id"] != identifier]
                tiles.pop(identifier)
                label = "Remove section " + section["title"]
            else:
                raise Problem("Choose a valid section operation.")
            validate_sections(catalog, tiles)
            operation = self.commit(label, {SECTIONS_FILE: self.json_bytes(catalog), TILES_FILE: self.json_bytes(tiles)}, before)
        if operation: self.start_build()
        return {"id": identifier, "message": "Sections saved. Linked pages are preserved; preview is updating." if operation else "No section changes were needed."}

    def settings(self, data):
        with self.lock:
            path = self.root / "_config.yml"
            before = path.read_bytes()
            config = self.yaml("load", documents=[before.decode()])[0]
            photo = valid_url(data.get("profile_image"), True)
            if photo != config.get("profile_image"):
                config["favicon_version"] = int(config.get("favicon_version", 1)) + 1
            config["profile_image"] = photo
            config["email"] = str(data.get("email", "")).strip()
            for field in ["two_page", "full"]:
                config.setdefault("cv", {})[field] = valid_url(data.get("cv", {}).get(field))
            for field, value in data.get("social", {}).items():
                if field in config.get("social", {}):
                    config["social"][field] = valid_url(value)
            self.commit("Update shared website settings", {"_config.yml": self.yaml("dump", data=config).encode()}, {"_config.yml": before})
        self.start_build()
        return {"message": "Shared settings saved for every page."}

    def person(self, data):
        with self.lock:
            path = self.root / "_data/people.json"
            before = path.read_bytes()
            people = json.loads(before)
            name = str(data.get("name", "")).strip()
            if not name:
                raise Problem("Enter the person's name.")
            identifier = data.get("id") or slugify(name).replace("-", "_")
            if not re.fullmatch(r"[a-z0-9_]+", identifier):
                raise Problem("Invalid person identifier.")
            aliases = list(dict.fromkeys([name] + [a.strip() for a in data.get("aliases", []) if a.strip()]))
            occupied = {alias for key, person in people.items() if key != identifier for alias in person["aliases"]}
            if occupied.intersection(aliases):
                raise Problem("That name or alias already belongs to another person.")
            people[identifier] = {"name": name, "url": valid_url(data.get("url"), True), "aliases": aliases}
            self.commit("Update profile for " + name, {"_data/people.json": self.json_bytes(people)}, {"_data/people.json": before})
        self.start_build()
        return {"message": "Profile saved. Shared mentions will use this link.", "id": identifier}

    def upload(self, data):
        filename = Path(str(data.get("name", ""))).name
        extension = Path(filename).suffix.lower()
        if extension not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".pdf"}:
            raise Problem("Choose a JPG, PNG, GIF, WebP, AVIF, SVG, or PDF file.")
        try:
            content = base64.b64decode(data.get("content", ""), validate=True)
        except ValueError:
            raise Problem("The file could not be read.")
        if not content or len(content) > 25 * 1024 * 1024:
            raise Problem("Choose a file smaller than 25 MB.")
        identifier = secrets.token_hex(12)
        url = "/assets/uploads/" + slugify(Path(filename).stem)[:70] + "-" + identifier[:8] + extension
        (self.cache / "uploads" / identifier).write_bytes(content)
        result = {"id": identifier, "url": url, "name": filename}
        (self.cache / "uploads" / (identifier + ".json")).write_text(json.dumps(result))
        return result

    @staticmethod
    def validate_video(schema):
        if not isinstance(schema, dict) or schema.get("@type") != "VideoObject":
            raise Problem("Invalid video information.")
        date = schema.get("uploadDate", "")
        try:
            parsed = datetime.fromisoformat(date.replace("Z", "+00:00"))
            if "T" not in date or parsed.utcoffset() is None:
                raise ValueError()
        except (ValueError, TypeError):
            raise Problem("The video needs its actual upload datetime with a timezone, such as 2026-03-11T20:05:04-07:00.")
        if not re.fullmatch(r"https://www\.youtube\.com/embed/[A-Za-z0-9_-]{11}", schema.get("embedUrl", "")):
            raise Problem("Use a valid YouTube video.")

    def video(self, data):
        url = urlsplit(str(data.get("url", "")))
        if url.netloc.removeprefix("www.") in {"youtube.com", "m.youtube.com"}:
            identifier = parse_qs(url.query).get("v", [url.path.rsplit("/", 1)[-1]])[0]
        elif url.netloc == "youtu.be":
            identifier = url.path.strip("/")
        else:
            raise Problem("Paste a YouTube watch, Shorts, or youtu.be URL.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", identifier):
            raise Problem("The YouTube video ID is not valid.")
        title = str(data.get("title", "")).strip()
        date = str(data.get("uploadDate", "")).strip()
        if not title or not date:
            try:
                request = Request("https://www.youtube.com/watch?v=" + identifier, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(request, timeout=15) as response:
                    raw = response.read(8 * 1024 * 1024).decode()
                dates = set(re.findall(r'"uploadDate":"([^"\\]+)"', raw))
                if len(dates) == 1 and not date:
                    date = dates.pop()
                name = re.search(r"<title>(.*?)</title>", raw, re.S)
                if name and not title:
                    title = unescape(name[1]).removesuffix(" - YouTube")
            except Exception:
                pass
        return {"@context": "https://schema.org", "@type": "VideoObject", "name": title or "Video",
                "description": str(data.get("description") or title or "Video"), "uploadDate": date,
                "thumbnailUrl": "https://img.youtube.com/vi/" + identifier + "/hqdefault.jpg",
                "embedUrl": "https://www.youtube.com/embed/" + identifier}

    def build(self, production=False):
        folder = self.cache / "previews" / secrets.token_hex(8)
        folder.mkdir(parents=True)
        command = ["/bin/bash", str(self.root / "scripts/jekyll.sh"), "build", "--trace", "--destination", str(folder)]
        if not production:
            config = self.cache / "preview-config.json"
            config.write_text(json.dumps({"url": self.origin, "baseurl": "", "analytics_id": ""}))
            command += ["--config", "_config.yml," + str(config)]
        env = os.environ.copy()
        env["JEKYLL_ENV"] = "production" if production else "development"
        result = subprocess.run(command, cwd=self.root, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)
        if result.returncode:
            raise Problem("Build failed:\n" + result.stdout[-7000:])
        if production:
            checked = subprocess.run([shutil.which("python3") or "python3", "scripts/validate_site.py", str(folder)], cwd=self.root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
            if checked.returncode:
                raise Problem("Validation failed:\n" + checked.stdout[-7000:])
        # Keep recent previews without accumulating a full asset copy per save.
        previews = sorted((self.cache / "previews").iterdir(), key=lambda path: path.stat().st_mtime, reverse=True)
        for previous in previews[3:]:
            if previous != self.preview and previous.is_dir():
                shutil.rmtree(previous, ignore_errors=True)
        return folder, result.stdout

    def start_build(self):
        if self.build_status["running"]:
            self.build_status["again"] = True
            return {"message": "Preview build queued."}
        self.build_status = {"running": True, "ready": self.preview is not None, "error": "", "log": "", "again": False}
        def worker():
            try:
                while True:
                    self.build_status["again"] = False
                    with self.lock:
                        folder, log = self.build()
                        self.preview = folder
                        self.build_status.update({"ready": True, "log": log, "error": ""})
                    if not self.build_status.get("again"):
                        break
            except Exception as error:
                self.build_status["error"] = str(error)
            finally:
                self.build_status["running"] = False
        threading.Thread(target=worker, daemon=True).start()
        return {"message": "Building preview."}

    def git(self, *args):
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        result = subprocess.run(["git", *args], cwd=self.root, env=env, stdin=subprocess.DEVNULL, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        if result.returncode:
            raise Problem(result.stdout.strip() or "Git could not complete that operation.")
        return result.stdout

    def git_changes(self):
        raw = self.git("status", "--porcelain=v1", "-z", "--untracked-files=all")
        chunks = raw.split("\0")
        result = []
        i = 0
        while i < len(chunks):
            entry = chunks[i]
            i += 1
            if not entry:
                continue
            result.append(entry[3:])
            if "R" in entry[:2] or "C" in entry[:2]:
                result.append(chunks[i]); i += 1
        return sorted(set(result))

    def fingerprint(self, names):
        return digest(self.json_bytes({name: digest((self.root / name).read_bytes()) if (self.root / name).is_file() else None for name in names}))

    def review_changes(self):
        with self.lock:
            branch = self.git("branch", "--show-current").strip()
            if branch != "main":
                raise Problem("Publishing is configured for main. Switch to main before publishing.")
            names = self.git_changes()
            if not names:
                raise Problem("There are no local changes to publish.")
            fingerprint = self.fingerprint(names)
            head = self.git("rev-parse", "HEAD").strip()
            self.build(production=True)
            if self.git_changes() != names or self.fingerprint(names) != fingerprint or self.git("rev-parse", "HEAD").strip() != head:
                raise Problem("Files changed while the production checks were running. Run Review & validate again.")
            self.review = {"id": secrets.token_hex(16), "files": names, "fingerprint": fingerprint, "head": head, "branch": branch}
            return {"id": self.review["id"], "files": names, "branch": branch, "message": "Production build and all checks passed. Review every listed file before publishing."}

    def publish(self, data):
        with self.lock:
            review = self.review
            if not review or data.get("review") != review["id"]:
                raise Problem("Review and validate the changes first.")
            names = self.git_changes()
            if names != review["files"] or self.fingerprint(names) != review["fingerprint"] or self.git("rev-parse", "HEAD").strip() != review["head"] or self.git("branch", "--show-current").strip() != review["branch"]:
                raise Problem("Files or the branch changed after review. Run Review & validate again.")
            message = str(data.get("message", "")).strip()
            if not message:
                raise Problem("Enter a short description of the update.")
            self.git("add", "--", *names)
            self.git("commit", "-m", message)
            self.review = None
            try:
                self.git("push", "origin", "HEAD:main")
            except Problem as error:
                raise Problem("The commit was saved locally, but GitHub could not be updated. Your changes are safe. Run git push origin main after fixing GitHub access.\n" + str(error))
            return {"message": "Pushed to GitHub. The Pages workflow will build and deploy the website."}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    @property
    def manager(self):
        return self.server.manager

    def send(self, status, content, kind="application/json; charset=utf-8"):
        body = content if isinstance(content, bytes) else content.encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        return secrets.compare_digest(self.headers.get("X-Manager-Token", ""), self.server.token)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith("/api/"):
            if not self.authorized():
                return self.send(403, '{"error":"Open the website manager to continue."}')
            try:
                if path == "/api/state": result = self.manager.state()
                elif path == "/api/page": result = self.manager.page(parse_qs(urlsplit(self.path).query).get("id", [""])[0])
                elif path == "/api/status": result = self.manager.build_status
                elif path == "/api/s3/status": result = self.manager.storage.status()
                elif path == "/api/s3/files":
                    query = parse_qs(urlsplit(self.path).query)
                    result = self.manager.storage.browse(prefix=query.get("prefix", [None])[0], kind=query.get("kind", ["image"])[0], cursor=query.get("cursor", [None])[0])
                else: return self.send(404, '{"error":"Unknown operation."}')
                return self.send(200, json.dumps(result, ensure_ascii=False))
            except Exception as error:
                return self.send(400, json.dumps({"error": str(error)}))
        static = Path(__file__).parent / "site_manager"
        if path in {"/__manager", "/__manager/"}:
            text = (static / "index.html").read_text().replace("__MANAGER_TOKEN__", self.server.token)
            return self.send(200, text, "text/html; charset=utf-8")
        if path.startswith("/__manager/"):
            base = static
            relative = path[len("/__manager/"):]
        elif path.startswith("/__uploads/"):
            identifier = path.removeprefix("/__uploads/")
            if not re.fullmatch(r"[a-f0-9]{24}", identifier): return self.send(404, b"")
            info_path = self.manager.cache / "uploads" / (identifier + ".json")
            if not info_path.exists(): return self.send(404, b"")
            info = json.loads(info_path.read_text())
            return self.send(200, (self.manager.cache / "uploads" / identifier).read_bytes(), mimetypes.guess_type(info["url"])[0] or "application/octet-stream")
        elif path.startswith("/assets/uploads/"):
            # Newly saved uploads must be visible while the next preview builds.
            base = self.manager.root / "assets/uploads"
            relative = unquote(path.removeprefix("/assets/uploads/"))
        elif self.manager.preview:
            base = self.manager.preview
            relative = unquote(path).lstrip("/") or "index.html"
        else:
            return self.send(200, '<p>The preview is building. <a href="/__manager/">Return to the website manager</a>.</p>', "text/html; charset=utf-8")
        target = (base / relative).resolve()
        if not target.is_relative_to(base.resolve()) or not target.is_file():
            if self.manager.preview and base == self.manager.preview and (base / "404.html").is_file():
                return self.send(404, (base / "404.html").read_bytes(), "text/html; charset=utf-8")
            return self.send(404, b"Not found", "text/plain; charset=utf-8")
        return self.send(200, target.read_bytes(), mimetypes.guess_type(str(target))[0] or "application/octet-stream")

    def do_POST(self):
        if not self.authorized() or self.headers.get("Origin") != self.manager.origin:
            return self.send(403, '{"error":"Open the website manager to continue."}')
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 36 * 1024 * 1024:
                raise Problem("Choose a file smaller than 25 MB.")
            data = json.loads(self.rfile.read(size))
            operations = {"save": self.manager.save, "delete": self.manager.delete, "undo": self.manager.undo,
                          "reorder": self.manager.reorder, "sections": self.manager.manage_sections, "settings": self.manager.settings, "person": self.manager.person,
                          "upload": self.manager.upload, "video": self.manager.video, "review": lambda _: self.manager.review_changes(),
                          "publish": self.manager.publish, "build": lambda _: self.manager.start_build(),
                          "s3/configure": self.manager.storage.configure, "s3/connect": lambda _: self.manager.storage.connect(),
                          "s3/install": lambda _: self.manager.storage.install(),
                          "s3/install-images": lambda _: self.manager.storage.install_images(),
                          "s3/prepare-images": self.manager.storage.prepare_images,
                          "s3/prepare-image-urls": self.manager.storage.prepare_image_urls,
                          "s3/resolve": self.manager.storage.resolve}
            name = urlsplit(self.path).path.removeprefix("/api/")
            if name not in operations: return self.send(404, '{"error":"Unknown operation."}')
            result = operations[name](data)
            self.send(200, json.dumps(result, ensure_ascii=False))
        except Exception as error:
            self.send(400, json.dumps({"error": str(error)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4111)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError:
        raise SystemExit("Port " + str(args.port) + " is already in use. Open the existing manager, or run with --port 4112.")
    origin = "http://127.0.0.1:" + str(server.server_port)
    server.manager = SiteManager(root, origin)
    server.token = secrets.token_hex(32)
    server.manager.start_build()
    print("Website manager: " + origin + "/__manager/", flush=True)
    print("Keep this terminal open. Press Control-C to stop.", flush=True)
    if not args.no_browser:
        webbrowser.open(origin + "/__manager/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
