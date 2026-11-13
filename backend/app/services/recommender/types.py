"""Value types shared by the recommender modules."""
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, Field

from app.models.domain import SessionKind

_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def fmt_day(day: date) -> str:
    """'martes 17', the way reasons mention a date."""
    return f"{_WEEKDAYS[day.weekday()]} {day.day}"


def fmt_clock(minutes: int) -> str:
    """Minutes since midnight as HH:MM."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def fmt_kg(weight: float) -> str:
    return f"{weight:g} kg"


class SetPrescription(BaseModel):
    reps: int = Field(ge=1)
    weight_kg: float | None = Field(
        default=None, ge=0, description="None until there is history to base a weight on."
    )
    rest_s: int = Field(ge=0)


class ExercisePrescription(BaseModel):
    key: str
    name: str
    priority: int = Field(ge=1, le=3, description="1 main lift, 2 secondary, 3 accessory.")
    sets: list[SetPrescription]
    reason: str
    carried_from: str | None = Field(
        default=None, description="Title and day of the session this exercise was moved from."
    )


class Prescription(BaseModel):
    """What a session asks for: exercises for strength, a duration for run/walk."""

    kind: SessionKind
    exercises: list[ExercisePrescription] = Field(default_factory=list)
    target_minutes: int | None = Field(default=None, ge=1)
    guidance: str | None = None
    reason: str | None = None
    notes: list[str] = Field(
        default_factory=list, description="Decisions taken when the session was built."
    )


@dataclass(frozen=True)
class Slot:
    """A concrete free window on a date, in minutes since local midnight."""

    day: date
    start_min: int
    end_min: int
    gym_access: bool

    @property
    def minutes(self) -> int:
        return self.end_min - self.start_min
