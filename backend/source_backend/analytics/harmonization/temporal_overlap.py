from collections import defaultdict
from typing import Any, Iterable

SUPPORTED_SENSORS = {"MODIS", "VIIRS"}


def parse_acquisition_time(value: Any) -> int:
    """Parse FIRMS HHMM acquisition time and return minutes after midnight."""
    raw = str(value).strip()

    if not raw or not raw.isdigit() or len(raw) > 4:
        raise ValueError(f"Invalid acquisition time: {value!r}")

    raw = raw.zfill(4)
    hour = int(raw[:2])
    minute = int(raw[2:])

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid acquisition time: {value!r}")

    return hour * 60 + minute


def calculate_temporal_overlap(
    observations: Iterable[dict[str, Any]],
    bin_minutes: int = 30,
) -> dict[str, Any]:
    """
    Compare MODIS and VIIRS presence in date/time bins.

    This measures temporal co-occurrence, not matching fires or calibration.
    Invalid acquisition times are counted and reported separately.
    """
    if not isinstance(bin_minutes, int) or not 1 <= bin_minutes <= 1440:
        raise ValueError("bin_minutes must be an integer between 1 and 1440.")

    bins: dict[tuple[str, int], set[str]] = defaultdict(set)
    invalid_times = []
    sensor_records = {"MODIS": 0, "VIIRS": 0}

    for index, row in enumerate(observations):
        sensor = str(row.get("instrument", "")).strip().upper()

        if sensor not in SUPPORTED_SENSORS:
            raise ValueError(f"Unsupported sensor at row {index}: {sensor!r}")

        acquisition_date = str(row.get("acquisition_date", "")).strip()
        if not acquisition_date:
            raise ValueError(f"Missing acquisition_date at row {index}.")

        try:
            minutes = parse_acquisition_time(row.get("acquisition_time"))
        except (TypeError, ValueError):
            invalid_times.append({
                "row_index": index,
                "acquisition_date": acquisition_date,
                "instrument": sensor,
                "acquisition_time": row.get("acquisition_time"),
            })
            continue

        bin_start = (minutes // bin_minutes) * bin_minutes
        bins[(acquisition_date, bin_start)].add(sensor)
        sensor_records[sensor] += 1

    shared = sum(sensors == SUPPORTED_SENSORS for sensors in bins.values())
    modis_only = sum(sensors == {"MODIS"} for sensors in bins.values())
    viirs_only = sum(sensors == {"VIIRS"} for sensors in bins.values())
    total = len(bins)

    def label(minutes: int) -> str:
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    shared_bins = [
        {"date": day, "bin_start": label(start)}
        for (day, start), sensors in sorted(bins.items())
        if sensors == SUPPORTED_SENSORS
    ]

    return {
        "bin_minutes": bin_minutes,
        "total_date_bins": total,
        "shared_bins": shared,
        "modis_only_bins": modis_only,
        "viirs_only_bins": viirs_only,
        "overlap_percent": round(shared / total * 100, 2) if total else 0.0,
        "sensor_records": sensor_records,
        "invalid_time_count": len(invalid_times),
        "invalid_times": invalid_times,
        "shared_bin_details": shared_bins,
    }
