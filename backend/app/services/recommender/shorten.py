"""Make a session fit in fewer minutes, keeping what matters most and saying what was cut."""
from dataclasses import dataclass, field

from app.models.domain import SessionKind
from app.services.recommender.duration import estimated_minutes
from app.services.recommender.types import ExercisePrescription, Prescription

MIN_SETS = 2
MIN_CARDIO_MINUTES = {SessionKind.RUN: 15, SessionKind.WALK: 10}


@dataclass(frozen=True)
class Shortened:
    prescription: Prescription
    dropped: list[ExercisePrescription] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def minimal_version(prescription: Prescription) -> Prescription:
    """Shortest version still worth doing: main lifts at MIN_SETS, or the minimum cardio time."""
    if prescription.kind is not SessionKind.STRENGTH:
        floor = MIN_CARDIO_MINUTES[prescription.kind]
        return prescription.model_copy(
            update={"target_minutes": min(prescription.target_minutes or floor, floor)}
        )
    main = [e for e in prescription.exercises if e.priority == 1] or prescription.exercises[:1]
    return prescription.model_copy(
        update={"exercises": [e.model_copy(update={"sets": e.sets[:MIN_SETS]}) for e in main]}
    )


def shorten(prescription: Prescription, available_min: int, factor: float = 1.0) -> Shortened | None:
    """Return a version that fits in `available_min`, or None when not even the minimal one does.

    Strength is cut in this order: accessories out (last first), then sets down to
    MIN_SETS (last exercise first), then secondary lifts out. Main lifts always stay.
    """
    if estimated_minutes(prescription, factor) <= available_min:
        return Shortened(prescription)
    if estimated_minutes(minimal_version(prescription), factor) > available_min:
        return None
    if prescription.kind is not SessionKind.STRENGTH:
        return Shortened(
            prescription.model_copy(update={"target_minutes": available_min}),
            notes=[f"Recortada de {prescription.target_minutes} a {available_min} min."],
        )

    exercises = [e.model_copy(deep=True) for e in prescription.exercises]
    dropped: list[ExercisePrescription] = []
    notes: list[str] = []

    def fits() -> bool:
        current = prescription.model_copy(update={"exercises": exercises})
        return estimated_minutes(current, factor) <= available_min

    def drop_last(priority: int, label: str) -> bool:
        for i in range(len(exercises) - 1, -1, -1):
            if exercises[i].priority == priority and len(exercises) > 1:
                removed = exercises.pop(i)
                dropped.append(removed)
                notes.append(f"Sin {removed.name} ({label}).")
                return True
        return False

    while not fits() and drop_last(3, "accesorio"):
        pass

    before = {e.key: len(e.sets) for e in exercises}
    while not fits():
        trimmable = [e for e in reversed(exercises) if len(e.sets) > MIN_SETS]
        if not trimmable:
            break
        # Take one set at a time from whoever has most, so the cut is spread out.
        target = max(trimmable, key=lambda e: len(e.sets))
        target.sets.pop()
    for e in exercises:
        if len(e.sets) < before[e.key]:
            notes.append(f"{e.name}: {before[e.key]} → {len(e.sets)} series.")

    while not fits() and drop_last(2, "secundario"):
        pass

    if not fits():
        minimal = minimal_version(prescription)
        kept = {e.key for e in minimal.exercises}
        return Shortened(
            minimal,
            dropped=[e for e in prescription.exercises if e.key not in kept],
            notes=["Reducida a los ejercicios principales con el mínimo de series."],
        )

    return Shortened(
        prescription.model_copy(update={"exercises": exercises}), dropped=dropped, notes=notes
    )
