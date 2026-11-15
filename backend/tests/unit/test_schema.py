import unittest

from app.database.base import Base
from app.database import models as _models  # noqa: F401


class SchemaFoundationTests(unittest.TestCase):
    def test_research_analytics_entities_are_registered(self):
        expected = {
            "source_products", "source_files", "ingestion_jobs", "backfill_runs",
            "raw_hotspots", "hotspot_observations",
            "geographic_regions", "spatial_grid_cells", "sensor_aggregates",
            "harmonization_models", "harmonized_activity", "historical_baselines",
            "anomaly_results", "report_jobs",
        }
        self.assertTrue(expected.issubset(Base.metadata.tables))
        self.assertIn("raw_payload", Base.metadata.tables["source_files"].columns)

    def test_spatial_entities_use_postgis_geometry(self):
        for table_name in ("hotspot_observations", "geographic_regions", "spatial_grid_cells"):
            table = Base.metadata.tables[table_name]
            self.assertIn("geom", table.columns)
            self.assertEqual(table.columns["geom"].type.srid, 4326)


if __name__ == "__main__":
    unittest.main()
