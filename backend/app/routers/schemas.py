"""Pydantic request/response schemas for the API routers."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.domain import WorkoutType


class StrengthDetailIn(BaseModel):
    exercise: str = Field(min_length=1)
    sets: int = Field(ge=1)
    reps: int = Field(ge=1)
    weight_kg: float = Field(ge=0)


class StrengthDetailOut(StrengthDetailIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class CardioDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    gps_polyline: str | None = None
    avg_pace_s_per_km: float | None = None


class WorkoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    type: WorkoutType
    start_time: datetime
    duration_s: int
    avg_hr: int | None = None
    max_hr: int | None = None
    calories: float | None = None
    strength_total_volume_kg: float | None = None
    strength_total_sets: int | None = None
    strength_exercises_count: int | None = None
    cardio_detail: CardioDetailOut | None = None
    strength_detail: StrengthDetailOut | None = None


class MetricsOut(BaseModel):
    total: float


class HRZoneOut(BaseModel):
    zone: int
    lower_bpm: int
    upper_bpm: int
    seconds_in_zone: int


class HRZonesOut(BaseModel):
    hr_max_bpm: int
    zones: list[HRZoneOut]


class MacrocicloIn(BaseModel):
    name: str = Field(min_length=1)
    start_date: date
    end_date: date


class MacrocicloOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    start_date: date
    end_date: date


class MesocicloIn(BaseModel):
    name: str = Field(min_length=1)
    order_index: int = Field(ge=1)
    start_date: date
    end_date: date
    weekly_increment_pct: float | None = None


class MesocicloOut(MesocicloIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    macrociclo_id: int


class MicrocicloIn(BaseModel):
    order_index: int = Field(ge=1)
    start_date: date
    end_date: date
    is_deload: bool = False
    base_load: float | None = Field(default=None, ge=0)


class MicrocicloOut(MicrocicloIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    mesociclo_id: int


class SesionIn(BaseModel):
    microciclo_id: int
    planned_type: WorkoutType
    planned_load: float = Field(ge=0)
    planned_volume: float | None = Field(default=None, ge=0)
    workout_id: int | None = None


class SesionOut(SesionIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ProgressionPointOut(BaseModel):
    microciclo_id: int
    target_load: float
    is_deload: bool


class ProgressionOut(BaseModel):
    macrociclo_id: int
    points: list[ProgressionPointOut]
