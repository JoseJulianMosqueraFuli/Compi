"""The recommended week: generate, recalculate, record what was done, evaluate."""
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.clock import get_now
from app.db import get_session
from app.models.domain import SessionStatus
from app.models.training import RecommendedSession, WeekPlan
from app.models.workout import Workout
from app.routers.training_schemas import (
    ChangeOut,
    EvaluationOut,
    SessionLogIn,
    SessionOut,
    SkipIn,
    WeekIn,
    WeekOut,
)
from app.services.recommender.availability import week_start_of
from app.services.week_service import (
    LoggedExercise,
    LoggedSet,
    SessionAlreadyLoggedError,
    WorkoutMismatchError,
    changes_of,
    comparison_for,
    evaluation,
    generate_week,
    get_preferences,
    local_now,
    log_session,
    replan_week,
    sessions_of,
)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(get_now)]


def _week_out(session: Session, plan: WeekPlan) -> WeekOut:
    sessions = sorted(
        sessions_of(session, plan),
        key=lambda s: (s.day is None, s.day, s.start_time, s.order_index),
    )
    return WeekOut(
        id=plan.id,  # type: ignore[arg-type]
        week_start=plan.week_start,
        week_end=date.fromordinal(plan.week_start.toordinal() + 6),
        duration_factor=plan.duration_factor,
        sessions=[SessionOut.of(s, comparison_for(session, s)) for s in sessions],
        changes=[ChangeOut.model_validate(c) for c in changes_of(session, plan)],
    )


def _get_session(session: Session, session_id: int) -> RecommendedSession:
    rec = session.get(RecommendedSession, session_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    return rec


def _get_plan(session: Session, plan_id: int) -> WeekPlan:
    plan = session.get(WeekPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="week not found")
    return plan


@router.get("/week", response_model=WeekOut)
def get_week(session: SessionDep, now: NowDep, day: date | None = None) -> WeekOut:
    """The stored week containing `day` (today if omitted); 404 until it is generated."""
    target = day or local_now(get_preferences(session), now).date()
    plan = session.exec(
        select(WeekPlan).where(WeekPlan.week_start == week_start_of(target))
    ).first()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="week not generated")
    out = _week_out(session, plan)
    session.commit()
    return out


@router.post("/week", response_model=WeekOut)
def create_week(payload: WeekIn, session: SessionDep, now: NowDep) -> WeekOut:
    """Propose the week containing `day`. With `regenerate`, pending sessions are rebuilt
    from the current preferences and history; logged and skipped ones are kept."""
    target = payload.day or local_now(get_preferences(session), now).date()
    plan = generate_week(session, target, now, regenerate=payload.regenerate)
    session.commit()
    return _week_out(session, plan)


@router.post("/week/{plan_id}/recalculate", response_model=WeekOut)
def recalculate_week(plan_id: int, session: SessionDep, now: NowDep) -> WeekOut:
    """Re-place the pending sessions in the windows still ahead."""
    plan = _get_plan(session, plan_id)
    replan_week(session, plan, now, trigger="manual")
    session.commit()
    return _week_out(session, plan)


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_recommended_session(session_id: int, session: SessionDep) -> SessionOut:
    rec = _get_session(session, session_id)
    return SessionOut.of(rec, comparison_for(session, rec))


@router.post("/sessions/{session_id}/log", response_model=SessionOut)
def log_recommended_session(
    session_id: int, payload: SessionLogIn, session: SessionDep, now: NowDep
) -> SessionOut:
    """Record what was actually done. The recommendation itself is not modified."""
    rec = _get_session(session, session_id)
    workout = None
    if payload.workout_id is not None:
        workout = session.get(Workout, payload.workout_id)
        if workout is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workout not found")
    try:
        log_session(
            session,
            rec,
            now,
            workout=workout,
            started_at=payload.started_at,
            duration_min=payload.duration_min,
            exercises=[
                LoggedExercise(
                    exercise_key=e.exercise_key,
                    name=e.name,
                    sets=[LoggedSet(s.reps, s.weight_kg, s.rest_s, s.rpe) for s in e.sets],
                )
                for e in payload.exercises
            ],
            distance_km=payload.distance_km,
            perceived_effort=payload.perceived_effort,
            notes=payload.notes,
        )
    except SessionAlreadyLoggedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="session already logged"
        ) from exc
    except WorkoutMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return SessionOut.of(rec, comparison_for(session, rec))


@router.post("/sessions/{session_id}/skip", response_model=SessionOut)
def skip_recommended_session(session_id: int, payload: SkipIn, session: SessionDep) -> SessionOut:
    rec = _get_session(session, session_id)
    if rec.status is not SessionStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="only pending sessions can be skipped"
        )
    rec.status = SessionStatus.SKIPPED
    rec.skip_reason = payload.reason
    rec.updated_at = datetime.now(UTC)
    session.add(rec)
    session.commit()
    return SessionOut.of(rec)


@router.post("/sessions/{session_id}/reopen", response_model=WeekOut)
def reopen_recommended_session(session_id: int, session: SessionDep, now: NowDep) -> WeekOut:
    """Put a skipped session back as pending and find it a window again."""
    rec = _get_session(session, session_id)
    if rec.status is not SessionStatus.SKIPPED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="only skipped sessions can be reopened"
        )
    rec.status = SessionStatus.PENDING
    rec.skip_reason = None
    session.add(rec)
    session.flush()
    plan = _get_plan(session, rec.week_plan_id)
    replan_week(session, plan, now, trigger="status")
    session.commit()
    return _week_out(session, plan)


@router.get("/evaluation", response_model=EvaluationOut)
def get_evaluation(session: SessionDep) -> EvaluationOut:
    """How the recommendations compare with what really happened."""
    out = EvaluationOut.model_validate(evaluation(session))
    session.commit()
    return out
