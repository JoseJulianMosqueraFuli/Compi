"""Add a single-writer HealthKit cursor and source observations for each category."""

import sqlalchemy as sa

from alembic import op

revision = "51e7a82bd063"
down_revision = "bf03fa6b4c07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_sync_cursor",
        sa.Column("kind", sa.String(20), primary_key=True),
        sa.Column("stream_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("last_sequence", sa.BigInteger(), nullable=False),
        sa.Column("last_digest", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "health_observation",
        sa.Column("kind", sa.String(20), sa.ForeignKey("health_sync_cursor.kind"), primary_key=True),
        sa.Column("sample_id", sa.Uuid(), primary_key=True),
        sa.Column("source_bundle", sa.String(255), nullable=False),
        sa.Column("start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("numeric_value", sa.Float()),
        sa.Column("category_value", sa.String(20)),
        sa.Column("duration_s", sa.Float()),
    )
    op.create_index("ix_health_observation_kind_start", "health_observation", ["kind", "start"])


def downgrade() -> None:
    op.drop_table("health_observation")
    op.drop_table("health_sync_cursor")
