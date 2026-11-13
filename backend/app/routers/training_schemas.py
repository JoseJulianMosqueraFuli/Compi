"""Request/response schemas for availability, preferences and recommendations."""
from datetime import date, datetime, time, timedelta
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.domain import SessionKind, SessionStatus
from app.models.training import RecommendedSession
from app.services.recommender.catalog import EXERCISES
from app.services.recommender.compare import SessionComparison
from app.services.recommender.types import Prescription


class WindowIn(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0 = Monday ... 6 = Sunday.")
    start_time: time
    end_time: time
    gym_access: bool = False

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class WindowOut(WindowIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ExceptionIn(BaseModel):
    day: date
    start_time: time | None = None
    end_time: time | None = None
    gym_access: bool = False
    note: str | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("give both start_time and end_time, or neither to block the day")
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("end_time must be after start_time")
        return self


class ExceptionOut(ExceptionIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    week_plan_id: int
    session_id: int | None
    created_at: datetime
    trigger: str
    kind: str
    summary: str
    reason: str


class AvailabilityOut(BaseModel):
    windows: list[WindowOut]
    exceptions: list[ExceptionOut]
    changes: list[ChangeOut] = Field(
        default_factory=list, description="What this edit changed in the stored weeks."
    )


class PreferencesIn(BaseModel):
    timezone: str = "UTC"
    strength_sessions_per_week: int = Field(default=3, ge=0, le=4)
    run_sessions_per_week: int = Field(default=2, ge=0, le=4)
    walk_sessions_per_week: int = Field(default=2, ge=0, le=7)
    strength_minutes: int = Field(default=60, ge=20, le=150)
    run_minutes: int = Field(default=30, ge=10, le=120)
    walk_minutes: int = Field(default=30, ge=10, le=180)
    excluded_exercises: list[str] = Field(default_factory=list)

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone: {value}") from exc
        return value

    @field_validator("excluded_exercises")
    @classmethod
    def _known_exercises(cls, value: list[str]) -> list[str]:
        unknown = [key for key in value if key not in EXERCISES]
        if unknown:
            raise ValueError(f"unknown exercises: {', '.join(unknown)}")
        return value


class PreferencesOut(PreferencesIn):
    model_config = ConfigDict(from_attributes=True)


class CatalogExerciseOut(BaseModel):
    key: str
    name: str
    priority: int
    sets: int
    rep_min: int
    rep_max: int
    rest_s: int


class SetIn(BaseModel):
    reps: int = Field(ge=0)
    weight_kg: float = Field(ge=0)
    rest_s: int | None = Field(default=None, ge=0)
    rpe: float | None = Field(default=None, ge=1, le=10)


class SetOut(SetIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_index: int


class ExerciseIn(BaseModel):
    exercise_key: str | None = None
    name: str | None = None
    sets: list[SetIn] = Field(min_length=1)

    @model_validator(mode="after")
    def _identified(self) -> Self:
        if self.exercise_key not in EXERCISES and not (self.name and self.name.strip()):
            raise ValueError("give a catalog exercise_key or a name")
        return self


class ExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_index: int
    exercise_key: str | None
    name: str
    sets: list[SetOut]


class SessionLogIn(BaseModel):
    workout_id: int | None = Field(
        default=None, description="Existing (e.g. synced) workout to record this session on."
    )
    started_at: datetime | None = None
    duration_min: float | None = Field(default=None, gt=0, le=600)
    exercises: list[ExerciseIn] = Field(default_factory=list)
    distance_km: float | None = Field(default=None, ge=0)
    perceived_effort: int | None = Field(default=None, ge=1, le=10)
    notes: str | None = None


class SkipIn(BaseModel):
    reason: str | None = None


class SessionOut(BaseModel):
    id: int
    week_plan_id: int
    order_index: int
    kind: SessionKind
    title: str
    requires_gym: bool
    status: SessionStatus
    day: date | None
    start_time: time | None
    end_time: time | None
    planned_minutes: int | None
    full_minutes: int
    prescription: Prescription
    reasons: list[str]
    workout_id: int | None
    skip_reason: str | None
    comparison: SessionComparison | None = None

    @classmethod
    def of(cls, s: RecommendedSession, comparison: SessionComparison | None = None) -> Self:
        end = None
        if s.day and s.start_time and s.planned_minutes is not None:
            end = (
                datetime.combine(s.day, s.start_time) + timedelta(minutes=s.planned_minutes)
            ).time()
        return cls(
            id=s.id,  # type: ignore[arg-type]
            week_plan_id=s.week_plan_id,
            order_index=s.order_index,
            kind=s.kind,
            title=s.title,
            requires_gym=s.requires_gym,
            status=s.status,
            day=s.day,
            start_time=s.start_time,
            end_time=end,
            planned_minutes=s.planned_minutes,
            full_minutes=s.full_minutes,
            prescription=Prescription.model_validate(s.prescription),
            reasons=list(s.reasons or []),
            workout_id=s.workout_id,
            skip_reason=s.skip_reason,
            comparison=comparison,
        )


class WeekIn(BaseModel):
    day: date | None = Field(default=None, description="Any date of the week; today if omitted.")
    regenerate: bool = False


class WeekOut(BaseModel):
    id: int
    week_start: date
    week_end: date
    duration_factor: float
    sessions: list[SessionOut]
    changes: list[ChangeOut]


class DurationPointOut(BaseModel):
    session_id: int
    title: str
    day: date | None
    kind: SessionKind
    estimated_min: int
    actual_min: float


class StrengthPointOut(BaseModel):
    day: date
    top_weight_kg: float
    best_reps: int
    volume_kg: float


class StrengthProgressOut(BaseModel):
    key: str
    name: str
    points: list[StrengthPointOut]


class RunPointOut(BaseModel):
    day: date
    minutes: float
    distance_km: float | None
    pace_s_per_km: float | None


class EvaluationOut(BaseModel):
    sessions: dict[str, int]
    duration_factor: float
    duration_mean_abs_error_min: float | None
    durations: list[DurationPointOut]
    mean_adherence: float | None
    adjustments: dict[str, int]
    strength_progress: list[StrengthProgressOut]
    runs: list[RunPointOut]
