import unittest
from datetime import date
from unittest.mock import Mock, patch

from app.database.repositories.harmonization import _refresh_year_analytics


class HarmonizationRepairTests(unittest.TestCase):
    def test_refreshes_only_derived_year_tables_from_existing_points(self):
        db = Mock()
        db.__enter__ = Mock(return_value=db)
        db.__exit__ = Mock(return_value=False)
        db.scalars.return_value.all.return_value = ["MODIS_NRT", "MODIS_SP"]
        with patch("app.database.repositories.harmonization.SessionLocal", return_value=db), \
             patch("app.database.repositories.harmonization._upsert_spatial_aggregates") as refresh:
            _refresh_year_analytics("MODIS", date(2020, 1, 1), date(2020, 12, 31))

        self.assertEqual(refresh.call_count, 2)
        self.assertEqual(refresh.call_args_list[0].args[1:],
                         ("MODIS", "MODIS_NRT", date(2020, 1, 1), date(2021, 1, 1)))
        self.assertEqual(refresh.call_args_list[1].args[1:],
                         ("MODIS", "MODIS_SP", date(2020, 1, 1), date(2021, 1, 1)))
        db.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
