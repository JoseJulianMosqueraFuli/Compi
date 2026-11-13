"""Habitual week, date exceptions, preferences and the exercise catalog.

Editing availability recalculates the pending sessions of every week still open and
returns what changed and why.
"""
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, col, select

from app.clock import get_now
from app.db import get_session
from app.models.training import AvailabilityException, AvailabilityWindow, PlanChange
from app.routers.training_schemas import (
    AvailabilityOut,
    CatalogExerciseOut,
    ChangeOut,
    ExceptionIn,
    ExceptionOut,
    PreferencesIn,
    PreferencesOut,
    WindowIn,
    WindowOut,
)
from app.services.recommender.catalog import EXERCISES
from app.services.week_service import get_preferences, local_now, replan_active_weeks

router = APIRouter(prefix="/api", tags=["availability"])

SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(get_now)]

EXCEPTIONS_LOOKBACK_DAYS = 7


def _availability(
    session: Session, today: date, changes: list[PlanChange] | None = None
) -> AvailabilityOut:
    windows = session.exec(
        select(AvailabilityWindow).order_by(
            col(AvailabilityWindow.weekday), col(AvailabilityWindow.start_time)
        )
    ).all()
    exceptions = session.exec(
        select(AvailabilityException)
        .where(col(AvailabilityException.day) >= today - timedelta(days=EXCEPTIONS_LOOKBACK_DAYS))
        .order_by(col(AvailabilityException.day), col(AvailabilityException.start_time))
    ).all()
    return AvailabilityOut(
        windows=[WindowOut.model_validate(w) for w in windows],
        exceptions=[ExceptionOut.model_validate(e) for e in exceptions],
        changes=[ChangeOut.model_validate(c) for c in changes or []],
    )


def _recalculate(session: Session, now: datetime) -> AvailabilityOut:
    changes = replan_active_weeks(session, now, trigger="availability")
    session.commit()
    today = local_now(get_preferences(session), now).date()
    return _availability(session, today, changes)


@router.get("/availability", response_model=AvailabilityOut)
def get_availability(session: SessionDep, now: NowDep) -> AvailabilityOut:
    today = local_now(get_preferences(session), now).date()
    session.commit()
    return _availability(session, today)


@router.put("/availability/windows", response_model=AvailabilityOut)
def replace_windows(payload: list[WindowIn], session: SessionDep, now: NowDep) -> AvailabilityOut:
    """Replace the whole habitual week."""
    by_day: dict[int, list[WindowIn]] = {}
    for window in payload:
        by_day.setdefault(window.weekday, []).append(window)
    for windows in by_day.values():
        ordered = sorted(windows, key=lambda w: w.start_time)
        for earlier, later in zip(ordered, ordered[1:], strict=False):
            if later.start_time < earlier.end_time:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="windows of the same weekday must not overlap",
                )
    for old in session.exec(select(AvailabilityWindow)).all():
        session.delete(old)
    session.flush()
    session.add_all(AvailabilityWindow(**w.model_dump()) for w in payload)
    session.flush()
    return _recalculate(session, now)


@router.post(
    "/availability/exceptions",
    response_model=AvailabilityOut,
    status_code=status.HTTP_201_CREATED,
)
def add_exception(payload: ExceptionIn, session: SessionDep, now: NowDep) -> AvailabilityOut:
    """Override one date: a window that exists only that day, or the day blocked."""
    session.add(AvailabilityException(**payload.model_dump()))
    session.flush()
    return _recalculate(session, now)


@router.delete("/availability/exceptions/{exception_id}", response_model=AvailabilityOut)
def delete_exception(exception_id: int, session: SessionDep, now: NowDep) -> AvailabilityOut:
    exception = session.get(AvailabilityException, exception_id)
    if exception is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="exception not found")
    session.delete(exception)
    session.flush()
    return _recalculate(session, now)


@router.get("/preferences", response_model=PreferencesOut)
def read_preferences(session: SessionDep) -> PreferencesOut:
    prefs = get_preferences(session)
    session.commit()
    return PreferencesOut.model_validate(prefs)


@router.put("/preferences", response_model=PreferencesOut)
def update_preferences(payload: PreferencesIn, session: SessionDep, now: NowDep) -> PreferencesOut:
    """Store what the user wants from a week. Existing weeks keep their sessions until
    they are regenerated; a timezone change does move what counts as 'now'."""
    prefs = get_preferences(session)
    for field, value in payload.model_dump().items():
        setattr(prefs, field, value)
    prefs.updated_at = now
    session.add(prefs)
    session.commit()
    return PreferencesOut.model_validate(prefs)


@router.get("/exercises", response_model=list[CatalogExerciseOut])
def list_exercises() -> list[CatalogExerciseOut]:
    return [
        CatalogExerciseOut(
            key=e.key,
            name=e.name,
            priority=e.priority,
            sets=e.sets,
            rep_min=e.rep_min,
            rep_max=e.rep_max,
            rest_s=e.rest_s,
        )
        for e in EXERCISES.values()
    ]
