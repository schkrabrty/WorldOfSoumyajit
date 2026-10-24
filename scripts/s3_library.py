"""Read-only S3 browsing and website-reference discovery for the local manager."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
from urllib.parse import quote, unquote, unquote_plus, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

DEFAULTS = {"bucket": "worldofsoumyajit", "region": "us-east-1", "prefix": "My Website related Stuffs/", "profile": "worldofsoumyajit"}
KINDS = {"image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg"}, "pdf": {".pdf"},
         "video": {".mp4", ".webm", ".mov"}, "audio": {".mp3", ".wav", ".ogg"}, "archive": {".zip", ".unitypackage"}}
URL_PATTERN = re.compile(r'''https?://[^\s<>"\\]+''')


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
            raise ValueError(result.stderr.strip()[-2500:] or "AWS could not complete the request. Choose Connect AWS and sign in again.")
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def status(self):
        try:
            executable = self.executable()
        except ValueError:
            executable = None
        return {**self.settings(), "available": bool(executable), "login_pending": bool(self.login_process and self.login_process.poll() is None)}

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

    def browse(self, prefix=None, kind="image", cursor=None):
        settings = self.settings()
        prefix = settings["prefix"] if prefix is None else prefix
        if not prefix.startswith(settings["prefix"]): raise ValueError("Choose a folder inside the configured website folder.")
        if kind not in {*KINDS, "all"}: raise ValueError("Choose a valid file type.")
        args = ["s3api", "list-objects-v2", "--bucket", settings["bucket"], "--prefix", prefix, "--delimiter", "/", "--max-keys", "500", "--no-paginate"]
        if cursor: args += ["--continuation-token", cursor]
        data = self.command(*args)
        objects = [item for item in data.get("Contents", []) if not item["Key"].endswith("/")]
        references = self.references(settings["bucket"])
        listing_keys = {item["Key"] for item in objects}
        folded = defaultdict(list)
        for key in listing_keys: folded[key.casefold()].append(key)
        pairs = {}
        for pair in references["pairs"]:
            full = object_keys(pair["full"], settings["bucket"]) & listing_keys
            small = object_keys(pair["small"], settings["bucket"]) & listing_keys
            if len(full) == 1 and len(small) == 1:
                full_key, small_key = next(iter(full)), next(iter(small))
                value = {"full_url": self.public_url(full_key), "small_url": self.public_url(small_key)}
                pairs[full_key] = pairs[small_key] = value
        # Suggest a pair only when both real objects are present in the listing.
        for item in objects:
            key = item["Key"]
            full_key = re.sub(r"_\d{2,5}[xX]\d{2,5}(?=\.[^./]+$)", "", key)
            if full_key not in listing_keys and len(folded[full_key.casefold()]) == 1:
                full_key = folded[full_key.casefold()][0]
            if full_key != key and full_key in listing_keys and key not in pairs:
                value = {"full_url": self.public_url(full_key), "small_url": self.public_url(key)}
                pairs[key] = value
                pairs.setdefault(full_key, value)
        files = []
        for item in objects:
            if kind != "all" and Path(item["Key"]).suffix.lower() not in KINDS[kind]: continue
            files.append({"key": item["Key"], "name": item["Key"].removeprefix(prefix), "url": self.public_url(item["Key"]),
                          "size": item["Size"], "modified": item.get("LastModified"), "pair": pairs.get(item["Key"])})
        return {"files": files, "folders": [item["Prefix"] for item in data.get("CommonPrefixes", [])], "prefix": prefix,
                "root": settings["prefix"], "bucket": settings["bucket"], "next": data.get("NextContinuationToken"), "kind": kind}

    def resolve(self, data):
        settings = self.settings()
        keys = list(dict.fromkeys(data.get("keys", [])))
        if not keys or len(keys) > 150: raise ValueError("Choose between 1 and 150 files.")
        for key in keys:
            if not isinstance(key, str) or not key.startswith(settings["prefix"]) or key.endswith("/"):
                raise ValueError("Choose a file inside the website's S3 folder.")
        def check(key):
            url = self.public_url(key)
            try:
                with urlopen(Request(url, method="HEAD"), timeout=20) as response:
                    if response.status != 200: raise ValueError("Not publicly readable")
            except Exception:
                raise ValueError("This file cannot be opened by website visitors. Check its S3 access: " + key)
            return {"key": key, "url": url}
        with ThreadPoolExecutor(max_workers=4) as pool: return {"files": list(pool.map(check, keys))}
