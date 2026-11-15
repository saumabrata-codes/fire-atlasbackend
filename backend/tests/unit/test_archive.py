import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.ingestion.jobs.archive import preserve_source


class RawArchiveTests(unittest.TestCase):
    def test_preserves_original_csv_and_checksum_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("app.ingestion.jobs.archive.RAW_ROOT", root), patch("app.ingestion.jobs.archive.ROOT", root):
                body = "latitude,longitude\n1,2\n"
                result = preserve_source("MODIS", "MODIS_NRT", body, 1)
                saved = root / result["path"]
                manifest = saved.with_suffix(".manifest.json")
                self.assertEqual(saved.read_text(encoding="utf-8"), body)
                self.assertEqual(hashlib.sha256(saved.read_bytes()).hexdigest(), result["sha256"])
                self.assertEqual(saved.stat().st_size, result["file_size"])
                self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["sha256"], result["sha256"])


if __name__ == "__main__":
    unittest.main()
