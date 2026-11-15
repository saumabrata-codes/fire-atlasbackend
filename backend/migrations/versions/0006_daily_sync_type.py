"""Distinguish the rolling automatic FIRMS sync from date backfills.

Revision ID: 0006_daily_sync_type
Revises: 0005_raw_archive_backfills
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_daily_sync_type"
down_revision = "0005_raw_archive_backfills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("backfill_runs", sa.Column("run_type", sa.String(24), nullable=False, server_default="backfill"))
    op.create_index("ix_backfill_runs_type_status", "backfill_runs", ["run_type", "status", "end_date"])


def downgrade() -> None:
    op.drop_index("ix_backfill_runs_type_status", table_name="backfill_runs")
    op.drop_column("backfill_runs", "run_type")
