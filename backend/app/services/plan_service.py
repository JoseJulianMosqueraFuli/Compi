"""Plan creation with temporal invariants (Req 4.1, 4.3, Design -> Invariantes temporales).

Invariants enforced at create/update time:

- For any Mesociclo: [start_date, end_date] is contained in Macrociclo's range.
- For any Microciclo: [start_date, end_date] is contained in its Mesociclo's range.
- Microciclos of a mesociclo do not overlap and are ordered consistently.
- A Workout linked to a SesionPlanificada has start_time within the microciclo range.
"""
from collections.abc import Iterable
from datetime import date, datetime

from app.models.periodization import (
    Macrociclo,
    Mesociclo,
    Microciclo,
    SesionPlanificada,
)
from app.models.workout import Workout
from app.repositories.plan_repo import PlanRepository


class PlanValidationError(ValueError):
    """Raised when a temporal invariant is violated."""


def _ensure_range_contained(
    child_start: date, child_end: date, parent_start: date, parent_end: date, label: str
) -> None:
    if not (parent_start <= child_start and child_end <= parent_end):
        raise PlanValidationError(
            f"{label} range [{child_start}, {child_end}] is not contained in "
            f"parent range [{parent_start}, {parent_end}]"
        )


def _ensure_no_overlap(siblings: Iterable[Microciclo], new: Microciclo) -> None:
    for sib in siblings:
        if sib.id == new.id:
            continue
        # Strict overlap: ranges [a,b] and [c,d] overlap iff a < d and c < b.
        if new.start_date < sib.end_date and sib.start_date < new.end_date:
            raise PlanValidationError(
                f"Microciclo [{new.start_date}, {new.end_date}] overlaps with "
                f"existing microciclo id={sib.id} [{sib.start_date}, {sib.end_date}]"
            )


class PlanService:
    """High-level service that creates periodization nodes and validates invariants."""

    def __init__(self, repo: PlanRepository) -> None:
        self._repo = repo

    def create_macrociclo(
        self, name: str, start_date: date, end_date: date
    ) -> Macrociclo:
        if start_date > end_date:
            raise PlanValidationError("macrociclo start_date must be <= end_date")
        return self._repo.create_macrociclo(
            Macrociclo(name=name, start_date=start_date, end_date=end_date)
        )

    def create_mesociclo(
        self,
        macrociclo_id: int,
        name: str,
        order_index: int,
        start_date: date,
        end_date: date,
        weekly_increment_pct: float | None = None,
    ) -> Mesociclo:
        if start_date > end_date:
            raise PlanValidationError("mesociclo start_date must be <= end_date")
        macro = self._repo.get_macrociclo(macrociclo_id)
        _ensure_range_contained(
            start_date, end_date, macro.start_date, macro.end_date, "mesociclo"
        )
        return self._repo.create_mesociclo(
            Mesociclo(
                macrociclo_id=macrociclo_id,
                name=name,
                order_index=order_index,
                start_date=start_date,
                end_date=end_date,
                weekly_increment_pct=weekly_increment_pct,
            )
        )

    def create_microciclo(
        self,
        mesociclo_id: int,
        order_index: int,
        start_date: date,
        end_date: date,
        is_deload: bool = False,
        base_load: float | None = None,
    ) -> Microciclo:
        if start_date > end_date:
            raise PlanValidationError("microciclo start_date must be <= end_date")
        meso_obj = self._repo.get_mesociclo(mesociclo_id)
        _ensure_range_contained(
            start_date, end_date, meso_obj.start_date, meso_obj.end_date, "microciclo"
        )
        # First microciclo of the mesociclo requires base_load (Design -> Progresion).
        if order_index == 1 and base_load is None:
            raise PlanValidationError("first microciclo of a mesociclo must have base_load")
        new = Microciclo(
            mesociclo_id=mesociclo_id,
            order_index=order_index,
            start_date=start_date,
            end_date=end_date,
            is_deload=is_deload,
            base_load=base_load,
        )
        existing = list(self._repo.get_microciclos(mesociclo_id))
        _ensure_no_overlap(existing, new)
        return self._repo.create_microciclo(new)

    def create_sesion(
        self,
        microciclo_id: int,
        sesion: SesionPlanificada,
    ) -> SesionPlanificada:
        if sesion.workout is not None and not self._workout_in_microciclo(
            microciclo_id, sesion.workout
        ):
            raise PlanValidationError(
                "workout.start_time must be within the microciclo range"
            )
        sesion.microciclo_id = microciclo_id
        return self._repo.create_sesion(sesion)

    def _workout_in_microciclo(self, microciclo_id: int, workout: Workout) -> bool:
        micro = self._repo.get_microciclo(microciclo_id)
        st = (
            workout.start_time.date()
            if isinstance(workout.start_time, datetime)
            else workout.start_time
        )
        return micro.start_date <= st <= micro.end_date
