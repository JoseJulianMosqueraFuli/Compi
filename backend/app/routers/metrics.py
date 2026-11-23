"""Aggregate metrics endpoints (Req 7.2, 8.2, 8.3)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.db import get_session
from app.models.auth import DEFAULT_HR_MAX_BPM, UserProfile
from app.models.domain import WorkoutType
from app.models.workout import Workout
from app.repositories.workout_repo import WorkoutRepository
from app.routers.schemas import MetricsOut
from app.services.metrics_service import total_training_load, total_volume

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

SessionDep = Annotated[Session, Depends(get_session)]


class ActivityTotals(BaseModel):
    strength_kg: float | None
    cardio_minutes: float | None
    estimated_load: float | None
    sessions_with_avg_hr: int


@router.get("/activity-totals", response_model=ActivityTotals)
def activity_totals(session: SessionDep) -> ActivityTotals:
    strength = session.exec(
        select(func.sum(Workout.strength_total_volume_kg)).where(Workout.type == WorkoutType.STRENGTH)
    ).one()
    cardio = session.exec(
        select(func.sum(Workout.duration_s)).where(Workout.type == WorkoutType.CARDIO)
    ).one()
    weighted, sessions = session.exec(
        select(func.sum(col(Workout.duration_s) / 60.0 * col(Workout.avg_hr)), func.count()).where(
            col(Workout.avg_hr) > 0
        )
    ).one()
    profile = session.get(UserProfile, 1)
    hr_max = profile.hr_max_bpm if profile else DEFAULT_HR_MAX_BPM
    return ActivityTotals(
        strength_kg=strength,
        cardio_minutes=None if cardio is None else cardio / 60,
        estimated_load=None if weighted is None else float(weighted) / hr_max,
        sessions_with_avg_hr=sessions,
    )


@router.get("/volume", response_model=MetricsOut)
def aggregate_volume(session: SessionDep) -> MetricsOut:
    repo = WorkoutRepository(session)
    workouts = repo.list(limit=10_000)
    return MetricsOut(total=total_volume(workouts))


@router.get("/load", response_model=MetricsOut)
def aggregate_load(session: SessionDep) -> MetricsOut:
    repo = WorkoutRepository(session)
    workouts = repo.list(limit=10_000)
    profile = session.get(UserProfile, 1)
    hr_max = profile.hr_max_bpm if profile is not None else 190
    return MetricsOut(total=total_training_load(workouts, hr_max))
