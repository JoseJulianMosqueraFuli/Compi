"""Progression sequence (Req 9.1, 9.2, Design -> Secuencia de progresión, Property 7)."""
from collections.abc import Sequence

from app.models.domain import ProgressionPoint
from app.models.periodization import Microciclo

DELOAD_FACTOR = 0.5  # Design -> deload reduces to 50% of previous microciclos's load.


def compute_progression(microciclos: Sequence[Microciclo]) -> list[ProgressionPoint]:
    """Compute target load per microciclo following the design rule.

    Rule:
      - target_load(M1) = M1.base_load (must be non-null, validated by PlanService).
      - For Mi, i>1, is_deload=False: target = previous * (1 + weekly_increment_pct).
        weekly_increment_pct is taken from the mesociclo parent.
      - For Mi, i>1, is_deload=True: target = previous * 0.5.
    Microciclos must be ordered by order_index; this is the caller's responsibility
    (PlanService keeps the ordering consistent).
    """
    if not microciclos:
        return []
    ordered = sorted(microciclos, key=lambda m: m.order_index)
    result: list[ProgressionPoint] = []
    prev_load: float | None = None
    for m in ordered:
        if prev_load is None:
            if m.base_load is None:
                raise ValueError(
                    f"microciclo id={m.id} (order_index=1) must have base_load"
                )
            load = float(m.base_load)
        elif m.is_deload:
            load = prev_load * DELOAD_FACTOR
        else:
            inc_pct = m.mesociclo.weekly_increment_pct or 0.0
            load = prev_load * (1.0 + inc_pct)
        if load < 0:
            raise ValueError("computed target_load is negative")
        result.append(
            ProgressionPoint(microciclo_id=m.id, target_load=load, is_deload=m.is_deload)
        )
        prev_load = load
    return result
