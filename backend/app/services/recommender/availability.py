"""Turn the habitual week plus date exceptions into concrete free slots."""
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.services.recommender.types import Slot

ROUND_TO_MIN = 5


@dataclass(frozen=True)
class WindowSpec:
    """A habitual window: weekday 0 = Monday."""

    weekday: int
    start: time
    end: time
    gym_access: bool


@dataclass(frozen=True)
class ExceptionSpec:
    """A date override; without times the day is blocked."""

    day: date
    start: time | None
    end: time | None
    gym_access: bool


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def week_start_of(day: date) -> date:
    """Monday of the week `day` belongs to."""
    return day - timedelta(days=day.weekday())


def resolve_slots(
    week_start: date,
    windows: Iterable[WindowSpec],
    exceptions: Iterable[ExceptionSpec],
    now: datetime | None = None,
) -> list[Slot]:
    """Free slots of the week starting at `week_start`, ordered by day and time.

    A date with any exception uses only its exception windows. With `now` (local, naive)
    days already gone are dropped and today's windows start no earlier than now.
    """
    windows = list(windows)
    by_day: dict[date, list[ExceptionSpec]] = {}
    for exc in exceptions:
        by_day.setdefault(exc.day, []).append(exc)

    slots: list[Slot] = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        if day in by_day:
            spans = [
                (_minutes(e.start), _minutes(e.end), e.gym_access)
                for e in by_day[day]
                if e.start is not None and e.end is not None
            ]
        else:
            spans = [
                (_minutes(w.start), _minutes(w.end), w.gym_access)
                for w in windows
                if w.weekday == day.weekday()
            ]
        for start, end, gym in spans:
            if now is not None:
                if day < now.date():
                    continue
                if day == now.date():
                    now_min = now.hour * 60 + now.minute
                    start = max(start, -(-now_min // ROUND_TO_MIN) * ROUND_TO_MIN)
            if end > start:
                slots.append(Slot(day=day, start_min=start, end_min=end, gym_access=gym))
    return _without_overlaps(slots)


def _without_overlaps(slots: Sequence[Slot]) -> list[Slot]:
    """Order the slots and trim any that overlap an earlier one on the same day."""
    result: list[Slot] = []
    for slot in sorted(slots, key=lambda s: (s.day, s.start_min, s.end_min)):
        if result and result[-1].day == slot.day and slot.start_min < result[-1].end_min:
            start = result[-1].end_min
            if slot.end_min <= start:
                continue
            slot = Slot(slot.day, start, slot.end_min, slot.gym_access)
        result.append(slot)
    return result
