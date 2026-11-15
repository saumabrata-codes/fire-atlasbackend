"""Persist raw FIRMS rows and resumable global backfill runs.

Revision ID: 0005_raw_archive_backfills
Revises: 0004_analytical_models
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_raw_archive_backfills"
down_revision = "0004_analytical_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_hotspots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_identity", sa.String(64), nullable=False),
        sa.Column("product_id", sa.String(64), sa.ForeignKey("source_products.product_id"), nullable=False),
        sa.Column("source_file_id", sa.Integer(), sa.ForeignKey("source_files.id"), nullable=False),
        sa.Column("acq_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("source_fields", sa.JSON(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_identity", name="uq_raw_hotspot_source_identity"),
    )
    op.create_index("ix_raw_hotspots_acq_datetime", "raw_hotspots", ["acq_datetime"])
    op.create_index("ix_raw_hotspots_location", "raw_hotspots", ["latitude", "longitude"])
    op.create_table(
        "backfill_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("sensors", sa.JSON(), nullable=False),
        sa.Column("products", sa.JSON(), nullable=False),
        sa.Column("product_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cursor_date", sa.Date(), nullable=False),
        sa.Column("area", sa.String(64), nullable=False, server_default="world"),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("chunks_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_processed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_backfill_runs_status_created", "backfill_runs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_backfill_runs_status_created", table_name="backfill_runs")
    op.drop_table("backfill_runs")
    op.drop_index("ix_raw_hotspots_location", table_name="raw_hotspots")
    op.drop_index("ix_raw_hotspots_acq_datetime", table_name="raw_hotspots")
    op.drop_table("raw_hotspots")
