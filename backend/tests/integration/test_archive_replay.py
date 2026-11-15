import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.ingestion.jobs.archive import preserve_source
from app.main import app


class ArchiveReplayTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.raw = self.root / "data" / "raw"
        self.raw.mkdir(parents=True)
        self.root_patch = patch("app.api.v1.endpoints.ingestion.ROOT", self.root)
        self.raw_patch = patch("app.api.v1.endpoints.ingestion.RAW_ROOT", self.raw)
        self.root_patch.start()
        self.raw_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.raw_patch.stop)
        self.addCleanup(self.temp.cleanup)

    def _archive(self):
        body = (
            "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,frp\n"
            "-1.1,-53.6,2026-11-13,1230,NOAA-21,VIIRS,82,4.2\n"
        )
        with patch("app.ingestion.jobs.archive.ROOT", self.root), patch("app.ingestion.jobs.archive.RAW_ROOT", self.raw):
            archive = preserve_source("VIIRS", "VIIRS_NOAA21_NRT", body, 1)
        return Path(archive["path"]).name, archive

    def test_archive_catalog_reports_checksum_status_without_exposing_local_paths(self):
        filename, archive = self._archive()
        response = self.client.get("/api/v1/ingestion/archives")
        self.assertEqual(response.status_code, 200)
        item = next(entry for entry in response.json()["archives"] if entry["file"] == filename)
        self.assertTrue(item["verified"])
        self.assertEqual(item["sha256"], archive["sha256"])
        self.assertNotIn("path", item)

    def test_replays_only_manifest_verified_csv(self):
        filename, archive = self._archive()
        source = Path(archive["path"])
        year, month = source.parent.parent.name, source.parent.name
        with patch("app.api.v1.endpoints.ingestion.persist_ingestion", return_value=("job-123", 1)) as persist:
            response = self.client.post(
                f"/api/v1/ingestion/archive/VIIRS/VIIRS_NOAA21_NRT/{year}/{month}/{filename}/replay"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["records_validated"], 1)
        self.assertEqual(response.json()["records_stored"], 1)
        self.assertEqual(response.json()["sha256"], archive["sha256"])
        self.assertEqual(persist.call_args.args[1:3], ("VIIRS", "VIIRS_NOAA21_NRT"))

    def test_rejects_changed_csv_before_database_write(self):
        filename, _ = self._archive()
        csv_path = self.raw / "viirs" / "viirs_noaa21_nrt"
        csv_path = next(csv_path.rglob(filename))
        year, month = csv_path.parent.parent.name, csv_path.parent.name
        csv_path.write_bytes(csv_path.read_bytes() + b"# tampered\n")
        with patch("app.api.v1.endpoints.ingestion.persist_ingestion") as persist:
            response = self.client.post(
                f"/api/v1/ingestion/archive/VIIRS/VIIRS_NOAA21_NRT/{year}/{month}/{filename}/replay"
            )
        self.assertEqual(response.status_code, 409)
        persist.assert_not_called()


if __name__ == "__main__":
    unittest.main()
