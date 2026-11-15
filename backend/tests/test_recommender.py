"""Unit and property tests for the pure recommender modules."""
from datetime import date, datetime, time, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.domain import SessionKind, SessionStatus
from app.services.recommender.availability import (
    ExceptionSpec,
    WindowSpec,
    resolve_slots,
    week_start_of,
)
from app.services.recommender.catalog import EXERCISES, TEMPLATES, split_for
from app.services.recommender.compare import DoneExercise, DoneSet, compare
from app.services.recommender.duration import (
    FACTOR_BOUNDS,
    estimated_minutes,
    learn_duration_factor,
    model_minutes,
)
from app.services.recommender.scheduler import (
    REASON_NO_GYM,
    REASON_NO_WINDOWS,
    REASON_TOO_SHORT,
    Demand,
    SessionState,
    place,
    replan,
)
from app.services.recommender.shorten import MIN_SETS, minimal_version, shorten
from app.services.recommender.training import (
    CardioOutcome,
    Performance,
    PerformedSet,
    cardio_prescription,
    prescribe_exercise,
    strength_prescription,
)
from app.services.recommender.types import (
    ExercisePrescription,
    Prescription,
    SetPrescription,
    Slot,
)

MONDAY = date(2026, 11, 16)


def _strength(template: str = "full_a") -> Prescription:
    prescription, _ = strength_prescription(template, {}, MONDAY)
    return prescription


def _one_set_exercise(key: str, priority: int, sets: int, reps: int = 5, rest_s: int = 60):
    return ExercisePrescription(
        key=key,
        name=key,
        priority=priority,
        sets=[SetPrescription(reps=reps, rest_s=rest_s) for _ in range(sets)],
        reason="",
    )


# --- duration -------------------------------------------------------------------------


def test_model_minutes_strength_follows_the_formula() -> None:
    # warm-up 300 + change 90 + one set (20 setup + 5 reps * 4 + 60 rest) = 490 s
    p = Prescription(kind=SessionKind.STRENGTH, exercises=[_one_set_exercise("x", 1, 1)])
    assert model_minutes(p) == pytest.approx(490 / 60)
    assert estimated_minutes(p) == 9


def test_model_minutes_empty_strength_is_zero() -> None:
    assert model_minutes(Prescription(kind=SessionKind.STRENGTH)) == 0.0


def test_factor_only_applies_to_strength() -> None:
    run = Prescription(kind=SessionKind.RUN, target_minutes=30)
    assert estimated_minutes(run, factor=1.5) == 30
    strength = _strength()
    assert estimated_minutes(strength, factor=1.5) > estimated_minutes(strength)


def test_learn_duration_factor_needs_three_samples() -> None:
    assert learn_duration_factor([(60, 90), (60, 90)]) == 1.0
    assert learn_duration_factor([(60, 90), (60, 90), (60, 90)]) == 1.5


def test_learn_duration_factor_uses_median_and_ignores_bad_samples() -> None:
    samples = [(60, 60), (60, 66), (0, 50), (60, 0), (60, 600)]
    assert learn_duration_factor(samples) == 1.1


def test_learn_duration_factor_only_reads_the_most_recent_eight() -> None:
    recent = [(60, 60)] * 8
    old = [(60, 120)] * 20
    assert learn_duration_factor(recent + old) == 1.0


@given(st.lists(st.tuples(st.floats(1, 200), st.floats(1, 400)), min_size=3, max_size=12))
@settings(max_examples=100)
def test_learned_factor_is_bounded(samples: list[tuple[float, float]]) -> None:
    low, high = FACTOR_BOUNDS
    assert low <= learn_duration_factor(samples) <= high


# --- shorten --------------------------------------------------------------------------


def test_shorten_keeps_a_session_that_already_fits() -> None:
    p = _strength()
    result = shorten(p, estimated_minutes(p))
    assert result is not None
    assert result.prescription == p
    assert result.dropped == [] and result.notes == []


def test_shorten_returns_none_below_the_minimal_version() -> None:
    p = _strength()
    assert shorten(p, estimated_minutes(minimal_version(p)) - 1) is None


def test_shorten_drops_accessories_before_touching_main_lifts() -> None:
    p = _strength()
    # Just under the full length: dropping one accessory is enough.
    result = shorten(p, estimated_minutes(p) - 1)
    assert result is not None
    assert [e.priority for e in result.dropped] == [3]
    main = [e for e in p.exercises if e.priority == 1]
    kept = {e.key: e for e in result.prescription.exercises}
    assert all(len(kept[e.key].sets) == len(e.sets) for e in main)


def test_minimal_version_keeps_only_main_lifts_at_min_sets() -> None:
    minimal = minimal_version(_strength())
    assert minimal.exercises
    assert all(e.priority == 1 and len(e.sets) == MIN_SETS for e in minimal.exercises)


def test_shorten_cardio_cuts_to_the_window_and_respects_the_floor() -> None:
    run = Prescription(kind=SessionKind.RUN, target_minutes=40)
    result = shorten(run, 20)
    assert result is not None and result.prescription.target_minutes == 20
    assert shorten(run, 14) is None  # runs need at least 15 min
    walk = Prescription(kind=SessionKind.WALK, target_minutes=30)
    assert shorten(walk, 10) is not None
    assert shorten(walk, 9) is None


@given(
    template=st.sampled_from(sorted(TEMPLATES)),
    available=st.integers(0, 120),
    factor=st.floats(0.6, 1.8),
)
@settings(max_examples=200)
def test_shorten_fits_and_never_drops_main_lifts(template: str, available: int, factor: float) -> None:
    p = _strength(template)
    result = shorten(p, available, factor)
    minimal_fits = estimated_minutes(minimal_version(p), factor) <= available
    assert (result is not None) == minimal_fits
    if result is None:
        return
    assert estimated_minutes(result.prescription, factor) <= available
    kept = {e.key: e for e in result.prescription.exercises}
    for main in (e for e in p.exercises if e.priority == 1):
        assert main.key in kept
        assert len(kept[main.key].sets) >= MIN_SETS
    dropped = {e.key for e in result.dropped}
    assert dropped.isdisjoint(kept)
    assert dropped | set(kept) <= {e.key for e in p.exercises}


# --- availability ---------------------------------------------------------------------


def test_week_start_of_is_monday() -> None:
    for offset in range(7):
        assert week_start_of(MONDAY + timedelta(days=offset)) == MONDAY


def test_habitual_windows_become_slots_of_the_week() -> None:
    windows = [
        WindowSpec(0, time(18), time(19, 30), True),
        WindowSpec(2, time(7), time(8), False),
    ]
    slots = resolve_slots(MONDAY, windows, [])
    assert slots == [
        Slot(MONDAY, 18 * 60, 19 * 60 + 30, True),
        Slot(MONDAY + timedelta(days=2), 7 * 60, 8 * 60, False),
    ]


def test_exceptions_replace_the_day_and_can_block_it() -> None:
    windows = [WindowSpec(d, time(18), time(19), True) for d in range(7)]
    tuesday, wednesday = MONDAY + timedelta(days=1), MONDAY + timedelta(days=2)
    exceptions = [
        ExceptionSpec(tuesday, None, None, False),
        ExceptionSpec(wednesday, time(6), time(7), False),
    ]
    slots = resolve_slots(MONDAY, windows, exceptions)
    by_day = {s.day: s for s in slots}
    assert tuesday not in by_day
    assert by_day[wednesday] == Slot(wednesday, 6 * 60, 7 * 60, False)
    assert len(slots) == 6


def test_now_drops_past_days_and_rounds_today_up() -> None:
    windows = [WindowSpec(d, time(18), time(20), True) for d in range(7)]
    now = datetime.combine(MONDAY + timedelta(days=3), time(18, 32))
    slots = resolve_slots(MONDAY, windows, [], now=now)
    assert slots[0] == Slot(now.date(), 18 * 60 + 35, 20 * 60, True)
    assert all(s.day >= now.date() for s in slots)
    assert len(slots) == 4


def test_overlapping_windows_are_trimmed() -> None:
    windows = [
        WindowSpec(0, time(18), time(19), True),
        WindowSpec(0, time(18, 30), time(20), False),
        WindowSpec(0, time(18, 15), time(18, 45), False),
    ]
    slots = resolve_slots(MONDAY, windows, [])
    assert slots == [
        Slot(MONDAY, 18 * 60, 19 * 60, True),
        Slot(MONDAY, 19 * 60, 20 * 60, False),
    ]


_window = st.builds(
    lambda wd, start, length, gym: WindowSpec(
        wd, time(start // 60, start % 60), time((start + length) // 60, (start + length) % 60), gym
    ),
    st.integers(0, 6),
    st.integers(0, 22 * 60),
    st.integers(1, 119),
    st.booleans(),
)


@given(st.lists(_window, max_size=15))
@settings(max_examples=100)
def test_resolved_slots_are_ordered_and_disjoint(windows: list[WindowSpec]) -> None:
    slots = resolve_slots(MONDAY, windows, [])
    assert slots == sorted(slots, key=lambda s: (s.day, s.start_min, s.end_min))
    for a, b in zip(slots, slots[1:], strict=False):
        if a.day == b.day:
            assert a.end_min <= b.start_min
    assert all(MONDAY <= s.day < MONDAY + timedelta(days=7) and s.minutes > 0 for s in slots)


# --- scheduler ------------------------------------------------------------------------


def _slot(day_offset: int, start_h: int, minutes: int, gym: bool = True) -> Slot:
    return Slot(MONDAY + timedelta(days=day_offset), start_h * 60, start_h * 60 + minutes, gym)


def _gym(i: int) -> Demand:
    return Demand(f"s{i}", SessionKind.STRENGTH, True, 60, 25)


def test_place_puts_strength_only_in_gym_windows() -> None:
    slots = [_slot(0, 7, 60, gym=False), _slot(1, 18, 60, gym=True)]
    schedule = place([_gym(1)], slots)
    assert schedule.placements["s1"].slot.gym_access


def test_place_spreads_strength_and_avoids_consecutive_days() -> None:
    slots = [_slot(d, 18, 90) for d in range(7)]
    schedule = place([_gym(i) for i in range(3)], slots)
    days = sorted(p.day for p in schedule.placements.values())
    assert len(days) == 3
    assert all((b - a).days >= 2 for a, b in zip(days, days[1:], strict=False))


def test_place_keeps_same_kind_on_different_days() -> None:
    slots = [_slot(0, 7, 60), _slot(0, 18, 60)]
    schedule = place([_gym(1), _gym(2)], slots)
    assert len(schedule.placements) == 1
    assert len(schedule.unscheduled) == 1


@pytest.mark.parametrize(
    ("slots", "reason"),
    [
        ([], REASON_NO_WINDOWS),
        ([_slot(0, 7, 90, gym=False)], REASON_NO_GYM),
        ([_slot(0, 7, 20, gym=True)], REASON_TOO_SHORT.format(min=25)),
    ],
)
def test_unscheduled_reasons(slots: list[Slot], reason: str) -> None:
    schedule = place([_gym(1)], slots)
    assert schedule.unscheduled == {"s1": reason}


def test_placed_minutes_are_capped_by_window_and_full_length() -> None:
    schedule = place([_gym(1)], [_slot(0, 18, 40)])
    assert schedule.placements["s1"].minutes == 40
    schedule = place([_gym(1)], [_slot(0, 18, 120)])
    assert schedule.placements["s1"].minutes == 60


_demand_kind = st.sampled_from(list(SessionKind))


@st.composite
def _demands(draw: st.DrawFn) -> list[Demand]:
    out = []
    for i, kind in enumerate(draw(st.lists(_demand_kind, max_size=6))):
        min_min = draw(st.integers(10, 40))
        out.append(
            Demand(i, kind, kind is SessionKind.STRENGTH, min_min + draw(st.integers(0, 40)), min_min)
        )
    return out


_slots = st.lists(
    st.builds(_slot, st.integers(0, 6), st.integers(6, 20), st.integers(10, 120), st.booleans()),
    max_size=10,
    unique_by=lambda s: (s.day, s.start_min),
)


@given(demands=_demands(), slots=_slots)
@settings(max_examples=100, deadline=None)
def test_place_invariants(demands: list[Demand], slots: list[Slot]) -> None:
    schedule = place(demands, slots)
    by_id = {d.id: d for d in demands}
    assert set(schedule.placements) | set(schedule.unscheduled) == set(by_id)
    assert set(schedule.placements).isdisjoint(schedule.unscheduled)
    used = [p.slot for p in schedule.placements.values()]
    assert len(used) == len(set(used)), "a window holds one session"
    seen: set[tuple[SessionKind, date]] = set()
    for p in schedule.placements.values():
        d = by_id[p.demand_id]
        assert p.slot in slots
        assert p.slot.gym_access or not d.requires_gym
        assert d.min_min <= p.minutes <= min(d.full_min, p.slot.minutes)
        assert (d.kind, p.day) not in seen, "same kind never shares a day"
        seen.add((d.kind, p.day))


def test_replan_keeps_done_sessions_and_pending_ones_that_still_fit() -> None:
    done = SessionState("done", SessionKind.STRENGTH, True, 60, 25, pending=False,
                        day=MONDAY, start_min=18 * 60)
    stays = SessionState("stays", SessionKind.RUN, False, 30, 15, pending=True,
                         day=MONDAY + timedelta(days=2), start_min=7 * 60)
    moves = SessionState("moves", SessionKind.STRENGTH, True, 60, 25, pending=True,
                         day=MONDAY + timedelta(days=3), start_min=18 * 60)
    # Thursday lost its window; Wednesday shrank; Saturday is new.
    slots = [_slot(2, 7, 20, gym=False), _slot(5, 10, 90)]
    schedule = replan([done, stays, moves], slots)
    assert "done" not in schedule.placements and "done" not in schedule.unscheduled
    assert schedule.placements["stays"].day == stays.day
    assert schedule.placements["stays"].minutes == 20
    assert schedule.placements["moves"].day == MONDAY + timedelta(days=5)


def test_replan_does_not_move_onto_a_day_with_a_done_session_of_the_same_kind() -> None:
    done = SessionState("done", SessionKind.STRENGTH, True, 60, 25, pending=False,
                        day=MONDAY, start_min=7 * 60)
    pending = SessionState("p", SessionKind.STRENGTH, True, 60, 25, pending=True)
    schedule = replan([done, pending], [_slot(0, 18, 90)])
    assert "p" in schedule.unscheduled


# --- training -------------------------------------------------------------------------


def _perf(days_ago: int, *sets: tuple[int, float] | tuple[int, float, float]) -> Performance:
    return Performance(MONDAY - timedelta(days=days_ago), tuple(PerformedSet(*s) for s in sets))


SQUAT = EXERCISES["squat"]  # 3 sets, 5-8 reps, +5 kg


def test_no_history_asks_for_a_starting_weight() -> None:
    p = prescribe_exercise(SQUAT, [], MONDAY)
    assert len(p.sets) == SQUAT.sets
    assert all(s.weight_kg is None and s.reps == SQUAT.rep_min for s in p.sets)


def test_top_of_range_adds_weight_and_resets_reps() -> None:
    p = prescribe_exercise(SQUAT, [_perf(3, (8, 100), (8, 100), (8, 100))], MONDAY)
    assert {(s.reps, s.weight_kg) for s in p.sets} == {(SQUAT.rep_min, 105)}


def test_inside_range_adds_one_rep() -> None:
    p = prescribe_exercise(SQUAT, [_perf(3, (6, 100), (6, 100), (6, 100))], MONDAY)
    assert {(s.reps, s.weight_kg) for s in p.sets} == {(7, 100)}


def test_near_max_effort_repeats() -> None:
    p = prescribe_exercise(SQUAT, [_perf(3, (8, 100), (8, 100), (8, 100, 10))], MONDAY)
    assert {(s.reps, s.weight_kg) for s in p.sets} == {(8, 100)}


def test_missing_sets_repeat_the_same_weight() -> None:
    p = prescribe_exercise(SQUAT, [_perf(3, (8, 100), (8, 100))], MONDAY)
    assert {s.weight_kg for s in p.sets} == {100}


def test_layoff_backs_off_ten_percent() -> None:
    p = prescribe_exercise(SQUAT, [_perf(30, (8, 100), (8, 100), (8, 100))], MONDAY)
    assert {(s.reps, s.weight_kg) for s in p.sets} == {(SQUAT.rep_min, 90)}


def test_two_sessions_below_range_back_off() -> None:
    history = [_perf(3, (4, 100), (4, 100), (4, 100)), _perf(7, (4, 100), (4, 100), (4, 100))]
    p = prescribe_exercise(SQUAT, history, MONDAY)
    assert {s.weight_kg for s in p.sets} == {90}


def test_working_weight_ignores_a_warm_up_set() -> None:
    p = prescribe_exercise(SQUAT, [_perf(3, (8, 40), (6, 100), (6, 100), (6, 100))], MONDAY)
    assert {s.weight_kg for s in p.sets} == {100}


def test_excluded_exercise_is_swapped_and_keeps_its_priority() -> None:
    prescription, notes = strength_prescription("full_a", {}, MONDAY, excluded={"squat"})
    keys = [e.key for e in prescription.exercises]
    assert "squat" not in keys and keys[0] == "leg_press"
    assert prescription.exercises[0].priority == 1
    assert notes and "Prensa de piernas" in notes[0]


def test_excluded_exercise_without_substitute_is_dropped() -> None:
    prescription, notes = strength_prescription("full_a", {}, MONDAY, excluded={"triceps"})
    assert "triceps" not in [e.key for e in prescription.exercises]
    assert len(prescription.exercises) == len(TEMPLATES["full_a"].exercises) - 1
    assert notes


def test_split_for_clamps_session_count() -> None:
    assert split_for(-1) == ()
    assert len(split_for(3)) == 3
    assert split_for(9) == split_for(4)


def test_walk_keeps_the_configured_minutes() -> None:
    p = cardio_prescription(SessionKind.WALK, 30, [CardioOutcome(60, SessionStatus.DONE)])
    assert p.target_minutes == 30


def test_run_progresses_holds_and_caps() -> None:
    done = [CardioOutcome(30, SessionStatus.DONE), CardioOutcome(30, SessionStatus.DONE)]
    assert cardio_prescription(SessionKind.RUN, 30, []).target_minutes == 30
    assert cardio_prescription(SessionKind.RUN, 30, done).target_minutes == 35
    missed = [CardioOutcome(35, SessionStatus.DONE), CardioOutcome(35, SessionStatus.SKIPPED)]
    assert cardio_prescription(SessionKind.RUN, 30, missed).target_minutes == 35
    at_cap = [CardioOutcome(60, SessionStatus.DONE)]
    assert cardio_prescription(SessionKind.RUN, 30, at_cap).target_minutes == 60


# --- compare --------------------------------------------------------------------------


def test_compare_strength_outcomes_and_adherence() -> None:
    prescription = Prescription(
        kind=SessionKind.STRENGTH,
        exercises=[_one_set_exercise("a", 1, 3), _one_set_exercise("b", 2, 2)],
    )
    performed = [
        DoneExercise("a", "a", (DoneSet(5, 100), DoneSet(5, 100), DoneSet(0, 100))),
        DoneExercise(None, "extra", (DoneSet(10, 20),)),
    ]
    result = compare(prescription, performed, actual_minutes=42.04)
    outcomes = {e.name: e.outcome for e in result.exercises}
    assert outcomes == {"a": "partial", "b": "omitted", "extra": "added"}
    assert result.adherence == pytest.approx(2 / 5)
    assert result.status is SessionStatus.PARTIAL
    assert result.actual_minutes == 42.0


def test_compare_strength_done_when_every_set_is_done() -> None:
    prescription = Prescription(kind=SessionKind.STRENGTH, exercises=[_one_set_exercise("a", 1, 2)])
    performed = [DoneExercise("a", "a", (DoneSet(5, 100), DoneSet(5, 105)))]
    result = compare(prescription, performed, actual_minutes=30)
    assert result.status is SessionStatus.DONE and result.adherence == 1.0


def test_compare_cardio_uses_ninety_percent_threshold() -> None:
    run = Prescription(kind=SessionKind.RUN, target_minutes=30)
    assert compare(run, [], 27).status is SessionStatus.DONE
    assert compare(run, [], 26).status is SessionStatus.PARTIAL
    assert compare(run, [], 60).adherence == 1.0
