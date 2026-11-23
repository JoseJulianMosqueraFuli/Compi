"""Explicit reconciliation of source observations with the user's editable workout log."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlmodel import Session, col, select

from app.db import get_session
from app.models.domain import SessionKind, WorkoutType
from app.models.health import HealthObservation
from app.models.health_workout import HealthWorkoutLink
from app.models.workout import Workout

router = APIRouter(prefix="/api/healthkit/workouts", tags=["healthkit-dashboard"])
SessionDep = Annotated[Session, Depends(get_session)]


class ImportedWorkout(BaseModel):
    sample_id: UUID
    source_bundle: str
    start: datetime
    end: datetime
    activity: str
    workout_id: int | None


class ConfirmWorkout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workout_id: Annotated[int, Field(strict=True, ge=1)] | None = None


class ConfirmedWorkout(BaseModel):
    workout_id: int


def _utc(value: datetime) -> datetime:
    # Observations are written in UTC; SQLite returns naive values.
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


@router.get("", response_model=list[ImportedWorkout])
def imported_workouts(
    session: SessionDep,
    source: Annotated[str, Query(min_length=1, max_length=255)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ImportedWorkout]:
    stmt = (
        select(HealthObservation, HealthWorkoutLink.workout_id)
        .outerjoin(HealthWorkoutLink, col(HealthWorkoutLink.sample_id) == col(HealthObservation.sample_id))
        .where(HealthObservation.kind == "workout", HealthObservation.source_bundle == source)
        .order_by(col(HealthObservation.start).desc(), col(HealthObservation.sample_id))
        .limit(limit)
    )
    return [
        ImportedWorkout(
            sample_id=sample.sample_id, source_bundle=sample.source_bundle, start=_utc(sample.start),
            end=_utc(sample.end), activity=sample.category_value, workout_id=workout_id,
        )
        for sample, workout_id in session.exec(stmt)
    ]


@router.post("/{sample_id}/confirm", response_model=ConfirmedWorkout)
def confirm_workout(sample_id: UUID, selection: ConfirmWorkout, session: SessionDep) -> ConfirmedWorkout:
    with session.begin():
        # PostgreSQL locks the source row. SQLite has no row locks; acquire its write
        # lock before reading to prevent simultaneous requests from making two snapshots.
        if session.get_bind().dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))
        sample = session.get(HealthObservation, ("workout", sample_id), with_for_update=True)
        link = session.get(HealthWorkoutLink, sample_id)
        if link is not None:
            if selection.workout_id is not None and selection.workout_id != link.workout_id:
                raise HTTPException(409, "Sample already confirmed with another workout")
            return ConfirmedWorkout(workout_id=link.workout_id)
        if sample is None:
            raise HTTPException(404, "Unknown workout sample")
        try:
            kind = SessionKind(sample.category_value)
        except ValueError:
            raise HTTPException(422, "Unsupported workout activity") from None
        if selection.workout_id is None:
            duration = int((_utc(sample.end) - _utc(sample.start)).total_seconds())
            if duration > 2**31 - 1:
                raise HTTPException(422, "Elapsed duration exceeds the supported workout range")
            workout = Workout(
                external_id=f"manual-{uuid4().hex}", type=kind.workout_type, subtype=kind.value,
                start_time=_utc(sample.start), duration_s=duration,
            )
            session.add(workout)
            session.flush()
        else:
            workout = session.get(Workout, selection.workout_id, with_for_update=True)
            if workout is None:
                raise HTTPException(404, "Unknown target workout")
            if workout.type != kind.workout_type or (
                workout.type == WorkoutType.CARDIO and workout.subtype not in (None, kind.value)
            ):
                raise HTTPException(409, "Target workout has an incompatible activity")
        session.add(HealthWorkoutLink(sample_id=sample_id, workout_id=workout.id))
        return ConfirmedWorkout(workout_id=workout.id)
