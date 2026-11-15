from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database.session import SessionLocal

router = APIRouter()



@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "fireatlas-api"}


@router.get("/health/ready")
def readiness() -> dict:
    try:
        with SessionLocal() as db:
            if db is None:
                return {"ready": False, "database_available": False, "postgis_available": False}
            row = db.execute(text("SELECT current_database(), PostGIS_Full_Version()")).one()
            return {
                "ready": True, "database_available": True, "postgis_available": True,
                "database": row[0], "postgis_version": row[1],
            }
    except SQLAlchemyError:
        return {"ready": False, "database_available": False, "postgis_available": False}
