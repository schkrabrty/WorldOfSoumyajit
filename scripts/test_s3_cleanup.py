#!/usr/bin/env python3
"""Test cleanup safeguards using local fixtures and mocked S3; never delete real objects."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import cleanup_s3


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        data = b"backup bytes"
        self.entry = {"key": "My Website related Stuffs/test.jpg", "size": len(data), "etag": '"abc"', "modified": "2026-01-01T00:00:00Z", "backup": "copy.bin", "sha256": hashlib.sha256(data).hexdigest()}
        (self.root / "copy.bin").write_bytes(data)
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps({"bucket": "worldofsoumyajit", "files": [self.entry]}))
        self.library = Mock()
        self.library.settings.return_value = {"bucket": "worldofsoumyajit"}
    def tearDown(self): self.temp.cleanup()
    def apply(self, candidates):
        with patch.object(cleanup_s3, "S3Library", return_value=self.library), patch.object(cleanup_s3, "create_report", return_value=({"candidates": candidates}, None)):
            return cleanup_s3.apply_cleanup(self.root, self.manifest, keep_documents=False)
    def test_delete_uses_a_conditional_request_for_the_exact_backed_up_key(self):
        result = self.apply([self.entry])
        self.assertEqual(len(result["deleted"]), 1)
        self.library.command.assert_called_once_with("s3api", "delete-object", "--bucket", "worldofsoumyajit", "--key", self.entry["key"], "--if-match", self.entry["etag"])
    def test_newly_referenced_or_missing_object_is_never_deleted(self):
        self.assertEqual(len(self.apply([])["skipped"]), 1)
        self.library.command.assert_not_called()
    def test_changed_remote_object_is_never_deleted(self):
        result = self.apply([{**self.entry, "modified": "2026-10-24T00:00:00Z"}])
        self.assertEqual(len(result["skipped"]), 1)
        self.library.command.assert_not_called()
    def test_changed_local_backup_aborts_before_any_deletion(self):
        (self.root / "copy.bin").write_bytes(b"tampered")
        with self.assertRaises(ValueError): self.apply([self.entry])
        self.library.command.assert_not_called()
    def test_wrong_bucket_aborts(self):
        self.library.settings.return_value = {"bucket": "another-bucket"}
        with self.assertRaises(ValueError): self.apply([self.entry])
        self.library.command.assert_not_called()


if __name__ == "__main__": unittest.main()
