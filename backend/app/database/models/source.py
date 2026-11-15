from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class SourceProduct(Base):
    __tablename__ = "source_products"

    product_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sensor: Mapped[str] = mapped_column(String(16), nullable=False)
    satellite: Mapped[str] = mapped_column(String(32), nullable=False)
    instrument: Mapped[str] = mapped_column(String(16), nullable=False)
    processing_type: Mapped[str] = mapped_column(String(16), nullable=False)
    first_available: Mapped[date | None] = mapped_column(Date)
    latest_available: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
class SourceFile(Base):
    __tablename__ = "source_files"
    __table_args__ = (Index("ix_source_files_date_range", "source_date_start", "source_date_end"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("source_products.product_id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload: Mapped[bytes | None] = mapped_column(LargeBinary)
    source_date_start: Mapped[date | None] = mapped_column(Date)
    source_date_end: Mapped[date | None] = mapped_column(Date)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="validated")
class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (Index("ix_ingestion_jobs_source_file_type", "source_file_id", "job_type", "started_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("source_products.product_id"), nullable=False)
    job_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    source_file_id: Mapped[int | None] = mapped_column(ForeignKey("source_files.id"))
    records_downloaded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_validated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(2000))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BackfillRun(Base):
    __tablename__ = "backfill_runs"
    __table_args__ = (Index("ix_backfill_runs_status_created", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    sensors: Mapped[list] = mapped_column(JSON, nullable=False)
    products: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    product_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cursor_date: Mapped[date] = mapped_column(Date, nullable=False)
    area: Mapped[str] = mapped_column(String(64), nullable=False, default="world")
    run_type: Mapped[str] = mapped_column(String(24), nullable=False, default="backfill")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    chunks_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_processed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
class ReportJob(Base):
    __tablename__ = "report_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sensor: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    records_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_path: Mapped[str | None] = mapped_column(String(512))
    checksum: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
