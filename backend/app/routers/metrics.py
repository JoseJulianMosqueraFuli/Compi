"""Aggregate metrics endpoints (Req 7.2, 8.2, 8.3)."""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.models.auth import UserProfile
from app.repositories.workout_repo import WorkoutRepository
from app.routers.schemas import MetricsOut
from app.services.metrics_service import total_training_load, total_volume

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

SessionDep = Annotated[Session, Depends(get_session)]


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
