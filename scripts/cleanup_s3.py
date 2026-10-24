#!/usr/bin/env python3
"""One-time, backed-up S3 cleanup. The website manager never invokes this tool."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from audit_s3 import create_report
from s3_library import S3Library


def backup_candidates(root, report_path):
    root, report_path = Path(root), Path(report_path)
    report = json.loads(report_path.read_text())
    library = S3Library(root)
    folder = report_path.parent / "backup"
    folder.mkdir(exist_ok=True)
    def backup(entry):
        name = hashlib.sha256(entry["key"].encode()).hexdigest() + ".bin"
        path = folder / name
        metadata = library.command("s3api", "get-object", "--bucket", report["bucket"], "--key", entry["key"], "--if-match", entry["etag"], str(path), timeout=120)
        data = path.read_bytes()
        if len(data) != entry["size"] or metadata.get("ETag") != entry["etag"]:
            raise ValueError("Backup differs from the audited object: " + entry["key"])
        etag = entry["etag"].strip('"')
        if re.fullmatch(r"[a-f0-9]{32}", etag) and metadata.get("ServerSideEncryption") in {None, "AES256"}:
            if hashlib.md5(data, usedforsecurity=False).hexdigest() != etag:
                raise ValueError("Backup MD5 verification failed: " + entry["key"])
        acl = library.command("s3api", "get-object-acl", "--bucket", report["bucket"], "--key", entry["key"])
        return {**entry, "backup": name, "sha256": hashlib.sha256(data).hexdigest(), "metadata": metadata, "acl": acl}
    with ThreadPoolExecutor(max_workers=4) as pool:
        entries = list(pool.map(backup, report["candidates"]))
    manifest = {"created": datetime.now(timezone.utc).isoformat(), "bucket": report["bucket"],
                "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(), "files": entries}
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return path


def apply_cleanup(root, backup_path, keep_documents):
    root, backup_path = Path(root), Path(backup_path)
    backup = json.loads(backup_path.read_text())
    library = S3Library(root)
    if backup["bucket"] != library.settings()["bucket"]:
        raise ValueError("The configured bucket differs from the backup.")
    # Re-scan both source and deployed pages immediately before deletion.
    current, _ = create_report(root, live=True)
    available = {entry["key"]: entry for entry in current["candidates"]}
    selected = [entry for entry in backup["files"] if not keep_documents or not entry["key"].lower().endswith(".pdf")]
    result = {"created": datetime.now(timezone.utc).isoformat(), "bucket": backup["bucket"], "deleted": [], "skipped": [], "errors": []}
    journal = backup_path.parent / "deletion-results.json"
    # Validate all local copies first, before issuing any delete request.
    for entry in selected:
        path = backup_path.parent / entry["backup"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("The verified backup is missing or changed: " + entry["key"])
    for entry in selected:
        found = available.get(entry["key"])
        if not found or found["etag"] != entry["etag"] or found["size"] != entry["size"] or found["modified"] != entry["modified"]:
            result["skipped"].append({"key": entry["key"], "reason": "Now referenced, absent, or changed since the audit"})
        else:
            try:
                library.command("s3api", "delete-object", "--bucket", backup["bucket"], "--key", entry["key"], "--if-match", entry["etag"])
                result["deleted"].append({"key": entry["key"], "size": entry["size"], "sha256": entry["sha256"]})
            except Exception as error:
                result["errors"].append({"key": entry["key"], "error": str(error)})
        journal.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def restore(root, backup_path, key):
    library = S3Library(root)
    manifest = json.loads(Path(backup_path).read_text())
    entry = next(item for item in manifest["files"] if item["key"] == key)
    path = Path(backup_path).parent / entry["backup"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise ValueError("The backup checksum does not match.")
    args = ["s3api", "put-object", "--bucket", manifest["bucket"], "--key", key, "--body", str(path), "--if-none-match", "*"]
    metadata = entry["metadata"]
    for name, flag in [("ContentType", "--content-type"), ("CacheControl", "--cache-control"), ("ContentDisposition", "--content-disposition"), ("ContentEncoding", "--content-encoding")]:
        if metadata.get(name): args += [flag, metadata[name]]
    if metadata.get("Metadata"): args += ["--metadata", json.dumps(metadata["Metadata"])]
    library.command(*args)
    grants = entry.get("acl", {}).get("Grants", [])
    if any(grant.get("Grantee", {}).get("URI") == "http://acs.amazonaws.com/groups/global/AllUsers" and grant.get("Permission") == "READ" for grant in grants):
        library.command("s3api", "put-object-acl", "--bucket", manifest["bucket"], "--key", key, "--acl", "public-read")
    return {"restored": key}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "delete-images", "delete-all", "restore"])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--key")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report_path = root / ".site-manager/s3-audit/report.json"
    if args.action == "backup":
        path = backup_candidates(root, report_path)
        print(json.dumps({"backup_manifest": str(path), "verified_files": len(json.loads(path.read_text())["files"])}))
    elif args.action == "restore":
        if not args.manifest or not args.key: parser.error("restore requires --manifest and --key")
        print(json.dumps(restore(root, args.manifest, args.key)))
    else:
        if not args.manifest: parser.error("deletion requires the verified --manifest and an explicit delete action")
        result = apply_cleanup(root, args.manifest, keep_documents=args.action == "delete-images")
        print(json.dumps({"deleted_files": len(result["deleted"]), "deleted_bytes": sum(item["size"] for item in result["deleted"]),
                          "skipped": result["skipped"], "errors": result["errors"]}, indent=2))
