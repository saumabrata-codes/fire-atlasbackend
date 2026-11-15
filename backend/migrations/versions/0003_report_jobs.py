"""Track generated report files and their source-data counts.

Revision ID: 0003_report_jobs
Revises: 0002_ingestion_metadata
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_report_jobs"
down_revision = "0002_ingestion_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("report_type", sa.String(32), nullable=False),
        sa.Column("sensor", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("records_included", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_path", sa.String(512)),
        sa.Column("checksum", sa.String(64)),
        sa.Column("error_message", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_report_jobs_created_status", "report_jobs", ["created_at", "status"])


def downgrade() -> None:
    op.drop_index("ix_report_jobs_created_status", table_name="report_jobs")
    op.drop_table("report_jobs")
