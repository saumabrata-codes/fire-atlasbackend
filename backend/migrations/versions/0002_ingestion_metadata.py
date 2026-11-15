"""Track FIRMS products, raw files, and ingestion jobs.

Revision ID: 0002_ingestion_metadata
Revises: 0001_initial_schema
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_ingestion_metadata"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_products",
        sa.Column("product_id", sa.String(64), primary_key=True),
        sa.Column("sensor", sa.String(16), nullable=False),
        sa.Column("satellite", sa.String(32), nullable=False),
        sa.Column("instrument", sa.String(16), nullable=False),
        sa.Column("processing_type", sa.String(16), nullable=False),
        sa.Column("first_available", sa.Date()),
        sa.Column("latest_available", sa.Date()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "source_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.String(64), sa.ForeignKey("source_products.product_id"), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False, unique=True),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("source_date_start", sa.Date()),
        sa.Column("source_date_end", sa.Date()),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("product_id", sa.String(64), sa.ForeignKey("source_products.product_id"), nullable=False),
        sa.Column("job_type", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("source_file_id", sa.Integer(), sa.ForeignKey("source_files.id")),
        sa.Column("records_downloaded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_validated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(2000)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.add_column("hotspot_observations", sa.Column("source_file_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_hotspot_source_file", "hotspot_observations", "source_files", ["source_file_id"], ["id"])
    op.create_index("ix_ingestion_jobs_product_status", "ingestion_jobs", ["product_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_product_status", table_name="ingestion_jobs")
    op.drop_constraint("fk_hotspot_source_file", "hotspot_observations", type_="foreignkey")
    op.drop_column("hotspot_observations", "source_file_id")
    op.drop_table("ingestion_jobs")
    op.drop_table("source_files")
    op.drop_table("source_products")
