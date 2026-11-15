from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class HotspotObservation(Base):
    __tablename__ = "hotspot_observations"
    __table_args__ = (
        UniqueConstraint("source_identity", name="uq_hotspot_source_identity"),
        Index("ix_hotspot_natural_key", "product", "acq_datetime", "satellite", "latitude", "longitude"),
        Index("ix_hotspot_source_file_id", "source_file_id"),
        Index("ix_hotspot_acq_sensor", "acq_datetime", "sensor"),
        Index("ix_hotspot_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    sensor: Mapped[str] = mapped_column(String(16), nullable=False)
    satellite: Mapped[str] = mapped_column(String(32), nullable=False)
    instrument: Mapped[str] = mapped_column(String(16), nullable=False)
    product: Mapped[str] = mapped_column(String(64), nullable=False)
    acq_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(32))
    frp: Mapped[float | None] = mapped_column(Float)
    source_file: Mapped[str] = mapped_column(String(512), nullable=False)
    source_file_id: Mapped[int | None] = mapped_column(ForeignKey("source_files.id"))
    source_fields: Mapped[dict] = mapped_column(JSON, nullable=False)
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RawHotspot(Base):
    """Immutable FIRMS row payload retained separately from normalized observations."""
    __tablename__ = "raw_hotspots"
    __table_args__ = (
        UniqueConstraint("source_identity", name="uq_raw_hotspot_source_identity"),
        Index("ix_raw_hotspots_source_file", "source_file_id"),
        Index("ix_raw_hotspots_acq_datetime", "acq_datetime"),
        Index("ix_raw_hotspots_location", "latitude", "longitude"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[str] = mapped_column(ForeignKey("source_products.product_id"), nullable=False)
    source_file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"), nullable=False)
    acq_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    source_fields: Mapped[dict] = mapped_column(JSON, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
