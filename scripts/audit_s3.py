#!/usr/bin/env python3
"""Audit S3 against source pages, the live website, and document links. No deletions."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zlib
from s3_library import S3Library, collect_references, object_keys, URL_PATTERN


def document_links(data):
    """Read URI strings in ordinary PDF objects and Flate-compressed object streams."""
    chunks = [data]
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        try: chunks.append(zlib.decompress(match[1]))
        except zlib.error: pass
    links = set()
    for chunk in chunks:
        text = chunk.decode("latin1").replace(r"\(", "(").replace(r"\)", ")").replace(r"\/", "/")
        links.update(URL_PATTERN.findall(text))
        for match in re.finditer(rb"/URI\s*<([0-9A-Fa-f\s]+)>", chunk):
            try:
                raw = bytes.fromhex(match[1].decode())
                links.add(raw.decode("utf-16") if raw.startswith((b"\xfe\xff", b"\xff\xfe")) else raw.decode("utf-8"))
            except (ValueError, UnicodeError): pass
    return links


def create_report(root, live=True):
    root = Path(root).resolve()
    library = S3Library(root)
    settings = library.settings()
    folder = root / ".site-manager/s3-audit"
    folder.mkdir(parents=True, exist_ok=True)
    inventory = library.inventory()
    (folder / "inventory.json").write_text(json.dumps({"Contents": inventory}, indent=2) + "\n")
    versioning = library.command("s3api", "get-bucket-versioning", "--bucket", settings["bucket"])
    references = collect_references(root, live=live, bucket=settings["bucket"])
    if live and references["failures"]:
        (folder / "scan-errors.json").write_text(json.dumps(references["failures"], indent=2))
        raise ValueError("The live website could not be scanned completely. No cleanup list is ready; see scan-errors.json.")
    keys = references["keys"]
    # Retain dependencies reachable through PDFs linked from the website too.
    visited = set()
    while True:
        documents = [item for item in inventory if item["Key"].lower().endswith(".pdf") and item["Key"] in keys and item["Key"] not in visited]
        if not documents: break
        for item in documents:
            key = item["Key"];visited.add(key)
            target = folder / (hashlib.sha256(key.encode()).hexdigest() + ".pdf")
            library.command("s3api", "get-object", "--bucket", settings["bucket"], "--key", key, "--if-match", item["ETag"], str(target))
            for url in document_links(target.read_bytes()):
                for linked_key in object_keys(url, settings["bucket"]):
                    keys.setdefault(linked_key, []).append("document:" + key)
    protected, candidates, markers, outside = [], [], [], []
    for item in inventory:
        entry = {"key": item["Key"], "size": item["Size"], "etag": item["ETag"], "modified": item.get("LastModified")}
        if item["Key"].endswith("/"): markers.append(entry)
        elif item["Key"] in keys: protected.append({**entry, "references": sorted(set(keys[item["Key"]]))})
        elif not item["Key"].startswith(settings["prefix"]): outside.append(entry)
        else: candidates.append(entry)
    report = {"created": datetime.now(timezone.utc).isoformat(), "bucket": settings["bucket"], "prefix": settings["prefix"],
              "versioning": versioning.get("Status", "Disabled"), "source_files": references["scanned_files"], "live_pages": references["live_pages"],
              "documents_scanned": len(visited), "live_failures": references["failures"], "protected": protected, "candidates": candidates,
              "folder_markers": markers, "outside_website_folder": outside}
    report_path = folder / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    for filename, entries in [("deletion-candidates.csv", candidates), ("referenced-files.csv", protected)]:
        with (folder / filename).open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["S3 key", "Bytes", "Last modified", "ETag", "References"])
            for entry in entries:
                writer.writerow([entry["key"], entry["size"], entry["modified"], entry["etag"], "; ".join(entry.get("references", []))])
    return report, report_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-only", action="store_true", help="Skip live pages; this report cannot authorize cleanup")
    args = parser.parse_args()
    report, path = create_report(Path(__file__).resolve().parents[1], live=not args.source_only)
    print(json.dumps({"report": str(path), "referenced_files": len(report["protected"]), "candidates": len(report["candidates"]),
                      "candidate_bytes": sum(item["size"] for item in report["candidates"]), "live_pages": report["live_pages"],
                      "documents_scanned": report["documents_scanned"], "bucket_versioning": report["versioning"]}, indent=2))
