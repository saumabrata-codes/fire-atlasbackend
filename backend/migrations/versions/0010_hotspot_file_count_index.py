"""Index normalized point rows by archived source file for quick coverage checks.

Revision ID: 0010_hotspot_file_count_index
Revises: 0009_hotspot_source_file_lookup
"""
from alembic import op

revision = "0010_hotspot_file_count_index"
down_revision = "0009_hotspot_source_file_lookup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_hotspot_source_file_id", "hotspot_observations", ["source_file_id"])


def downgrade() -> None:
    op.drop_index("ix_hotspot_source_file_id", table_name="hotspot_observations")
