from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from datetime import date, datetime, time, timezone
from pathlib import Path
from uuid import uuid4

from app.database.models import HotspotObservation, IngestionJob, ReportJob, SourceFile, SourceProduct


def persist_report_job(db: Session, report_id: str, sensor: str, records_included: int,
                       output_path: str, checksum: str) -> None:
    now = datetime.now().astimezone()
    db.add(ReportJob(
        id=report_id, report_type="observation_summary_pdf", sensor=sensor,
        status="completed", records_included=records_included, output_path=output_path,
        checksum=checksum, created_at=now, completed_at=now,
    ))
    db.commit()
def list_report_jobs(db: Session, limit: int = 50) -> list[dict]:
    rows = db.scalars(select(ReportJob).order_by(ReportJob.created_at.desc()).limit(limit)).all()
    return [{
        "id": row.id, "report_type": row.report_type, "sensor": row.sensor,
        "status": row.status, "records_included": row.records_included,
        "output_path": row.output_path, "checksum": row.checksum,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    } for row in rows]
