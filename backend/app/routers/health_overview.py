"""Private read side of HealthKit ingestion, served only by the computer's dashboard API."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from app.db import get_session
from app.models.health import HealthObservation, HealthSyncCursor
from app.services.duration_experiment import Evaluation, evaluate_sessions, source_sessions

router = APIRouter(prefix="/api/healthkit", tags=["healthkit-dashboard"])
SessionDep = Annotated[Session, Depends(get_session)]


class Coverage(BaseModel):
    kind: str
    samples: int
    sources: list[str]
    last_batch: datetime | None


class SourceSelection(BaseModel):
    source: str = Field(min_length=1, max_length=255)


@router.get("/coverage", response_model=list[Coverage])
def coverage(session: SessionDep) -> list[Coverage]:
    coverage_by_kind = {
        kind: Coverage(kind=kind, samples=0, sources=[], last_batch=None)
        for kind in ("workout", "heart_rate", "sleep", "body_mass")
    }
    for cursor in session.exec(select(HealthSyncCursor)):
        stamp = cursor.updated_at
        coverage_by_kind[cursor.kind].last_batch = stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)
    rows = session.exec(
        select(HealthObservation.kind, HealthObservation.source_bundle, func.count())
        .group_by(HealthObservation.kind, HealthObservation.source_bundle)
        .order_by(HealthObservation.source_bundle)
    )
    for kind, source, count in rows:
        coverage_by_kind[kind].sources.append(source)
        coverage_by_kind[kind].samples += count
    return list(coverage_by_kind.values())


@router.post("/duration-evaluation", response_model=Evaluation)
def duration_evaluation(selection: SourceSelection, session: SessionDep) -> Evaluation:
    return evaluate_sessions(source_sessions(session, selection.source))
