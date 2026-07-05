"""Workout endpoints (Req 7.1, 7.4, 3.5, 8.1)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db import get_session
from app.models.auth import UserProfile
from app.models.workout import StrengthDetail, recompute_strength_summary
from app.repositories.workout_repo import WorkoutRepository
from app.routers.schemas import (
    HRZoneOut,
    HRZonesOut,
    StrengthDetailIn,
    StrengthDetailOut,
    WorkoutOut,
)
from app.services.metrics_service import compute_hr_zones

router = APIRouter(prefix="/api/workouts", tags=["workouts"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[WorkoutOut])
def list_workouts(
    session: SessionDep,
    workout_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[WorkoutOut]:
    repo = WorkoutRepository(session)
    items = repo.list(limit=limit, offset=offset)
    if workout_type is not None:
        items = [w for w in items if w.type.value == workout_type]
    return [WorkoutOut.model_validate(w) for w in items]


@router.get("/{workout_id}", response_model=WorkoutOut)
def get_workout(workout_id: int, session: SessionDep) -> WorkoutOut:
    repo = WorkoutRepository(session)
    try:
        workout = repo.get(workout_id)
    except LookupError as exc:  # WorkoutNotFoundError -> 404 via handler in main.py
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workout not found") from exc
    return WorkoutOut.model_validate(workout)


@router.post(
    "/{workout_id}/strength-detail",
    response_model=StrengthDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def attach_strength_detail(
    workout_id: int, payload: StrengthDetailIn, session: SessionDep
) -> StrengthDetailOut:
    repo = WorkoutRepository(session)
    try:
        workout = repo.get(workout_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workout not found") from exc
    detail = StrengthDetail(
        workout_id=workout.id,  # type: ignore[arg-type]
        exercise=payload.exercise,
        sets=payload.sets,
        reps=payload.reps,
        weight_kg=payload.weight_kg,
    )
    recompute_strength_summary(workout, detail)
    session.add(workout)
    repo.attach_strength_detail(workout.id, detail)  # type: ignore[arg-type]
    session.commit()
    return StrengthDetailOut.model_validate(detail)


@router.get("/{workout_id}/metrics", response_model=HRZonesOut)
def workout_metrics(workout_id: int, session: SessionDep) -> HRZonesOut:
    repo = WorkoutRepository(session)
    try:
        workout = repo.get(workout_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workout not found") from exc
    profile = session.get(UserProfile, 1)
    hr_max = profile.hr_max_bpm if profile is not None else 190
    zones = compute_hr_zones(hr_max)
    duration = workout.duration_s
    # Distribute duration across the 5 zones; the MVP uses a uniform split as a
    # first approximation (Design -> Formulas -> seconds_in_zone).
    per_zone = duration // 5
    leftovers = duration - per_zone * 5
    secs = [per_zone] * 5
    secs[0] += leftovers
    return HRZonesOut(
        hr_max_bpm=hr_max,
        zones=[
            HRZoneOut(
                zone=z.zone,
                lower_bpm=z.lower_bpm,
                upper_bpm=z.upper_bpm,
                seconds_in_zone=secs[i],
            )
            for i, z in enumerate(zones)
        ],
    )
