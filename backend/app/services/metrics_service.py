"""Pure metric computations (Req 8.1, 8.2, 8.3 - Properties 4, 5, 6).

Fórmulas (Design -> Data Models -> Fórmulas de métricas):

- Zonas FC: 5 zonas contiguas en %FCmax con cortes 60/70/80/90%.
- Volumen: fuerza -> strength_total_volume_kg, cardio -> duration_s / 60.
- Carga (TRIMP simplificado): carga = duration_min * (avg_hr / hr_max).
"""
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.models.domain import HRZone, WorkoutType
from app.models.workout import Workout

# Boundaries for the 5 %FCmax zones (Design -> Fórmulas de métricas -> Zonas).
ZONE_CUTS: tuple[float, ...] = (0.60, 0.70, 0.80, 0.90)


@dataclass(frozen=True)
class HRZoneSpec:
    """A contiguous heart-rate zone definition."""

    zone: int
    lower_bpm: int
    upper_bpm: int

    def to_hr_zone(self, seconds_in_zone: int = 0) -> HRZone:
        return HRZone(
            zone=self.zone,
            lower_bpm=self.lower_bpm,
            upper_bpm=self.upper_bpm,
            seconds_in_zone=seconds_in_zone,
        )


def compute_hr_zones(hr_max_bpm: int) -> list[HRZoneSpec]:
    """Return 5 contiguous, non-overlapping %FCmax zones (Req 8.1, Property 4).

    The first zone's lower bound is 0 and the last zone's upper bound is hr_max_bpm.
    """
    if hr_max_bpm <= 0:
        raise ValueError("hr_max_bpm must be positive")
    boundaries = [0] + [int(round(hr_max_bpm * cut)) for cut in ZONE_CUTS] + [hr_max_bpm]
    zones: list[HRZoneSpec] = []
    for i in range(5):
        lower = boundaries[i]
        upper = boundaries[i + 1]
        # Ensure adjacency: make upper of zone i exactly equal to lower of zone i+1.
        if i > 0:
            lower = zones[i - 1].upper_bpm
        zones.append(HRZoneSpec(zone=i + 1, lower_bpm=lower, upper_bpm=upper))
    return zones


def workout_volume(workout: Workout) -> float:
    """Volume for a single workout (Req 8.2)."""
    if workout.type == WorkoutType.STRENGTH:
        return float(workout.strength_total_volume_kg or 0.0)
    return float(workout.duration_s) / 60.0


def total_volume(workouts: Iterable[Workout]) -> float:
    """Aggregate volume over a collection of workouts (Req 8.2, Property 5)."""
    return sum(workout_volume(w) for w in workouts)


def _effective_avg_hr(workout: Workout) -> int:
    """Best-effort avg HR for the load formula (Req 8.3)."""
    if workout.avg_hr is not None:
        return workout.avg_hr
    if workout.max_hr is not None:
        return int(round(workout.max_hr * 0.75))
    return 0


def workout_training_load(workout: Workout, hr_max_bpm: int) -> float:
    """TRIMP simplificado para un workout (Req 8.3).

    carga = duration_min * (avg_hr / hr_max). With avg_hr = None approximated
    as max_hr * 0.75 (or 0 if both are missing), so the value stays non-negative.
    """
    if hr_max_bpm <= 0:
        raise ValueError("hr_max_bpm must be positive")
    duration_min = workout.duration_s / 60.0
    return duration_min * (_effective_avg_hr(workout) / hr_max_bpm)


def total_training_load(workouts: Sequence[Workout], hr_max_bpm: int) -> float:
    """Aggregate training load over a sequence of workouts (Req 8.3, Property 6)."""
    return sum(workout_training_load(w, hr_max_bpm) for w in workouts)
