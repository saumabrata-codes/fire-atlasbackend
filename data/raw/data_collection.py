"""Collect NASA FIRMS MODIS and VIIRS fire detections by continent.

The output uses the existing FireAtlas/MODIS CSV column order. VIIRS thermal
fields are mapped to their equivalent common columns so both products can be
written to one consistently ordered CSV file.
"""

from __future__ import annotations

import csv
import io
import os
import time
import argparse
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# Continent bounding boxes in FIRMS order: west,south,east,north.
REGIONS = {
    "south-america": ("South_America", "-82,-56,-34,13"),
    "africa": ("Africa", "-18,-35,52,38"),
    "australia": ("Australia", "112,-44,154,-10"),
}
STANDARD_SOURCES = ("MODIS_SP", "VIIRS_SNPP_SP")
CHUNK_DAYS = 5

CSV_COLUMNS = (
    "latitude",
    "longitude",
    "brightness",
    "scan",
    "track",
    "acq_date",
    "acq_time",
    "satellite",
    "instrument",
    "confidence",
    "version",
    "bright_t31",
    "frp",
    "daynight",
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).resolve().parent
BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"


def load_env_value(name: str) -> str:
    """Read a setting from the environment or the repository's .env file."""
    if value := os.environ.get(name):
        return value.strip()

    env_file = REPOSITORY_ROOT / ".env"
    if not env_file.exists():
        raise FileNotFoundError(f"Environment file not found: {env_file}")

    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")

    raise RuntimeError(f"{name} is not configured in {env_file}")


def fetch_csv(
    api_key: str, source: str, region_area: str, first_day: date, days: int
) -> str:
    """Fetch one historical FIRMS Area API window with bounded retries."""
    url = f"{BASE_URL}/{api_key}/{source}/{region_area}/{days}/{first_day.isoformat()}"
    request = Request(url, headers={"User-Agent": "FireAtlas-data-collection/1.0"})

    for attempt in range(1, 5):
        try:
            with urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8-sig")
            if not body.strip() or body.lstrip().lower().startswith(("error", "invalid")):
                raise RuntimeError(f"FIRMS returned an invalid response for {source}")
            return body
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            if attempt == 4:
                raise RuntimeError(
                    f"FIRMS request failed for {source}, starting {first_day}"
                ) from exc
            time.sleep(2**attempt)

    raise AssertionError("unreachable")


def normalized_rows(text: str):
    """Yield rows in the established CSV order for either MODIS or VIIRS."""
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        # Keep MODIS names/order; map the equivalent VIIRS temperature fields.
        if not row.get("brightness"):
            row["brightness"] = row.get("bright_ti4", "")
        if not row.get("bright_t31"):
            row["bright_t31"] = row.get("bright_ti5", "")
        yield {column: row.get(column, "") for column in CSV_COLUMNS}


def source_windows(year: int, start_date: date, end_date: date):
    """Select science products, continuing with NRT where 2026 SP data ends."""
    if year == 2026:
        standard_end = date(2026, 8, 31)
        return (
            ("MODIS_SP", start_date, standard_end),
            ("MODIS_NRT", standard_end + timedelta(days=1), end_date),
            ("VIIRS_SNPP_SP", start_date, standard_end),
            ("VIIRS_SNPP_NRT", standard_end + timedelta(days=1), end_date),
        )
    return tuple((source, start_date, end_date) for source in STANDARD_SOURCES)


def collect_year(year: int, region_name: str, region_area: str) -> tuple[int, Path]:
    """Download one requested year and atomically create its regional CSV."""
    start_date = date(year, 1, 1)
    end_date = date(2026, 11, 15) if year == 2026 else date(year, 12, 31)
    output_file = OUTPUT_DIR / f"{region_name}_{start_date}_to_{end_date}.csv"
    if output_file.exists():
        raise FileExistsError(f"Refusing to overwrite existing dataset: {output_file}")

    api_key = load_env_value("FIRMS_API_KEY")
    if not api_key:
        raise RuntimeError("FIRMS_API_KEY is empty")

    temporary_file = output_file.with_suffix(".csv.part")
    total_rows = 0

    with temporary_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for source, window_start, window_end in source_windows(year, start_date, end_date):
            cursor = window_start
            while cursor <= window_end:
                days = min(CHUNK_DAYS, (window_end - cursor).days + 1)
                print(
                    f"Collecting {source}: {cursor} to {cursor + timedelta(days=days - 1)}",
                    flush=True,
                )
                text = fetch_csv(api_key, source, region_area, cursor, days)
                rows = list(normalized_rows(text))
                writer.writerows(rows)
                total_rows += len(rows)
                cursor += timedelta(days=days)

    temporary_file.replace(output_file)
    return total_rows, output_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect annual NASA FIRMS continent CSV files")
    parser.add_argument("--region", choices=REGIONS, required=True)
    parser.add_argument("years", nargs="+", type=int, help="calendar years to collect in order")
    args = parser.parse_args()

    region_name, region_area = REGIONS[args.region]
    for year in args.years:
        rows, output_file = collect_year(year, region_name, region_area)
        print(f"Saved {rows:,} observations to {output_file}", flush=True)


if __name__ == "__main__":
    main()
