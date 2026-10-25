"""S3 browsing, image thumbnails, and website-reference discovery for the manager."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from urllib.parse import quote, unquote, unquote_plus, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

DEFAULTS = {"bucket": "worldofsoumyajit", "region": "us-east-1", "prefix": "My Website related Stuffs/", "profile": "worldofsoumyajit"}
KINDS = {"image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg"}, "pdf": {".pdf"},
         "video": {".mp4", ".webm", ".mov"}, "audio": {".mp3", ".wav", ".ogg"}, "archive": {".zip", ".unitypackage"}}
URL_PATTERN = re.compile(r'''https?://[^\s<>"\\]+''')
THUMBNAIL_FOLDER = "_thumbnails"
THUMBNAIL_RECIPE = "webp-800-v1"
MAX_PHOTO_BYTES = 50 * 1024 * 1024


class AWSProblem(ValueError):
    def __init__(self, message):
        super().__init__(message)
        match = re.search(r"An error occurred \(([^)]+)\)", message)
        self.code = match[1] if match else ""


def object_keys(value, bucket=DEFAULTS["bucket"]):
    """Keep both interpretations of legacy plus signs rather than risk a false deletion."""
    result = set()
    raw = unescape(value)
    for candidate in {raw, raw.rstrip("'\"),;]}.")}:
        parts = urlsplit(candidate)
        host = (parts.hostname or "").lower()
        if (host.startswith(bucket + ".s3.") or host.startswith(bucket + ".s3-")) and host.endswith(".amazonaws.com"):
            path = parts.path.lstrip("/")
        elif host == "s3.amazonaws.com" or host.startswith("s3."):
            first, _, path = parts.path.lstrip("/").partition("/")
            if first != bucket:
                continue
        else:
            continue
        result.update({unquote(path), unquote_plus(path)})
    return result


def collect_references(root, live=False, bucket=DEFAULTS["bucket"]):
    root = Path(root)
    references = defaultdict(set)
    urls = set()
    pairs = []
    failures = []

    def record(value, source):
        keys = object_keys(value, bucket)
        if keys:
            urls.add(unescape(value).rstrip("'\"),;]}"))
        for key in keys:
            references[key].add(source)

    class Links(HTMLParser):
        def __init__(self, source):
            super().__init__(convert_charrefs=True)
            self.source = source
            self.anchor = None
        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            for key in ["href", "src", "content", "poster"]:
                if attributes.get(key):
                    record(attributes[key], self.source)
            if tag == "a":
                self.anchor = attributes.get("href")
            if tag == "img" and self.anchor and attributes.get("src"):
                pairs.append({"full": self.anchor, "small": attributes["src"]})
        def handle_endtag(self, tag):
            if tag == "a":
                self.anchor = None

    def scan(text, source):
        for match in URL_PATTERN.findall(text):
            record(match, source)
        if not source.endswith((".js", ".css")) and "<" in text:
            Links(source).feed(text)

    paths = list(root.glob("*.html")) + [root / "_config.yml"]
    for directory in ["_data", "_includes", "_layouts", "assets/css", "assets/js"]:
        paths.extend(path for path in (root / directory).rglob("*") if path.is_file() and path.suffix.lower() in {".html", ".json", ".yml", ".css", ".js"})
    for path in paths:
        text = path.read_text()
        if path.suffix == ".json":
            def strings(value):
                if isinstance(value, str):
                    scan(value, str(path.relative_to(root)))
                elif isinstance(value, dict):
                    for child in value.values(): strings(child)
                elif isinstance(value, list):
                    for child in value: strings(child)
            strings(json.loads(text))
        else:
            scan(text, str(path.relative_to(root)))
    live_pages = 0
    if live:
        try:
            with urlopen("https://worldofsoumyajit.com/sitemap.xml", timeout=20) as response:
                sitemap = ET.fromstring(response.read())
            locations = [node.text for node in sitemap.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
            if not locations:
                raise ValueError("The live sitemap is empty.")
            def fetch(url):
                if urlsplit(url).hostname != "worldofsoumyajit.com":
                    return url, None, "Unexpected sitemap hostname"
                try:
                    with urlopen(Request(url, headers={"User-Agent": "WorldOfSoumyajit media audit"}), timeout=25) as response:
                        return url, response.read().decode(), None
                except Exception as error:
                    return url, None, str(error)
            with ThreadPoolExecutor(max_workers=5) as pool:
                for url, text, error in pool.map(fetch, locations):
                    if error: failures.append({"url": url, "error": error})
                    else:
                        scan(text, "live:" + url)
                        live_pages += 1
        except Exception as error:
            failures.append({"url": "https://worldofsoumyajit.com/sitemap.xml", "error": str(error)})
    return {"keys": {key: sorted(sources) for key, sources in references.items()}, "urls": sorted(urls), "pairs": pairs,
            "live_pages": live_pages, "failures": failures, "scanned_files": len(paths)}


class S3Library:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.cache = self.root / ".site-manager"
        self.cache.mkdir(exist_ok=True)
        self.settings_path = self.cache / "s3-settings.json"
        self.login_process = None
        self.login_log = None
        self.reference_cache = None
        self.reference_lock = threading.Lock()
        self.thumbnail_lock = threading.Lock()
        self.image_setup_lock = threading.Lock()

    def settings(self):
        result = dict(DEFAULTS)
        if self.settings_path.exists(): result.update(json.loads(self.settings_path.read_text()))
        return result

    def configure(self, data):
        current = self.settings()
        for key in DEFAULTS:
            if key in data: current[key] = str(data[key]).strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", current["bucket"]): raise ValueError("Enter a valid S3 bucket name.")
        if not re.fullmatch(r"[a-z0-9-]+", current["region"]): raise ValueError("Enter a valid AWS region.")
        if not current["profile"]: raise ValueError("Enter the AWS profile name.")
        current["prefix"] = current["prefix"].lstrip("/")
        if current["prefix"] and not current["prefix"].endswith("/"): current["prefix"] += "/"
        self.settings_path.write_text(json.dumps(current, indent=2) + "\n")
        return {"message": "S3 library settings saved on this computer."}

    def executable(self):
        for path in [self.root / ".site-manager/aws-cli-bin/aws", shutil.which("aws")]:
            if path and Path(path).is_file(): return str(path)
        raise ValueError("AWS CLI 2 is not installed. Run bash scripts/setup_aws.sh once, then choose Connect AWS.")

    def command(self, *args, timeout=75):
        settings = self.settings()
        command = [self.executable(), *args, "--profile", settings["profile"], "--region", settings["region"], "--no-cli-pager", "--output", "json"]
        env = os.environ.copy();env.update({"AWS_PAGER": "", "AWS_EC2_METADATA_DISABLED": "true", "AWS_CLI_AUTO_PROMPT": "off"})
        result = subprocess.run(command, cwd=self.root, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise AWSProblem(result.stderr.strip()[-2500:] or "AWS could not complete the request. Choose Connect AWS and sign in again.")
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def status(self):
        try:
            executable = self.executable()
        except ValueError:
            executable = None
        return {**self.settings(), "available": bool(executable), "thumbnails_ready": self.images_ready(),
                "login_pending": bool(self.login_process and self.login_process.poll() is None)}

    def connect(self):
        if self.login_process and self.login_process.poll() is None: return {"message": "Complete the AWS sign-in page already open in your browser."}
        settings = self.settings()
        log_path = self.cache / "aws-login.log"
        log_path.touch(mode=0o600, exist_ok=True)
        self.login_log = log_path.open("w")
        self.login_process = subprocess.Popen([self.executable(), "login", "--profile", settings["profile"], "--region", settings["region"], "--no-cli-pager"],
                                              cwd=self.root, stdin=subprocess.PIPE, stdout=self.login_log, stderr=subprocess.STDOUT, text=True)
        # Decline the CLI's optional AI-agent configuration; it is unrelated to S3 browsing.
        self.login_process.stdin.write("n\n");self.login_process.stdin.close()
        return {"message": "The AWS sign-in page is opening. Sign in and approve MFA there, then refresh the file list."}

    def install(self):
        result = subprocess.run(["/bin/bash", str(self.root / "scripts/setup_aws.sh")], cwd=self.root,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
        if result.returncode: raise ValueError("AWS setup did not finish:\n" + result.stdout[-2500:])
        return {"message": "AWS support is installed. Choose Connect AWS to sign in."}

    def public_url(self, key):
        settings = self.settings()
        return "https://" + settings["bucket"] + ".s3." + settings["region"] + ".amazonaws.com/" + quote(key, safe="/")

    def inventory(self, prefix=""):
        settings = self.settings()
        result = self.command("s3api", "list-objects-v2", "--bucket", settings["bucket"], "--prefix", prefix, "--page-size", "1000", timeout=120)
        return result.get("Contents", [])

    def references(self, bucket):
        paths = list(self.root.glob("*.html")) + [self.root / "_config.yml"]
        paths += [path for path in (self.root / "_data").glob("*") if path.is_file()]
        stamp = (bucket, tuple(sorted((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths)))
        with self.reference_lock:
            if not self.reference_cache or self.reference_cache[0] != stamp:
                self.reference_cache = (stamp, collect_references(self.root, bucket=bucket))
            return self.reference_cache[1]

    def image_python(self):
        return self.cache / "images-venv/bin/python3"

    def images_ready(self):
        return self.image_python().is_file() and (self.image_python().parent.parent / ".ready").is_file()

    def install_images(self):
        with self.image_setup_lock:
            if not self.images_ready():
                result = subprocess.run(["/bin/bash", str(Path(__file__).with_name("setup_images.sh")), str(self.root), sys.executable],
                                        capture_output=True, text=True, timeout=300)
                if result.returncode:
                    raise ValueError("Photo support could not be installed. Run bash scripts/setup_images.sh and try again.\n" + result.stderr[-1500:])
        return {"message": "Photo thumbnail support is ready on this computer."}

    def render_thumbnail(self, source, destination):
        self.install_images()
        result = subprocess.run([str(self.image_python()), str(Path(__file__).with_name("image_thumbnails.py")), str(source), str(destination)],
                                capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise ValueError("This photo could not be resized: " + result.stderr.strip()[-1000:])
        return json.loads(result.stdout)

    def thumbnail_key(self, key, etag):
        identity = json.dumps([self.settings()["bucket"], key, etag, THUMBNAIL_RECIPE], ensure_ascii=True)
        version = hashlib.sha256(identity.encode()).hexdigest()[:24]
        folder, _, name = key.rpartition("/")
        return (folder + "/" if folder else "") + THUMBNAIL_FOLDER + "/" + Path(name).stem[:100] + "-" + version + ".webp"

    def _siblings(self, prefix):
        return self.command("s3api", "list-objects-v2", "--bucket", self.settings()["bucket"], "--prefix", prefix,
                            "--delimiter", "/", "--page-size", "1000", timeout=120).get("Contents", [])

    def _pairs(self, objects, bucket):
        listing_keys = {item["Key"] for item in objects}
        folded = defaultdict(list)
        for key in listing_keys: folded[key.casefold()].append(key)
        pairs = {}
        for pair in self.references(bucket)["pairs"]:
            full = object_keys(pair["full"], bucket) & listing_keys
            small = object_keys(pair["small"], bucket) & listing_keys
            if len(full) == 1 and len(small) == 1:
                full_key, small_key = next(iter(full)), next(iter(small))
                if full_key != small_key:
                    value = {"full_key": full_key, "small_key": small_key,
                             "full_url": self.public_url(full_key), "small_url": self.public_url(small_key)}
                    pairs[full_key] = pairs[small_key] = value
        for item in objects:
            key = item["Key"]
            full_key = re.sub(r"_\d{2,5}[xX]\d{2,5}(?=\.[^./]+$)", "", key)
            if full_key not in listing_keys and len(folded[full_key.casefold()]) == 1:
                full_key = folded[full_key.casefold()][0]
            if full_key != key and full_key in listing_keys and key not in pairs:
                value = {"full_key": full_key, "small_key": key,
                         "full_url": self.public_url(full_key), "small_url": self.public_url(key)}
                pairs[key] = value
                pairs.setdefault(full_key, value)
        return pairs

    def browse(self, prefix=None, kind="image", cursor=None):
        settings = self.settings()
        prefix = settings["prefix"] if prefix is None else prefix
        if not prefix.startswith(settings["prefix"]): raise ValueError("Choose a folder inside the configured website folder.")
        if kind not in {*KINDS, "all"}: raise ValueError("Choose a valid file type.")
        args = ["s3api", "list-objects-v2", "--bucket", settings["bucket"], "--prefix", prefix, "--delimiter", "/", "--max-keys", "500", "--no-paginate"]
        if cursor: args += ["--continuation-token", cursor]
        data = self.command(*args)
        objects = [item for item in data.get("Contents", []) if not item["Key"].endswith("/")]
        pairs = self._pairs(objects, settings["bucket"])
        thumbnail_prefix = prefix + THUMBNAIL_FOLDER + "/"
        if any(item["Prefix"] == thumbnail_prefix for item in data.get("CommonPrefixes", [])):
            generated = {item["Key"] for item in self._siblings(thumbnail_prefix)}
            for item in objects:
                key = item["Key"]
                small = self.thumbnail_key(key, item.get("ETag", ""))
                if key not in pairs and small in generated:
                    pairs[key] = {"full_key": key, "small_key": small, "full_url": self.public_url(key), "small_url": self.public_url(small)}
        files = []
        for item in objects:
            if kind != "all" and Path(item["Key"]).suffix.lower() not in KINDS[kind]: continue
            files.append({"key": item["Key"], "name": item["Key"].removeprefix(prefix), "url": self.public_url(item["Key"]),
                          "size": item["Size"], "modified": item.get("LastModified"), "pair": pairs.get(item["Key"])})
        return {"files": files, "folders": [item["Prefix"] for item in data.get("CommonPrefixes", []) if item["Prefix"] != thumbnail_prefix], "prefix": prefix,
                "root": settings["prefix"], "bucket": settings["bucket"], "next": data.get("NextContinuationToken"), "kind": kind}

    def _checked_keys(self, data):
        settings = self.settings()
        keys = data.get("keys", [])
        if not isinstance(keys, list) or not keys or len(keys) > 150: raise ValueError("Choose between 1 and 150 files.")
        for key in keys:
            if not isinstance(key, str) or not key.startswith(settings["prefix"]) or key.endswith("/"):
                raise ValueError("Choose a file inside the website's S3 folder.")
        return list(dict.fromkeys(keys))

    def _public(self, key):
        url = self.public_url(key)
        try:
            with urlopen(Request(url, method="HEAD"), timeout=20) as response:
                if response.status != 200: raise ValueError("Not publicly readable")
        except Exception:
            raise ValueError("This file cannot be opened by website visitors. Check its S3 access: " + key)
        return {"key": key, "url": url}

    def resolve(self, data):
        keys = self._checked_keys(data)
        with ThreadPoolExecutor(max_workers=4) as pool: return {"files": list(pool.map(self._public, keys))}

    def _head(self, key):
        try:
            return self.command("s3api", "head-object", "--bucket", self.settings()["bucket"], "--key", key)
        except AWSProblem as error:
            if error.code in {"404", "NoSuchKey", "NotFound"}: return None
            raise

    def _public_thumbnail(self, key, original):
        try:
            return self._public(key)
        except ValueError:
            # Older buckets publish individual photos with ACLs rather than a bucket policy.
            # Mirror only that public-read grant onto our own derivative, never change the source.
            acl = self.command("s3api", "get-object-acl", "--bucket", self.settings()["bucket"], "--key", original)
            public = any(grant.get("Grantee", {}).get("URI") == "http://acs.amazonaws.com/groups/global/AllUsers"
                         and grant.get("Permission") in {"READ", "FULL_CONTROL"} for grant in acl.get("Grants", []))
            if not public:
                raise ValueError("The thumbnail is saved but cannot be opened by visitors. Allow public read for the website's _thumbnails folders in S3, then try again.")
            self.command("s3api", "put-object-acl", "--bucket", self.settings()["bucket"], "--key", key, "--acl", "public-read")
            return self._public(key)

    def prepare_images(self, data):
        keys = self._checked_keys(data)
        if any(Path(key).suffix.lower() not in KINDS["image"] or THUMBNAIL_FOLDER in key.split("/") for key in keys):
            raise ValueError("Choose original pictures from their S3 folder.")
        settings = self.settings()
        # Serialize writes so repeated clicks and concurrent local requests share the same work.
        with self.thumbnail_lock:
            folders = {key.rpartition("/")[0] + "/" for key in keys}
            pairs = {}
            for folder in sorted(folders): pairs.update(self._pairs(self._siblings(folder), settings["bucket"]))
            files = []
            for key in keys:
                pair = pairs.get(key)
                original = pair["full_key"] if pair else key
                if not original.startswith(settings["prefix"]): raise ValueError("Choose a picture inside the website folder.")
                self._public(original)
                if pair:
                    self._public(pair["small_key"])
                    files.append({"key": original, "url": pair["full_url"], "name": Path(original).name, "pair": pair, "thumbnail_status": "reused"})
                    continue
                if Path(original).suffix.lower() == ".svg":
                    files.append({"key": original, "url": self.public_url(original), "name": Path(original).name, "pair": None, "thumbnail_status": "vector"})
                    continue
                source = self._head(original)
                if not source or not source.get("ETag"): raise ValueError("This picture no longer exists in S3: " + original)
                small = self.thumbnail_key(original, source["ETag"])
                status = "reused"
                if self._head(small) is None:
                    if source.get("ContentLength", 0) > MAX_PHOTO_BYTES: raise ValueError("Choose a photo smaller than 50 MB: " + original)
                    with tempfile.TemporaryDirectory(prefix="site-photo-", dir=self.cache) as workspace:
                        download, thumbnail = Path(workspace) / "original", Path(workspace) / "thumbnail.webp"
                        self.command("s3api", "get-object", "--bucket", settings["bucket"], "--key", original, "--if-match", source["ETag"], str(download), timeout=120)
                        self.render_thumbnail(download, thumbnail)
                        metadata = {"site-manager-thumbnail": THUMBNAIL_RECIPE,
                                    "source-id": hashlib.sha256(original.encode()).hexdigest(), "source-etag": source["ETag"].strip('"')}
                        try:
                            self.command("s3api", "put-object", "--bucket", settings["bucket"], "--key", small, "--body", str(thumbnail),
                                         "--content-type", "image/webp", "--cache-control", "public, max-age=31536000, immutable",
                                         "--metadata", json.dumps(metadata), "--if-none-match", "*", timeout=120)
                            status = "created"
                        except AWSProblem as error:
                            if error.code not in {"PreconditionFailed", "412"} or self._head(small) is None: raise
                self._public_thumbnail(small, original)
                latest = self._head(original)
                if not latest or latest.get("ETag") != source["ETag"]:
                    raise ValueError("The original picture changed while its thumbnail was being prepared. Choose it again: " + original)
                pair = {"full_key": original, "small_key": small, "full_url": self.public_url(original), "small_url": self.public_url(small)}
                files.append({"key": original, "url": pair["full_url"], "name": Path(original).name, "pair": pair, "thumbnail_status": status})
            return {"files": files, "message": "Pictures are ready. Thumbnails are used in tiles; originals open in the image viewer."}

    def prepare_image_urls(self, data):
        """Resolve legacy plus-encoded S3 URLs; external and local images stay as supplied."""
        urls = data.get("urls", [])
        if not isinstance(urls, list) or not urls or len(urls) > 150 or any(not isinstance(url, str) for url in urls):
            raise ValueError("Choose between 1 and 150 image URLs.")
        settings = self.settings()
        mapping = {}
        for url in dict.fromkeys(urls):
            candidates = sorted(key for key in object_keys(url, settings["bucket"]) if key.startswith(settings["prefix"]))
            if not candidates or any(THUMBNAIL_FOLDER in key.split("/") for key in candidates): continue
            matches = [key for key in candidates if self._head(key) is not None]
            if len(matches) != 1:
                raise ValueError("This S3 image URL is missing or ambiguous. Choose the picture with Choose from S3 instead: " + url)
            mapping[url] = matches[0]
        if not mapping: return {"files": []}
        prepared = {file["key"]: file for file in self.prepare_images({"keys": list(dict.fromkeys(mapping.values()))})["files"]}
        # A legacy small image can resolve to its original; match by either key.
        for file in list(prepared.values()):
            if file.get("pair"): prepared[file["pair"]["small_key"]] = file
        return {"files": [{"input_url": url, **prepared[key]} for url, key in mapping.items()]}
