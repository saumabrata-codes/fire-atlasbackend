import unittest
from contextlib import nullcontext
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.workers.historical_backfill import (
    _eligible_quality, _plan, _resume_paused_run, _subtract_covered_ranges,
    _range_already_committed, process_one_chunk,
)
from app.ingestion.quality import eligible_detection


class HistoricalBackfillPlanTests(unittest.TestCase):
    def test_worker_does_not_touch_database_or_fetch_when_collection_is_disabled(self):
        with patch("app.workers.historical_backfill.get_settings", return_value=SimpleNamespace(
                firms_collection_enabled=False)), \
             patch("app.workers.historical_backfill.SessionLocal") as database:
            self.assertFalse(process_one_chunk("run-1"))
        database.assert_not_called()

    def test_quality_filter_drops_low_or_missing_confidence(self):
        self.assertTrue(_eligible_quality({"sensor": "MODIS", "confidence": "30"}))
        self.assertFalse(_eligible_quality({"sensor": "MODIS", "confidence": "29"}))
        self.assertTrue(_eligible_quality({"sensor": "VIIRS", "confidence": "n"}))
        self.assertFalse(_eligible_quality({"sensor": "VIIRS", "confidence": "l"}))
        self.assertFalse(_eligible_quality({"sensor": "VIIRS", "confidence": None}))

    def test_shared_quality_gate_requires_official_viirs_categories(self):
        self.assertTrue(eligible_detection({"sensor": "VIIRS", "confidence": "h"}))
        self.assertFalse(eligible_detection({"sensor": "VIIRS", "confidence": "82"}))
        self.assertTrue(eligible_detection({"sensor": "MODIS", "confidence": "50"}))
        self.assertFalse(eligible_detection({"sensor": "MODIS", "confidence": ""}))

    def test_plan_clips_to_nasa_availability(self):
        available = [
            {"data_id": "MODIS_SP", "min_date": "2000-11-01", "max_date": "2020-01-31"},
            {"data_id": "MODIS_NRT", "min_date": "2019-09-01", "max_date": "2020-03-01"},
            {"data_id": "VIIRS_SNPP_SP", "min_date": "2012-01-20", "max_date": "2020-01-31"},
        ]
        plans = _plan(available, ["MODIS", "VIIRS"], date(2000, 1, 1), date(2006, 12, 31))
        self.assertEqual(len(plans), 7)
        self.assertEqual(plans[0], {"sensor": "MODIS", "product": "MODIS_SP",
                                    "start": "2000-11-01", "end": "2000-12-31", "year": 2000})
        self.assertEqual(plans[-1]["start"], "2006-01-01")
        self.assertEqual(plans[-1]["end"], "2006-12-31")

    def test_nrt_starts_after_standard_record(self):
        available = [
            {"data_id": "MODIS_SP", "min_date": "2000-11-01", "max_date": "2020-01-31"},
            {"data_id": "MODIS_NRT", "min_date": "2019-09-01", "max_date": "2020-03-01"},
        ]
        plans = _plan(available, ["MODIS"], date(2019, 9, 1), date(2020, 3, 1))
        nrt = next(item for item in plans if item["product"] == "MODIS_NRT")
        self.assertEqual(nrt["start"], "2020-02-01")
        self.assertEqual(nrt["year"], 2020)

    def test_plan_orders_each_sensor_year_modis_before_viirs(self):
        available = [
            {"data_id": "MODIS_SP", "min_date": "2000-11-01", "max_date": "2013-12-31"},
            {"data_id": "VIIRS_SNPP_SP", "min_date": "2012-01-20", "max_date": "2013-12-31"},
        ]
        plans = _plan(available, ["VIIRS", "MODIS"], date(2012, 1, 1), date(2013, 12, 31))
        self.assertEqual([(p["year"], p["sensor"]) for p in plans], [
            (2012, "MODIS"), (2012, "VIIRS"), (2013, "MODIS"), (2013, "VIIRS"),
        ])

    def test_year_is_verified_before_worker_advances_to_next_sensor_year(self):
        run = SimpleNamespace(
            status="processing",
            products=[
                {"sensor": "MODIS", "year": 2000, "start": "2000-11-01", "end": "2000-12-31"},
                {"sensor": "VIIRS", "year": 2000, "start": "2000-12-01", "end": "2000-12-31"},
            ],
            product_index=0,
            cursor_date=date(2001, 1, 1),
            end_date=date(2000, 12, 31),
            area="world",
            sensors=["MODIS", "VIIRS"],
            chunks_completed=1,
            records_processed=10,
            run_type="backfill",
        )
        db = Mock()
        db.get.return_value = run
        call_order = Mock()
        with patch("app.workers.historical_backfill.SessionLocal", return_value=nullcontext(db)), \
             patch("app.workers.historical_backfill.get_settings", return_value=SimpleNamespace(firms_collection_enabled=True)), \
             patch("app.workers.historical_backfill.harmonize_sensor_year") as verify, \
             patch("app.workers.historical_backfill._save_run") as save:
            verify.return_value = {"verified": True}
            call_order.attach_mock(verify, "verify")
            call_order.attach_mock(save, "save")
            advanced = process_one_chunk("run-1")

        self.assertTrue(advanced)
        self.assertEqual(call_order.mock_calls, [
            unittest.mock.call.verify("MODIS", 2000),
            unittest.mock.call.save("run-1", product_index=1, cursor_date=date(2000, 12, 1)),
        ])

    def test_worker_finishes_other_products_in_year_before_verifying_it(self):
        run = SimpleNamespace(
            status="processing",
            products=[
                {"sensor": "MODIS", "year": 2000, "start": "2000-11-01", "end": "2000-12-31"},
                {"sensor": "MODIS", "year": 2000, "start": "2000-11-01", "end": "2000-12-31",
                 "product": "MODIS_NRT"},
            ],
            product_index=0,
            cursor_date=date(2001, 1, 1),
            end_date=date(2000, 12, 31),
            area="world",
            sensors=["MODIS", "VIIRS"],
            chunks_completed=1,
            records_processed=10,
            run_type="backfill",
        )
        db = Mock()
        db.get.return_value = run
        with patch("app.workers.historical_backfill.SessionLocal", return_value=nullcontext(db)), \
             patch("app.workers.historical_backfill.get_settings", return_value=SimpleNamespace(firms_collection_enabled=True)), \
             patch("app.workers.historical_backfill.harmonize_sensor_year") as verify, \
             patch("app.workers.historical_backfill._save_run") as save:
            advanced = process_one_chunk("run-1")

        self.assertTrue(advanced)
        verify.assert_not_called()
        save.assert_called_once_with("run-1", product_index=1, cursor_date=date(2000, 11, 1))

    def test_resume_replans_from_start_for_coverage_subtraction(self):
        products = [{"sensor": "MODIS", "year": 2012}, {"sensor": "VIIRS", "year": 2012}]
        run = SimpleNamespace(status="paused", products=products, product_index=1,
                              cursor_date=date(2012, 7, 1), start_date=date(2000, 1, 1),
                              last_error="temporary stop")
        _resume_paused_run(run)
        self.assertEqual(run.status, "queued")
        self.assertEqual(run.products, [])
        self.assertEqual(run.product_index, 0)
        self.assertEqual(run.cursor_date, date(2000, 1, 1))
        self.assertIsNone(run.last_error)

    def test_replanned_resume_subtracts_only_matching_product_coverage(self):
        available = [
            {"data_id": "MODIS_SP", "min_date": "2000-11-01", "max_date": "2002-12-31"},
            {"data_id": "VIIRS_SNPP_SP", "min_date": "2012-01-20", "max_date": "2012-12-31"},
        ]
        covered = [{"product": "MODIS_SP", "start": date(2000, 11, 1),
                    "end": date(2002, 4, 4)}]
        plans = _plan(available, ["MODIS", "VIIRS"], date(2000, 1, 1),
                      date(2012, 12, 31), covered)
        modis = [p for p in plans if p["sensor"] == "MODIS"]
        viirs = [p for p in plans if p["sensor"] == "VIIRS"]
        self.assertEqual(modis[0]["start"], "2002-04-05")
        self.assertEqual(modis[0]["year"], 2002)
        self.assertEqual(viirs[0]["start"], "2012-01-20")
        self.assertEqual([(p["year"], p["sensor"]) for p in plans],
                         sorted((p["year"], p["sensor"]) for p in plans))

    def test_coverage_subtraction_splits_missing_gaps(self):
        gaps = _subtract_covered_ranges(
            date(2020, 1, 1), date(2020, 1, 20),
            [(date(2020, 1, 5), date(2020, 1, 9)),
             (date(2020, 1, 15), date(2020, 1, 16))],
        )
        self.assertEqual(gaps, [
            (date(2020, 1, 1), date(2020, 1, 4)),
            (date(2020, 1, 10), date(2020, 1, 14)),
            (date(2020, 1, 17), date(2020, 1, 20)),
        ])

    def test_crash_recovery_skips_a_fully_committed_chunk(self):
        db = Mock()
        db.execute.return_value.all.return_value = [
            (date(2020, 1, 1), date(2020, 1, 5)),
        ]
        with patch("app.workers.historical_backfill.SessionLocal", return_value=nullcontext(db)):
            committed = _range_already_committed(
                "MODIS_SP", "historical", date(2020, 1, 1), date(2020, 1, 5)
            )
        self.assertTrue(committed)

    def test_crash_recovery_does_not_skip_a_partially_committed_chunk(self):
        db = Mock()
        db.execute.return_value.all.return_value = [
            (date(2020, 1, 2), date(2020, 1, 5)),
        ]
        with patch("app.workers.historical_backfill.SessionLocal", return_value=nullcontext(db)):
            committed = _range_already_committed(
                "MODIS_SP", "historical", date(2020, 1, 1), date(2020, 1, 5)
            )
        self.assertFalse(committed)


if __name__ == "__main__":
    unittest.main()
