"""Create the first observation table and PostGIS geometry index.

Revision ID: 0001_initial_schema
Revises:
"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "hotspot_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_identity", sa.String(64), nullable=False),
        sa.Column("sensor", sa.String(16), nullable=False),
        sa.Column("satellite", sa.String(32), nullable=False),
        sa.Column("instrument", sa.String(16), nullable=False),
        sa.Column("product", sa.String(64), nullable=False),
        sa.Column("acq_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("confidence", sa.String(32)),
        sa.Column("frp", sa.Float()),
        sa.Column("source_file", sa.String(512), nullable=False),
        sa.Column("source_fields", sa.JSON(), nullable=False),
        sa.Column("geom", Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_identity", name="uq_hotspot_source_identity"),
    )
    op.create_index("ix_hotspot_acq_sensor", "hotspot_observations", ["acq_datetime", "sensor"])
    op.create_index("ix_hotspot_geom", "hotspot_observations", ["geom"], postgresql_using="gist")


def downgrade() -> None:
    op.drop_index("ix_hotspot_geom", table_name="hotspot_observations")
    op.drop_index("ix_hotspot_acq_sensor", table_name="hotspot_observations")
    op.drop_table("hotspot_observations")
