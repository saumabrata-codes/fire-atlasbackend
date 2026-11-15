
from collections import defaultdict
from datetime import date
from typing import Any


SUPPORTED_SENSORS = {"MODIS", "VIIRS"}


def get_period(record_date: date, aggregation: str) -> str:
    if aggregation == "daily":
        return record_date.isoformat()
    if aggregation == "monthly":
        return record_date.strftime("%Y-%m")
    if aggregation == "yearly":
        return record_date.strftime("%Y")

    raise ValueError("Unsupported aggregation type.")


def calculate_sensor_comparison(
    observations: list[dict[str, Any]],
    aggregation: str,
) -> dict[str, Any]:

    sensor_counts = {"MODIS": 0, "VIIRS": 0}
    frp_values = {"MODIS": [], "VIIRS": []}

    period_counts = defaultdict(
        lambda: {"MODIS": 0, "VIIRS": 0}
    )

    product_counts = defaultdict(int)

    for observation in observations:
        sensor = observation.get("instrument")

        if sensor not in SUPPORTED_SENSORS:
            raise ValueError(f"Unsupported or missing instrument: {sensor}")

        sensor_counts[sensor] += 1

        record_date = observation.get("acquisition_date")
        if isinstance(record_date, str):
            record_date = date.fromisoformat(record_date)

        if not isinstance(record_date, date):
            raise ValueError("Invalid or missing acquisition_date.")

        period = get_period(record_date, aggregation)
        period_counts[period][sensor] += 1

        product = observation.get("source_dataset") or "unknown"
        product_counts[(product, sensor)] += 1

        frp = observation.get("frp")

        if frp is not None:
            frp = float(frp)

            if frp < 0:
                raise ValueError("FRP cannot be negative.")

            frp_values[sensor].append(frp)

    total_detections = sum(sensor_counts.values())

    sensor_summaries = {}

    for sensor in ("MODIS", "VIIRS"):
        values = frp_values[sensor]
        count = sensor_counts[sensor]

        sensor_summaries[sensor] = {
            "detection_share_percent": (
                round(count / total_detections * 100, 2)
                if total_detections else 0.0
            ),
            "mean_frp_mw": (
                sum(values) / len(values) if values else None
            ),
            "max_frp_mw": max(values) if values else None,
            "observations_with_frp": len(values),
        }

    time_series = [
        {
            "period": period,
            "MODIS": counts["MODIS"],
            "VIIRS": counts["VIIRS"],
            "total_detections": sum(counts.values()),
        }
        for period, counts in sorted(period_counts.items())
    ]

    product_summaries = [
        {
            "source_product": product,
            "sensor": sensor,
            "detection_count": count,
        }
        for (product, sensor), count in sorted(product_counts.items())
    ]

    return {
        "total_hotspot_detections": total_detections,
        "sensor_counts": sensor_counts,
        "sensor_summaries": sensor_summaries,
        "time_series": time_series,
        "product_summaries": product_summaries,
    }
