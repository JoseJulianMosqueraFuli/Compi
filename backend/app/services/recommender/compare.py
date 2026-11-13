"""Recommended versus performed: the basis for judging the recommender."""
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from app.models.domain import SessionKind, SessionStatus
from app.services.recommender.types import Prescription

CARDIO_DONE_RATIO = 0.9


@dataclass(frozen=True)
class DoneSet:
    reps: int
    weight_kg: float


@dataclass(frozen=True)
class DoneExercise:
    key: str | None
    name: str
    sets: tuple[DoneSet, ...]


class ExerciseComparison(BaseModel):
    key: str | None
    name: str
    outcome: str  # completed | partial | omitted | added
    recommended_sets: int
    performed_sets: int
    recommended_reps: int | None = None
    recommended_weight_kg: float | None = None
    performed_reps: list[int] = []
    performed_weights_kg: list[float] = []
    weight_changed: bool = False


class SessionComparison(BaseModel):
    status: SessionStatus
    adherence: float  # share of the recommended sets (or minutes) that were done
    exercises: list[ExerciseComparison] = []
    target_minutes: int | None = None
    actual_minutes: float | None = None


def compare_strength(
    prescription: Prescription, performed: Sequence[DoneExercise]
) -> SessionComparison:
    """Match what was done to what was recommended, exercise by exercise.

    Exercises are matched by catalog key. Anything done that was not recommended counts
    as a voluntary addition; anything recommended and not done, as omitted.
    """
    done_by_key: dict[str, DoneExercise] = {}
    extras: list[DoneExercise] = []
    recommended_keys = {e.key for e in prescription.exercises}
    for exercise in performed:
        if exercise.key in recommended_keys and exercise.key not in done_by_key:
            done_by_key[exercise.key] = exercise
        else:
            extras.append(exercise)

    rows: list[ExerciseComparison] = []
    total = matched = 0
    for rec in prescription.exercises:
        done = done_by_key.get(rec.key)
        done_sets = [s for s in done.sets if s.reps > 0] if done else []
        total += len(rec.sets)
        matched += min(len(done_sets), len(rec.sets))
        weight = rec.sets[0].weight_kg if rec.sets else None
        outcome = (
            "omitted" if not done_sets
            else "completed" if len(done_sets) >= len(rec.sets)
            else "partial"
        )
        rows.append(
            ExerciseComparison(
                key=rec.key,
                name=rec.name,
                outcome=outcome,
                recommended_sets=len(rec.sets),
                performed_sets=len(done_sets),
                recommended_reps=rec.sets[0].reps if rec.sets else None,
                recommended_weight_kg=weight,
                performed_reps=[s.reps for s in done_sets],
                performed_weights_kg=[s.weight_kg for s in done_sets],
                weight_changed=weight is not None and any(s.weight_kg != weight for s in done_sets),
            )
        )
    for extra in extras:
        sets = [s for s in extra.sets if s.reps > 0]
        rows.append(
            ExerciseComparison(
                key=extra.key,
                name=extra.name,
                outcome="added",
                recommended_sets=0,
                performed_sets=len(sets),
                performed_reps=[s.reps for s in sets],
                performed_weights_kg=[s.weight_kg for s in sets],
            )
        )

    adherence = matched / total if total else 0.0
    status = SessionStatus.DONE if total and matched == total else SessionStatus.PARTIAL
    return SessionComparison(status=status, adherence=round(adherence, 3), exercises=rows)


def compare_cardio(prescription: Prescription, actual_minutes: float) -> SessionComparison:
    target = prescription.target_minutes or 0
    adherence = min(1.0, actual_minutes / target) if target else 0.0
    status = SessionStatus.DONE if adherence >= CARDIO_DONE_RATIO else SessionStatus.PARTIAL
    return SessionComparison(
        status=status,
        adherence=round(adherence, 3),
        target_minutes=target,
        actual_minutes=round(actual_minutes, 1),
    )


def compare(
    prescription: Prescription, performed: Sequence[DoneExercise], actual_minutes: float
) -> SessionComparison:
    if prescription.kind is SessionKind.STRENGTH:
        result = compare_strength(prescription, performed)
        return result.model_copy(update={"actual_minutes": round(actual_minutes, 1)})
    return compare_cardio(prescription, actual_minutes)
