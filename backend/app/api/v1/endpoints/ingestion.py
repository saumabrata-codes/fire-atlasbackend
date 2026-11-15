import hashlib
import json
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.application.observations import get_observations
from app.core.config import get_settings
from app.database.repositories import list_ingestion_jobs, persist_ingestion
from app.database.models import BackfillRun
from app.database.session import SessionLocal
from app.geospatial.bounds import validate_observation_filters
from app.ingestion.firms.client import FirmsClient
from app.ingestion.jobs.archive import RAW_ROOT, ROOT, preserve_source
from app.ingestion.quality import eligible_detection
from app.ingestion.readers.firms_csv import parse_firms_csv

router = APIRouter()


class BackfillRequest(BaseModel):
    start_date: date
    end_date: date
    sensors: list[str] = Field(default_factory=lambda: ["MODIS", "VIIRS"])
    area: str = "world"


@router.post("/ingestion/backfills", status_code=202)
def create_backfill(payload: BackfillRequest) -> dict:
    """Queue a resumable global historical download for the FIRMS worker."""
    if not get_settings().firms_collection_enabled:
        raise HTTPException(status_code=409, detail="FIRMS collection is paused until frontend acceptance")
    start, end = payload.start_date, payload.end_date
    if start > end:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if end > date.today():
        raise HTTPException(status_code=422, detail="end_date cannot be in the future")
    sensors = [str(x).upper() for x in payload.sensors]
    if not sensors or set(sensors) - {"MODIS", "VIIRS"}:
        raise HTTPException(status_code=422, detail="sensors must contain MODIS, VIIRS, or both")
    if len(sensors) != len(set(sensors)):
        raise HTTPException(status_code=422, detail="each sensor may be selected only once")
    if payload.area.lower() != "world":
        raise HTTPException(status_code=422, detail="Historical backfills currently require area=world")
    sensors = sorted(set(sensors))
    run_id = str(uuid4())
    try:
        with SessionLocal() as db:
            db.add(BackfillRun(id=run_id, start_date=start, end_date=end, cursor_date=start,
                               sensors=sensors, products=[], area="world", status="queued", run_type="backfill"))
            db.commit()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable or migrations are not applied") from exc
    return {"id": run_id, "status": "queued", "start_date": start.isoformat(),
            "end_date": end.isoformat(), "sensors": sensors, "area": "world",
            "note": "The FIRMS worker will retrieve available products in resumable 1–5 day chunks."}


@router.get("/ingestion/backfills")
def list_backfills(limit: int = Query(20, ge=1, le=100)) -> dict:
    try:
        with SessionLocal() as db:
            rows = db.query(BackfillRun).order_by(BackfillRun.created_at.desc()).limit(limit).all()
            return {"backfills": [{
                "id": row.id, "status": row.status, "start_date": row.start_date.isoformat(),
                "end_date": row.end_date.isoformat(), "cursor_date": row.cursor_date.isoformat(),
                "sensors": row.sensors, "run_type": row.run_type, "chunks_completed": row.chunks_completed,
                "records_processed": row.records_processed, "last_error": row.last_error,
            } for row in rows]}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc



@router.get("/ingestion/status")
def ingestion_status() -> dict:
    settings = get_settings()
    observations, sample_mode = get_observations()
    return {
        "mode": "sample" if sample_mode else "live",
        "firms_configured": bool(settings.firms_api_key),
        "collection_enabled": settings.firms_collection_enabled,
        "products": ["MODIS_NRT", "VIIRS_SNPP_NRT"],
        "sample_records": len(observations),
        "note": "Bundled records are demonstration fixtures, not live NASA observations." if sample_mode else "Live source observations are available from PostGIS.",
    }


@router.get("/ingestion/availability")
async def firms_availability() -> dict:
    settings = get_settings()
    client = FirmsClient(settings.firms_api_key, settings.firms_base_url)
    try:
        rows = await client.fetch_availability(settings.firms_availability_url)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"FIRMS availability request failed: {exc}") from exc
    return {"products": rows, "source": "NASA FIRMS data_availability API"}


@router.get("/ingestion/jobs")
def ingestion_jobs() -> dict:
    try:
        with SessionLocal() as db:
            return {"jobs": list_ingestion_jobs(db)}
    except SQLAlchemyError:
        return {"jobs": [], "database_available": False}


@router.get("/ingestion/archives")
def ingestion_archives(limit: int = Query(50, ge=1, le=200)) -> dict:
    """List local FIRMS files and mark whether each file matches its manifest."""
    raw_root = RAW_ROOT.resolve()
    manifests = sorted(
        raw_root.rglob("*.manifest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]
    archives = []
    for manifest_path in manifests:
        try:
            metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
            filename = metadata["file"]
            if Path(filename).name != filename or not filename.endswith(".csv"):
                continue
            csv_path = manifest_path.with_name(filename).resolve()
            if not csv_path.is_relative_to(raw_root) or not csv_path.is_file():
                continue
            payload = csv_path.read_bytes()
            sensor = metadata["sensor"].upper()
            product = metadata["product"].upper()
            checksum_valid = hashlib.sha256(payload).hexdigest() == metadata["sha256"]
            size_valid = len(payload) == metadata["file_size"]
            expected_parent = Path(sensor.lower()) / product.lower()
            relative_parent = csv_path.parent.relative_to(raw_root)
            if relative_parent.parent.parent != expected_parent:
                continue
            archives.append({
                "sensor": sensor, "product": product, "file": filename,
                "year": csv_path.parent.parent.name, "month": csv_path.parent.name,
                "record_count": metadata["record_count"], "downloaded_at": metadata["downloaded_at"],
                "sha256": metadata["sha256"], "verified": checksum_valid and size_valid,
            })
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    return {"archives": archives}


@router.post("/ingestion/sample/{sensor}")
async def ingest_small_sample(
    sensor: str, day_range: int = Query(1, ge=1, le=5),
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
) -> dict:
    settings = get_settings()
    if not settings.firms_collection_enabled:
        raise HTTPException(status_code=409, detail="FIRMS collection is paused until frontend acceptance")
    normalized = sensor.upper()
    if normalized not in {"MODIS", "VIIRS"}:
        raise HTTPException(status_code=404, detail="Sensor must be MODIS or VIIRS")
    if not settings.firms_api_key:
        raise HTTPException(status_code=503, detail="FIRMS_API_KEY is not configured")
    bbox = validate_observation_filters(None, None, west, south, east, north)
    if bbox is None:
        raise HTTPException(status_code=422, detail="Choose a small study-area bounding box before requesting live sample data")
    area = ",".join(str(value) for value in bbox)
    source = "MODIS_NRT" if normalized == "MODIS" else "VIIRS_SNPP_NRT"
    client = FirmsClient(settings.firms_api_key, settings.firms_base_url)
    try:
        availability = await client.fetch_availability(settings.firms_availability_url)
        available_ids = {row.get("data_id", "").upper(): row for row in availability}
        if normalized == "MODIS":
            candidates = ["MODIS_NRT"]
        else:
            candidates = ["VIIRS_SNPP_NRT", "VIIRS_NOAA21_NRT", "VIIRS_NOAA20_NRT"]
        dated = [(name, available_ids[name].get("max_date", "")) for name in candidates if name in available_ids]
        dated = [item for item in dated if item[1]]
        if not dated:
            raise RuntimeError(f"No current {normalized} NRT product is listed as available by FIRMS")
        source, latest_date = max(dated, key=lambda item: item[1])
        csv_text = await client.fetch_area(source, area, day_range)
        parsed = parse_firms_csv(csv_text, normalized, source, f"live/{source}.csv")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"FIRMS request failed: {exc}") from exc
    eligible = [row for row in parsed if eligible_detection(row)]
    try:
        archive = preserve_source(normalized, source, csv_text, len(parsed))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not preserve the FIRMS source file: {exc}") from exc
    persisted = False
    job_id = None
    persistence_note = "PostGIS is unavailable; the untouched source CSV and checksum manifest were saved locally."
    try:
        with SessionLocal() as db:
            job_id, _ = persist_ingestion(
                db, normalized, source, latest_date, archive,
                [{**row, "source_file": archive["path"]} for row in parsed],
            )
        persisted = True
        persistence_note = "Raw source file, ingestion job, product metadata, and observations were saved to PostGIS."
    except SQLAlchemyError:
        pass
    return {"sensor": normalized, "source": source, "area": area, "source_latest_available_date": latest_date,
            "records_validated": len(parsed), "records_quality_eligible": len(eligible), "records": eligible[:100],
            "stored": persisted, "job_id": job_id, "archive": archive, "note": persistence_note}


@router.post("/ingestion/archive/{sensor}/{product}/{year}/{month}/{filename}/replay")
def replay_archived_source(sensor: str, product: str, year: str, month: str, filename: str) -> dict:
    """Verify a previously archived FIRMS CSV and load it into PostGIS."""
    normalized = sensor.upper()
    product_id = product.upper()
    allowed_products = {
        "MODIS": {"MODIS_NRT", "MODIS_SP"},
        "VIIRS": {"VIIRS_SNPP_NRT", "VIIRS_SNPP_SP", "VIIRS_NOAA20_NRT", "VIIRS_NOAA20_SP",
                  "VIIRS_NOAA21_NRT", "VIIRS_NOAA21_SP"},
    }
    if normalized not in allowed_products or product_id not in allowed_products[normalized]:
        raise HTTPException(status_code=404, detail="Unknown FIRMS sensor/product combination")
    if Path(filename).name != filename or not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="filename must be a CSV file name, not a path")
    if len(year) != 4 or not year.isdigit() or len(month) != 2 or not month.isdigit() or not 1 <= int(month) <= 12:
        raise HTTPException(status_code=400, detail="year and month must identify a valid archive folder")

    raw_root = RAW_ROOT.resolve()
    csv_path = (raw_root / normalized.lower() / product_id.lower() / year / month / filename).resolve()
    if not csv_path.is_relative_to(raw_root):
        raise HTTPException(status_code=400, detail="Archive path is outside the raw data directory")
    manifest_path = csv_path.with_suffix(".manifest.json")
    if not csv_path.is_file() or not manifest_path.is_file():
        raise HTTPException(status_code=404, detail="Archived CSV or checksum manifest was not found")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        body = csv_path.read_bytes()
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="Could not read the archive and its manifest") from exc
    actual_checksum = hashlib.sha256(body).hexdigest()
    if (manifest.get("sensor", "").upper() != normalized or manifest.get("product", "").upper() != product_id
            or manifest.get("file") != filename or manifest.get("sha256") != actual_checksum
            or manifest.get("file_size") != len(body)):
        raise HTTPException(status_code=409, detail="Archived CSV does not match its manifest")
    relative_path = str(csv_path.relative_to(ROOT.resolve()))
    csv_text = body.decode("utf-8-sig")
    observations = parse_firms_csv(csv_text, normalized, product_id, relative_path)
    if len(observations) != manifest.get("record_count"):
        raise HTTPException(status_code=409, detail="Validated record count does not match the archive manifest")
    try:
        downloaded_at = date.fromisoformat(manifest["downloaded_at"][:10])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Archive manifest has no valid download date") from exc
    archive = {**manifest, "path": relative_path}
    try:
        with SessionLocal() as db:
            job_id, stored_count = persist_ingestion(
                db, normalized, product_id, downloaded_at.isoformat(), archive,
                [{**row, "source_file": relative_path} for row in observations],
            )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="PostGIS is unavailable; the verified archive remains on disk") from exc
    return {"sensor": normalized, "product": product_id, "archive": relative_path,
            "sha256": actual_checksum, "records_validated": len(observations),
            "records_stored": stored_count, "stored": True, "job_id": job_id}
