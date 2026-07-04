"""Planned vs actual comparison (Req 9.3, Property 8)."""
from app.models.domain import PlannedVsActual


def compare_planned_vs_actual(planned: float, actual: float) -> PlannedVsActual:
    """Compare a planned value to an executed value (Req 9.3, Property 8).

    delta = actual - planned.
    delta_pct = (actual - planned) / planned * 100 when planned > 0;
                when planned == 0, returns 0.0 if actual == 0 else float('inf').
    """
    if planned < 0 or actual < 0:
        raise ValueError("planned and actual must be non-negative")
    delta = actual - planned
    delta_pct = (
        (0.0 if actual == 0 else float("inf")) if planned == 0 else (delta / planned) * 100.0
    )
    return PlannedVsActual(
        planned_load=planned, actual_load=actual, delta=delta, delta_pct=delta_pct
    )
