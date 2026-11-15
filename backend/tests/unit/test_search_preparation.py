import unittest
from contextlib import nullcontext
from datetime import date
from unittest.mock import Mock, patch

from app.database.repositories.harmonization import prepare_date_range


class SearchPreparationTests(unittest.TestCase):
    def _database_with_covered_dates(self):
        db = Mock()
        bounds_result = Mock()
        bounds_result.one.return_value = (date(2020, 1, 1), date(2020, 1, 5))
        ranges_result = Mock()
        ranges_result.all.return_value = [(date(2020, 1, 1), date(2020, 1, 5))]
        db.execute.side_effect = [bounds_result, ranges_result]
        db.scalars.return_value.all.return_value = [17]
        return db

    def test_ready_database_coverage_is_returned_without_reprocessing(self):
        db = self._database_with_covered_dates()

        with patch("app.database.repositories.harmonization.SessionLocal",
                   return_value=nullcontext(db)), \
             patch("app.database.repositories.harmonization._pending_source_file_ids",
                   return_value=[]) as pending, \
             patch("app.database.repositories.harmonization.process_source_file") as process:
            result = prepare_date_range(
                date(2020, 1, 1), date(2020, 1, 5),
                bbox=(-123.0, 37.0, -122.0, 38.0), sensor="MODIS",
            )

        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["coverage_complete"])
        self.assertEqual(result["source_files_ready"], 1)
        self.assertEqual(result["records_added"], 0)
        pending.assert_called_once_with(
            db, limit=1, start=date(2020, 1, 1), end=date(2020, 1, 5),
            sensor="MODIS", bbox=(-123.0, 37.0, -122.0, 38.0),
        )
        process.assert_not_called()

    def test_pending_stored_file_is_processed_before_ready_result(self):
        db = self._database_with_covered_dates()
        with patch("app.database.repositories.harmonization.SessionLocal",
                   return_value=nullcontext(db)), \
             patch("app.database.repositories.harmonization._pending_source_file_ids",
                   return_value=[17]), \
             patch("app.database.repositories.harmonization.process_source_file",
                   return_value={"status": "completed", "records_processed": 21}) as process:
            result = prepare_date_range(
                date(2020, 1, 1), date(2020, 1, 5),
                bbox=(-123.0, 37.0, -122.0, 38.0), sensor="MODIS",
            )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["records_added"], 21)
        self.assertEqual(result["source_files_found"], 1)
        process.assert_called_once_with(17)


if __name__ == "__main__":
    unittest.main()
