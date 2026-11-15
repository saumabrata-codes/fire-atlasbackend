import hashlib
import json

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app.database.models import HarmonizationModel, HotspotObservation, IngestionJob, RawHotspot, ReportJob, SourceFile, SourceProduct
from app.database.repositories.observations import upsert_observations
from app.ingestion.quality import eligible_detection


def persist_ingestion(db: Session, sensor: str, product_id: str, latest_available: str,
                      archive: dict, observations: list[dict], job_type: str = "incremental") -> tuple[str, int]:
    now = datetime.fromisoformat(archive["downloaded_at"])
    eligible_observations = [row for row in observations if eligible_detection(row)]
    start_date = min((date.fromisoformat(row["acq_datetime"][:10]) for row in eligible_observations), default=None)
    end_date = max((date.fromisoformat(row["acq_datetime"][:10]) for row in eligible_observations), default=None)
    first_source_date = date.fromisoformat(archive["source_date_start"]) if archive.get("source_date_start") else start_date
    satellite = {
        "MODIS_NRT": "TERRA/AQUA", "MODIS_SP": "TERRA/AQUA",
        "VIIRS_SNPP_NRT": "SUOMI-NPP", "VIIRS_SNPP_SP": "SUOMI-NPP",
        "VIIRS_NOAA20_NRT": "NOAA-20", "VIIRS_NOAA20_SP": "NOAA-20",
        "VIIRS_NOAA21_NRT": "NOAA-21", "VIIRS_NOAA21_SP": "NOAA-21",
    }.get(product_id, "unknown")
    product_statement = insert(SourceProduct).values(
        product_id=product_id, sensor=sensor, satellite=satellite, instrument=sensor,
        processing_type=product_id.rsplit("_", 1)[-1], latest_available=date.fromisoformat(latest_available),
        first_available=first_source_date,
    ).on_conflict_do_update(
        index_elements=[SourceProduct.product_id],
        set_={"latest_available": func.greatest(SourceProduct.latest_available, date.fromisoformat(latest_available)),
              "first_available": func.least(SourceProduct.first_available, first_source_date)
              if first_source_date else SourceProduct.first_available,
              "updated_at": func.now()},
    )
    db.execute(product_statement)
    repository_root = Path(__file__).resolve().parents[4]
    archive_path = (repository_root / archive["path"]).resolve()
    if not archive_path.is_relative_to(repository_root.resolve()):
        raise ValueError("Archive path is outside the FireAtlas data directory")
    payload = archive_path.read_bytes()
    if len(payload) != archive["file_size"]:
        raise ValueError("Archived source file size differs from its manifest")
    file_statement = insert(SourceFile).values(
        product_id=product_id, file_path=archive["path"], file_name=Path(archive["path"]).name,
        checksum=archive["sha256"], file_size=archive["file_size"], record_count=len(eligible_observations),
        source_date_start=date.fromisoformat(archive["source_date_start"]) if archive.get("source_date_start") else start_date,
        source_date_end=date.fromisoformat(archive["source_date_end"]) if archive.get("source_date_end") else end_date,
        raw_payload=payload, downloaded_at=now, status="validated",
    ).on_conflict_do_nothing(index_elements=[SourceFile.checksum]).returning(SourceFile.id)
    source_file_id = db.scalar(file_statement)
    if source_file_id is None:
        source_file_id = db.scalar(select(SourceFile.id).where(SourceFile.checksum == archive["sha256"]))
    job_id = str(uuid4())
    db.add(IngestionJob(
        id=job_id, product_id=product_id, job_type=job_type, status="completed",
        source_file_id=source_file_id, records_downloaded=len(observations),
        records_validated=len(observations), records_processed=0,
        started_at=now, completed_at=datetime.now(now.tzinfo),
    ))
    stored = upsert_observations(db, eligible_observations, source_file_id)
    if eligible_observations:
        period_start = min(date.fromisoformat(row["acq_datetime"][:10]) for row in eligible_observations)
        period_end = max(date.fromisoformat(row["acq_datetime"][:10]) for row in eligible_observations) + timedelta(days=1)
        _upsert_spatial_aggregates(db, sensor, product_id, period_start, period_end)
    db.query(IngestionJob).filter(IngestionJob.id == job_id).update({"records_processed": stored})
    db.commit()
    return job_id, stored


def persist_raw_ingestion(db: Session, sensor: str, product_id: str, latest_available: str,
                          archive: dict, observations: list[dict], downloaded_records: int,
                          job_type: str) -> tuple[str, int]:
    """Commit quality-screened raw rows and original file bytes without derived data."""
    now = datetime.fromisoformat(archive["downloaded_at"])
    first = date.fromisoformat(archive["source_date_start"]) if archive.get("source_date_start") else None
    last = date.fromisoformat(archive["source_date_end"]) if archive.get("source_date_end") else None
    satellite = {
        "MODIS_NRT": "TERRA/AQUA", "MODIS_SP": "TERRA/AQUA",
        "VIIRS_SNPP_NRT": "SUOMI-NPP", "VIIRS_SNPP_SP": "SUOMI-NPP",
        "VIIRS_NOAA20_NRT": "NOAA-20", "VIIRS_NOAA20_SP": "NOAA-20",
        "VIIRS_NOAA21_NRT": "NOAA-21", "VIIRS_NOAA21_SP": "NOAA-21",
    }.get(product_id, "unknown")
    product_insert = insert(SourceProduct).values(
        product_id=product_id, sensor=sensor, satellite=satellite, instrument=sensor,
        processing_type=product_id.rsplit("_", 1)[-1], first_available=first,
        latest_available=date.fromisoformat(latest_available),
    ).on_conflict_do_update(
        index_elements=[SourceProduct.product_id],
        set_={"latest_available": func.greatest(SourceProduct.latest_available,
                                                date.fromisoformat(latest_available)),
              "updated_at": func.now()},
    )
    db.execute(product_insert)
    repository_root = Path(__file__).resolve().parents[4]
    source_path = (repository_root / archive["path"]).resolve()
    if not source_path.is_relative_to(repository_root.resolve()):
        raise ValueError("Archive path is outside the FireAtlas data directory")
    payload = source_path.read_bytes()
    if len(payload) != archive["file_size"]:
        raise ValueError("Archived source file size differs from its manifest")
    source_insert = insert(SourceFile).values(
        product_id=product_id, file_path=archive["path"], file_name=Path(archive["path"]).name,
        checksum=archive["sha256"], file_size=archive["file_size"], record_count=len(observations),
        source_date_start=first, source_date_end=last, raw_payload=payload,
        downloaded_at=now, status="validated",
    ).on_conflict_do_nothing(index_elements=[SourceFile.checksum]).returning(SourceFile.id)
    source_file_id = db.scalar(source_insert)
    if source_file_id is None:
        source_file_id = db.scalar(select(SourceFile.id).where(SourceFile.checksum == archive["sha256"]))
    raw_rows = []
    for row in observations:
        raw_fields = row.get("source_raw", row["raw"])
        fingerprint = hashlib.sha256((product_id + "|" + json.dumps(
            raw_fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )).encode("utf-8")).hexdigest()
        raw_rows.append({
            "source_identity": fingerprint, "product_id": product_id,
            "source_file_id": source_file_id,
            "acq_datetime": datetime.fromisoformat(row["acq_datetime"]),
            "latitude": row["latitude"], "longitude": row["longitude"],
            "source_fields": raw_fields,
        })
    stored = 0
    for offset in range(0, len(raw_rows), 2000):
        raw_insert = insert(RawHotspot).values(raw_rows[offset:offset + 2000])
        result = db.execute(raw_insert.on_conflict_do_nothing(
            constraint="uq_raw_hotspot_source_identity")).rowcount
        stored += max(result or 0, 0)
    db.query(SourceFile).filter(SourceFile.id == source_file_id).update({"record_count": stored})
    job_id = str(uuid4())
    db.add(IngestionJob(
        id=job_id, product_id=product_id, job_type=job_type, status="completed",
        source_file_id=source_file_id, records_downloaded=downloaded_records,
        records_validated=len(observations), records_processed=stored,
        started_at=now, completed_at=datetime.now(now.tzinfo),
    ))
    db.commit()
    return job_id, stored


def _upsert_spatial_aggregates(db: Session, sensor: str, product_id: str, start_date: date, end_date: date) -> None:
    """Refresh occupied quarter-degree cells and daily sensor statistics for imported dates."""
    params = {"product_id": product_id, "start_at": datetime.combine(start_date, time.min, tzinfo=timezone.utc),
              "end_at": datetime.combine(end_date, time.min, tzinfo=timezone.utc)}
    grouped = """
        SELECT least(floor(latitude * 4)::integer, 359) AS lat_idx,
               least(floor(longitude * 4)::integer, 719) AS lon_idx,
               sensor, satellite, product, date_trunc('day', acq_datetime) AS day_start,
               count(*)::bigint AS observations,
               count(frp)::bigint AS frp_count, sum(frp) AS frp_sum,
               avg(frp) AS frp_mean, max(frp) AS frp_max,
               count(*) FILTER (WHERE upper(coalesce(source_fields->>'daynight', source_fields->>'DAYNIGHT')) = 'D')::bigint AS day_count,
               count(*) FILTER (WHERE upper(coalesce(source_fields->>'daynight', source_fields->>'DAYNIGHT')) = 'N')::bigint AS night_count
        FROM hotspot_observations
        WHERE product = :product_id AND acq_datetime >= :start_at AND acq_datetime < :end_at
        GROUP BY 1, 2, sensor, satellite, product, date_trunc('day', acq_datetime)
    """
    db.execute(text(f"""
        WITH grouped AS ({grouped})
        INSERT INTO spatial_grid_cells (grid_system, resolution, cell_key, geom)
        SELECT 'fireatlas', '0.25deg', lat_idx::text || ':' || lon_idx::text,
               ST_MakeEnvelope(lon_idx / 4.0, lat_idx / 4.0,
                               (lon_idx + 1) / 4.0, (lat_idx + 1) / 4.0, 4326)
        FROM (SELECT DISTINCT lat_idx, lon_idx FROM grouped) cells
        ON CONFLICT (grid_system, resolution, cell_key) DO NOTHING
    """), params)
    db.execute(text(f"""
        WITH grouped AS ({grouped})
        INSERT INTO sensor_aggregates (
            grid_cell_id, sensor, satellite, product, period_level, period_start, period_end,
            observation_count, frp_observation_count, frp_sum_mw, frp_mean_mw, frp_max_mw,
            day_observation_count, night_observation_count, processing_version
        )
        SELECT cell.id, grouped.sensor, grouped.satellite, grouped.product, 'day', grouped.day_start,
               grouped.day_start + interval '1 day', grouped.observations, grouped.frp_count,
               grouped.frp_sum, grouped.frp_mean, grouped.frp_max, grouped.day_count,
               grouped.night_count, 'spatial-aggregate-v1'
        FROM grouped
        JOIN spatial_grid_cells cell ON cell.grid_system = 'fireatlas'
          AND cell.resolution = '0.25deg'
          AND cell.cell_key = grouped.lat_idx::text || ':' || grouped.lon_idx::text
        ON CONFLICT (grid_cell_id, sensor, satellite, product, period_level, period_start)
        DO UPDATE SET period_end = excluded.period_end,
                      observation_count = excluded.observation_count,
                      frp_observation_count = excluded.frp_observation_count,
                      frp_sum_mw = excluded.frp_sum_mw, frp_mean_mw = excluded.frp_mean_mw,
                      frp_max_mw = excluded.frp_max_mw,
                      day_observation_count = excluded.day_observation_count,
                      night_observation_count = excluded.night_observation_count,
                      processing_version = excluded.processing_version,
                      calculated_at = now()
    """), params)

    _upsert_harmonized_activity(db, sensor, start_date, end_date)


def _upsert_harmonized_activity(db: Session, sensor: str, start_date: date, end_date: date) -> None:
    """Align one sensor's daily counts and provenance on the shared spatial grid.

    This is spatial/temporal alignment only; values are deliberately not converted
    between MODIS and VIIRS measurement scales.
    """
    model_name = f"FIRMS {sensor} daily grid activity"
    model_insert = insert(HarmonizationModel).values(
        model_name=model_name, version="1.0", method="spatiotemporal_grid_aggregation",
        description=("Daily detection counts aligned to the shared 0.25-degree grid. "
                     "Sensor-specific counts remain uncalibrated and must not be interpreted as cross-sensor equivalent."),
        parameters={"sensor": sensor, "grid_system": "fireatlas", "resolution": "0.25deg",
                    "period": "day", "unit": "detections per grid cell per day"},
        validation_metrics=None, status="descriptive",
    )
    model_statement = model_insert.on_conflict_do_update(
        constraint="uq_harmonization_model_version",
        set_={"description": model_insert.excluded.description,
              "parameters": model_insert.excluded.parameters,
              "status": model_insert.excluded.status},
    )
    model_id = db.scalar(model_statement.returning(HarmonizationModel.id))
    params = {"sensor": sensor, "model_id": model_id,
              "start_at": datetime.combine(start_date, time.min, tzinfo=timezone.utc),
              "end_at": datetime.combine(end_date, time.min, tzinfo=timezone.utc)}
    db.execute(text("""
        WITH grouped AS (
            SELECT grid_cell_id, period_start, period_end,
                   sum(observation_count)::bigint AS activity,
                   count(*)::bigint AS source_aggregate_count,
                   array_agg(DISTINCT product ORDER BY product) AS products,
                   array_agg(DISTINCT satellite ORDER BY satellite) AS satellites
            FROM sensor_aggregates
            WHERE sensor = :sensor AND period_level = 'day'
              AND period_start >= :start_at AND period_start < :end_at
            GROUP BY grid_cell_id, period_start, period_end
        )
        INSERT INTO harmonized_activity (
            grid_cell_id, model_id, period_level, period_start, period_end,
            activity_estimate, uncertainty_lower, uncertainty_upper,
            contributing_observations, provenance, quality_status
        )
        SELECT grid_cell_id, :model_id, 'day', period_start, period_end,
               activity, NULL, NULL, activity,
               json_build_object('sensor', :sensor, 'products', products,
                                 'satellites', satellites,
                                 'source_aggregate_count', source_aggregate_count,
                                 'method', 'spatiotemporal_grid_aggregation'),
               'descriptive'
        FROM grouped
        ON CONFLICT (grid_cell_id, model_id, period_level, period_start)
        DO UPDATE SET period_end = excluded.period_end,
                      activity_estimate = excluded.activity_estimate,
                      contributing_observations = excluded.contributing_observations,
                      provenance = excluded.provenance,
                      quality_status = excluded.quality_status,
                      calculated_at = now()
    """), params)
def list_ingestion_jobs(db: Session, limit: int = 50) -> list[dict]:
    rows = db.scalars(select(IngestionJob).order_by(IngestionJob.started_at.desc()).limit(limit)).all()
    return [{
        "id": row.id, "product_id": row.product_id, "job_type": row.job_type,
        "status": row.status, "source_file_id": row.source_file_id,
        "records_downloaded": row.records_downloaded, "records_validated": row.records_validated,
        "records_processed": row.records_processed, "error_message": row.error_message,
        "started_at": row.started_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    } for row in rows]
