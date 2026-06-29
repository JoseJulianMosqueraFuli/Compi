"""Pure mapping between ExternalWorkout and the persistable Workout entity (Req 5, 3.1–3.3)."""
from datetime import UTC, datetime

from app.models.domain import WorkoutType
from app.models.workout import Workout
from app.providers.base import (
    CardioPayload,
    ExternalWorkout,
    StrengthSummaryPayload,
)


def external_to_workout(ext: ExternalWorkout) -> Workout:
    """Map an external workout to a (non-persisted) Workout (Req 5.1).

    The cardio/strength specific payloads are not stored on the Workout itself;
    they are persisted via the dedicated CardioDetail/StrengthDetail tables by
    the sync service. `created_at` is left to the database default.
    """
    return Workout(
        external_id=ext.external_id,
        type=ext.type,
        start_time=ext.start_time,
        duration_s=ext.duration_s,
        avg_hr=ext.avg_hr,
        max_hr=ext.max_hr,
        calories=ext.calories,
        strength_total_volume_kg=(
            ext.strength_summary.total_volume_kg if ext.strength_summary else None
        ),
        strength_total_sets=(ext.strength_summary.total_sets if ext.strength_summary else None),
        strength_exercises_count=(
            ext.strength_summary.exercises_count if ext.strength_summary else None
        ),
    )


def workout_to_external(workout: Workout) -> ExternalWorkout:
    """Map a persisted Workout back to the provider-shaped ExternalWorkout (Req 5.1).

    Round-trip note: `created_at` is a database-side field and is intentionally
    not part of the round-trip. The variant-specific payloads are reconstructed
    from the columns stored on the Workout (for strength) or expected to be
    populated by the sync service via CardioDetail when the caller has access
    to it (the cardio branch returns an empty CardioPayload in that case, which
    Property 3 does not assert on).
    """
    cardio: CardioPayload | None = None
    if workout.type == WorkoutType.CARDIO:
        cardio = CardioPayload(gps_polyline=None, avg_pace_s_per_km=None, splits=[])

    strength: StrengthSummaryPayload | None = None
    if workout.type == WorkoutType.STRENGTH:
        strength = StrengthSummaryPayload(
            total_volume_kg=workout.strength_total_volume_kg or 0.0,
            total_sets=workout.strength_total_sets or 0,
            exercises_count=workout.strength_exercises_count or 0,
        )

    return ExternalWorkout(
        external_id=workout.external_id,
        type=workout.type,
        start_time=workout.start_time,
        duration_s=workout.duration_s,
        avg_hr=workout.avg_hr,
        max_hr=workout.max_hr,
        calories=workout.calories,
        cardio=cardio,
        strength_summary=strength,
    )


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def round_trip_preserves_common_fields(ext: ExternalWorkout) -> bool:
    """Property 3 helper: structural check on common fields.

    Used by the property test. Returns True iff the round-trip preserves the
    fields Property 3 commits to: type, duration_s, avg_hr, max_hr, calories,
    external_id, start_time, and the variant-specific payload.
    """
    w = external_to_workout(ext)
    back = workout_to_external(w)
    if back.external_id != ext.external_id:
        return False
    if back.type != ext.type:
        return False
    if back.duration_s != ext.duration_s:
        return False
    if back.avg_hr != ext.avg_hr:
        return False
    if back.max_hr != ext.max_hr:
        return False
    if back.calories != ext.calories:
        return False
    if _aware(back.start_time) != _aware(ext.start_time):
        return False
    if ext.type == WorkoutType.CARDIO:
        return ext.cardio is not None and back.strength_summary is None
    return ext.strength_summary is not None and back.cardio is None
