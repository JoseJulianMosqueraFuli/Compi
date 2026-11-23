"""Link confirmed HealthKit samples to editable workouts."""

import sqlalchemy as sa

from alembic import op

revision = "5eae92dc4d10"
down_revision = "51e7a82bd063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_workout_link",
        sa.Column("sample_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workout_id", sa.Integer(), sa.ForeignKey("workout.id", ondelete="CASCADE"), nullable=False,
        ),
    )
    op.create_index("ix_health_workout_link_workout_id", "health_workout_link", ["workout_id"])


def downgrade() -> None:
    op.drop_table("health_workout_link")
