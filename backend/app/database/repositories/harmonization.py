"""Idempotent promotion of stored FIRMS source rows into query-ready tables."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.database.models import HotspotObservation, IngestionJob, RawHotspot, SourceFile, SourceProduct
from app.database.repositories.ingestion import _upsert_spatial_aggregates
from app.database.session import SessionLocal


_SATELLITE_SQL = """coalesce(
    nullif(upper(coalesce(r.source_fields->>'satellite', r.source_fields->>'SATELLITE', '')), ''),
    CASE
      WHEN p.product_id LIKE 'MODIS_%' THEN 'TERRA/AQUA'
      WHEN p.product_id LIKE 'VIIRS_SNPP_%' THEN 'SUOMI-NPP'
      WHEN p.product_id LIKE 'VIIRS_NOAA20_%' THEN 'NOAA-20'
      WHEN p.product_id LIKE 'VIIRS_NOAA21_%' THEN 'NOAA-21'
      ELSE 'unknown' END
)"""
_CONFIDENCE_SQL = "coalesce(r.source_fields->>'confidence', r.source_fields->>'CONFIDENCE', '')"
_FRP_SQL = "coalesce(r.source_fields->>'frp', r.source_fields->>'FRP', '')"


def process_source_file(source_file_id: int) -> dict:
    """Promote one archived chunk exactly once; concurrent callers serialize on its row."""
    with SessionLocal() as db:
        source_file = db.execute(
            select(SourceFile).where(SourceFile.id == source_file_id).with_for_update()
        ).scalar_one_or_none()
        if source_file is None:
            return {"source_file_id": source_file_id, "status": "missing", "records_processed": 0}

        job = db.scalar(select(IngestionJob).where(
            IngestionJob.source_file_id == source_file_id,
            IngestionJob.job_type == "harmonization",
        ).order_by(IngestionJob.started_at.desc()).limit(1))
        if job is not None and job.status == "completed":
            return {"source_file_id": source_file_id, "status": "completed",
                    "records_processed": job.records_processed, "reused": True}

        now = datetime.now(timezone.utc)
        if job is None:
            job = IngestionJob(
                id=str(uuid4()), product_id=source_file.product_id, job_type="harmonization",
                status="processing", source_file_id=source_file_id,
                records_downloaded=0, records_validated=0, records_processed=0,
                started_at=now,
            )
            db.add(job)
            db.flush()
        else:
            job.status = "processing"
            job.error_message = None
            job.started_at = now
            job.completed_at = None

        product = db.get(SourceProduct, source_file.product_id)
        if product is None:
            job.status = "failed"
            job.error_message = "Source product metadata is missing"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return {"source_file_id": source_file_id, "status": "failed", "records_processed": 0}

        # FIRMS confidence is used only as a quality gate. The two sensors remain
        # separate descriptive series; this does not claim cross-sensor calibration.
        statement = text(f"""
            INSERT INTO hotspot_observations (
                source_identity, sensor, satellite, instrument, product, acq_datetime,
                latitude, longitude, confidence, frp, source_file, source_file_id,
                source_fields, geom
            )
            SELECT r.source_identity, p.sensor, {_SATELLITE_SQL}, p.sensor, r.product_id,
                   r.acq_datetime, r.latitude, r.longitude,
                   NULLIF(trim({_CONFIDENCE_SQL}), ''),
                   CASE WHEN trim({_FRP_SQL}) ~ '^-?[0-9]+(\\.[0-9]+)?([eE][+-]?[0-9]+)?$'
                        THEN trim({_FRP_SQL})::double precision ELSE NULL END,
                   f.file_path, f.id, r.source_fields,
                   ST_SetSRID(ST_MakePoint(r.longitude, r.latitude), 4326)
            FROM raw_hotspots r
            JOIN source_products p ON p.product_id = r.product_id
            JOIN source_files f ON f.id = r.source_file_id
            WHERE r.source_file_id = :source_file_id
              AND (
                (p.sensor = 'MODIS' AND (
                    lower(trim({_CONFIDENCE_SQL})) IN ('n','h','nominal','high')
                    OR CASE WHEN trim({_CONFIDENCE_SQL}) ~ '^[0-9]+(\\.[0-9]+)?$'
                            THEN trim({_CONFIDENCE_SQL})::double precision >= 30 ELSE false END
                ))
                OR (p.sensor = 'VIIRS' AND lower(trim({_CONFIDENCE_SQL})) IN ('n','h','nominal','high'))
              )
              AND NOT EXISTS (
                SELECT 1 FROM hotspot_observations old
                WHERE old.product = r.product_id
                  AND old.acq_datetime = r.acq_datetime
                  AND old.satellite = {_SATELLITE_SQL}
                  AND old.latitude = r.latitude
                  AND old.longitude = r.longitude
              )
            ON CONFLICT ON CONSTRAINT uq_hotspot_source_identity DO NOTHING
        """)
        added = db.execute(statement, {"source_file_id": source_file_id}).rowcount or 0
        job.records_validated = source_file.record_count
        job.records_processed = max(added, 0)

        if source_file.source_date_start and source_file.source_date_end:
            _upsert_spatial_aggregates(
                db, product.sensor, source_file.product_id,
                source_file.source_date_start,
                source_file.source_date_end + timedelta(days=1),
            )
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"source_file_id": source_file_id, "status": "completed",
                "records_processed": max(added, 0), "reused": False}


def pending_source_file_ids(db: Session, limit: int = 1) -> list[int]:
    """Return only chunks with quality-eligible raw rows absent from point storage."""
    return _pending_source_file_ids(db, limit)


def _pending_source_file_ids(db: Session, limit: int, start: date | None = None,
                             end: date | None = None, sensor: str = "ALL",
                             bbox: tuple[float, float, float, float] | None = None) -> list[int]:
    candidates = select(
        SourceFile.id.label("file_id"),
        SourceFile.record_count.label("expected_count"),
        SourceFile.source_date_start.label("source_date_start"),
    ).join(SourceProduct, SourceProduct.product_id == SourceFile.product_id)
    if start:
        candidates = candidates.where(SourceFile.source_date_end >= start)
    if end:
        candidates = candidates.where(SourceFile.source_date_start <= end)
    if sensor != "ALL":
        candidates = candidates.where(SourceProduct.sensor == sensor)
    if bbox:
        west, south, east, north = bbox
        candidates = candidates.where(select(RawHotspot.id).where(
            RawHotspot.source_file_id == SourceFile.id,
            RawHotspot.longitude.between(west, east),
            RawHotspot.latitude.between(south, north),
        ).exists())
    candidates = candidates.subquery()
    observation_counts = select(
        HotspotObservation.source_file_id.label("source_file_id"),
        func.count().label("observation_count"),
    ).where(HotspotObservation.source_file_id.in_(select(candidates.c.file_id))).group_by(
        HotspotObservation.source_file_id
    ).subquery()
    statement = select(candidates.c.file_id).outerjoin(
        observation_counts, observation_counts.c.source_file_id == candidates.c.file_id
    ).where(
        candidates.c.expected_count > func.coalesce(observation_counts.c.observation_count, 0)
    ).order_by(candidates.c.source_date_start, candidates.c.file_id).limit(limit)
    return list(db.scalars(statement).all())


def _refresh_year_analytics(sensor: str, first: date, last: date) -> None:
    """Rebuild derived yearly grids from normalized points without touching raw or point rows."""
    with SessionLocal() as db:
        products = list(db.scalars(select(HotspotObservation.product).where(
            HotspotObservation.sensor == sensor,
            HotspotObservation.acq_datetime >= datetime.combine(first, datetime.min.time(), tzinfo=timezone.utc),
            HotspotObservation.acq_datetime < datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc),
        ).distinct()).all())
        for product in products:
            _upsert_spatial_aggregates(db, sensor, product, first, last + timedelta(days=1))
        db.commit()


def harmonize_sensor_year(sensor: str, year: int, _repair_attempted: bool = False) -> dict:
    """Finish and verify one sensor/year before the collection cursor advances."""
    first, last = date(year, 1, 1), date(year, 12, 31)
    with SessionLocal() as db:
        ids = list(db.scalars(select(SourceFile.id).join(
            SourceProduct, SourceProduct.product_id == SourceFile.product_id
        ).where(
            SourceProduct.sensor == sensor,
            SourceFile.source_date_start <= last,
            SourceFile.source_date_end >= first,
            select(RawHotspot.id).where(RawHotspot.source_file_id == SourceFile.id).exists(),
        ).order_by(SourceFile.source_date_start, SourceFile.id)).all())
        pending_ids = set(_pending_source_file_ids(
            db, limit=max(len(ids), 1), start=first, end=last, sensor=sensor
        ))
    processed = 0
    for source_file_id in ids:
        if source_file_id not in pending_ids:
            continue
        result = process_source_file(source_file_id)
        if result["status"] != "completed":
            raise RuntimeError(f"Source file {source_file_id} did not harmonize successfully")
        processed += result["records_processed"]
    with SessionLocal() as db:
        row_count_mismatches = db.scalar(text("""
            WITH selected_files AS MATERIALIZED (
                SELECT f.id, f.product_id, f.record_count,
                       f.source_date_start, f.source_date_end,
                       CASE WHEN f.source_date_start >= :year_start
                                  AND f.source_date_end <= :year_end
                            THEN f.record_count END AS in_year_raw_count
                FROM source_files f
                JOIN source_products p ON p.product_id = f.product_id
                WHERE p.sensor = :sensor AND f.source_date_start <= :year_end
                  AND f.source_date_end >= :year_start
            ), boundary_raw AS (
                SELECT f.id AS source_file_id, r.row_count
                FROM selected_files f
                CROSS JOIN LATERAL (
                    SELECT count(*)::bigint AS row_count
                    FROM raw_hotspots r
                    WHERE r.source_file_id = f.id
                      AND r.acq_datetime >= :start_at AND r.acq_datetime < :end_at
                ) r
                WHERE f.in_year_raw_count IS NULL
            ), expected_products AS (
                SELECT f.product_id,
                       sum(coalesce(f.in_year_raw_count, r.row_count, 0))::bigint AS raw_count
                FROM selected_files f
                LEFT JOIN boundary_raw r ON r.source_file_id = f.id
                GROUP BY f.product_id
            ), normalized AS (
                SELECT h.product AS product_id, count(*)::bigint AS point_count
                FROM hotspot_observations h
                WHERE h.sensor = :sensor AND h.acq_datetime >= :start_at
                  AND h.acq_datetime < :end_at
                GROUP BY h.product
            )
            SELECT count(*) FROM expected_products r
            FULL OUTER JOIN normalized h ON h.product_id = r.product_id
            WHERE r.raw_count IS DISTINCT FROM h.point_count
        """), {"sensor": sensor, "year_start": first, "year_end": last,
               "start_at": datetime.combine(first, datetime.min.time(), tzinfo=timezone.utc),
               "end_at": datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)})
        aggregate_mismatches = db.scalar(text("""
            WITH selected_files AS MATERIALIZED (
                SELECT f.id
                FROM source_files f
                JOIN source_products p ON p.product_id = f.product_id
                WHERE p.sensor = :sensor AND f.source_date_start <= :year_end
                  AND f.source_date_end >= :year_start
            ), expected AS (
                SELECT least(floor(h.latitude * 4)::integer, 359)::text || ':' ||
                       least(floor(h.longitude * 4)::integer, 719)::text AS cell_key,
                       h.sensor, h.satellite, h.product,
                       date_trunc('day', h.acq_datetime) AS period_start,
                       count(*)::bigint AS observation_count,
                       count(h.frp)::bigint AS frp_observation_count,
                       sum(h.frp)::double precision AS frp_sum_mw,
                       avg(h.frp)::double precision AS frp_mean_mw,
                       max(h.frp)::double precision AS frp_max_mw,
                       count(*) FILTER (WHERE upper(coalesce(
                           h.source_fields->>'daynight', h.source_fields->>'DAYNIGHT')) = 'D')::bigint
                           AS day_observation_count,
                       count(*) FILTER (WHERE upper(coalesce(
                           h.source_fields->>'daynight', h.source_fields->>'DAYNIGHT')) = 'N')::bigint
                           AS night_observation_count
                FROM hotspot_observations h
                JOIN selected_files f ON f.id = h.source_file_id
                WHERE h.sensor = :sensor AND h.acq_datetime >= :start_at
                  AND h.acq_datetime < :end_at
                GROUP BY cell_key, h.sensor, h.satellite, h.product,
                         date_trunc('day', h.acq_datetime)
            ), actual AS (
                SELECT c.cell_key, a.sensor, a.satellite, a.product, a.period_start,
                       a.period_end, a.observation_count, a.frp_observation_count,
                       a.frp_sum_mw, a.frp_mean_mw, a.frp_max_mw,
                       a.day_observation_count, a.night_observation_count,
                       a.processing_version
                FROM sensor_aggregates a
                JOIN spatial_grid_cells c ON c.id = a.grid_cell_id
                WHERE a.sensor = :sensor AND a.period_level = 'day'
                  AND a.period_start >= :start_at AND a.period_start < :end_at
                  AND c.grid_system = 'fireatlas' AND c.resolution = '0.25deg'
            )
            SELECT count(*) FROM expected e
            FULL OUTER JOIN actual a
              ON a.cell_key = e.cell_key AND a.sensor = e.sensor
             AND a.satellite = e.satellite AND a.product = e.product
             AND a.period_start = e.period_start
            WHERE e.observation_count IS DISTINCT FROM a.observation_count
               OR e.frp_observation_count IS DISTINCT FROM a.frp_observation_count
               OR (e.frp_sum_mw IS NULL) IS DISTINCT FROM (a.frp_sum_mw IS NULL)
               OR abs(coalesce(e.frp_sum_mw, 0) - coalesce(a.frp_sum_mw, 0)) >
                    greatest(1e-9, abs(coalesce(e.frp_sum_mw, 0)) * 1e-9)
               OR (e.frp_mean_mw IS NULL) IS DISTINCT FROM (a.frp_mean_mw IS NULL)
               OR abs(coalesce(e.frp_mean_mw, 0) - coalesce(a.frp_mean_mw, 0)) >
                    greatest(1e-9, abs(coalesce(e.frp_mean_mw, 0)) * 1e-9)
               OR e.frp_max_mw IS DISTINCT FROM a.frp_max_mw
               OR e.day_observation_count IS DISTINCT FROM a.day_observation_count
               OR e.night_observation_count IS DISTINCT FROM a.night_observation_count
               OR a.period_end IS DISTINCT FROM e.period_start + interval '1 day'
               OR a.processing_version IS DISTINCT FROM 'spatial-aggregate-v1'
        """), {"sensor": sensor,
               "year_start": first, "year_end": last,
               "start_at": datetime.combine(first, datetime.min.time(), tzinfo=timezone.utc),
               "end_at": datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)})
        activity_mismatches = db.scalar(text("""
            WITH expected AS (
                SELECT a.grid_cell_id, a.period_start, max(a.period_end) AS period_end,
                       sum(a.observation_count)::bigint AS activity,
                       count(*)::bigint AS source_aggregate_count,
                       array_agg(DISTINCT a.product ORDER BY a.product) AS products,
                       array_agg(DISTINCT a.satellite ORDER BY a.satellite) AS satellites
                FROM sensor_aggregates a
                WHERE a.sensor = :sensor AND a.period_level = 'day'
                  AND a.period_start >= :start_at AND a.period_start < :end_at
                GROUP BY a.grid_cell_id, a.period_start
            ), actual AS (
                SELECT h.grid_cell_id, h.period_start, h.period_end,
                       h.activity_estimate, h.contributing_observations,
                       h.uncertainty_lower, h.uncertainty_upper,
                       h.provenance, h.quality_status
                FROM harmonized_activity h
                JOIN harmonization_models m ON m.id = h.model_id
                WHERE h.period_level = 'day'
                  AND h.period_start >= :start_at AND h.period_start < :end_at
                  AND m.model_name = 'FIRMS ' || :sensor || ' daily grid activity'
                  AND m.version = '1.0'
            )
            SELECT count(*) FROM expected e
            FULL OUTER JOIN actual a
              ON a.grid_cell_id = e.grid_cell_id AND a.period_start = e.period_start
            WHERE e.activity IS DISTINCT FROM a.activity_estimate
               OR e.activity IS DISTINCT FROM a.contributing_observations
               OR e.period_end IS DISTINCT FROM a.period_end
               OR a.uncertainty_lower IS NOT NULL OR a.uncertainty_upper IS NOT NULL
               OR a.quality_status IS DISTINCT FROM 'descriptive'
               OR a.provenance->>'sensor' IS DISTINCT FROM :sensor
               OR (a.provenance->>'source_aggregate_count')::bigint
                    IS DISTINCT FROM e.source_aggregate_count
               OR ((a.provenance->'products')::jsonb IS DISTINCT FROM to_jsonb(e.products))
               OR ((a.provenance->'satellites')::jsonb IS DISTINCT FROM to_jsonb(e.satellites))
        """), {"sensor": sensor,
               "start_at": datetime.combine(first, datetime.min.time(), tzinfo=timezone.utc),
               "end_at": datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)})
    repaired_derived_tables = False
    if (not row_count_mismatches and (aggregate_mismatches or activity_mismatches)
            and not _repair_attempted):
        # A prior partial run may have committed normalized points but stopped
        # before its derived outputs. Repair those outputs, then rerun the gate.
        _refresh_year_analytics(sensor, first, last)
        return {
            **harmonize_sensor_year(sensor, year, _repair_attempted=True),
            "derived_tables_repaired": True,
        }
    if row_count_mismatches or aggregate_mismatches or activity_mismatches:
        raise RuntimeError(
            f"{sensor} {year} harmonization verification failed: "
            f"{row_count_mismatches} product/year raw/point counts differ, "
            f"{aggregate_mismatches} daily sensor aggregates missing or incorrect, "
            f"{activity_mismatches} harmonized activity rows missing or incorrect"
        )
    return {"sensor": sensor, "year": year, "source_files": len(ids),
            "records_added": processed, "verified": True,
            "derived_tables_repaired": repaired_derived_tables}


def prepare_date_range(start: date | None, end: date | None,
                       bbox: tuple[float, float, float, float] | None = None,
                       sensor: str = "ALL") -> dict:
    """Prioritize and complete stored source chunks that overlap a user search."""
    if start is None and end is None:
        return {"status": "not_requested", "source_files_found": 0,
                "source_files_ready": 0, "records_added": 0,
                "requested_bounds": list(bbox) if bbox else None}
    with SessionLocal() as db:
        bounds_statement = select(
            text("min(source_files.source_date_start)"),
            text("max(source_files.source_date_end)"),
        ).select_from(SourceFile).join(
            SourceProduct, SourceProduct.product_id == SourceFile.product_id
        )
        if sensor != "ALL":
            bounds_statement = bounds_statement.where(SourceProduct.sensor == sensor)
        min_date, max_date = db.execute(bounds_statement).one()
        if min_date is None or max_date is None:
            return {"status": "raw_data_unavailable", "source_files_found": 0,
                    "source_files_ready": 0, "coverage_files_found": 0,
                    "records_added": 0, "requested_bounds": list(bbox) if bbox else None}
        start = start or min_date
        end = end or max_date
        ranges_statement = select(
            SourceFile.source_date_start, SourceFile.source_date_end
        ).join(SourceProduct, SourceProduct.product_id == SourceFile.product_id).where(
            SourceFile.source_date_start <= end,
            SourceFile.source_date_end >= start,
        )
        if sensor != "ALL":
            ranges_statement = ranges_statement.where(SourceProduct.sensor == sensor)
        ranges = list(db.execute(ranges_statement).all())
        coverage_statement = select(SourceFile.id).join(
            SourceProduct, SourceProduct.product_id == SourceFile.product_id
        ).where(
            SourceFile.source_date_start <= end,
            SourceFile.source_date_end >= start,
        ).order_by(SourceFile.source_date_start, SourceFile.id)
        if sensor != "ALL":
            coverage_statement = coverage_statement.where(SourceProduct.sensor == sensor)
        coverage_ids = list(db.scalars(coverage_statement).all())
        ids = _pending_source_file_ids(db, limit=max(len(coverage_ids), 1),
                                       start=start, end=end, sensor=sensor, bbox=bbox)

    completed = 0
    processed_rows = 0
    for source_file_id in ids:
        result = process_source_file(source_file_id)
        if result["status"] == "completed":
            completed += 1
            processed_rows += result["records_processed"]
    covered = []
    for range_start, range_end in sorted(ranges):
        left, right = max(range_start, start), min(range_end, end)
        if not covered or left > covered[-1][1] + timedelta(days=1):
            covered.append([left, right])
        else:
            covered[-1][1] = max(covered[-1][1], right)
    missing_ranges = []
    cursor = start
    for range_start, range_end in covered:
        if cursor < range_start:
            missing_ranges.append({"start": cursor.isoformat(),
                                   "end": (range_start - timedelta(days=1)).isoformat()})
        cursor = max(cursor, range_end + timedelta(days=1))
    if cursor <= end:
        missing_ranges.append({"start": cursor.isoformat(), "end": end.isoformat()})
    covered_days = sum((right - left).days + 1 for left, right in covered)
    return {
        "status": ("ready" if not missing_ranges else
                   "partial" if coverage_ids else "raw_data_unavailable"),
        "source_files_found": len(ids), "source_files_ready": len(coverage_ids),
        "coverage_files_found": len(coverage_ids),
        "coverage_complete": not missing_ranges,
        "covered_days": covered_days,
        "requested_days": (end - start).days + 1,
        "missing_ranges": missing_ranges,
        "records_added": processed_rows,
        "requested_bounds": list(bbox) if bbox else None,
    }
