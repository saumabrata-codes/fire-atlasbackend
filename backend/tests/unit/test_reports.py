import re
import unittest

from app.reporting.observations import build_observation_report


class PdfReportTests(unittest.TestCase):
    def test_pdf_has_consistent_cross_reference_and_report_text(self):
        report = build_observation_report([
            {
                "id": "record-1", "sensor": "MODIS", "satellite": "TERRA",
                "product": "MODIS_NRT", "acq_datetime": "2026-11-12T12:30:00+00:00",
                "confidence": "high", "frp": 3.4,
            },
            {
                "id": "record-2", "sensor": "VIIRS", "satellite": "NOAA-21",
                "product": "VIIRS_NOAA21_NRT", "acq_datetime": "2026-11-12T12:35:00+00:00",
                "confidence": "82", "frp": 5.2,
            },
        ], "ALL", sample_mode=True)
        self.assertTrue(report.startswith(b"%PDF-1.4"))
        self.assertTrue(report.endswith(b"%%EOF\n"))
        startxref = int(re.search(rb"startxref\n(\d+)\n%%EOF", report).group(1))
        self.assertEqual(report[startxref:startxref + 5], b"xref\n")
        xref = report[startxref:].splitlines()
        count = int(xref[1].split()[1])
        for entry in xref[3:3 + count - 1]:
            offset = int(entry[:10])
            self.assertRegex(report[offset:offset + 10], rb"\d+ 0 obj")
        self.assertIn(b"/Count 1", report)
        self.assertIn(b"/Type /Font", report)
        for expected in ("MODIS", "VIIRS", "METHOD AND LIMITATIONS", "Demonstration fixtures"):
            self.assertIn(expected.encode("cp1252").hex().upper().encode("ascii"), report)


if __name__ == "__main__":
    unittest.main()
