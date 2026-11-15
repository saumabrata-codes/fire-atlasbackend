"""Store an exact copy of each original FIRMS CSV in PostgreSQL.

Revision ID: 0007_raw_csv_database_copy
Revises: 0006_daily_sync_type
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_raw_csv_database_copy"
down_revision = "0006_daily_sync_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_files", sa.Column("raw_payload", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("source_files", "raw_payload")
