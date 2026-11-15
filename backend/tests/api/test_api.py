import unittest
from contextlib import nullcontext
from datetime import date, datetime, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.main import app


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patches = [
            patch("app.api.v1.endpoints.health.SessionLocal", return_value=nullcontext(None)),
            patch("app.api.v1.endpoints.observations.SessionLocal", return_value=nullcontext(None)),
            patch("app.api.v1.endpoints.observations.database_summary", return_value=None),
            patch("app.api.v1.endpoints.reports.SessionLocal", return_value=nullcontext(None)),
            patch("app.api.v1.endpoints.analytics.SessionLocal", return_value=nullcontext(None)),
            patch("app.api.v1.endpoints.ingestion.get_settings", return_value=SimpleNamespace(
                firms_api_key="", firms_base_url="https://example.test/area",
                firms_availability_url="https://example.test/availability",
                firms_collection_enabled=False,
            )),
            patch("app.application.observations.SessionLocal", return_value=nullcontext(None)),
            patch("app.application.observations.list_observations", return_value=[]),
            patch("app.application.observations.has_observations", return_value=False),
            patch("app.application.observations.has_raw_sources", return_value=False),
            patch("app.api.v1.endpoints.observations.prepare_date_range", return_value={"status": "ready"}),
            patch("app.api.v1.endpoints.analytics.prepare_date_range", return_value={"status": "ready"}),
            patch("app.api.v1.endpoints.reports.prepare_date_range", return_value={"status": "ready"}),
        ]
        for item in cls.patches:
            item.start()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        for item in reversed(cls.patches):
            item.stop()

    def test_health_endpoint(self):
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readiness_reports_postgis_unavailable_without_database(self):
        response = self.client.get("/api/v1/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ready"])
        self.assertFalse(response.json()["postgis_available"])

    def test_local_frontend_origins_can_call_api_and_read_report_headers(self):
        response = self.client.get("/api/v1/health", headers={"Origin": "http://127.0.0.1:5175"})
        self.assertEqual(response.headers["access-control-allow-origin"], "http://127.0.0.1:5175")
        self.assertIn("X-FireAtlas-Report-Tracked", response.headers["access-control-expose-headers"])

    def test_overview_keeps_sensor_counts_separate(self):
        response = self.client.get("/api/v1/overview/summary")
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["sample_mode"])
        self.assertEqual(data["modis_detections"] + data["viirs_detections"], data["total_detections"])
        self.assertIn("not unique fires", data["observations"])

    def test_map_endpoint_returns_geojson_points(self):
        response = self.client.get("/api/v1/map/hotspots?sensor=VIIRS")
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["count"], 5)
        self.assertTrue(all(feature["geometry"]["type"] == "Point" for feature in data["features"]))

    def test_map_endpoint_supports_date_and_bbox_filtering(self):
        response = self.client.get("/api/v1/map/hotspots?start=2026-11-12&end=2026-11-12&west=-35&south=-10&east=50&north=20")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 8)

    def test_map_endpoint_pages_large_result_sets(self):
        response = self.client.get("/api/v1/map/hotspots?limit=3&offset=3")
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["count"], 3)
        self.assertTrue(data["has_more"])
        self.assertEqual(data["next_offset"], 6)

    def test_empty_live_query_does_not_fall_back_to_unrelated_fixtures(self):
        with patch("app.application.observations.has_observations", return_value=True):
            response = self.client.get("/api/v1/map/hotspots?west=77&south=28&east=78&north=29")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["sample_mode"])
        self.assertEqual(response.json()["count"], 0)

    def test_map_endpoint_rejects_incomplete_bbox_and_reversed_dates(self):
        incomplete = self.client.get("/api/v1/map/hotspots?west=-35&south=-10")
        reversed_dates = self.client.get("/api/v1/map/hotspots?start=2026-11-13&end=2026-11-12")
        self.assertEqual(incomplete.status_code, 422)
        self.assertEqual(reversed_dates.status_code, 422)

    def test_grid_map_returns_paginated_precomputed_geojson_cells(self):
        cell = SimpleNamespace(
            cell_key="0.0:0.0", geometry='{"type":"Polygon","coordinates":[]}',
            modis=7, viirs=3, total=10,
        )
        database = SimpleNamespace(execute=Mock())
        database.execute.return_value.all.return_value = [cell, cell]
        with patch("app.api.v1.endpoints.observations.SessionLocal", return_value=nullcontext(database)):
            response = self.client.get(
                "/api/v1/map/grid?sensor=ALL&limit=1&offset=4&start=2026-01-01&end=2026-01-31"
                "&west=75&south=10&east=80&north=15"
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "sensor_aggregates")
        self.assertEqual(body["count"], 1)
        self.assertTrue(body["has_more"])
        self.assertEqual(body["next_offset"], 5)
        self.assertEqual(body["features"][0]["properties"]["total"], 10)
        self.assertEqual(body["features"][0]["geometry"]["type"], "Polygon")
        statement = database.execute.call_args.args[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("sensor_aggregates", sql)
        self.assertIn("ST_MakeEnvelope", sql)

    def test_status_does_not_mislabel_fixture_as_live_data(self):
        response = self.client.get("/api/v1/ingestion/status")
        self.assertEqual(response.status_code, 200)
        self.assertIn("not live NASA observations", response.json()["note"])

    def test_calendar_returns_observed_dates_without_zero_filling(self):
        daily = self.client.get("/api/v1/calendar/daily").json()
        monthly = self.client.get("/api/v1/calendar/monthly").json()
        self.assertEqual(len(daily["days"]), 1)
        self.assertEqual(daily["days"][0]["total"], 10)
        self.assertIn("not zero-filled", daily["coverage_note"])
        self.assertEqual(monthly["months"][0]["total"], 10)

    def test_region_calendar_forwards_date_sensor_and_bounds(self):
        from datetime import date
        result = {
            "sample_mode": False,
            "series": [{"period_start": "2001-01-01T00:00:00+00:00",
                        "modis": 9, "viirs": 0, "total": 9}],
            "coverage_note": "Missing periods are not zero-filled.",
            "source": "precomputed_sensor_aggregates", "covered_days": 5,
            "spatial_note": "Full intersecting grid cells are included.",
            "preprocessing": {"status": "ready"},
        }
        with patch("app.api.v1.endpoints.calendar.time_series", return_value=result) as query:
            response = self.client.get(
                "/api/v1/calendar/monthly?start=2001-01-01&end=2001-01-31&sensor=VIIRS"
                "&west=68&south=6&east=98&north=37"
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["months"][0]["month"], "2001-01")
        self.assertEqual(body["sensor"], "VIIRS")
        self.assertEqual(body["covered_days"], 5)
        self.assertEqual(body["preprocessing"]["status"], "ready")
        query.assert_called_once_with(start=date(2001, 1, 1), end=date(2001, 1, 31),
                                      period="month", sensor="VIIRS", west=68.0,
                                      south=6.0, east=98.0, north=37.0)

    def test_yearly_calendar_returns_only_observed_years(self):
        response = self.client.get("/api/v1/calendar/yearly")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["years"][0]["total"], 10)
        self.assertIn("not zero-filled", response.json()["coverage_note"])

    def test_harmonized_activity_endpoint_is_registered(self):
        response = self.client.get("/api/v1/analytics/harmonized?period=year")
        self.assertEqual(response.status_code, 503)

    def test_area_timeseries_reads_precomputed_grid_aggregates(self):
        from app.api.v1.endpoints.analytics import time_series
        database = SimpleNamespace(execute=Mock())
        database.execute.return_value.all.return_value = [SimpleNamespace(
            period_start=datetime(2026, 1, 1, tzinfo=timezone.utc), total=12,
            modis=7, viirs=5, frp_sum_mw=30.0, frp_mean_mw=2.5,
            frp_observation_count=12, covered_days=4,
        )]
        with patch("app.api.v1.endpoints.analytics.SessionLocal",
                   return_value=nullcontext(database)), \
             patch("app.api.v1.endpoints.analytics.prepare_date_range",
                   return_value={"status": "ready"}):
            result = time_series(date(2026, 1, 1), date(2026, 1, 31), "month", "ALL",
                                 68.0, 6.0, 98.0, 37.0)
        self.assertEqual(result["source"], "precomputed_sensor_aggregates")
        self.assertEqual(result["series"][0]["covered_days"], 4)
        self.assertIn("0.25-degree cells", result["spatial_note"])
        statement = database.execute.call_args.args[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("sensor_aggregates", sql)
        self.assertIn("spatial_grid_cells", sql)
        self.assertNotIn("hotspot_observations", sql)

    def test_harmonized_area_series_uses_daily_harmonized_grid(self):
        from app.api.v1.endpoints.analytics import harmonized_series
        database = SimpleNamespace(execute=Mock())
        database.execute.return_value.all.return_value = [SimpleNamespace(
            period_start=datetime(2001, 1, 1, tzinfo=timezone.utc), total=20,
            modis=20, viirs=0, grid_periods=8,
        )]
        with patch("app.api.v1.endpoints.analytics.SessionLocal",
                   return_value=nullcontext(database)), \
             patch("app.api.v1.endpoints.analytics.prepare_date_range",
                   return_value={"status": "ready"}):
            result = harmonized_series(date(2001, 1, 1), date(2001, 1, 31), "month",
                                       68.0, 6.0, 98.0, 37.0)
        self.assertEqual(result["source"], "harmonized_activity")
        self.assertFalse(result["cross_sensor_calibrated"])
        self.assertEqual(result["series"][0]["total"], 20)
        statement = database.execute.call_args.args[0]
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("harmonized_activity", sql)
        self.assertIn("spatial_grid_cells", sql)
        self.assertIn("period_level =", sql)

    def test_prepare_endpoint_accepts_area_and_date_and_returns_storage_status(self):
        with patch("app.api.v1.endpoints.analytics.prepare_date_range", return_value={
            "status": "ready", "source_files_found": 2, "source_files_ready": 2,
        }) as prepare:
            response = self.client.post("/api/v1/analytics/prepare", json={
                "start": "2026-11-12", "end": "2026-11-13", "sensor": "ALL",
                "west": 75, "south": 10, "east": 80, "north": 15,
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source_files_ready"], 2)
        prepare.assert_called_once()

    def test_worldview_imagery_link_includes_date_and_region(self):
        response = self.client.get(
            "/api/v1/imagery/worldview-link?day=2026-11-13&west=75&south=10&east=80&north=15"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "NASA Worldview / GIBS")
        self.assertIn("VIIRS_SNPP_CorrectedReflectance_TrueColor", response.json()["layers"])
        self.assertIn("2026-11-13", response.json()["browse_url"])
        images = response.json()["images"]
        self.assertEqual(len(images), 5)
        self.assertEqual({image["sensor"] for image in images}, {"MODIS", "VIIRS"})
        self.assertIn("VIIRS_NOAA21_CorrectedReflectance_TrueColor",
                      {image["layer"] for image in images})
        query = parse_qs(urlparse(images[0]["image_url"]).query)
        self.assertEqual(query["TIME"], ["2026-11-13"])
        self.assertEqual(query["BBOX"], ["75.0,10.0,80.0,15.0"])
        self.assertEqual(query["LAYERS"], [images[0]["layer"]])

    def test_region_summary_includes_language_model_fallback_and_imagery(self):
        buckets = [{"total": total, "modis": total, "viirs": 0,
                    "frp_sum_mw": 4.0, "frp_observation_count": 1}
                   for total in (1, 2, 3, 4, 5, 12)]
        data = {"series": buckets, "sample_mode": False, "data_available": True,
                "preprocessing": {"status": "ready"}}
        with patch("app.api.v1.endpoints.analytics.time_series", return_value=data), \
             patch("app.api.v1.endpoints.analytics.explain_with_llm", new_callable=AsyncMock,
                   return_value=(None, "summary_rules")):
            response = self.client.get(
                "/api/v1/analytics/region-summary?start=2026-01-01&end=2026-06-30&west=75&south=10&east=80&north=15"
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(len(body["summary_lines"]), 10)
        self.assertEqual(body["explanation_source"], "summary_rules")
        self.assertIn("worldview.earthdata.nasa.gov", body["imagery"]["browse_url"])
        self.assertEqual(len(body["imagery"]["images"]), 5)

    def test_region_summary_returns_configured_language_model_explanation(self):
        data = {"series": [], "sample_mode": False, "data_available": False,
                "preprocessing": None}
        with patch("app.api.v1.endpoints.analytics.time_series", return_value=data), \
             patch("app.api.v1.endpoints.analytics.explain_with_llm", new_callable=AsyncMock,
                   return_value=("Stored detections are sparse.", "test-model")):
            response = self.client.get("/api/v1/analytics/region-summary?sensor=VIIRS")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["explanation"], "Stored detections are sparse.")
        self.assertEqual(response.json()["explanation_source"], "test-model")

    def test_region_question_is_answered_from_the_requested_stored_analytics(self):
        data = {"series": [{"period_start": "2026-01-01T00:00:00+00:00", "total": 4,
                            "modis": 4, "viirs": 0, "frp_sum_mw": 6.0,
                            "frp_observation_count": 2}],
                "sample_mode": False, "data_available": True,
                "preprocessing": {"status": "ready"},
                "spatial_note": "Chart uses stored grid aggregates."}
        with patch("app.api.v1.endpoints.analytics.time_series", return_value=data) as series, \
             patch("app.api.v1.endpoints.analytics.explain_with_llm", new_callable=AsyncMock,
                   return_value=("The selected data contains four MODIS detections.", "test-model")) as llm:
            response = self.client.post("/api/v1/analytics/explain", json={
                "question": "What does the chart show?",
                "start": "2026-01-01", "end": "2026-01-31", "sensor": "MODIS",
                "west": 75, "south": 10, "east": 80, "north": 15,
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["explanation_source"], "test-model")
        self.assertEqual(response.json()["explanation"], "The selected data contains four MODIS detections.")
        series.assert_called_once_with(
            date(2026, 1, 1), date(2026, 1, 31), "month", "MODIS", 75.0, 10.0, 80.0, 15.0
        )
        llm.assert_awaited_once()

    def test_raw_route_builds_sensor_quality_filter_query(self):
        database = SimpleNamespace(execute=Mock())
        database.execute.return_value.all.return_value = []
        with patch("app.api.v1.endpoints.raw.SessionLocal", return_value=nullcontext(database)):
            response = self.client.get("/api/v1/raw/hotspots?start=2026-11-12&end=2026-11-13")
        self.assertEqual(response.status_code, 200)
        query = database.execute.call_args.args[0]
        sql = str(query.compile(dialect=postgresql.dialect()))
        self.assertIn("raw_hotspots.source_fields", sql)
        self.assertIn("source_fields ->>", sql)
        self.assertIn(" >= ", sql)

    def test_sensor_comparison_keeps_confidence_labels_separate(self):
        data = self.client.get("/api/v1/sensors/comparison").json()
        self.assertEqual(data["sensors"]["modis"]["detections"], 5)
        self.assertEqual(data["sensors"]["viirs"]["detections"], 5)
        self.assertIn("not assumed equivalent", data["method_note"])

    def test_anomaly_endpoint_refuses_to_infer_from_inadequate_baseline(self):
        data = self.client.get("/api/v1/anomalies/summary").json()
        self.assertFalse(data["available"])
        self.assertFalse(data["formal_anomaly"])
        self.assertTrue(data["missing_is_zero"] is False)

    def test_anomaly_endpoint_uses_requested_sensor_area_and_consecutive_months(self):
        from datetime import date
        series = [{
            "period_start": f"2026-{month:02d}-01T00:00:00+00:00",
            "total": value, "modis": 0, "viirs": value,
            "frp_sum_mw": None, "frp_observation_count": 0,
        } for month, value in enumerate([2, 3, 4, 6, 8, 18], start=1)]
        with patch("app.api.v1.endpoints.anomalies.time_series", return_value={
            "series": series, "sample_mode": False, "data_available": True,
        }) as query:
            response = self.client.get(
                "/api/v1/anomalies/summary?start=2026-01-01&end=2026-06-30&sensor=VIIRS"
                "&west=70&south=5&east=90&north=30"
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["available"])
        self.assertFalse(body["formal_anomaly"])
        self.assertIn("potential spike", body["result"])
        query.assert_called_once_with(date(2026, 1, 1), date(2026, 6, 30), "month",
                                      "VIIRS", 70.0, 5.0, 90.0, 30.0)

    def test_anomaly_endpoint_suppresses_comparison_across_missing_months(self):
        series = [{
            "period_start": f"2026-{month:02d}-01T00:00:00+00:00",
            "total": value, "modis": value, "viirs": 0,
        } for month, value in zip([1, 2, 4, 5, 6, 7], [2, 3, 4, 6, 8, 18])]
        with patch("app.api.v1.endpoints.anomalies.time_series", return_value={
            "series": series, "sample_mode": False, "data_available": True,
        }):
            response = self.client.get("/api/v1/anomalies/summary?sensor=MODIS")
        self.assertFalse(response.json()["available"])
        self.assertIn("missing months break", response.json()["result"])

    def test_csv_report_is_downloadable(self):
        response = self.client.get("/api/v1/reports/observations.csv?sensor=MODIS")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/csv; charset=utf-8")
        self.assertEqual(len(response.text.splitlines()), 6)

    def test_csv_report_applies_sensor_date_and_bounding_box_filters(self):
        response = self.client.get(
            "/api/v1/reports/observations.csv?sensor=MODIS&start=2026-11-12&end=2026-11-12&west=29.3&south=-3.6&east=29.5&north=-3.3"
        )
        self.assertEqual(response.status_code, 200)
        rows = response.text.splitlines()
        self.assertEqual(len(rows), 2)
        self.assertIn("TERRA", rows[1])

    def test_summary_pdf_report_is_downloadable_and_labeled_as_sample(self):
        archive = {"path": "data/reports/test.pdf", "sha256": "a" * 64, "file_size": 100}
        with patch("app.api.v1.endpoints.reports.archive_report", return_value=archive):
            response = self.client.get("/api/v1/reports/summary.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-1.4"))
        self.assertEqual(response.headers["x-fireatlas-report-sample-mode"], "true")
        self.assertEqual(response.headers["x-fireatlas-report-tracked"], "false")

    def test_live_ingestion_requires_backend_map_key(self):
        with patch("app.api.v1.endpoints.ingestion.get_settings", return_value=SimpleNamespace(
                firms_collection_enabled=True, firms_api_key="")):
            response = self.client.post("/api/v1/ingestion/sample/MODIS")
        self.assertEqual(response.status_code, 503)
        self.assertIn("FIRMS_API_KEY", response.json()["detail"])

    def test_firms_collection_is_paused_by_default(self):
        response = self.client.post("/api/v1/ingestion/sample/MODIS?west=-10&south=-10&east=10&north=10")
        self.assertEqual(response.status_code, 409)
        self.assertIn("paused until frontend acceptance", response.json()["detail"])

    def test_historical_backfill_cannot_be_queued_while_collection_is_paused(self):
        response = self.client.post("/api/v1/ingestion/backfills", json={
            "start_date": "2000-01-01", "end_date": "2000-12-31",
            "sensors": ["MODIS"], "area": "world",
        })
        self.assertEqual(response.status_code, 409)
        self.assertIn("paused until frontend acceptance", response.json()["detail"])

    def test_availability_requires_backend_map_key(self):
        response = self.client.get("/api/v1/ingestion/availability")
        self.assertEqual(response.status_code, 503)
        self.assertIn("FIRMS_API_KEY", response.json()["detail"])

    def test_area_request_window_cannot_exceed_five_days(self):
        response = self.client.post("/api/v1/ingestion/sample/VIIRS?day_range=6&west=-10&south=-10&east=10&north=10")
        self.assertEqual(response.status_code, 422)

    def test_viirs_ingestion_uses_newest_available_nrt_source(self):
        csv_text = "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,frp\n1,2,2026-11-12,1230,NOAA-21,VIIRS,82,4.2\n"
        sources = [
            {"data_id": "VIIRS_SNPP_NRT", "max_date": "2026-11-02"},
            {"data_id": "VIIRS_NOAA20_NRT", "max_date": "2026-11-10"},
            {"data_id": "VIIRS_NOAA21_NRT", "max_date": "2026-11-12"},
        ]
        archive = {"path": "data/raw/viirs/sample.csv", "sha256": "abc123"}
        with patch("app.api.v1.endpoints.ingestion.get_settings", return_value=SimpleNamespace(
                 firms_collection_enabled=True, firms_api_key="test-key", firms_base_url="https://example.test/area",
                 firms_availability_url="https://example.test/availability")), \
             patch("app.api.v1.endpoints.ingestion.FirmsClient.fetch_availability", new_callable=AsyncMock, return_value=sources), \
             patch("app.api.v1.endpoints.ingestion.FirmsClient.fetch_area", new_callable=AsyncMock, return_value=csv_text) as fetch_area, \
             patch("app.api.v1.endpoints.ingestion.preserve_source", return_value=archive), \
             patch("app.api.v1.endpoints.ingestion.persist_ingestion", return_value=("job-123", 1)):
            response = self.client.post("/api/v1/ingestion/sample/VIIRS?west=-10&south=-10&east=10&north=10")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "VIIRS_NOAA21_NRT")
        self.assertTrue(response.json()["stored"])
        self.assertEqual(response.json()["job_id"], "job-123")
        self.assertEqual(response.json()["records_validated"], 1)
        self.assertEqual(response.json()["area"], "-10.0,-10.0,10.0,10.0")
        fetch_area.assert_awaited_once_with("VIIRS_NOAA21_NRT", "-10.0,-10.0,10.0,10.0", 1)

    def test_live_sample_requires_a_bounded_area(self):
        with patch("app.api.v1.endpoints.ingestion.get_settings") as settings:
            settings.return_value.firms_collection_enabled = True
            settings.return_value.firms_api_key = "test-key"
            settings.return_value.firms_base_url = "https://example.test/area"
            settings.return_value.firms_availability_url = "https://example.test/availability"
            response = self.client.post("/api/v1/ingestion/sample/MODIS")
        self.assertEqual(response.status_code, 422)
        self.assertIn("study-area bounding box", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
