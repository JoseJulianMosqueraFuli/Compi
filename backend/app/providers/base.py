"""WorkoutProvider abstraction and external workout payloads (Req 5.1)."""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from app.models.domain import WorkoutType


class AuthResult(NamedTuple):
    """Outcome of an authentication call."""

    success: bool
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: datetime | None = None


class CardioPayload(BaseModel):
    """Cardio-specific payload attached to an ExternalWorkout of type cardio."""

    model_config = ConfigDict(frozen=True)

    gps_polyline: str | None = None
    avg_pace_s_per_km: float | None = Field(default=None, ge=0)
    splits: list[dict] = Field(default_factory=list)


class StrengthSummaryPayload(BaseModel):
    """Strength summary attached to an ExternalWorkout of type strength (Req 3.3)."""

    model_config = ConfigDict(frozen=True)

    total_volume_kg: float = Field(ge=0)
    total_sets: int = Field(ge=0)
    exercises_count: int = Field(ge=0)


class ExternalWorkout(BaseModel):
    """A workout as returned by an external provider, before persisting (Req 5.1).

    `external_id` is the deduplication key (Req 6.2, 6.3).
    """

    model_config = ConfigDict(frozen=True)

    external_id: str = Field(min_length=1)
    type: WorkoutType
    start_time: datetime
    duration_s: int = Field(ge=0)
    avg_hr: int | None = Field(default=None, ge=0)
    max_hr: int | None = Field(default=None, ge=0)
    calories: float | None = Field(default=None, ge=0)
    cardio: CardioPayload | None = None
    strength_summary: StrengthSummaryPayload | None = None


class WorkoutProvider(ABC):
    """Common interface for any external workout source (Req 5.1, 5.3)."""

    @abstractmethod
    def authenticate(self) -> AuthResult:
        """Authenticate against the provider (no-op for MockProvider, Req 5.4)."""

    @abstractmethod
    def is_authenticated(self) -> bool:
        """True if a valid token is available; for Huawei this triggers refresh if expired."""

    @abstractmethod
    def fetch_workouts(self, since: datetime) -> list[ExternalWorkout]:
        """Return workouts whose start_time is >= since."""
