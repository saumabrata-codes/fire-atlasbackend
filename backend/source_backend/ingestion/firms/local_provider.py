
import calendar
import csv
from datetime import date
from pathlib import Path
from typing import Iterator

from .models import FireObservation, ObservationValidationError


class RegionalCSVProvider:
    """Stream and normalize local regional FIRMS archives."""

    def __init__(self, data_dir=None):
        # local_provider.py -> firms -> ingestion -> app -> backend -> repo
        self.data_dir = (
            Path(data_dir)
            if data_dir is not None
            else Path(__file__).resolve().parents[4] / "data" / "regional"
        )

        self.report = {
            "files_scanned": 0,
            "rows_scanned": 0,
            "records_returned": 0,
            "invalid_rows": 0,
            "errors": [],
        }

    def _files(self, start_date: date, end_date: date):
        """Yield CSV files whose year/month can overlap the requested range."""

        month_names = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }

        years = {
            str(year)
            for year in range(start_date.year, end_date.year + 1)
        }

        for path in sorted(self.data_dir.rglob("*.csv")):
            if path.relative_to(self.data_dir).parts[0] not in {"asia_firms", "north_america"}:
                continue
            parts = [part.lower() for part in path.parts]
            name = path.name.lower()

            # Skip files that do not appear to belong to the requested years.
            if not any(
                year in parts or year in name
                for year in years
            ):
                continue

            # Restrict monthly archives to months overlapping the date range.
            month = month_names.get(path.stem.lower())

            if month is not None:
                year_dirs = [
                    part
                    for part in path.parts
                    if part.isdigit() and len(part) == 4
                ]

                if year_dirs:
                    year = int(year_dirs[-1])

                    if not start_date.year <= year <= end_date.year:
                        continue

                    month_start = date(year, month, 1)
                    month_end = date(
                        year,
                        month,
                        calendar.monthrange(year, month)[1],
                    )

                    if not (
                        month_start <= end_date
                        and month_end >= start_date
                    ):
                        continue

            yield path

    @staticmethod
    def _region(path: Path) -> str:
        text = str(path).lower()

        if "asia_firms" in text:
            return "Asia"
        if "north_america" in text:
            return "North America"
        if "south_america" in text:
            return "South America"
        if "europe" in text:
            return "Europe"

        return "Unknown"

    def iter_observations(
        self,
        start_date: date,
        end_date: date,
        bbox=None,
        sensors=None,
    ) -> Iterator[FireObservation]:
        """Stream validated observations from regional CSV archives."""

        if start_date > end_date:
            raise ValueError("start_date cannot be after end_date")

        selected_sensors = {
            str(sensor).strip().upper()
            for sensor in (sensors or ["MODIS", "VIIRS"])
        }

        if (
            not selected_sensors
            or not selected_sensors.issubset({"MODIS", "VIIRS"})
        ):
            raise ValueError("Sensors must be MODIS and/or VIIRS")

        if bbox is not None:
            if len(bbox) != 4:
                raise ValueError(
                    "Bounding box must contain west, south, east, north"
                )

            west, south, east, north = bbox

            if (
                west > east
                or south > north
                or west < -180
                or east > 180
                or south < -90
                or north > 90
            ):
                raise ValueError("Invalid bounding box")

        self.report = {
            "files_scanned": 0,
            "rows_scanned": 0,
            "records_returned": 0,
            "invalid_rows": 0,
            "errors": [],
        }

        for path in self._files(start_date, end_date):
            self.report["files_scanned"] += 1
            region = self._region(path)

            try:
                with path.open(
                    "r",
                    encoding="utf-8-sig",
                    newline="",
                ) as handle:
                    reader = csv.DictReader(handle)

                    if not reader.fieldnames:
                        self.report["invalid_rows"] += 1
                        continue

                    for row in reader:
                        self.report["rows_scanned"] += 1

                        try:
                            # Support normalized and original FIRMS schemas.
                            acquisition_date = (
                                row.get("acquisition_date")
                                or row.get("acq_date")
                            )

                            if not acquisition_date:
                                raise ValueError(
                                    "Missing acquisition date"
                                )

                            observed_date = date.fromisoformat(
                                acquisition_date.strip()
                            )

                            if not start_date <= observed_date <= end_date:
                                continue

                            instrument = (
                                row.get("instrument") or ""
                            ).strip().upper()

                            if instrument not in selected_sensors:
                                continue

                            normalized = dict(row)

                            normalized["acquisition_date"] = (
                                observed_date.isoformat()
                            )

                            normalized["acquisition_time"] = (
                                row.get("acquisition_time")
                                or row.get("acq_time")
                            )

                            # Preserve the original dataset/product label.
                            # For raw archives without one, use a clearly
                            # labelled local archive identifier.
                            original_source = (
                                row.get("source_dataset") or ""
                            ).strip()

                            normalized["source_dataset"] = (
                                original_source
                                or (
                                    path.stem.split("_20", 1)[0]
                                    if "_20" in path.stem
                                    else f"local_archive:{region}:{path.stem}"
                                )
                            )

                            # Preserve archive provenance independently.
                            normalized["raw_properties"] = {
                                **row,
                                "_archive_region": region,
                                "_archive_file": path.name,
                            }

                            observation = (
                                FireObservation.from_processed_row(
                                    normalized
                                )
                            )

                            if bbox is not None:
                                west, south, east, north = bbox

                                if not (
                                    west <= observation.longitude <= east
                                    and south <= observation.latitude <= north
                                ):
                                    continue

                            self.report["records_returned"] += 1
                            yield observation

                        except (
                            ValueError,
                            TypeError,
                            KeyError,
                            ObservationValidationError,
                        ) as error:
                            self.report["invalid_rows"] += 1

                            if len(self.report["errors"]) < 20:
                                self.report["errors"].append({
                                    "file": path.name,
                                    "error": str(error),
                                })

            except (OSError, csv.Error) as error:
                self.report["invalid_rows"] += 1

                if len(self.report["errors"]) < 20:
                    self.report["errors"].append({
                        "file": str(path),
                        "error": str(error),
                    })

    def fetch_historical_data(
        self,
        start_date: date,
        end_date: date,
        bbox=None,
        sensors=None,
    ):
        """Return observations as a list.

        Use iter_observations() for large datasets to avoid loading
        all matching observations into memory.
        """
        return list(
            self.iter_observations(
                start_date=start_date,
                end_date=end_date,
                bbox=bbox,
                sensors=sensors,
            )
        )

    def get_report(self):
        """Return a copy of the latest scan report."""
        return {
            **self.report,
            "errors": list(self.report["errors"]),
        }
