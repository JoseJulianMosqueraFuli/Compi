"""Retrospective walk-forward comparison for the time occupied by a recorded session."""

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import median

from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.models.health import HealthObservation

VERSION = "duration-walk-forward-v1"
HISTORY_SIZE = 8
WARMUP = 3
ACTIVITIES = ("strength", "walk", "run")


@dataclass(frozen=True)
class RecordedSession:
    start: datetime
    end: datetime
    activity: str

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60


class Scores(BaseModel):
    mae_minutes: float
    underestimated: int


class Evaluation(BaseModel):
    version: str = VERSION
    observed_sessions: int
    evaluated_sessions: int
    baseline: Scores | None
    by_activity: Scores | None


def _scores(errors: list[float]) -> Scores | None:
    if not errors:
        return None
    return Scores(
        mae_minutes=round(sum(abs(e) for e in errors) / len(errors), 2),
        underestimated=sum(e > 0 for e in errors),
    )


def evaluate_sessions(records: Sequence[RecordedSession]) -> Evaluation:
    valid = [r for r in records if r.activity in ACTIVITIES and r.end > r.start]
    by_end = sorted(valid, key=lambda r: (r.end, r.start, r.activity))
    by_start = sorted(valid, key=lambda r: (r.start, r.end, r.activity))
    recent: deque[float] = deque(maxlen=HISTORY_SIZE)
    recent_by_activity: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=HISTORY_SIZE))
    baseline_errors: list[float] = []
    activity_errors: list[float] = []
    finished = 0
    for current in by_start:
        while finished < len(by_end) and by_end[finished].end <= current.start:
            past = by_end[finished]
            recent.append(past.minutes)
            recent_by_activity[past.activity].append(past.minutes)
            finished += 1
        same_kind = recent_by_activity[current.activity]
        if len(same_kind) >= WARMUP:
            baseline_errors.append(current.minutes - median(recent))
            activity_errors.append(current.minutes - median(same_kind))
    return Evaluation(
        observed_sessions=len(valid),
        evaluated_sessions=len(activity_errors),
        baseline=_scores(baseline_errors),
        by_activity=_scores(activity_errors),
    )


def source_sessions(session: Session, source: str) -> list[RecordedSession]:
    rows = session.exec(
        select(HealthObservation.start, HealthObservation.end, HealthObservation.category_value).where(
            HealthObservation.kind == "workout",
            HealthObservation.source_bundle == source,
            col(HealthObservation.category_value).in_(ACTIVITIES),
        )
    )
    return [RecordedSession(start, end, activity) for start, end, activity in rows if activity]
