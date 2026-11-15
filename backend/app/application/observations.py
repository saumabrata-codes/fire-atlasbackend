from datetime import date

from sqlalchemy.exc import SQLAlchemyError

from app.database.repositories import has_observations, list_observations
from app.database.repositories.observations import has_raw_sources
from app.database.session import SessionLocal
from app.application.sample_observations import load_sample_observations


def get_observations(sensor: str = "ALL", limit: int = 10000,
                     start: date | None = None, end: date | None = None,
                     bbox: tuple[float, float, float, float] | None = None,
                     offset: int = 0) -> tuple[list[dict], bool]:
    try:
        with SessionLocal() as db:
            rows = list_observations(db, sensor, limit, start, end, bbox, offset)
            database_has_live_rows = bool(rows) or has_observations(db) or has_raw_sources(db)
        if database_has_live_rows:
            return rows, False
    except SQLAlchemyError:
        pass
    rows = load_sample_observations()
    if sensor != "ALL":
        rows = [row for row in rows if row["sensor"] == sensor]
    if start:
        rows = [row for row in rows if date.fromisoformat(row["acq_datetime"][:10]) >= start]
    if end:
        rows = [row for row in rows if date.fromisoformat(row["acq_datetime"][:10]) <= end]
    if bbox:
        west, south, east, north = bbox
        rows = [row for row in rows if west <= row["longitude"] <= east and south <= row["latitude"] <= north]
    return rows[offset:offset + limit], True
