from datetime import date

from fastapi import APIRouter, Query

from app.api.v1.endpoints.analytics import time_series
from app.application.region_summary import build_summary_lines, has_consecutive_months
from app.geospatial.bounds import validate_observation_filters

router = APIRouter()


@router.get("/anomalies/summary")
def anomalies_summary(
    start: date | None = None,
    end: date | None = None,
    sensor: str = Query("ALL", pattern="^(ALL|MODIS|VIIRS)$"),
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
) -> dict:
    """Return a cautious monthly screen for the requested sensor and map area."""
    bbox = validate_observation_filters(start, end, west, south, east, north)
    data = time_series(start, end, "month", sensor, west, south, east, north)
    lines = build_summary_lines(data["series"], start, end, sensor, bbox)
    anomaly_line = next((line for line in lines if "spike" in line.lower()),
                        "No elementary monthly spike check was possible with the available buckets.")
    available = len(data["series"]) >= 6 and has_consecutive_months(data["series"])
    reason = ("Elementary comparison available; this is not a formal anomaly score."
              if available else
              "The elementary screen requires six consecutive monthly buckets with stored detections; "
              "missing months are unknown and are not treated as zero.")
    return {
        "available": available,
        "method": "elementary_prior_month_mean_screen",
        "formal_anomaly": False,
        "sample_mode": data["sample_mode"],
        "data_available": data["data_available"],
        "sensor": sensor,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "bounds": list(bbox) if bbox else None,
        "monthly_buckets": len(data["series"]),
        "covered_days": data.get("covered_days", sum(int(row.get("covered_days", 0)) for row in data["series"])),
        "result": anomaly_line,
        "reason": reason,
        "missing_is_zero": False,
        "reason": None if available else (
            "The elementary screen requires six consecutive monthly buckets with stored detections; "
            "missing months are unknown and are not treated as zero."
        ),
    }
