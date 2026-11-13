"""How long a session takes: a simple model first, corrected by what really happened."""
import math
from collections.abc import Sequence
from statistics import median

from app.models.domain import SessionKind
from app.services.recommender.types import Prescription

WARMUP_S = 300
EXERCISE_CHANGE_S = 90
SET_SETUP_S = 20
SECONDS_PER_REP = 4

MIN_SAMPLES = 3
MAX_SAMPLES = 8
FACTOR_BOUNDS = (0.6, 1.8)


def model_minutes(prescription: Prescription) -> float:
    """Minutes the prescription takes on paper, before any personal correction."""
    if prescription.kind is not SessionKind.STRENGTH:
        return float(prescription.target_minutes or 0)
    if not prescription.exercises:
        return 0.0
    seconds = WARMUP_S
    for exercise in prescription.exercises:
        seconds += EXERCISE_CHANGE_S
        for s in exercise.sets:
            seconds += SET_SETUP_S + s.reps * SECONDS_PER_REP + s.rest_s
    return seconds / 60.0


def estimated_minutes(prescription: Prescription, factor: float = 1.0) -> int:
    """Minutes to reserve in a window. The learned factor only applies to strength:
    a run or walk lasts what it prescribes."""
    minutes = model_minutes(prescription)
    if prescription.kind is SessionKind.STRENGTH:
        minutes *= factor
    return math.ceil(minutes - 1e-9)


def learn_duration_factor(samples: Sequence[tuple[float, float]]) -> float:
    """Real/model duration ratio from completed sessions, most recent first.

    Each sample is (model_minutes, actual_minutes). Until there are MIN_SAMPLES the
    declared durations stand (factor 1.0). The median keeps one odd session from moving it.
    """
    ratios = [actual / model for model, actual in samples[:MAX_SAMPLES] if model > 0 and actual > 0]
    if len(ratios) < MIN_SAMPLES:
        return 1.0
    low, high = FACTOR_BOUNDS
    return round(min(high, max(low, median(ratios))), 2)
