"""Index normalized rows by source identity fields for fast duplicate checks.

Revision ID: 0009_hotspot_source_file_lookup
Revises: 0008_raw_harmonization_indexes
"""
from alembic import op

revision = "0009_hotspot_source_file_lookup"
down_revision = "0008_raw_harmonization_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_hotspot_natural_key", "hotspot_observations",
        ["product", "acq_datetime", "satellite", "latitude", "longitude"],
    )


def downgrade() -> None:
    op.drop_index("ix_hotspot_natural_key", table_name="hotspot_observations")
