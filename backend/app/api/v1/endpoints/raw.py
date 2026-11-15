from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import case, cast, Float, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.database.models import RawHotspot, SourceProduct
from app.database.session import SessionLocal
from app.geospatial.bounds import validate_observation_filters

router = APIRouter()


@router.get("/raw/hotspots")
def raw_hotspots(
    start: date | None = None,
    end: date | None = None,
    sensor: str = Query("ALL", pattern="^(ALL|MODIS|VIIRS)$"),
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
) -> dict:
    """Paged source-row access for periods with no harmonized output."""
    bbox = validate_observation_filters(start, end, west, south, east, north)
    statement = select(RawHotspot, SourceProduct.sensor).join(
        SourceProduct, SourceProduct.product_id == RawHotspot.product_id
    ).order_by(RawHotspot.acq_datetime.desc(), RawHotspot.id.desc())
    confidence = func.lower(func.trim(func.coalesce(
        RawHotspot.source_fields["confidence"].as_string(),
        RawHotspot.source_fields["CONFIDENCE"].as_string(), "",
    )))
    numeric_confidence = func.coalesce(
        RawHotspot.source_fields["confidence"].as_string(),
        RawHotspot.source_fields["CONFIDENCE"].as_string(), "",
    )
    modis_eligible = confidence.in_(["n", "h", "nominal", "high"]) | (case(
        (numeric_confidence.op("~")(r"^[0-9]+(\.[0-9]+)?$"),
         cast(numeric_confidence, Float)), else_=0.0,
    ) >= 30.0)
    viirs_eligible = confidence.in_(["n", "h", "nominal", "high"])
    statement = statement.where(
        ((SourceProduct.sensor == "MODIS") & modis_eligible)
        | ((SourceProduct.sensor == "VIIRS") & viirs_eligible)
    )
    if start:
        statement = statement.where(RawHotspot.acq_datetime >= datetime.combine(start, time.min, tzinfo=timezone.utc))
    if end:
        statement = statement.where(RawHotspot.acq_datetime < datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc))
    if sensor != "ALL":
        statement = statement.where(SourceProduct.sensor == sensor)
    if bbox:
        west_value, south_value, east_value, north_value = bbox
        statement = statement.where(
            RawHotspot.longitude.between(west_value, east_value),
            RawHotspot.latitude.between(south_value, north_value),
        )
    try:
        with SessionLocal() as db:
            rows = db.execute(statement.limit(limit + 1).offset(offset)).all()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Raw observation database is unavailable") from exc
    selected = rows[:limit]
    return {
        "count": len(selected), "offset": offset, "has_more": len(rows) > limit,
        "next_offset": offset + limit if len(rows) > limit else None,
        "records": [{
            "product": row.RawHotspot.product_id, "sensor": row.sensor,
            "acq_datetime": row.RawHotspot.acq_datetime.isoformat(),
            "latitude": row.RawHotspot.latitude, "longitude": row.RawHotspot.longitude,
            "source_file_id": row.RawHotspot.source_file_id,
            "source_fields": row.RawHotspot.source_fields,
        } for row in selected],
    }
