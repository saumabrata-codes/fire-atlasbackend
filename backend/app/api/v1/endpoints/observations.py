import json
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.application.observations import get_observations
from app.application.sample_observations import load_sample_observations
from app.database.repositories.harmonization import prepare_date_range
from app.database.repositories import database_summary
from app.database.models import SensorAggregate, SpatialGridCell
from app.database.session import SessionLocal

router = APIRouter()



from app.geospatial.bounds import validate_observation_filters


@router.get("/overview/summary")
def overview_summary(
    start: date | None = None, end: date | None = None,
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
) -> dict:
    bbox = validate_observation_filters(start, end, west, south, east, north)
    preprocessing = prepare_date_range(start, end, bbox) if start or end else None
    observations = load_sample_observations()
    if start:
        observations = [row for row in observations if date.fromisoformat(row["acq_datetime"][:10]) >= start]
    if end:
        observations = [row for row in observations if date.fromisoformat(row["acq_datetime"][:10]) <= end]
    if bbox:
        west_value, south_value, east_value, north_value = bbox
        observations = [row for row in observations if west_value <= row["longitude"] <= east_value and south_value <= row["latitude"] <= north_value]
    modis = [item for item in observations if item["sensor"] == "MODIS"]
    viirs = [item for item in observations if item["sensor"] == "VIIRS"]
    fallback = {
        "sample_mode": True,
        "as_of": max((x["acq_datetime"] for x in observations), default=None),
        "total_detections": len(observations),
        "modis_detections": len(modis),
        "viirs_detections": len(viirs),
        "mean_frp": round(sum(x["frp"] or 0 for x in observations) / max(len(observations), 1), 1),
        "observations": "Satellite hotspot detections; not unique fires.",
    }
    try:
        with SessionLocal() as db:
            result = database_summary(db, start, end, bbox) or fallback
            result["preprocessing"] = preprocessing
            return result
    except SQLAlchemyError:
        fallback["preprocessing"] = preprocessing
        return fallback


@router.get("/map/hotspots")
def hotspots(
    sensor: str = Query("ALL", pattern="^(ALL|MODIS|VIIRS)$"),
    limit: int = Query(5000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    start: date | None = None,
    end: date | None = None,
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
) -> dict:
    bbox = validate_observation_filters(start, end, west, south, east, north)
    preprocessing = prepare_date_range(start, end, bbox, sensor) if start or end else None
    observations, sample_mode = get_observations(sensor, limit + 1, start, end, bbox, offset)
    selected = observations[:limit]
    return {
        "sample_mode": sample_mode,
        "count": len(selected),
        "offset": offset,
        "has_more": len(observations) > limit,
        "next_offset": offset + limit if len(observations) > limit else None,
        "preprocessing": preprocessing,
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [x["longitude"], x["latitude"]]},
             "properties": {k: v for k, v in x.items() if k not in {"latitude", "longitude", "raw"}}}
            for x in selected
        ],
    }


@router.get("/map/grid")
def map_grid(
    sensor: str = Query("ALL", pattern="^(ALL|MODIS|VIIRS)$"),
    limit: int = Query(2000, ge=1, le=20000),
    offset: int = Query(0, ge=0),
    start: date | None = None,
    end: date | None = None,
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
) -> dict:
    """Return a paginated map layer from precomputed cell aggregates, not a point sample."""
    bbox = validate_observation_filters(start, end, west, south, east, north)
    preprocessing = prepare_date_range(start, end, bbox, sensor) if start or end else None
    modis_count = func.sum(SensorAggregate.observation_count).filter(
        SensorAggregate.sensor == "MODIS"
    ).label("modis")
    viirs_count = func.sum(SensorAggregate.observation_count).filter(
        SensorAggregate.sensor == "VIIRS"
    ).label("viirs")
    statement = select(
        SpatialGridCell.cell_key,
        func.ST_AsGeoJSON(SpatialGridCell.geom).label("geometry"),
        modis_count,
        viirs_count,
        func.sum(SensorAggregate.observation_count).label("total"),
    ).join(SensorAggregate, SensorAggregate.grid_cell_id == SpatialGridCell.id).where(
        SpatialGridCell.grid_system == "fireatlas",
        SpatialGridCell.resolution == "0.25deg",
        SensorAggregate.period_level == "day",
    )
    if start:
        statement = statement.where(
            SensorAggregate.period_start >= datetime.combine(start, time.min, tzinfo=timezone.utc)
        )
    if end:
        statement = statement.where(
            SensorAggregate.period_start < datetime.combine(
                end + timedelta(days=1), time.min, tzinfo=timezone.utc
            )
        )
    if sensor != "ALL":
        statement = statement.where(SensorAggregate.sensor == sensor)
    if bbox:
        west_value, south_value, east_value, north_value = bbox
        statement = statement.where(SpatialGridCell.geom.intersects(
            func.ST_MakeEnvelope(west_value, south_value, east_value, north_value, 4326)
        ))
    statement = statement.group_by(SpatialGridCell.id).order_by(
        SpatialGridCell.cell_key
    ).offset(offset).limit(limit + 1)
    try:
        with SessionLocal() as db:
            rows = db.execute(statement).all()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Precomputed map aggregates are unavailable") from exc
    has_more = len(rows) > limit
    features = []
    for row in rows[:limit]:
        geometry = json.loads(row.geometry) if isinstance(row.geometry, str) else row.geometry
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "cell_key": row.cell_key,
                "sensor": sensor,
                "modis": int(row.modis or 0),
                "viirs": int(row.viirs or 0),
                "total": int(row.total or 0),
                "resolution": "0.25deg",
            },
        })
    return {
        "type": "FeatureCollection",
        "source": "sensor_aggregates",
        "sensor": sensor,
        "count": len(features),
        "offset": offset,
        "has_more": has_more,
        "next_offset": offset + limit if has_more else None,
        "preprocessing": preprocessing,
        "coverage_note": "Cell counts come from stored daily aggregates. Intersecting cells are included in full; missing periods are not zero-filled.",
        "features": features,
    }
