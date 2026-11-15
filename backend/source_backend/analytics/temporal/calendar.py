
from collections import defaultdict
from datetime import date
from typing import Any


SUPPORTED_SENSORS = {"MODIS", "VIIRS"}


def get_calendar_period(record_date: date, aggregation: str) -> str:
    if aggregation == "daily":
        return record_date.isoformat()

    if aggregation == "monthly":
        return record_date.strftime("%Y-%m")

    if aggregation == "yearly":
        return record_date.strftime("%Y")

    raise ValueError("Unsupported aggregation type.")


def calculate_calendar(
    observations: list[dict[str, Any]],
    aggregation: str,
) -> dict[str, Any]:
    if aggregation not in {"daily", "monthly", "yearly"}:
        raise ValueError("Unsupported aggregation type.")

    period_counts = defaultdict(
        lambda: {"MODIS": 0, "VIIRS": 0}
    )

    sensor_summary = {"MODIS": 0, "VIIRS": 0}

    for observation in observations:
        sensor = observation.get("instrument")

        if sensor not in SUPPORTED_SENSORS:
            raise ValueError(f"Unsupported or missing instrument: {sensor}")

        record_date = observation.get("acquisition_date")

        if isinstance(record_date, str):
            record_date = date.fromisoformat(record_date)

        if not isinstance(record_date, date):
            raise ValueError("Invalid or missing acquisition_date.")

        period = get_calendar_period(record_date, aggregation)

        period_counts[period][sensor] += 1
        sensor_summary[sensor] += 1

    calendar_periods = []

    for period, counts in sorted(period_counts.items()):
        total = sum(counts.values())

        calendar_periods.append({
            "period": period,
            "MODIS": counts["MODIS"],
            "VIIRS": counts["VIIRS"],
            "total_detections": total,
            "status": "observed_with_detections",
        })

    total_detections = sum(sensor_summary.values())

    highest_activity = max(
        calendar_periods,
        key=lambda item: item["total_detections"],
        default=None,
    )

    activity_summary = {
        "total_detections": total_detections,
        "periods_with_detections": len(calendar_periods),
        "highest_activity_period": (
            highest_activity["period"] if highest_activity else None
        ),
        "highest_activity_detections": (
            highest_activity["total_detections"] if highest_activity else 0
        ),
    }

    return {
        "calendar_periods": calendar_periods,
        "activity_summary": activity_summary,
        "sensor_summary": sensor_summary,
    }
