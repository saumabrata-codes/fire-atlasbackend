import hashlib
import json

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from datetime import date, datetime, time, timezone
from app.database.models import HotspotObservation, SourceFile


def has_observations(db: Session) -> bool:
    return bool(db.scalar(select(HotspotObservation.id).limit(1)))


def has_raw_sources(db: Session) -> bool:
    return bool(db.scalar(select(SourceFile.id).limit(1)))
def upsert_observations(db: Session, observations: list[dict], source_file_id: int | None = None) -> int:
    if not observations:
        return 0
    for offset in range(0, len(observations), 5000):
        batch = observations[offset:offset + 5000]
        records = []
        for row in batch:
            raw = row.get("source_raw", row["raw"])
            raw_identity = hashlib.sha256(
                (row["product"] + "|" + json.dumps(raw, sort_keys=True, separators=(",", ":"))).encode()
            ).hexdigest() if source_file_id is not None else None
            records.append({
                "identity": row["id"], "sensor": row["sensor"], "satellite": row["satellite"],
                "instrument": row["instrument"], "product": row["product"],
                "acq_datetime": row["acq_datetime"], "latitude": row["latitude"],
                "longitude": row["longitude"], "confidence": row["confidence"],
                "frp": str(row["frp"]) if row["frp"] is not None else None,
                "source_file": row["source_file"], "source_fields": row["raw"],
                "raw_identity": raw_identity, "source_raw": raw,
            })
        db.execute(text("""
            WITH batch AS (
                SELECT * FROM jsonb_to_recordset(CAST(:records AS jsonb)) AS entry(
                    identity text, sensor text, satellite text, instrument text, product text,
                    acq_datetime timestamptz, latitude double precision, longitude double precision,
                    confidence text, frp double precision, source_file text, source_fields json,
                    raw_identity text, source_raw json
                )
            ), archive AS (
                INSERT INTO raw_hotspots (
                    source_identity, product_id, source_file_id, acq_datetime,
                    latitude, longitude, source_fields
                )
                SELECT raw_identity, product, :source_file_id, acq_datetime, latitude,
                       longitude, source_raw
                FROM batch WHERE raw_identity IS NOT NULL
                ON CONFLICT ON CONSTRAINT uq_raw_hotspot_source_identity DO NOTHING
            )
            INSERT INTO hotspot_observations (
                source_identity, sensor, satellite, instrument, product, acq_datetime,
                latitude, longitude, confidence, frp, source_file, source_file_id, source_fields, geom
            )
            SELECT identity, sensor, satellite, instrument, product, acq_datetime,
                   latitude, longitude, confidence, frp, source_file, :source_file_id, source_fields,
                   ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
            FROM batch
            ON CONFLICT ON CONSTRAINT uq_hotspot_source_identity DO UPDATE SET
                confidence = excluded.confidence, frp = excluded.frp,
                source_fields = excluded.source_fields, source_file = excluded.source_file,
                source_file_id = excluded.source_file_id
        """), {"records": json.dumps(records, separators=(",", ":")), "source_file_id": source_file_id})
    return len(observations)


def list_observations(db: Session, sensor: str, limit: int = 5000,
                      start: date | None = None, end: date | None = None,
                      bbox: tuple[float, float, float, float] | None = None,
                      offset: int = 0) -> list[dict]:
    statement = select(HotspotObservation).order_by(HotspotObservation.acq_datetime.desc(), HotspotObservation.id.desc()).limit(limit).offset(offset)
    if sensor != "ALL":
        statement = statement.where(HotspotObservation.sensor == sensor)
    if start:
        statement = statement.where(HotspotObservation.acq_datetime >= datetime.combine(start, time.min, tzinfo=timezone.utc))
    if end:
        end_exclusive = datetime.combine(end, time.max, tzinfo=timezone.utc)
        statement = statement.where(HotspotObservation.acq_datetime <= end_exclusive)
    if bbox:
        west, south, east, north = bbox
        statement = statement.where(
            HotspotObservation.geom.intersects(func.ST_MakeEnvelope(west, south, east, north, 4326))
        )
    rows = db.scalars(statement).all()
    return [{
        "id": row.source_identity, "latitude": row.latitude, "longitude": row.longitude,
        "acq_datetime": row.acq_datetime.isoformat(), "satellite": row.satellite,
        "instrument": row.instrument, "sensor": row.sensor, "product": row.product,
        "confidence": row.confidence, "frp": row.frp, "source_file": row.source_file,
        "raw": row.source_fields,
    } for row in rows]
def database_summary(db: Session, start: date | None = None, end: date | None = None,
                    bbox: tuple[float, float, float, float] | None = None) -> dict | None:
    if not has_observations(db):
        return None
    statement = db.query(
        func.count(HotspotObservation.id),
        func.count(HotspotObservation.id).filter(HotspotObservation.sensor == "MODIS"),
        func.count(HotspotObservation.id).filter(HotspotObservation.sensor == "VIIRS"),
        func.avg(HotspotObservation.frp),
        func.max(HotspotObservation.acq_datetime),
    )
    if start:
        statement = statement.filter(HotspotObservation.acq_datetime >= datetime.combine(start, time.min, tzinfo=timezone.utc))
    if end:
        statement = statement.filter(HotspotObservation.acq_datetime <= datetime.combine(end, time.max, tzinfo=timezone.utc))
    if bbox:
        west, south, east, north = bbox
        statement = statement.filter(HotspotObservation.geom.intersects(func.ST_MakeEnvelope(west, south, east, north, 4326)))
    total, modis, viirs, mean_frp, latest = statement.one()
    return {
        "sample_mode": False, "as_of": latest.isoformat() if latest else None,
        "total_detections": total, "modis_detections": modis, "viirs_detections": viirs,
        "mean_frp": round(float(mean_frp or 0), 1),
        "observations": "Satellite hotspot detections; not unique fires.",
    }
