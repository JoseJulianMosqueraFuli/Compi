"""Training: what each session contains, decided from what was actually done before."""
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from statistics import median_low

from app.models.domain import SessionKind, SessionStatus
from app.services.recommender.catalog import EXERCISES, TEMPLATES, Exercise
from app.services.recommender.types import (
    ExercisePrescription,
    Prescription,
    SetPrescription,
    fmt_kg,
)

LAYOFF_DAYS = 21
BACKOFF = 0.9
HARD_RPE = 9.5
RUN_STEP = 1.1
RUN_CAP_FACTOR = 2

RUN_GUIDANCE = (
    "Ritmo cómodo: deberías poder hablar en frases completas. Si aún no aguantas corriendo "
    "todo el tiempo, alterna 2 min de carrera con 1 min caminando."
)
WALK_GUIDANCE = "Paso ligero y continuo, sin llegar a quedarte sin aire."


@dataclass(frozen=True)
class PerformedSet:
    reps: int
    weight_kg: float
    rpe: float | None = None


@dataclass(frozen=True)
class Performance:
    """One exercise as it was done on a day."""

    day: date
    sets: tuple[PerformedSet, ...]


History = Mapping[str, Sequence[Performance]]  # by exercise key, most recent first


def _half_kg(weight: float) -> float:
    return round(weight * 2) / 2


def _reference(performance: Performance) -> tuple[float, int, int, bool]:
    """Working weight, fewest reps at that weight or heavier, sets done, and whether it was
    near the limit. The working weight is the median so a pyramid or a warm-up set does
    not pass for the weight of the day."""
    work = [s for s in performance.sets if s.reps > 0]
    weight = median_low([s.weight_kg for s in work])
    at_weight = [s for s in work if s.weight_kg >= weight]
    rpes = [s.rpe for s in at_weight if s.rpe is not None]
    return weight, min(s.reps for s in at_weight), len(work), bool(rpes) and max(rpes) >= HARD_RPE


def prescribe_exercise(
    exercise: Exercise, performances: Sequence[Performance], today: date
) -> ExercisePrescription:
    """Sets, reps, weight and rest for an exercise, with the reason behind the numbers."""

    def build(weight: float | None, reps: int, reason: str) -> ExercisePrescription:
        reps = max(exercise.rep_min, min(exercise.rep_max, reps))
        return ExercisePrescription(
            key=exercise.key,
            name=exercise.name,
            priority=exercise.priority,
            sets=[
                SetPrescription(reps=reps, weight_kg=weight, rest_s=exercise.rest_s)
                for _ in range(exercise.sets)
            ],
            reason=reason,
        )

    rep_range = f"{exercise.rep_min}-{exercise.rep_max}"
    done = [p for p in performances if any(s.reps > 0 for s in p.sets)]
    if not done:
        return build(
            None,
            exercise.rep_min,
            "Sin registros previos: elige un peso con el que termines cada serie con 2-3 "
            "repeticiones de margen. Lo que registres será el punto de partida.",
        )

    weight, low_reps, sets_done, hard = _reference(done[0])
    last = f"{sets_done} series de al menos {low_reps} con {fmt_kg(weight)}"
    loaded = weight > 0
    days_off = (today - done[0].day).days

    if days_off > LAYOFF_DAYS and loaded:
        return build(
            _half_kg(weight * BACKOFF),
            exercise.rep_min,
            f"Han pasado {days_off} días desde la última vez ({last}): retoma con un 10 % menos.",
        )
    if sets_done < exercise.sets:
        return build(
            weight,
            low_reps,
            f"La última vez hiciste {sets_done} de {exercise.sets} series ({last}): "
            "repite el mismo peso hasta completarlas todas.",
        )
    if low_reps >= exercise.rep_max and not hard:
        if not loaded:
            return build(
                weight,
                exercise.rep_max,
                f"Llegaste al tope del rango {rep_range} sin carga ({last}): añade peso "
                "cuando quieras y regístralo.",
            )
        return build(
            weight + exercise.increment_kg,
            exercise.rep_min,
            f"Completaste el tope del rango {rep_range} ({last}): sube a "
            f"{fmt_kg(weight + exercise.increment_kg)} y vuelve a {exercise.rep_min} repeticiones.",
        )
    if low_reps < exercise.rep_min:
        if len(done) > 1 and loaded:
            prev_weight, prev_low, _, _ = _reference(done[1])
            if prev_low < exercise.rep_min and prev_weight >= weight:
                return build(
                    _half_kg(weight * BACKOFF),
                    exercise.rep_min,
                    f"Dos sesiones seguidas por debajo de {exercise.rep_min} repeticiones "
                    f"({last}): baja un 10 % para volver a entrar en el rango {rep_range}.",
                )
        return build(
            weight,
            exercise.rep_min,
            f"No llegaste a {exercise.rep_min} repeticiones en todas las series ({last}): "
            "repite el mismo peso.",
        )
    if hard:
        return build(
            weight,
            low_reps,
            f"El esfuerzo registrado fue casi máximo ({last}): repite peso y repeticiones "
            "antes de progresar.",
        )
    return build(
        weight,
        low_reps + 1,
        f"Hiciste {last}: mantén el peso y busca una repetición más por serie "
        f"(rango {rep_range}).",
    )


def strength_prescription(
    template_key: str,
    history: History,
    today: date,
    excluded: Collection[str] = (),
) -> tuple[Prescription, list[str]]:
    """Full prescription for a template, swapping excluded exercises for their alternative."""
    exercises: list[ExercisePrescription] = []
    notes: list[str] = []
    used: set[str] = set()
    for key in TEMPLATES[template_key].exercises:
        chosen = key
        if key in excluded:
            options = [
                a for a in EXERCISES[key].alternatives
                if a not in excluded and a not in used and a not in TEMPLATES[template_key].exercises
            ]
            if not options:
                notes.append(f"Sin {EXERCISES[key].name}: lo excluiste y no hay sustituto.")
                continue
            chosen = options[0]
            notes.append(
                f"{EXERCISES[chosen].name} en lugar de {EXERCISES[key].name}, que excluiste."
            )
        used.add(chosen)
        exercise = EXERCISES[chosen]
        prescribed = prescribe_exercise(exercise, history.get(chosen, ()), today)
        if chosen != key:
            # A substitute takes the role (and the cut order) of the exercise it replaces.
            prescribed = prescribed.model_copy(update={"priority": EXERCISES[key].priority})
        exercises.append(prescribed)
    return Prescription(kind=SessionKind.STRENGTH, exercises=exercises), notes


@dataclass(frozen=True)
class CardioOutcome:
    """How a past run/walk recommendation ended."""

    target_min: int
    status: SessionStatus


def _round5(minutes: float) -> int:
    return int(round(minutes / 5) * 5)


def cardio_prescription(
    kind: SessionKind, base_min: int, previous_week: Sequence[CardioOutcome]
) -> Prescription:
    """Duration for a run or walk. Runs grow about 10 % a week while the previous week's
    runs were all completed, between the configured duration and twice that."""
    if kind is SessionKind.WALK:
        return Prescription(
            kind=kind,
            target_minutes=base_min,
            guidance=WALK_GUIDANCE,
            reason=f"Los {base_min} min que configuraste: suma actividad sin restar "
            "recuperación a la fuerza.",
        )
    if not previous_week:
        return Prescription(
            kind=kind,
            target_minutes=base_min,
            guidance=RUN_GUIDANCE,
            reason=f"Punto de partida: los {base_min} min que configuraste.",
        )
    cap = base_min * RUN_CAP_FACTOR
    last_target = min(cap, max(base_min, max(o.target_min for o in previous_week)))
    if all(o.status is SessionStatus.DONE for o in previous_week):
        target = min(cap, max(_round5(last_target * RUN_STEP), last_target + 5))
        reason = (
            f"Completaste todas las carreras de la semana anterior: de {last_target} a "
            f"{target} min."
            if target > last_target
            else f"Ya estás en el tope de {cap} min (el doble de lo configurado): se mantiene."
        )
    else:
        target = last_target
        reason = (
            f"La semana anterior no completaste todas las carreras: se mantiene en "
            f"{target} min."
        )
    return Prescription(kind=kind, target_minutes=target, guidance=RUN_GUIDANCE, reason=reason)
