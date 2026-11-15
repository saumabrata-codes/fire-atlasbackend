import csv
import io
from datetime import date
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from app.application.observations import get_observations
from app.database.repositories import list_report_jobs, persist_report_job
from app.database.repositories.harmonization import prepare_date_range
from app.database.session import SessionLocal
from app.geospatial.bounds import validate_observation_filters
from app.reporting.observations import archive_report, build_observation_report, report_filename

router = APIRouter()



@router.get("/reports/observations.csv")
def export_observations_csv(
    sensor: str = Query("ALL", pattern="^(ALL|MODIS|VIIRS)$"), start: date | None = None,
    end: date | None = None, west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90), east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
) -> StreamingResponse:
    bbox = validate_observation_filters(start, end, west, south, east, north)
    if start or end:
        prepare_date_range(start, end, bbox, sensor)
    observations, _ = get_observations(sensor, limit=10000, start=start, end=end, bbox=bbox)
    buffer = io.StringIO()
    columns = ["id", "sensor", "satellite", "instrument", "product", "acq_datetime", "latitude", "longitude", "confidence", "frp", "source_file"]
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(observations)
    buffer.seek(0)
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=fireatlas-observations.csv"})


@router.get("/reports/summary.pdf")
def export_summary_pdf(
    sensor: str = Query("ALL", pattern="^(ALL|MODIS|VIIRS)$"), start: date | None = None,
    end: date | None = None, west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90), east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
) -> Response:
    bbox = validate_observation_filters(start, end, west, south, east, north)
    if start or end:
        prepare_date_range(start, end, bbox, sensor)
    observations, sample_mode = get_observations(sensor, limit=10000, start=start, end=end, bbox=bbox)
    try:
        body = build_observation_report(observations, sensor, sample_mode)
        archive = archive_report(body)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not save the PDF report: {exc}") from exc
    report_id = str(uuid4())
    tracked = False
    try:
        with SessionLocal() as db:
            if db is not None:
                persist_report_job(db, report_id, sensor, len(observations), archive["path"], archive["sha256"])
                tracked = True
    except SQLAlchemyError:
        pass
    return Response(
        content=body, media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={report_filename(sensor)}",
            "X-FireAtlas-Report-Id": report_id,
            "X-FireAtlas-Report-Tracked": str(tracked).lower(),
            "X-FireAtlas-Report-Sample-Mode": str(sample_mode).lower(),
        },
    )


@router.get("/reports/jobs")
def report_jobs() -> dict:
    try:
        with SessionLocal() as db:
            return {"jobs": list_report_jobs(db) if db is not None else [], "database_available": db is not None}
    except SQLAlchemyError:
        return {"jobs": [], "database_available": False}
