"""Add lookup indexes for chunked raw processing.

Revision ID: 0008_raw_harmonization_indexes
Revises: 0007_raw_csv_database_copy
"""
from alembic import op

revision = "0008_raw_harmonization_indexes"
down_revision = "0007_raw_csv_database_copy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_raw_hotspots_source_file", "raw_hotspots", ["source_file_id"])
    op.create_index("ix_source_files_date_range", "source_files", ["source_date_start", "source_date_end"])
    op.create_index(
        "ix_ingestion_jobs_source_file_type", "ingestion_jobs",
        ["source_file_id", "job_type", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_source_file_type", table_name="ingestion_jobs")
    op.drop_index("ix_source_files_date_range", table_name="source_files")
    op.drop_index("ix_raw_hotspots_source_file", table_name="raw_hotspots")
