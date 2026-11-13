"""Availability, preferences and recommended sessions.

What the recommender proposed lives here and is never rewritten by logging: what was
actually done is stored in Workout / WorkoutExercise / ExerciseSet and only linked.
"""
from datetime import UTC, date, datetime, time

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.domain import SessionKind, SessionStatus

TRAINING_PREFERENCES_SINGLETON_ID = 1


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AvailabilityWindow(SQLModel, table=True):
    """A free window of the habitual week, in the user's local time."""

    __tablename__ = "availability_window"

    id: int | None = Field(default=None, primary_key=True)
    weekday: int = Field(ge=0, le=6, index=True, description="0 = Monday ... 6 = Sunday.")
    start_time: time
    end_time: time
    gym_access: bool = Field(default=False)


class AvailabilityException(SQLModel, table=True):
    """Overrides the habitual windows of one date.

    Any exception on a date replaces that date's habitual windows. A row without times
    blocks the day; a row with times is a window that exists only on that date.
    """

    __tablename__ = "availability_exception"

    id: int | None = Field(default=None, primary_key=True)
    day: date = Field(index=True)
    start_time: time | None = Field(default=None)
    end_time: time | None = Field(default=None)
    gym_access: bool = Field(default=False)
    note: str | None = Field(default=None)


class TrainingPreferences(SQLModel, table=True):
    """Singleton with what the user wants from a week (MVP single-user)."""

    __tablename__ = "training_preferences"

    id: int = Field(default=TRAINING_PREFERENCES_SINGLETON_ID, primary_key=True)
    timezone: str = Field(default="UTC", description="IANA zone the windows are expressed in.")
    strength_sessions_per_week: int = Field(default=3, ge=0, le=4)
    run_sessions_per_week: int = Field(default=2, ge=0, le=4)
    walk_sessions_per_week: int = Field(default=2, ge=0, le=7)
    strength_minutes: int = Field(default=60, ge=20, le=150)
    run_minutes: int = Field(default=30, ge=10, le=120)
    walk_minutes: int = Field(default=30, ge=10, le=180)
    excluded_exercises: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=_utcnow)


class WeekPlan(SQLModel, table=True):
    """The recommended week starting on a Monday."""

    __tablename__ = "week_plan"

    id: int | None = Field(default=None, primary_key=True)
    week_start: date = Field(unique=True, index=True)
    duration_factor: float = Field(
        default=1.0, description="Real/estimated strength duration ratio used for this plan."
    )
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class RecommendedSession(SQLModel, table=True):
    """One session the recommender proposed, with where it was placed and why."""

    __tablename__ = "recommended_session"

    id: int | None = Field(default=None, primary_key=True)
    week_plan_id: int = Field(foreign_key="week_plan.id", index=True)
    order_index: int = Field(ge=1)
    kind: SessionKind
    template_key: str
    title: str
    requires_gym: bool = Field(default=False)
    status: SessionStatus = Field(default=SessionStatus.PENDING)

    # Placement in local time; all None while the session does not fit anywhere.
    day: date | None = Field(default=None, index=True)
    start_time: time | None = Field(default=None)
    planned_minutes: int | None = Field(default=None, ge=0)

    full_minutes: int = Field(ge=0, description="Estimated minutes of the full version.")
    min_minutes: int = Field(ge=0, description="Estimated minutes of the shortest useful version.")

    base_prescription: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="Full version as first recommended; every recalculation starts from it.",
    )
    prescription: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="Version in force for the current placement.",
    )
    reasons: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    workout_id: int | None = Field(default=None, foreign_key="workout.id", index=True)
    skip_reason: str | None = Field(default=None)
    updated_at: datetime = Field(default_factory=_utcnow)


class PlanChange(SQLModel, table=True):
    """What a recalculation changed in a week and why."""

    __tablename__ = "plan_change"

    id: int | None = Field(default=None, primary_key=True)
    week_plan_id: int = Field(foreign_key="week_plan.id", index=True)
    session_id: int | None = Field(default=None, foreign_key="recommended_session.id", index=True)
    created_at: datetime = Field(default_factory=_utcnow)
    trigger: str
    kind: str
    summary: str
    reason: str
