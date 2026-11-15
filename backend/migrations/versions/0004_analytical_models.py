"""Add region, grid, aggregate, harmonization, baseline, and anomaly schemas.

Revision ID: 0004_analytical_models
Revises: 0003_report_jobs
"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

revision = "0004_analytical_models"
down_revision = "0003_report_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "geographic_regions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("region_type", sa.String(32), nullable=False),
        sa.Column("source", sa.String(96)),
        sa.Column("source_code", sa.String(96)),
        sa.Column("country_code", sa.String(8)),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("geographic_regions.id")),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("geom", Geometry("MULTIPOLYGON", srid=4326), nullable=False),
    )
    op.create_index("ix_geographic_regions_geom", "geographic_regions", ["geom"], postgresql_using="gist")
    op.create_index("ix_geographic_regions_country_code", "geographic_regions", ["country_code"])

    op.create_table(
        "spatial_grid_cells",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("grid_system", sa.String(24), nullable=False),
        sa.Column("resolution", sa.String(24), nullable=False),
        sa.Column("cell_key", sa.String(40), nullable=False),
        sa.Column("geom", Geometry("POLYGON", srid=4326), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("grid_system", "resolution", "cell_key", name="uq_spatial_grid_cell_key"),
    )
    op.create_index("ix_spatial_grid_cells_geom", "spatial_grid_cells", ["geom"], postgresql_using="gist")

    op.create_table(
        "sensor_aggregates",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("grid_cell_id", sa.BigInteger(), sa.ForeignKey("spatial_grid_cells.id"), nullable=False),
        sa.Column("sensor", sa.String(16), nullable=False),
        sa.Column("satellite", sa.String(32), nullable=False),
        sa.Column("product", sa.String(64), nullable=False),
        sa.Column("period_level", sa.String(16), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("frp_observation_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("frp_sum_mw", sa.Float()),
        sa.Column("frp_mean_mw", sa.Float()),
        sa.Column("frp_max_mw", sa.Float()),
        sa.Column("day_observation_count", sa.BigInteger()),
        sa.Column("night_observation_count", sa.BigInteger()),
        sa.Column("processing_version", sa.String(32), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("grid_cell_id", "sensor", "satellite", "product", "period_level", "period_start", name="uq_sensor_aggregate_cell_source_period"),
    )
    op.create_index("ix_sensor_aggregates_period", "sensor_aggregates", ["period_level", "period_start", "sensor"])

    op.create_table(
        "harmonization_models",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_name", sa.String(96), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("method", sa.String(64), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("validation_metrics", sa.JSON()),
        sa.Column("training_period_start", sa.Date()),
        sa.Column("training_period_end", sa.Date()),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("model_name", "version", name="uq_harmonization_model_version"),
    )

    op.create_table(
        "harmonized_activity",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("grid_cell_id", sa.BigInteger(), sa.ForeignKey("spatial_grid_cells.id"), nullable=False),
        sa.Column("model_id", sa.Integer(), sa.ForeignKey("harmonization_models.id"), nullable=False),
        sa.Column("period_level", sa.String(16), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activity_estimate", sa.Float(), nullable=False),
        sa.Column("uncertainty_lower", sa.Float()),
        sa.Column("uncertainty_upper", sa.Float()),
        sa.Column("contributing_observations", sa.BigInteger(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("quality_status", sa.String(24), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("grid_cell_id", "model_id", "period_level", "period_start", name="uq_harmonized_activity_cell_model_period"),
    )
    op.create_index("ix_harmonized_activity_period", "harmonized_activity", ["period_level", "period_start"])

    op.create_table(
        "historical_baselines",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("grid_cell_id", sa.BigInteger(), sa.ForeignKey("spatial_grid_cells.id"), nullable=False),
        sa.Column("model_id", sa.Integer(), sa.ForeignKey("harmonization_models.id"), nullable=False),
        sa.Column("month_of_year", sa.Integer(), nullable=False),
        sa.Column("baseline_start", sa.Date(), nullable=False),
        sa.Column("baseline_end", sa.Date(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("mean_activity", sa.Float()),
        sa.Column("median_activity", sa.Float()),
        sa.Column("standard_deviation", sa.Float()),
        sa.Column("percentile_90", sa.Float()),
        sa.Column("percentile_95", sa.Float()),
        sa.Column("quality_status", sa.String(24), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("grid_cell_id", "model_id", "month_of_year", "baseline_start", "baseline_end", name="uq_historical_baseline_cell_model_season"),
    )
    op.create_index("ix_historical_baselines_season", "historical_baselines", ["month_of_year", "baseline_start", "baseline_end"])

    op.create_table(
        "anomaly_results",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("grid_cell_id", sa.BigInteger(), sa.ForeignKey("spatial_grid_cells.id"), nullable=False),
        sa.Column("model_id", sa.Integer(), sa.ForeignKey("harmonization_models.id"), nullable=False),
        sa.Column("baseline_id", sa.BigInteger(), sa.ForeignKey("historical_baselines.id"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_activity", sa.Float(), nullable=False),
        sa.Column("expected_median", sa.Float(), nullable=False),
        sa.Column("robust_z_score", sa.Float()),
        sa.Column("percentile", sa.Float()),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("data_status", sa.String(24), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("grid_cell_id", "model_id", "period_start", name="uq_anomaly_cell_model_period"),
    )
    op.create_index("ix_anomaly_results_period_severity", "anomaly_results", ["period_start", "severity"])


def downgrade() -> None:
    op.drop_index("ix_anomaly_results_period_severity", table_name="anomaly_results")
    op.drop_table("anomaly_results")
    op.drop_index("ix_historical_baselines_season", table_name="historical_baselines")
    op.drop_table("historical_baselines")
    op.drop_index("ix_harmonized_activity_period", table_name="harmonized_activity")
    op.drop_table("harmonized_activity")
    op.drop_table("harmonization_models")
    op.drop_index("ix_sensor_aggregates_period", table_name="sensor_aggregates")
    op.drop_table("sensor_aggregates")
    op.drop_index("ix_spatial_grid_cells_geom", table_name="spatial_grid_cells")
    op.drop_table("spatial_grid_cells")
    op.drop_index("ix_geographic_regions_country_code", table_name="geographic_regions")
    op.drop_index("ix_geographic_regions_geom", table_name="geographic_regions")
    op.drop_table("geographic_regions")
