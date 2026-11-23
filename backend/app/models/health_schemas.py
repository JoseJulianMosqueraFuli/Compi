"""Wire contract shared with the HealthKit companion."""

from datetime import UTC
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

ObservationKind = Literal["heart_rate", "body_mass", "sleep", "workout"]
FiniteNumber = Annotated[float, Field(strict=True, allow_inf_nan=False)]
MAX_CHANGES = 500
CATEGORIES = {
    "sleep": {"in_bed", "awake", "asleep", "core", "deep", "rem", "unknown"},
    "workout": {"strength", "walk", "run", "other"},
}


class HealthSampleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: UUID
    source_bundle: Annotated[str, Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9.-]+$")]
    start: AwareDatetime
    end: AwareDatetime
    value: FiniteNumber | Annotated[str, Field(strict=True, min_length=1, max_length=20)]
    duration_s: Annotated[FiniteNumber, Field(ge=0)] | None = None

    @field_validator("start", "end")
    @classmethod
    def normalize_timezone(cls, value: AwareDatetime) -> AwareDatetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.end < self.start:
            raise ValueError("end must be on or after start")
        return self


class HealthBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stream_id: UUID
    kind: ObservationKind
    sequence: Annotated[int, Field(strict=True, ge=1, le=2**63 - 1)]
    upserts: list[HealthSampleIn] = Field(max_length=MAX_CHANGES)
    deletions: list[UUID] = Field(max_length=MAX_CHANGES)

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        sample_ids = [sample.sample_id for sample in self.upserts] + self.deletions
        if len(sample_ids) > MAX_CHANGES:
            raise ValueError("batch exceeds the change limit")
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("each sample may occur only once per batch")
        for sample in self.upserts:
            if self.kind in CATEGORIES:
                if sample.value not in CATEGORIES[self.kind]:
                    raise ValueError("unsupported category for this observation kind")
            elif not isinstance(sample.value, float) or sample.value <= 0:
                raise ValueError("heart rate (bpm) and body mass (kg) must be positive numbers")
            if self.kind != "workout" and sample.duration_s is not None:
                raise ValueError("active duration applies only to workouts")
        return self


class HealthBatchAck(BaseModel):
    sequence: int
    applied: bool
