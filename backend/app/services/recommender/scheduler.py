"""Organization: place sessions in free windows and re-place them when availability changes.

Rules, in order of importance:
- A session goes in one window, a window holds one session.
- Strength only goes in windows with gym access (when the session requires it).
- Sessions of the same kind go on different days.
- Place as many sessions as possible; then avoid strength on consecutive days; then
  prefer windows where the full version fits; then avoid two sessions on one day; then
  spread same-kind sessions out; then lose as few minutes as possible; then earlier.
"""
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field
from datetime import date

from app.models.domain import SessionKind
from app.services.recommender.types import Slot

STAGE_ORDER = (SessionKind.STRENGTH, SessionKind.RUN, SessionKind.WALK)
MAX_GAP_CREDIT = 3

REASON_NO_GYM = "No queda ninguna ventana con acceso al gimnasio."
REASON_NO_WINDOWS = "No queda ninguna ventana libre."
REASON_TOO_SHORT = "Ninguna ventana libre alcanza los {min} min mínimos de esta sesión."
REASON_DAYS_TAKEN = (
    "Las ventanas que sirven ya están ocupadas o caen en días con otra sesión del mismo tipo."
)


@dataclass(frozen=True)
class Demand:
    """A session that needs a window."""

    id: Hashable
    kind: SessionKind
    requires_gym: bool
    full_min: int
    min_min: int


@dataclass(frozen=True)
class Occupied:
    """A session that already has its day; it only counts for spacing."""

    kind: SessionKind
    day: date


@dataclass(frozen=True)
class Placement:
    demand_id: Hashable
    slot: Slot
    minutes: int

    @property
    def day(self) -> date:
        return self.slot.day

    @property
    def start_min(self) -> int:
        return self.slot.start_min


@dataclass
class Schedule:
    placements: dict[Hashable, Placement] = field(default_factory=dict)
    unscheduled: dict[Hashable, str] = field(default_factory=dict)


def usable(demand: Demand, slot: Slot) -> bool:
    return (slot.gym_access or not demand.requires_gym) and slot.minutes >= demand.min_min


def _unscheduled_reason(demand: Demand, free: Sequence[Slot]) -> str:
    if not free:
        return REASON_NO_WINDOWS
    reachable = [s for s in free if s.gym_access or not demand.requires_gym]
    if not reachable:
        return REASON_NO_GYM
    if not any(s.minutes >= demand.min_min for s in reachable):
        return REASON_TOO_SHORT.format(min=demand.min_min)
    return REASON_DAYS_TAKEN


def _best_slot_per_day(demand: Demand, free: Sequence[Slot]) -> dict[date, Slot]:
    """Same-kind sessions never share a day, so each day needs only its best window:
    one where the full version fits if there is any, otherwise the longest; then earliest."""
    best: dict[date, Slot] = {}
    for slot in free:
        if not usable(demand, slot):
            continue
        current = best.get(slot.day)
        if current is None or _slot_rank(demand, slot) > _slot_rank(demand, current):
            best[slot.day] = slot
    return best


def _slot_rank(demand: Demand, slot: Slot) -> tuple[int, int]:
    return (min(slot.minutes, demand.full_min), -slot.start_min)


def _score(
    kind: SessionKind,
    chosen: Sequence[tuple[Demand, Slot]],
    occupied: Sequence[Occupied],
) -> tuple:
    days = sorted(s.day for _, s in chosen)
    same_kind = sorted([o.day for o in occupied if o.kind is kind] + days)
    gaps = [(b - a).days for a, b in zip(same_kind, same_kind[1:], strict=False)]
    consecutive = sum(1 for g in gaps if g < 2) if kind is SessionKind.STRENGTH else 0
    full = sum(1 for d, s in chosen if s.minutes >= d.full_min)
    other_days = [o.day for o in occupied if o.kind is not kind]
    shared = sum(other_days.count(day) for day in days)
    min_gap = min((min(g, MAX_GAP_CREDIT) for g in gaps), default=MAX_GAP_CREDIT)
    spread = sum(min(g, MAX_GAP_CREDIT) for g in gaps)
    minutes = sum(min(s.minutes, d.full_min) for d, s in chosen)
    earliness = tuple(-(day.toordinal()) for day in days)
    return (len(chosen), -consecutive, full, -shared, min_gap, spread, minutes, earliness)


def _place_stage(
    kind: SessionKind,
    demands: Sequence[Demand],
    free: Sequence[Slot],
    occupied: Sequence[Occupied],
) -> list[tuple[Demand, Slot]]:
    """Best assignment of this kind's demands to distinct days, by exhaustive search."""
    taken_days = {o.day for o in occupied if o.kind is kind}
    options = [
        {day: slot for day, slot in _best_slot_per_day(d, free).items() if day not in taken_days}
        for d in demands
    ]
    signatures = [(d.requires_gym, d.full_min, d.min_min) for d in demands]

    best_score: tuple | None = None
    best: list[tuple[Demand, Slot]] = []
    chosen: list[tuple[Demand, Slot] | None] = []

    def search(i: int) -> None:
        nonlocal best_score, best
        placed = [c for c in chosen if c is not None]
        if i == len(demands):
            score = _score(kind, placed, occupied)
            if best_score is None or score > best_score:
                best_score, best = score, list(placed)
            return
        if best_score is not None and len(placed) + len(demands) - i < best_score[0]:
            return
        # Identical demands are interchangeable: only try them in increasing day order.
        twin = i > 0 and signatures[i] == signatures[i - 1]
        previous = chosen[i - 1] if twin else None
        if not twin or previous is not None:
            used = {c[1].day for c in placed}
            used_slots = {c[1] for c in placed}
            for day in sorted(options[i]):
                slot = options[i][day]
                if day in used or slot in used_slots:
                    continue
                if previous is not None and day <= previous[1].day:
                    continue
                chosen.append((demands[i], slot))
                search(i + 1)
                chosen.pop()
        chosen.append(None)
        search(i + 1)
        chosen.pop()

    search(0)
    return best


def place(
    demands: Sequence[Demand],
    slots: Sequence[Slot],
    occupied: Sequence[Occupied] = (),
) -> Schedule:
    """Place `demands` in `slots`; `occupied` are sessions that already have a day."""
    schedule = Schedule()
    free = sorted(slots, key=lambda s: (s.day, s.start_min))
    occupied = list(occupied)
    for kind in STAGE_ORDER:
        stage = sorted(
            (d for d in demands if d.kind is kind),
            key=lambda d: (d.requires_gym, d.full_min, d.min_min),
        )
        if not stage:
            continue
        assignment = _place_stage(kind, stage, free, occupied)
        for demand, slot in assignment:
            schedule.placements[demand.id] = Placement(
                demand_id=demand.id, slot=slot, minutes=min(slot.minutes, demand.full_min)
            )
            occupied.append(Occupied(kind=kind, day=slot.day))
        used = {slot for _, slot in assignment}
        free = [s for s in free if s not in used]
        for demand in stage:
            if demand.id not in schedule.placements:
                schedule.unscheduled[demand.id] = _unscheduled_reason(demand, free)
    return schedule


@dataclass(frozen=True)
class SessionState:
    """A session of an existing week, as the re-planner needs to see it."""

    id: Hashable
    kind: SessionKind
    requires_gym: bool
    full_min: int
    min_min: int
    pending: bool
    day: date | None = None
    start_min: int | None = None

    def demand(self) -> Demand:
        return Demand(self.id, self.kind, self.requires_gym, self.full_min, self.min_min)


def replan(sessions: Sequence[SessionState], slots: Sequence[Slot]) -> Schedule:
    """Re-place the pending sessions of a week after availability changed.

    Sessions that are no longer pending are never touched. A pending session stays on
    its day while that day still has a window that can hold it (its duration may grow or
    shrink with the window); only the ones left without a window are moved.
    """
    schedule = Schedule()
    free = sorted(slots, key=lambda s: (s.day, s.start_min))
    occupied = [
        Occupied(kind=s.kind, day=s.day) for s in sessions if not s.pending and s.day is not None
    ]
    displaced: list[Demand] = []

    pending = [s for s in sessions if s.pending]
    placed_first = sorted(
        pending,
        key=lambda s: (s.day is None, s.day or date.min, s.start_min or 0),
    )
    for state in placed_first:
        demand = state.demand()
        same_day = [s for s in free if s.day == state.day and usable(demand, s)]
        clash = any(o.kind is state.kind and o.day == state.day for o in occupied)
        if state.day is None or not same_day or clash:
            displaced.append(demand)
            continue
        holding = [s for s in same_day if s.start_min <= (state.start_min or 0) < s.end_min]
        slot = max(holding or same_day, key=lambda s: _slot_rank(demand, s))
        schedule.placements[state.id] = Placement(
            demand_id=state.id, slot=slot, minutes=min(slot.minutes, demand.full_min)
        )
        occupied.append(Occupied(kind=state.kind, day=slot.day))
        free.remove(slot)

    moved = place(displaced, free, occupied)
    schedule.placements.update(moved.placements)
    schedule.unscheduled.update(moved.unscheduled)
    return schedule
