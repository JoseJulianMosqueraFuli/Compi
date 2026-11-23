"""Minimal record of the user's decision to reconcile a HealthKit workout."""

from uuid import UUID

from sqlmodel import Field, SQLModel


class HealthWorkoutLink(SQLModel, table=True):
    __tablename__ = "health_workout_link"

    # The link outlives source corrections and deletions. Manual workout data remains user-owned.
    sample_id: UUID = Field(primary_key=True)
    workout_id: int = Field(foreign_key="workout.id", ondelete="CASCADE", index=True)
