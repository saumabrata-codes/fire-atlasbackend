from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.application.observations import get_observations
from app.application.imagery import build_region_imagery, build_worldview_url
from app.application.region_summary import build_summary_lines, explain_with_llm
from app.database.models import HarmonizationModel, HarmonizedActivity, HotspotObservation, SensorAggregate, SpatialGridCell
from app.database.repositories.harmonization import prepare_date_range
from app.database.session import SessionLocal
from app.geospatial.bounds import validate_observation_filters

router = APIRouter()


class PrepareRequest(BaseModel):
    start: date
    end: date
    sensor: str = Field(default="ALL", pattern="^(ALL|MODIS|VIIRS)$")
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)


class ExplainRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    start: date | None = None
    end: date | None = None
    sensor: str = Field(default="ALL", pattern="^(ALL|MODIS|VIIRS)$")
    west: float | None = Field(default=None, ge=-180, le=180)
    south: float | None = Field(default=None, ge=-90, le=90)
    east: float | None = Field(default=None, ge=-180, le=180)
    north: float | None = Field(default=None, ge=-90, le=90)


def _period_summary(daily_query, period: str):
    daily = daily_query.cte("daily_summary").prefix_with("MATERIALIZED")
    bucket = func.date_trunc(period, daily.c.observation_day).label("period_start")
    return select(
        bucket,
        func.sum(daily.c.total).label("total"),
        func.sum(daily.c.modis).label("modis"),
        func.sum(daily.c.viirs).label("viirs"),
        func.sum(daily.c.frp_sum_mw).label("frp_sum_mw"),
        (func.sum(daily.c.frp_sum_mw) /
         func.nullif(func.sum(daily.c.frp_observation_count), 0)).label("frp_mean_mw"),
        func.sum(daily.c.frp_observation_count).label("frp_observation_count"),
        func.count().label("covered_days"),
    ).group_by(bucket).order_by(bucket)


@router.post("/analytics/prepare")
def prepare_search(payload: PrepareRequest) -> dict:
    """Prepare only already-stored raw chunks needed for a user's area/date search."""
    bbox = validate_observation_filters(
        payload.start, payload.end, payload.west, payload.south, payload.east, payload.north
    )
    try:
        result = prepare_date_range(payload.start, payload.end, bbox, payload.sensor)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Raw-data harmonization is unavailable") from exc
    return {**result, "start": payload.start.isoformat(), "end": payload.end.isoformat(),
            "sensor": payload.sensor,
            "note": "Existing raw source chunks were harmonized before results are served. No FIRMS download is started by this request."}


@router.get("/analytics/region-summary")
async def region_summary(
    start: date | None = None,
    end: date | None = None,
    sensor: str = Query("ALL", pattern="^(ALL|MODIS|VIIRS)$"),
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
) -> dict:
    bbox = validate_observation_filters(start, end, west, south, east, north)
    data = time_series(start, end, "month", sensor, west, south, east, north)
    lines = build_summary_lines(data["series"], start, end, sensor, bbox,
                                data.get("spatial_note"))
    try:
        explanation, model = await explain_with_llm(lines)
    except Exception:
        explanation, model = None, "summary_rules_llm_unavailable"
    return {
        "summary_lines": lines,
        "explanation": explanation,
        "explanation_source": model,
        "sample_mode": data["sample_mode"],
        "preprocessing": data.get("preprocessing"),
        "data_available": data["data_available"],
        "imagery": {
            "provider": "NASA Worldview / GIBS",
            "images": build_region_imagery(
                end or date.today(), bbox or (-180.0, -90.0, 180.0, 90.0)
            ),
            "browse_url": build_worldview_url(
                end or date.today(), bbox or (-180.0, -90.0, 180.0, 90.0)
            ),
            "note": "Imagery is visual context; date coverage varies and imagery is not a FIRMS hotspot observation.",
        },
    }


@router.post("/analytics/explain")
async def explain_region(payload: ExplainRequest) -> dict:
    """Answer a user question using only verified stored analytics for the requested area."""
    question = payload.question.strip()
    if len(question) < 3:
        raise HTTPException(status_code=422, detail="question must contain at least 3 non-space characters")
    bbox = validate_observation_filters(
        payload.start, payload.end, payload.west, payload.south, payload.east, payload.north
    )
    data = time_series(
        payload.start, payload.end, "month", payload.sensor,
        payload.west, payload.south, payload.east, payload.north,
    )
    lines = build_summary_lines(
        data["series"], payload.start, payload.end, payload.sensor, bbox,
        data.get("spatial_note"),
    )
    try:
        explanation, model = await explain_with_llm(lines, question)
    except Exception:
        explanation, model = None, "summary_rules_llm_unavailable"
    return {
        "question": question,
        "explanation": explanation,
        "explanation_source": model,
        "summary_lines": lines,
        "data_available": data["data_available"],
        "sample_mode": data["sample_mode"],
        "preprocessing": data.get("preprocessing"),
        "note": ("The explanation uses verified stored analytics only. Satellite detections are not unique fires, "
                 "and MODIS/VIIRS are not cross-sensor calibrated."),
    }


@router.get("/analytics/harmonized")
def harmonized_series(
    start: date | None = None,
    end: date | None = None,
    period: str = Query("month", pattern="^(day|month|year)$"),
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
) -> dict:
    """Chart-ready common-grid activity with separate MODIS and VIIRS series."""
    bbox = validate_observation_filters(start, end, west, south, east, north)
    preprocessing = prepare_date_range(start, end, bbox) if start or end else None
    modis_model = HarmonizationModel.model_name == "FIRMS MODIS daily grid activity"
    viirs_model = HarmonizationModel.model_name == "FIRMS VIIRS daily grid activity"
    daily_activity = select(
        HarmonizedActivity.period_start.label("observation_day"),
        func.sum(HarmonizedActivity.activity_estimate).label("total"),
        func.sum(HarmonizedActivity.activity_estimate).filter(modis_model).label("modis"),
        func.sum(HarmonizedActivity.activity_estimate).filter(viirs_model).label("viirs"),
        func.count(HarmonizedActivity.id).label("grid_periods"),
    ).join(HarmonizationModel, HarmonizationModel.id == HarmonizedActivity.model_id).where(
        HarmonizedActivity.period_level == "day",
        HarmonizationModel.model_name.in_((
            "FIRMS MODIS daily grid activity", "FIRMS VIIRS daily grid activity"
        )),
    ).group_by(HarmonizedActivity.period_start)
    if bbox:
        daily_activity = daily_activity.join(
            SpatialGridCell, SpatialGridCell.id == HarmonizedActivity.grid_cell_id
        )
    if start:
        daily_activity = daily_activity.where(
            HarmonizedActivity.period_start >= datetime.combine(start, time.min, tzinfo=timezone.utc)
        )
    if end:
        daily_activity = daily_activity.where(
            HarmonizedActivity.period_start < datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
        )
    if bbox:
        west_value, south_value, east_value, north_value = bbox
        daily_activity = daily_activity.where(
            SpatialGridCell.grid_system == "fireatlas",
            SpatialGridCell.resolution == "0.25deg",
            SpatialGridCell.geom.intersects(
                func.ST_MakeEnvelope(west_value, south_value, east_value, north_value, 4326)),
        )
    daily_activity = daily_activity.cte("daily_harmonized_activity").prefix_with("MATERIALIZED")
    bucket = func.date_trunc(period, daily_activity.c.observation_day).label("period_start")
    statement = select(
        bucket,
        func.sum(daily_activity.c.total).label("total"),
        func.sum(daily_activity.c.modis).label("modis"),
        func.sum(daily_activity.c.viirs).label("viirs"),
        func.sum(daily_activity.c.grid_periods).label("grid_periods"),
    ).group_by(bucket).order_by(bucket)
    try:
        with SessionLocal() as db:
            rows = db.execute(statement).all()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Harmonized activity database is unavailable") from exc
    return {
        "period": period, "source": "harmonized_activity", "sample_mode": False,
        "series": [{
            "period_start": row.period_start.isoformat(), "total": row.total,
            "modis": row.modis or 0, "viirs": row.viirs or 0,
            "grid_periods": row.grid_periods,
        } for row in rows],
        "cross_sensor_calibrated": False,
        "preprocessing": preprocessing,
        "method_note": "Spatial and daily alignment only. Sensor counts remain separate and uncalibrated; intersecting grid cells are included in full.",
    }


@router.get("/analytics/timeseries")
def time_series(
    start: date | None = None,
    end: date | None = None,
    period: str = Query("month", pattern="^(day|month|year)$"),
    sensor: str = Query("ALL", pattern="^(ALL|MODIS|VIIRS)$"),
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
) -> dict:
    bbox = validate_observation_filters(start, end, west, south, east, north)
    preprocessing = prepare_date_range(start, end, bbox, sensor) if start or end else None
    daily_sensor_query = select(
        SensorAggregate.period_start.label("observation_day"),
        func.sum(SensorAggregate.observation_count).label("total"),
        func.sum(SensorAggregate.observation_count).filter(SensorAggregate.sensor == "MODIS").label("modis"),
        func.sum(SensorAggregate.observation_count).filter(SensorAggregate.sensor == "VIIRS").label("viirs"),
        func.sum(SensorAggregate.frp_sum_mw).label("frp_sum_mw"),
        func.sum(SensorAggregate.frp_observation_count).label("frp_observation_count"),
    ).where(SensorAggregate.period_level == "day").group_by(SensorAggregate.period_start)
    if bbox:
        daily_sensor_query = daily_sensor_query.join(
            SpatialGridCell, SpatialGridCell.id == SensorAggregate.grid_cell_id
        )
    if start:
        daily_sensor_query = daily_sensor_query.where(
            SensorAggregate.period_start >= datetime.combine(start, time.min, tzinfo=timezone.utc)
        )
    if end:
        daily_sensor_query = daily_sensor_query.where(
            SensorAggregate.period_start < datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
        )
    if sensor != "ALL":
        daily_sensor_query = daily_sensor_query.where(SensorAggregate.sensor == sensor)
    if bbox:
        west_value, south_value, east_value, north_value = bbox
        daily_sensor_query = daily_sensor_query.where(SpatialGridCell.geom.intersects(
            func.ST_MakeEnvelope(west_value, south_value, east_value, north_value, 4326)))
    statement = _period_summary(daily_sensor_query, period)
    try:
        with SessionLocal() as db:
            rows = db.execute(statement).all()
            source = "precomputed_sensor_aggregates"
            if not rows:
                raw_day = func.date_trunc("day", HotspotObservation.acq_datetime).label("observation_day")
                daily_raw_query = select(
                    raw_day,
                    func.count().label("total"),
                    func.count().filter(HotspotObservation.sensor == "MODIS").label("modis"),
                    func.count().filter(HotspotObservation.sensor == "VIIRS").label("viirs"),
                    func.sum(HotspotObservation.frp).label("frp_sum_mw"),
                    func.count(HotspotObservation.frp).label("frp_observation_count"),
                ).group_by(raw_day)
                if start:
                    daily_raw_query = daily_raw_query.where(HotspotObservation.acq_datetime >= datetime.combine(start, time.min, tzinfo=timezone.utc))
                if end:
                    daily_raw_query = daily_raw_query.where(HotspotObservation.acq_datetime < datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc))
                if sensor != "ALL":
                    daily_raw_query = daily_raw_query.where(HotspotObservation.sensor == sensor)
                if bbox:
                    west_value, south_value, east_value, north_value = bbox
                    daily_raw_query = daily_raw_query.where(HotspotObservation.geom.intersects(
                        func.ST_MakeEnvelope(west_value, south_value, east_value, north_value, 4326)))
                raw_query = _period_summary(daily_raw_query, period)
                rows = db.execute(raw_query).all()
                if rows:
                    source = "on_demand_observation_aggregation"
    except Exception:
        # Keep offline/demo behavior explicit while live database analytics remain unavailable.
        observations, sample_mode = get_observations(sensor=sensor, start=start, end=end, bbox=bbox)
        if not sample_mode:
            raise HTTPException(status_code=503, detail="Historical analytics database is unavailable")
        grouped: dict[str, dict] = {}
        for item in observations:
            moment = datetime.fromisoformat(item["acq_datetime"])
            if period == "year":
                label = moment.strftime("%Y-01-01T00:00:00+00:00")
            elif period == "month":
                label = moment.strftime("%Y-%m-01T00:00:00+00:00")
            else:
                label = moment.strftime("%Y-%m-%dT00:00:00+00:00")
            entry = grouped.setdefault(label, {"period_start": label, "total": 0, "modis": 0,
                                               "viirs": 0, "frp_sum_mw": 0.0, "frp_observation_count": 0,
                                               "covered_dates": set()})
            entry["total"] += 1
            entry[item["sensor"].lower()] += 1
            entry["covered_dates"].add(moment.date().isoformat())
            if item.get("frp") is not None:
                entry["frp_sum_mw"] += item["frp"]
                entry["frp_observation_count"] += 1
        rows = [type("Bucket", (), {**item,
                                     "covered_days": len(item["covered_dates"]),
                                     "frp_mean_mw": item["frp_sum_mw"] / item["frp_observation_count"]
                                     if item["frp_observation_count"] else None})
                for _, item in sorted(grouped.items())]
        source = "sample_fixtures" if sample_mode else "on_demand_observation_aggregation"
    return {
        "period": period, "sensor": sensor, "sample_mode": source == "sample_fixtures", "source": source,
        "series": [{
            "period_start": row.period_start.isoformat() if hasattr(row.period_start, "isoformat")
            else str(row.period_start), "total": row.total,
            "modis": row.modis, "viirs": row.viirs,
            "frp_sum_mw": round(float(row.frp_sum_mw), 3) if row.frp_sum_mw is not None else None,
            "frp_mean_mw": round(float(row.frp_mean_mw), 3) if row.frp_mean_mw is not None else None,
            "frp_observation_count": row.frp_observation_count,
            "covered_days": int(row.covered_days or 0),
        } for row in rows],
        "covered_days": sum(int(row.covered_days or 0) for row in rows),
        "data_available": bool(rows),
        "coverage_note": "Counts are sensor-specific satellite detections, not unique fires. Missing periods are not zero-filled. MODIS and VIIRS counts are kept separate; they are not asserted to be measurement-equivalent.",
        "spatial_note": ("Bounding-box chart totals use full intersecting 0.25-degree cells from precomputed aggregates; map points retain exact coordinates."
                         if bbox and source == "precomputed_sensor_aggregates" else
                         "Chart totals use the requested area and observed periods; missing periods are not zero-filled."),
        "preprocessing": preprocessing,
    }
