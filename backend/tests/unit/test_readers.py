import unittest

from app.ingestion.readers.firms_csv import parse_firms_csv


class FirmsReaderTests(unittest.TestCase):
    def test_normalizes_modis_time_and_preserves_confidence(self):
        csv_text = "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,frp\n10,20,2026-11-12,530,TERRA,MODIS,nominal,12.5\n"
        row = parse_firms_csv(csv_text, "MODIS", "MCD14DL", "original.csv")[0]
        self.assertEqual(row["acq_datetime"], "2026-11-12T05:30:00+00:00")
        self.assertEqual(row["confidence"], "nominal")
        self.assertEqual(row["source_file"], "original.csv")

    def test_rejects_invalid_coordinates_and_keeps_viirs_numeric_confidence(self):
        csv_text = "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,frp\n95,20,2026-11-12,1200,NOAA-20,VIIRS,78,4.2\n-10,40,2026-11-12,1200,NOAA-20,VIIRS,78,4.2\n"
        rows = parse_firms_csv(csv_text, "VIIRS", "VIIRS_NOAA20_NRT", "viirs.csv")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["confidence"], "78")
        self.assertEqual(rows[0]["sensor"], "VIIRS")

    def test_skips_rows_without_a_valid_time(self):
        csv_text = "latitude,longitude,acq_date,acq_time\n0,0,not-a-date,\n"
        self.assertEqual(parse_firms_csv(csv_text, "MODIS", "test", "x.csv"), [])

    def test_identity_is_stable_if_quality_values_are_revised(self):
        row = "1,2,2026-11-12,1230,NOAA-20,VIIRS,82,4.2"
        header = "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,frp\n"
        first = parse_firms_csv(header + row + "\n", "VIIRS", "VIIRS_SNPP_NRT", "a.csv")[0]
        revised = parse_firms_csv(header + row.replace(",82,4.2", ",high,5.1") + "\n", "VIIRS", "VIIRS_SNPP_NRT", "b.csv")[0]
        self.assertEqual(first["id"], revised["id"])


if __name__ == "__main__":
    unittest.main()
