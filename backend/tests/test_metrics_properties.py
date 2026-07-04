"""Property-based tests for metrics (Property 4, 5, 6)."""
import math
from datetime import UTC, datetime

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.models.domain import WorkoutType
from app.models.workout import Workout
from app.services.metrics_service import (
    compute_hr_zones,
    total_training_load,
    total_volume,
    workout_training_load,
    workout_volume,
)


# Feature: compi-training-platform, Property 4: Zonas de FC bien formadas y exhaustivas  # noqa: E501
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(hr_max=st.integers(min_value=100, max_value=230))
def test_hr_zones_are_well_formed(hr_max: int) -> None:
    """Property 4: zones are ordered, contiguous, non-overlapping and cover 0..hr_max."""
    zones = compute_hr_zones(hr_max)
    assert len(zones) == 5
    # Ordered ascending by zone index.
    assert [z.zone for z in zones] == [1, 2, 3, 4, 5]
    # Contiguity: upper of zone i == lower of zone i+1.
    for prev, cur in zip(zones, zones[1:], strict=False):
        assert prev.upper_bpm == cur.lower_bpm, "zones must be contiguous"
    # Non-overlap and exhaustiveness: covered range is 0..hr_max.
    assert zones[0].lower_bpm == 0
    assert zones[-1].upper_bpm == hr_max
    # No bpm is in two zones: for any bpm, exactly one zone matches the inclusive range.
    for bpm in (0, hr_max // 2, hr_max - 1, hr_max):
        in_zones = [z for z in zones if z.lower_bpm <= bpm <= z.upper_bpm]
        assert len(in_zones) == 1


@settings(max_examples=50)
@given(hr_max=st.integers(min_value=100, max_value=230))
def test_hr_zones_count_is_five(hr_max: int) -> None:
    """Defensive: the design commits to 5 zones."""
    assert len(compute_hr_zones(hr_max)) == 5


# Feature: compi-training-platform, Property 5: Volumen de entrenamiento no negativo y aditivo


@st.composite
def workouts_with_volume(draw: st.DrawFn) -> Workout:
    """Strategy that yields a Workout with a non-negative implied volume."""
    is_strength = draw(st.booleans())
    duration = draw(st.integers(min_value=0, max_value=7200))
    if is_strength:
        sets = draw(st.integers(min_value=0, max_value=20))
        reps = draw(st.integers(min_value=0, max_value=20))
        weight = draw(st.floats(min_value=0.0, max_value=300.0, allow_nan=False))
        volume = sets * reps * weight
        return Workout(
            external_id=f"w-{draw(st.integers(min_value=0, max_value=1_000_000))}",
            type=WorkoutType.STRENGTH,
            start_time=datetime(2026, 1, 1, tzinfo=UTC),
            duration_s=duration,
            strength_total_volume_kg=volume,
            strength_total_sets=sets,
            strength_exercises_count=1,
        )
    return Workout(
        external_id=f"w-{draw(st.integers(min_value=0, max_value=1_000_000))}",
        type=WorkoutType.CARDIO,
        start_time=datetime(2026, 1, 1, tzinfo=UTC),
        duration_s=duration,
    )


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(workouts=st.lists(workouts_with_volume(), min_size=0, max_size=30))
def test_volume_is_non_negative(workouts: list[Workout]) -> None:
    """Property 5: aggregate volume is non-negative."""
    assert total_volume(workouts) >= 0


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    a=st.lists(workouts_with_volume(), min_size=0, max_size=20),
    b=st.lists(workouts_with_volume(), min_size=0, max_size=20),
)
def test_volume_is_additive(a: list[Workout], b: list[Workout]) -> None:
    """Property 5: total_volume(a) + total_volume(b) == total_volume(a + b)."""
    lhs = total_volume(a) + total_volume(b)
    rhs = total_volume(list(a) + list(b))
    assert math.isclose(lhs, rhs, rel_tol=1e-9, abs_tol=1e-9)


@settings(max_examples=50)
@given(w=workouts_with_volume())
def test_single_workout_volume_matches_formula(w: Workout) -> None:
    """Sanity: single-workout helper matches the documented formula."""
    if w.type == WorkoutType.STRENGTH:
        assert workout_volume(w) == float(w.strength_total_volume_kg or 0.0)
    else:
        assert workout_volume(w) == w.duration_s / 60.0


# Feature: compi-training-platform, Property 6: Carga de entrenamiento no negativa y monótona


@st.composite
def workouts_with_load(draw: st.DrawFn) -> Workout:
    """Strategy that yields a Workout with avg_hr or max_hr (or both)."""
    duration = draw(st.integers(min_value=0, max_value=7200))
    avg = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=220)))
    mx = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=220)))
    return Workout(
        external_id=f"w-{draw(st.integers(min_value=0, max_value=1_000_000))}",
        type=WorkoutType.CARDIO,
        start_time=datetime(2026, 1, 1, tzinfo=UTC),
        duration_s=duration,
        avg_hr=avg,
        max_hr=mx,
    )


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    workouts=st.lists(workouts_with_load(), min_size=0, max_size=30),
    hr_max=st.integers(min_value=100, max_value=230),
)
def test_training_load_is_non_negative(workouts: list[Workout], hr_max: int) -> None:
    """Property 6: aggregate load is non-negative."""
    assert total_training_load(workouts, hr_max) >= 0


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    base=st.lists(workouts_with_load(), min_size=0, max_size=20),
    extra=workouts_with_load(),
    hr_max=st.integers(min_value=100, max_value=230),
)
def test_training_load_is_monotonic(base: list[Workout], extra: Workout, hr_max: int) -> None:
    """Property 6: adding a workout never reduces the total load."""
    before = total_training_load(base, hr_max)
    after = total_training_load([*base, extra], hr_max)
    assert after >= before


@settings(max_examples=50)
@given(w=workouts_with_load(), hr_max=st.integers(min_value=100, max_value=230))
def test_single_workout_load_is_non_negative(w: Workout, hr_max: int) -> None:
    assert workout_training_load(w, hr_max) >= 0
