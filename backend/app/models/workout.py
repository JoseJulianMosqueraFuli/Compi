"""Workout, CardioDetail and the per-set strength log (Requirement 3.1–3.5)."""
from collections.abc import Iterable
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
    subtype: str | None = Field(
        default=None, description="Finer activity within the type, e.g. 'run' or 'walk'."
    )
    start_time: datetime
    duration_s: int = Field(ge=0)
    avg_hr: int | None = Field(default=None, ge=0)
    max_hr: int | None = Field(default=None, ge=0)
    calories: float | None = Field(default=None, ge=0)
    perceived_effort: int | None = Field(default=None, ge=1, le=10)
    notes: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)

    strength_total_volume_kg: float | None = Field(default=None, ge=0)
    strength_total_sets: int | None = Field(default=None, ge=0)
    strength_exercises_count: int | None = Field(default=None, ge=0)

    cardio_detail: Mapped[Optional["CardioDetail"]] = Relationship(
        back_populates="workout",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"},
    )
    exercises: Mapped[list["WorkoutExercise"]] = Relationship(
        back_populates="workout",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "WorkoutExercise.order_index",
        },
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
    distance_m: float | None = Field(default=None, ge=0)
    splits: list[dict] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="Per-split metrics as JSON-serializable dicts.",
    )

    workout: Mapped["Workout"] = Relationship(back_populates="cardio_detail")


class WorkoutExercise(SQLModel, table=True):
    """One exercise performed within a strength workout (Requirement 3.4, 3.5)."""

    __tablename__ = "workout_exercise"

    id: int | None = Field(default=None, primary_key=True)
    workout_id: int = Field(foreign_key="workout.id", index=True)
    order_index: int = Field(ge=1)
    exercise_key: str | None = Field(
        default=None,
        index=True,
        description="Catalog key; None for exercises the catalog does not know.",
    )
    name: str

    workout: Mapped["Workout"] = Relationship(back_populates="exercises")
    sets: Mapped[list["ExerciseSet"]] = Relationship(
        back_populates="exercise",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "ExerciseSet.order_index",
        },
    )


class ExerciseSet(SQLModel, table=True):
    """A single set as it was actually done: its own weight, reps, rest and effort."""

    __tablename__ = "exercise_set"

    id: int | None = Field(default=None, primary_key=True)
    workout_exercise_id: int = Field(foreign_key="workout_exercise.id", index=True)
    order_index: int = Field(ge=1)
    reps: int = Field(ge=0)
    weight_kg: float = Field(ge=0)
    rest_s: int | None = Field(default=None, ge=0, description="Rest taken after this set.")
    rpe: float | None = Field(default=None, ge=1, le=10)

    exercise: Mapped["WorkoutExercise"] = Relationship(back_populates="sets")


def recompute_strength_summary(workout: Workout, exercises: Iterable[WorkoutExercise]) -> None:
    """Recompute and store the embedded strength summary for a workout (Req 3.3)."""
    if workout.type is not WorkoutType.STRENGTH:
        raise ValueError("recompute_strength_summary only applies to strength workouts")
    exercise_list = list(exercises)
    all_sets = [s for e in exercise_list for s in e.sets]
    workout.strength_total_sets = len(all_sets)
    workout.strength_total_volume_kg = float(sum(s.reps * s.weight_kg for s in all_sets))
    workout.strength_exercises_count = len(exercise_list)
