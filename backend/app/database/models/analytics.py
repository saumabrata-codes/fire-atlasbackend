from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class HarmonizationModel(Base):
    __tablename__ = "harmonization_models"
    __table_args__ = (UniqueConstraint("model_name", "version", name="uq_harmonization_model_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_name: Mapped[str] = mapped_column(String(96), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    validation_metrics: Mapped[dict | None] = mapped_column(JSON)
    training_period_start: Mapped[date | None] = mapped_column(Date)
    training_period_end: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
class HarmonizedActivity(Base):
    __tablename__ = "harmonized_activity"
    __table_args__ = (
        UniqueConstraint("grid_cell_id", "model_id", "period_level", "period_start", name="uq_harmonized_activity_cell_model_period"),
        Index("ix_harmonized_activity_period", "period_level", "period_start"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    grid_cell_id: Mapped[int] = mapped_column(ForeignKey("spatial_grid_cells.id"), nullable=False)
    model_id: Mapped[int] = mapped_column(ForeignKey("harmonization_models.id"), nullable=False)
    period_level: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activity_estimate: Mapped[float] = mapped_column(Float, nullable=False)
    uncertainty_lower: Mapped[float | None] = mapped_column(Float)
    uncertainty_upper: Mapped[float | None] = mapped_column(Float)
    contributing_observations: Mapped[int] = mapped_column(BigInteger, nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    quality_status: Mapped[str] = mapped_column(String(24), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
class HistoricalBaseline(Base):
    __tablename__ = "historical_baselines"
    __table_args__ = (
        UniqueConstraint("grid_cell_id", "model_id", "month_of_year", "baseline_start", "baseline_end", name="uq_historical_baseline_cell_model_season"),
        Index("ix_historical_baselines_season", "month_of_year", "baseline_start", "baseline_end"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    grid_cell_id: Mapped[int] = mapped_column(ForeignKey("spatial_grid_cells.id"), nullable=False)
    model_id: Mapped[int] = mapped_column(ForeignKey("harmonization_models.id"), nullable=False)
    month_of_year: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_start: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_end: Mapped[date] = mapped_column(Date, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mean_activity: Mapped[float | None] = mapped_column(Float)
    median_activity: Mapped[float | None] = mapped_column(Float)
    standard_deviation: Mapped[float | None] = mapped_column(Float)
    percentile_90: Mapped[float | None] = mapped_column(Float)
    percentile_95: Mapped[float | None] = mapped_column(Float)
    quality_status: Mapped[str] = mapped_column(String(24), nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
class AnomalyResult(Base):
    __tablename__ = "anomaly_results"
    __table_args__ = (
        UniqueConstraint("grid_cell_id", "model_id", "period_start", name="uq_anomaly_cell_model_period"),
        Index("ix_anomaly_results_period_severity", "period_start", "severity"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    grid_cell_id: Mapped[int] = mapped_column(ForeignKey("spatial_grid_cells.id"), nullable=False)
    model_id: Mapped[int] = mapped_column(ForeignKey("harmonization_models.id"), nullable=False)
    baseline_id: Mapped[int] = mapped_column(ForeignKey("historical_baselines.id"), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_activity: Mapped[float] = mapped_column(Float, nullable=False)
    expected_median: Mapped[float] = mapped_column(Float, nullable=False)
    robust_z_score: Mapped[float | None] = mapped_column(Float)
    percentile: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    data_status: Mapped[str] = mapped_column(String(24), nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
