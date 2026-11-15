from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class GeographicRegion(Base):
    __tablename__ = "geographic_regions"
    __table_args__ = (Index("ix_geographic_regions_geom", "geom", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    region_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str | None] = mapped_column(String(96))
    source_code: Mapped[str | None] = mapped_column(String(96))
    country_code: Mapped[str | None] = mapped_column(String(8), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("geographic_regions.id"))
    properties: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False)
class SpatialGridCell(Base):
    __tablename__ = "spatial_grid_cells"
    __table_args__ = (
        UniqueConstraint("grid_system", "resolution", "cell_key", name="uq_spatial_grid_cell_key"),
        Index("ix_spatial_grid_cells_geom", "geom", postgresql_using="gist"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    grid_system: Mapped[str] = mapped_column(String(24), nullable=False)
    resolution: Mapped[str] = mapped_column(String(24), nullable=False)
    cell_key: Mapped[str] = mapped_column(String(40), nullable=False)
    geom = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
class SensorAggregate(Base):
    __tablename__ = "sensor_aggregates"
    __table_args__ = (
        UniqueConstraint(
            "grid_cell_id", "sensor", "satellite", "product", "period_level", "period_start",
            name="uq_sensor_aggregate_cell_source_period",
        ),
        Index("ix_sensor_aggregates_period", "period_level", "period_start", "sensor"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    grid_cell_id: Mapped[int] = mapped_column(ForeignKey("spatial_grid_cells.id"), nullable=False)
    sensor: Mapped[str] = mapped_column(String(16), nullable=False)
    satellite: Mapped[str] = mapped_column(String(32), nullable=False)
    product: Mapped[str] = mapped_column(String(64), nullable=False)
    period_level: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observation_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    frp_observation_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    frp_sum_mw: Mapped[float | None] = mapped_column(Float)
    frp_mean_mw: Mapped[float | None] = mapped_column(Float)
    frp_max_mw: Mapped[float | None] = mapped_column(Float)
    day_observation_count: Mapped[int | None] = mapped_column(BigInteger)
    night_observation_count: Mapped[int | None] = mapped_column(BigInteger)
    processing_version: Mapped[str] = mapped_column(String(32), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
