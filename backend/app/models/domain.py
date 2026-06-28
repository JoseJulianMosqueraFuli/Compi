"""Domain value types and enums used across models, services, and providers."""
from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class WorkoutType(str, Enum):
    """Discriminator for the kind of workout (Requirement 3.1)."""

    CARDIO = "cardio"
    STRENGTH = "strength"


class Split(BaseModel):
    """One split of a cardio workout (e.g. per km)."""

    model_config = ConfigDict(frozen=True)

    distance_m: float = Field(ge=0)
    duration_s: float = Field(ge=0)
    pace_s_per_km: float | None = Field(default=None, ge=0)


class HRZone(BaseModel):
    """A heart-rate training zone for a given hr_max (Requirement 8.1)."""

    model_config = ConfigDict(frozen=True)

    zone: int = Field(ge=1, le=5)
    lower_bpm: int = Field(ge=0)
    upper_bpm: int = Field(ge=0)
    seconds_in_zone: int = Field(ge=0, default=0)


class ProgressionPoint(BaseModel):
    """A point in a mesocycle progression (Requirement 9.1, 9.2)."""

    model_config = ConfigDict(frozen=True)

    microciclo_id: int
    target_load: float = Field(ge=0)
    is_deload: bool = False


class PlannedVsActual(BaseModel):
    """Comparison between planned and executed session values (Requirement 9.3)."""

    model_config = ConfigDict(frozen=True)

    planned_load: float = Field(ge=0)
    actual_load: float = Field(ge=0)
    delta: float
    delta_pct: float


PositiveInt = Annotated[int, Field(ge=0)]
