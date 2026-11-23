"""Private read side of HealthKit ingestion, served only by the computer's dashboard API."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Self
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from sqlalchemy import func, or_
from sqlmodel import Session, col, select

from app.db import get_session
from app.models.health import HealthObservation, HealthSyncCursor
from app.models.health_schemas import ObservationKind
from app.services.duration_experiment import Evaluation, evaluate_sessions, source_sessions

router = APIRouter(prefix="/api/healthkit", tags=["healthkit-dashboard"])
SessionDep = Annotated[Session, Depends(get_session)]


class Coverage(BaseModel):
    kind: str
    samples: int
    sources: list[str]
    latest_by_source: dict[str, datetime] = Field(default_factory=dict)
    last_batch: datetime | None


class SourceSelection(BaseModel):
    source: str = Field(min_length=1, max_length=255)


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


class IntervalSelection(SourceSelection):
    kind: ObservationKind
    start: AwareDatetime
    end: AwareDatetime
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if not timedelta(0) < self.end - self.start <= timedelta(days=2):
            raise ValueError("choose a time interval of up to two days")
        return self


class TimelineSample(BaseModel):
    sample_id: UUID
    start: datetime
    end: datetime
    value: float | str


class TimelinePage(BaseModel):
    samples: list[TimelineSample]
    has_more: bool


@router.get("/coverage", response_model=list[Coverage])
def coverage(session: SessionDep) -> list[Coverage]:
    coverage_by_kind = {
        kind: Coverage(kind=kind, samples=0, sources=[], last_batch=None)
        for kind in ("workout", "heart_rate", "sleep", "body_mass")
    }
    for cursor in session.exec(select(HealthSyncCursor)):
        coverage_by_kind[cursor.kind].last_batch = _utc(cursor.updated_at)
    rows = session.exec(
        select(
            HealthObservation.kind,
            HealthObservation.source_bundle,
            func.count(),
            func.max(HealthObservation.start),
        )
        .group_by(HealthObservation.kind, HealthObservation.source_bundle)
        .order_by(HealthObservation.source_bundle)
    )
    for kind, source, count, latest in rows:
        coverage_by_kind[kind].sources.append(source)
        coverage_by_kind[kind].samples += count
        coverage_by_kind[kind].latest_by_source[source] = _utc(latest)
    return list(coverage_by_kind.values())


@router.post("/timeline", response_model=TimelinePage)
def timeline(selection: IntervalSelection, session: SessionDep) -> TimelinePage:
    start, end = _utc(selection.start), _utc(selection.end)
    begins = col(HealthObservation.start)
    in_window = begins >= start
    if selection.kind in ("sleep", "workout"):
        # Include intervals crossing midnight. The upper bound is exclusive.
        in_window = or_(in_window, col(HealthObservation.end) > start)
    page_size = 200
    rows = session.exec(
        select(HealthObservation)
        .where(
            HealthObservation.kind == selection.kind,
            HealthObservation.source_bundle == selection.source,
            begins < end,
            in_window,
        )
        .order_by(begins, col(HealthObservation.sample_id))
        .offset(selection.offset)
        .limit(page_size + 1)
    ).all()
    return TimelinePage(
        samples=[
            TimelineSample(
                sample_id=row.sample_id,
                start=_utc(row.start),
                end=_utc(row.end),
                value=row.numeric_value if row.numeric_value is not None else row.category_value,
            )
            for row in rows[:page_size]
        ],
        has_more=len(rows) > page_size,
    )


@router.post("/duration-evaluation", response_model=Evaluation)
def duration_evaluation(selection: SourceSelection, session: SessionDep) -> Evaluation:
    return evaluate_sessions(source_sessions(session, selection.source))
