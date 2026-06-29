"""Property-based test for the ExternalWorkout <-> Workout round-trip (Property 3)."""
from datetime import UTC, datetime

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.models.domain import WorkoutType
from app.providers.base import (
    CardioPayload,
    ExternalWorkout,
    StrengthSummaryPayload,
)
from app.providers.mapping import (
    external_to_workout,
    round_trip_preserves_common_fields,
    workout_to_external,
)

# Feature: compi-training-platform, Property 3: Round-trip de mapeo de entrenamientos


@st.composite
def external_workouts(draw: st.DrawFn) -> ExternalWorkout:
    """Strategy that generates well-formed ExternalWorkout instances (both variants)."""
    is_cardio = draw(st.booleans())
    start_naive = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 1, 1),
        )
    )
    start = start_naive.replace(tzinfo=UTC)
    duration = draw(st.integers(min_value=0, max_value=7200))
    avg_hr = draw(st.one_of(st.none(), st.integers(min_value=30, max_value=220)))
    max_hr = draw(st.one_of(st.none(), st.integers(min_value=30, max_value=220)))
    calories = draw(st.one_of(st.none(), st.floats(min_value=0, max_value=2000, allow_nan=False)))

    base = dict(
        external_id=f"ext-{draw(st.integers(min_value=0, max_value=10_000))}",
        start_time=start,
        duration_s=duration,
        avg_hr=avg_hr,
        max_hr=max_hr,
        calories=calories,
    )

    if is_cardio:
        return ExternalWorkout(
            **base,
            type=WorkoutType.CARDIO,
            cardio=CardioPayload(
                gps_polyline=None,
                avg_pace_s_per_km=draw(
                    st.one_of(st.none(), st.floats(min_value=0, max_value=1800, allow_nan=False))
                ),
                splits=[
                    {
                        "distance_m": draw(
                            st.floats(min_value=0, max_value=10_000, allow_nan=False)
                        ),
                        "duration_s": draw(
                            st.floats(min_value=0, max_value=3600, allow_nan=False)
                        ),
                    }
                ],
            ),
        )
    return ExternalWorkout(
        **base,
        type=WorkoutType.STRENGTH,
        strength_summary=StrengthSummaryPayload(
            total_volume_kg=draw(st.floats(min_value=0, max_value=10_000, allow_nan=False)),
            total_sets=draw(st.integers(min_value=0, max_value=20)),
            exercises_count=draw(st.integers(min_value=0, max_value=10)),
        ),
    )


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(ext=external_workouts())
def test_round_trip_preserves_common_fields(ext: ExternalWorkout) -> None:
    """Property 3: mapping to Workout and back preserves common + variant fields."""
    assert round_trip_preserves_common_fields(ext)


@settings(max_examples=100)
@given(ext=external_workouts())
def test_external_to_workout_carries_fields(ext: ExternalWorkout) -> None:
    """Forward mapping copies type, duration, HR and calories (Req 3.1, 3.2, 3.3)."""
    w = external_to_workout(ext)
    assert w.external_id == ext.external_id
    assert w.type == ext.type
    assert w.duration_s == ext.duration_s
    assert w.avg_hr == ext.avg_hr
    assert w.max_hr == ext.max_hr
    assert w.calories == ext.calories
    if ext.type == WorkoutType.STRENGTH and ext.strength_summary is not None:
        assert w.strength_total_volume_kg == ext.strength_summary.total_volume_kg
        assert w.strength_total_sets == ext.strength_summary.total_sets
        assert w.strength_exercises_count == ext.strength_summary.exercises_count


@settings(max_examples=100)
@given(ext=external_workouts())
def test_back_to_external_sets_correct_variant(ext: ExternalWorkout) -> None:
    """Reverse mapping emits the right variant payload and null on the other (Req 3.2, 3.3)."""
    w = external_to_workout(ext)
    back = workout_to_external(w)
    if ext.type == WorkoutType.CARDIO:
        assert back.strength_summary is None
    else:
        assert back.cardio is None
        assert back.strength_summary is not None
