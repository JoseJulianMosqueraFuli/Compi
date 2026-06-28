"""Workout, CardioDetail and StrengthDetail entities (Requirement 3.1–3.5)."""
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import JSON, Column
from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship, SQLModel

from app.models.domain import WorkoutType


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Workout(SQLModel, table=True):
    """A real workout executed by the user (Requirement 3.1, 3.3)."""

    __tablename__ = "workout"

    id: int | None = Field(default=None, primary_key=True)
    external_id: str = Field(unique=True, index=True, description="Deduplication key (Req 6.2).")
    type: WorkoutType
    start_time: datetime
    duration_s: int = Field(ge=0)
    avg_hr: int | None = Field(default=None, ge=0)
    max_hr: int | None = Field(default=None, ge=0)
    calories: float | None = Field(default=None, ge=0)
    created_at: datetime = Field(default_factory=_utcnow)

    strength_total_volume_kg: float | None = Field(default=None, ge=0)
    strength_total_sets: int | None = Field(default=None, ge=0)
    strength_exercises_count: int | None = Field(default=None, ge=0)

    cardio_detail: Mapped[Optional["CardioDetail"]] = Relationship(
        back_populates="workout",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"},
    )
    strength_detail: Mapped[Optional["StrengthDetail"]] = Relationship(
        back_populates="workout",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"},
    )
    sesiones_planificadas: Mapped[list["SesionPlanificada"]] = Relationship(
        back_populates="workout",
    )


class CardioDetail(SQLModel, table=True):
    """Optional cardio detail attached 1:0..1 to a Workout of type cardio (Requirement 3.2)."""

    __tablename__ = "cardio_detail"

    id: int | None = Field(default=None, primary_key=True)
    workout_id: int = Field(foreign_key="workout.id", unique=True, index=True)

    gps_polyline: str | None = Field(default=None)
    avg_pace_s_per_km: float | None = Field(default=None, ge=0)
    splits: list[dict] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="Per-split metrics as JSON-serializable dicts.",
    )

    workout: Mapped["Workout"] = Relationship(back_populates="cardio_detail")


class StrengthDetail(SQLModel, table=True):
    """Manually-enriched strength detail (Requirement 3.4, 3.5)."""

    __tablename__ = "strength_detail"

    id: int | None = Field(default=None, primary_key=True)
    workout_id: int = Field(foreign_key="workout.id", unique=True, index=True)

    exercise: str
    sets: int = Field(ge=1)
    reps: int = Field(ge=1)
    weight_kg: float = Field(ge=0)

    workout: Mapped["Workout"] = Relationship(back_populates="strength_detail")


def recompute_strength_summary(workout: Workout, detail: StrengthDetail) -> None:
    """Recompute and store the embedded strength summary for a workout (Req 3.3)."""
    if workout.type is not WorkoutType.STRENGTH:
        raise ValueError("recompute_strength_summary only applies to strength workouts")
    workout.strength_total_sets = detail.sets
    workout.strength_total_volume_kg = detail.sets * detail.reps * detail.weight_kg
    workout.strength_exercises_count = 1
