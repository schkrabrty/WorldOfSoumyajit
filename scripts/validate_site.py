#!/usr/bin/env python3
"""Check built pages, shared components, local links, and search discovery files."""

import argparse
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit
import xml.etree.ElementTree as ET


PEOPLE = json.loads((Path(__file__).resolve().parents[1] / "_data/people.json").read_text())
ALIASES = {
    alias: person_id
    for person_id, person in PEOPLE.items()
    for alias in person["aliases"]
}
PERSON_PATTERN = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(alias) for alias in sorted(ALIASES, key=len, reverse=True)) + r")(?!\w)"
)


def image_identity(url):
    """Ignore the favicon cache version when comparing it with the portrait."""
    parts = urlsplit(url or "")
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "favicon"]
    return parts._replace(query=urlencode(query), fragment="").geturl()


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.ids = Counter()
        self.meta = {}
        self.links = []
        self.assets = []
        self.icons = []
        self.canonicals = []
        self.refreshes = []
        self.portrait = None
        self.title = ""
        self.schemas = []
        self.people = []
        self.has_lightbox = False
        self._header = False
        self._body = False
        self._title = False
        self._anchor = None
        self._script = False
        self._json = False
        self._script_text = ""
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "body":
            self._body = True
        if "id" in attrs:
            self.ids[attrs["id"]] += 1
        if "data-lightbox" in attrs:
            self.has_lightbox = True
        if tag == "header" and attrs.get("id") == "header":
            self._header = True
        if tag == "img" and self._header:
            self.portrait = attrs.get("src")
        if tag == "title":
            self._title = True
        if tag == "meta":
            self.meta[attrs.get("name", attrs.get("property"))] = attrs.get("content")
            if attrs.get("http-equiv", "").lower() == "refresh":
                self.refreshes.append(attrs.get("content", ""))
        if tag == "a":
            self._anchor = attrs.get("href")
            self.links.append(attrs.get("href", ""))
        if tag == "link":
            rel = attrs.get("rel", "").split()
            if "icon" in rel:
                self.icons.append(attrs.get("href"))
            if "canonical" in rel:
                self.canonicals.append(attrs.get("href"))
            if "stylesheet" in rel:
                self.assets.append(attrs.get("href", ""))
        if tag == "script":
            self._script = True
            self._json = attrs.get("type") == "application/ld+json"
            self._script_text = ""
            if attrs.get("src"):
                self.assets.append(attrs["src"])

    def handle_endtag(self, tag):
        if tag == "body":
            self._body = False
        if tag == "header":
            self._header = False
        if tag == "title":
            self._title = False
        if tag == "a":
            self._anchor = None
        if tag == "script":
            if self._json:
                self.schemas.append(json.loads(self._script_text))
            self._script = False
            self._json = False

    def handle_data(self, text):
        if self._title:
            self.title += text
        if self._script:
            self._script_text += text
        elif self._body:
            for match in PERSON_PATTERN.finditer(" ".join(text.split())):
                name = match.group()
                self.people.append((ALIASES[name], name, self._anchor))


def validate(destination):
    root = destination.resolve()
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)

    sitemap = ET.parse(root / "sitemap.xml")
    urls = [item.text for item in sitemap.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    check(bool(urls), "The sitemap is empty")
    check(len(urls) == len(set(urls)), "The sitemap contains duplicate URLs")
    robots = (root / "robots.txt").read_text()
    declarations = [line.split(":", 1)[1].strip() for line in robots.splitlines() if line.startswith("Sitemap:")]
    check(len(declarations) == 1, "robots.txt must declare one sitemap")
    sitemap_url = declarations[0]
    origin = urlsplit(sitemap_url)
    base_path = origin.path.removesuffix("sitemap.xml")

    def local_file(url):
        path = unquote(urlsplit(url).path)
        if base_path != "/":
            if not path.startswith(base_path):
                return None
            path = path[len(base_path):]
        else:
            path = path.lstrip("/")
        target = (root / path).resolve()
        if target.is_dir():
            target /= "index.html"
        return target if target.is_relative_to(root) else None

    parsed = {}
    public = set()
    profile_mentions = 0
    video_dates = 0

    def schema_objects(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from schema_objects(child)
        elif isinstance(value, list):
            for child in value:
                yield from schema_objects(child)

    for path in sorted(root.rglob("*.html")):
        text = path.read_text()
        page = Page(text)
        parsed[path.resolve()] = page
        name = path.relative_to(root)
        for schema in schema_objects(page.schemas):
            types = schema.get("@type", [])
            if "VideoObject" not in (types if isinstance(types, list) else [types]):
                continue
            value = schema.get("uploadDate", "")
            valid = isinstance(value, str) and bool(re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value
            ))
            if valid:
                try:
                    valid = datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None
                except ValueError:
                    valid = False
            check(valid, f"{name}: VideoObject uploadDate needs a valid ISO 8601 datetime with a timezone: {value!r}")
            video_dates += 1
        if not page.ids["header"]:
            continue
        check("{{" not in text and "{%" not in text, f"{name}: unrendered template")
        for identifier in ["header", "menu", "main", "footer"]:
            check(page.ids[identifier] == 1, f"{name}: expected one #{identifier}")
        check(page.title.strip(), f"{name}: missing title")
        check(len(page.icons) == 1 and image_identity(page.icons[0]) == image_identity(page.portrait), f"{name}: favicon and portrait differ")
        if page.has_lightbox:
            check(any(urlsplit(asset).path.endswith("/lightbox-plus-jquery.min.js") for asset in page.assets), f"{name}: missing lightbox script")
        for person_id, label, person_url in page.people:
            expected = PEOPLE[person_id]["url"]
            check(person_url == expected, f"{name}: {label} should link to {expected}")
            profile_mentions += 1
        if "noindex" not in page.meta.get("robots", ""):
            check(len(page.canonicals) == 1, f"{name}: expected one canonical URL")
            if page.canonicals:
                canonical = page.canonicals[0]
                public.add(canonical)
                check(local_file(canonical) == path.resolve(), f"{name}: canonical URL resolves to another page")
                check(page.meta.get("og:url") == canonical, f"{name}: Open Graph URL differs from canonical")
            for key in ["description", "og:title", "og:description", "og:image"]:
                check(bool(page.meta.get(key)), f"{name}: missing {key}")
    check(public == set(urls), f"Sitemap differs from public pages: missing {sorted(public - set(urls))}; extra {sorted(set(urls) - public)}")
    redirects = json.loads((Path(__file__).resolve().parents[1] / "_data/redirects.json").read_text())
    for old_url, target_url in redirects.items():
        source = local_file(urljoin(sitemap_url, old_url.lstrip("/")))
        target = urljoin(sitemap_url, target_url.lstrip("/"))
        alias_url = urljoin(sitemap_url, old_url.lstrip("/"))
        page = parsed.get(source)
        check(page is not None, f"Missing legacy redirect: {old_url}")
        check(alias_url not in urls, f"Legacy redirect in sitemap: {old_url}")
        check(target in urls, f"Legacy redirect must lead directly to a public canonical page: {old_url}")
        if page:
            check(page.canonicals == [target], f"{old_url}: incorrect redirect canonical")
            check(page.refreshes == [f"0; url={target}"], f"{old_url}: missing immediate redirect")
            check(any(urljoin(alias_url, link) == target for link in page.links), f"{old_url}: missing fallback link")
    for url in urls:
        parsed_url = urlsplit(url)
        check(parsed_url.scheme == "https" and parsed_url.netloc == origin.netloc, f"Invalid sitemap URL: {url}")
        target = local_file(url)
        check(target is not None and target.is_file(), f"Missing sitemap target: {url}")
    for path, page in parsed.items():
        if not page.ids["header"]:
            continue
        page_url = page.canonicals[0] if page.canonicals else urljoin(sitemap_url, str(path.relative_to(root)))
        for reference in page.links + page.assets:
            url = urljoin(page_url, reference)
            parts = urlsplit(url)
            if parts.scheme not in ["http", "https"] or parts.netloc != origin.netloc:
                continue
            target = local_file(url)
            check(target is not None and target.is_file(), f"{path.relative_to(root)}: missing local target {reference}")
            # Text fragments select text rather than an element ID.
            if target in parsed and parts.fragment and not parts.fragment.startswith(":~:text="):
                fragment = unquote(parts.fragment.split(":~:text=", 1)[0])
                check(fragment in parsed[target].ids, f"{path.relative_to(root)}: missing anchor {reference}")
    for internal in ["_includes", "_layouts", "_data", "_plugins", "_config.yml", "Gemfile", "Gemfile.lock", "scripts", "Preview Website.command"]:
        check(not (root / internal).exists(), f"Internal build file published: {internal}")
    for source in Path(".").glob("google*.html"):
        if source.read_text().startswith("google-site-verification:"):
            check((root / source.name).read_bytes() == source.read_bytes(), "Google verification file changed")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Validated {len(public)} public pages, {profile_mentions} person links, {len(redirects)} legacy redirects, {video_dates} video datetimes, sitemap coverage, metadata, shared components, and local links.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", nargs="?", type=Path, default=Path("_site"))
    validate(parser.parse_args().destination)
