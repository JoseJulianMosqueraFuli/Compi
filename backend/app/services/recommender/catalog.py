"""Exercise catalog and strength session templates.

Rep ranges follow double progression: add reps inside the range, then add weight.
Main lifts work lower reps with longer rests (strength); secondary lifts and
accessories work higher reps with shorter rests (muscle mass).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Exercise:
    key: str
    name: str
    priority: int  # 1 main lift, 2 secondary, 3 accessory
    sets: int
    rep_min: int
    rep_max: int
    rest_s: int
    increment_kg: float
    alternatives: tuple[str, ...] = ()


_EXERCISES = (
    Exercise("squat", "Sentadilla con barra", 1, 3, 5, 8, 150, 5.0, ("leg_press",)),
    Exercise("rdl", "Peso muerto rumano", 1, 3, 6, 10, 150, 5.0, ("leg_curl",)),
    Exercise("bench", "Press de banca", 1, 3, 5, 8, 150, 2.5, ("incline_db",)),
    Exercise("ohp", "Press militar", 1, 3, 6, 10, 120, 2.5, ("incline_db",)),
    Exercise("row", "Remo con barra", 1, 3, 6, 10, 120, 2.5, ("cable_row",)),
    Exercise("leg_press", "Prensa de piernas", 2, 3, 8, 12, 120, 10.0, ("lunge",)),
    Exercise("lunge", "Zancadas con mancuernas", 2, 3, 8, 12, 90, 2.0, ("leg_press",)),
    Exercise("pulldown", "Jalón al pecho", 2, 3, 8, 12, 90, 2.5, ("cable_row",)),
    Exercise("cable_row", "Remo en polea", 2, 3, 8, 12, 90, 2.5, ("pulldown",)),
    Exercise("incline_db", "Press inclinado con mancuernas", 2, 3, 8, 12, 90, 2.0, ()),
    Exercise("leg_curl", "Curl femoral", 3, 2, 10, 15, 60, 2.5, ()),
    Exercise("calf_raise", "Elevación de talones", 3, 2, 10, 15, 60, 5.0, ()),
    Exercise("lateral_raise", "Elevaciones laterales", 3, 2, 12, 15, 60, 1.0, ("face_pull",)),
    Exercise("face_pull", "Face pull", 3, 2, 12, 15, 60, 2.5, ("lateral_raise",)),
    Exercise("curl", "Curl de bíceps", 3, 2, 10, 15, 60, 1.0, ()),
    Exercise("triceps", "Extensión de tríceps en polea", 3, 2, 10, 15, 60, 2.5, ()),
    Exercise("cable_crunch", "Crunch en polea", 3, 2, 10, 15, 60, 2.5, ()),
)

EXERCISES: dict[str, Exercise] = {e.key: e for e in _EXERCISES}


@dataclass(frozen=True)
class Template:
    key: str
    title: str
    exercises: tuple[str, ...]


_TEMPLATES = (
    Template("full_a", "Fuerza A · cuerpo completo",
             ("squat", "bench", "cable_row", "leg_curl", "lateral_raise", "triceps")),
    Template("full_b", "Fuerza B · cuerpo completo",
             ("rdl", "ohp", "pulldown", "lunge", "curl", "cable_crunch")),
    Template("full_c", "Fuerza C · cuerpo completo",
             ("leg_press", "incline_db", "row", "calf_raise", "face_pull", "curl")),
    Template("upper_a", "Fuerza · tren superior A",
             ("bench", "row", "incline_db", "pulldown", "lateral_raise", "triceps")),
    Template("lower_a", "Fuerza · tren inferior A",
             ("squat", "rdl", "leg_press", "leg_curl", "calf_raise", "cable_crunch")),
    Template("upper_b", "Fuerza · tren superior B",
             ("ohp", "pulldown", "bench", "cable_row", "face_pull", "curl")),
    Template("lower_b", "Fuerza · tren inferior B",
             ("rdl", "leg_press", "lunge", "leg_curl", "calf_raise", "cable_crunch")),
)

TEMPLATES: dict[str, Template] = {t.key: t for t in _TEMPLATES}

# Full body while there are up to three days (each muscle still gets worked if a day is
# missed); upper/lower split with four.
_SPLITS: dict[int, tuple[str, ...]] = {
    0: (),
    1: ("full_a",),
    2: ("full_a", "full_b"),
    3: ("full_a", "full_b", "full_c"),
    4: ("upper_a", "lower_a", "upper_b", "lower_b"),
}


def split_for(sessions_per_week: int) -> tuple[str, ...]:
    """Template keys for a week with this many strength sessions."""
    return _SPLITS[max(0, min(sessions_per_week, max(_SPLITS)))]
