"""Data-access layer for Workout, CardioDetail and StrengthDetail (Req 6.2, 6.3, 7.1, 7.4)."""
from collections.abc import Sequence
from datetime import date, datetime

from sqlmodel import Session, select

from app.models.domain import WorkoutType
from app.models.workout import CardioDetail, StrengthDetail, Workout


class WorkoutNotFoundError(LookupError):
    """Raised when a workout is queried by id and does not exist (Req 7.4)."""


class WorkoutRepository:
    """Repository encapsulating persistence and queries for workouts."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def exists(self, external_id: str) -> bool:
        """Return True iff a workout with this external_id is already stored (Req 6.2)."""
        stmt = select(Workout.id).where(Workout.external_id == external_id)
        return self._session.exec(stmt).first() is not None

    def insert(self, workout: Workout) -> Workout:
        """Persist a new workout. Caller is responsible for deduplication (Req 6.3)."""
        self._session.add(workout)
        self._session.flush()
        return workout

    def attach_cardio_detail(self, workout_id: int, detail: CardioDetail) -> CardioDetail:
        detail.workout_id = workout_id
        self._session.add(detail)
        self._session.flush()
        return detail

    def attach_strength_detail(self, workout_id: int, detail: StrengthDetail) -> StrengthDetail:
        detail.workout_id = workout_id
        self._session.add(detail)
        self._session.flush()
        return detail

    def get(self, workout_id: int) -> Workout:
        """Return the workout with the given id or raise WorkoutNotFoundError (Req 7.4)."""
        workout = self._session.get(Workout, workout_id)
        if workout is None:
            raise WorkoutNotFoundError(workout_id)
        return workout

    def get_optional(self, workout_id: int) -> Workout | None:
        """Return the workout or None without raising."""
        return self._session.get(Workout, workout_id)

    def list(
        self,
        workout_type: WorkoutType | None = None,
        since: datetime | date | None = None,
        until: datetime | date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Workout]:
        """List workouts with optional type/date filters, ordered by start_time desc."""
        stmt = select(Workout)
        if workout_type is not None:
            stmt = stmt.where(Workout.type == workout_type)
        if since is not None:
            stmt = stmt.where(Workout.start_time >= since)
        if until is not None:
            stmt = stmt.where(Workout.start_time <= until)
        stmt = stmt.order_by(Workout.start_time.desc()).offset(offset).limit(limit)
        return self._session.exec(stmt).all()
