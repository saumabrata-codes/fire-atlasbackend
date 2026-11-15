import unittest
from contextlib import nullcontext
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.database.repositories.harmonization import _pending_source_file_ids, harmonize_sensor_year


class HarmonizationQueryTests(unittest.TestCase):
    def test_pending_query_limits_by_year_sensor_and_area(self):
        db = Mock()
        db.scalars.return_value = SimpleNamespace(all=lambda: [])
        result = _pending_source_file_ids(
            db, 20, start=date(2020, 1, 1), end=date(2020, 12, 31),
            sensor="VIIRS", bbox=(70.0, 5.0, 90.0, 30.0),
        )
        self.assertEqual(result, [])
        (statement,) = db.scalars.call_args.args
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("source_date_end >= '2020-01-01'", sql)
        self.assertIn("source_date_start <= '2020-12-31'", sql)
        self.assertIn("sensor = 'VIIRS'", sql)
        self.assertIn("longitude BETWEEN 70.0 AND 90.0", sql)
        self.assertIn("latitude BETWEEN 5.0 AND 30.0", sql)
        self.assertIn("LIMIT 20", sql)

    def test_year_gate_compares_aggregate_and_harmonized_values(self):
        db = Mock()
        db.scalars.return_value.all.return_value = []
        db.scalar.side_effect = [0, 0, 0]
        with patch("app.database.repositories.harmonization.SessionLocal",
                   return_value=nullcontext(db)), \
             patch("app.database.repositories.harmonization._pending_source_file_ids",
                   return_value=[]):
            result = harmonize_sensor_year("MODIS", 2020)

        self.assertTrue(result["verified"])
        raw_sql = str(db.scalar.call_args_list[0].args[0])
        aggregate_sql = str(db.scalar.call_args_list[1].args[0])
        activity_sql = str(db.scalar.call_args_list[2].args[0])
        self.assertIn("selected_files AS MATERIALIZED", raw_sql)
        self.assertIn("f.source_date_start >= :year_start", raw_sql)
        self.assertIn("WHERE f.in_year_raw_count IS NULL", raw_sql)
        self.assertIn("CROSS JOIN LATERAL", raw_sql)
        self.assertIn("r.acq_datetime >= :start_at", raw_sql)
        self.assertIn("expected_products", raw_sql)
        self.assertIn("GROUP BY h.product", raw_sql)
        self.assertIn("r.raw_count IS DISTINCT FROM h.point_count", raw_sql)
        self.assertIn("FULL OUTER JOIN actual", aggregate_sql)
        self.assertIn("frp_sum_mw", aggregate_sql)
        self.assertIn("processing_version", aggregate_sql)
        self.assertIn("JOIN selected_files f ON f.id = h.source_file_id", aggregate_sql)
        self.assertIn("FULL OUTER JOIN actual", activity_sql)
        self.assertIn("contributing_observations", activity_sql)
        self.assertIn("source_aggregate_count", activity_sql)
        self.assertIn("provenance->'products'", activity_sql)


if __name__ == "__main__":
    unittest.main()
