from datetime import date

from fastapi import APIRouter, Query

from app.api.v1.endpoints.analytics import time_series
from app.geospatial.bounds import validate_observation_filters

router = APIRouter()


def _calendar(period: str, start: date | None, end: date | None, key: str,
              sensor: str, west: float | None, south: float | None,
              east: float | None, north: float | None) -> dict:
    bbox = validate_observation_filters(start, end, west, south, east, north)
    result = time_series(start=start, end=end, period=period, sensor=sensor,
                         west=west, south=south, east=east, north=north)
    output = []
    for row in result["series"]:
        bucket = row["period_start"][:10]
        label = bucket if period == "day" else bucket[:7] if period == "month" else bucket[:4]
        output.append({key: label, "modis": row["modis"] or 0, "viirs": row["viirs"] or 0,
                       "total": row["total"] or 0})
    plural = {"day": "days", "month": "months", "year": "years"}[period]
    return {"sample_mode": result["sample_mode"], plural: output,
            "coverage_note": result["coverage_note"], "source": result["source"],
            "sensor": sensor, "bounds": list(bbox) if bbox else None,
            "covered_days": result["covered_days"],
            "spatial_note": result["spatial_note"],
            "preprocessing": result["preprocessing"]}


@router.get("/calendar/monthly")
def monthly_calendar(
    start: date | None = None, end: date | None = None,
    sensor: str = Query("ALL", pattern="^(ALL|MODIS|VIIRS)$"),
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
) -> dict:
    return _calendar("month", start, end, "month", sensor, west, south, east, north)


@router.get("/calendar/daily")
def daily_calendar(
    start: date | None = None, end: date | None = None,
    sensor: str = Query("ALL", pattern="^(ALL|MODIS|VIIRS)$"),
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
) -> dict:
    return _calendar("day", start, end, "date", sensor, west, south, east, north)


@router.get("/calendar/yearly")
def yearly_calendar(
    start: date | None = None, end: date | None = None,
    sensor: str = Query("ALL", pattern="^(ALL|MODIS|VIIRS)$"),
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
) -> dict:
    return _calendar("year", start, end, "year", sensor, west, south, east, north)
