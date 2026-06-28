"""SQLModel entities and shared domain value types."""
from app.models.auth import (
    DEFAULT_HR_MAX_BPM,
    USER_PROFILE_SINGLETON_ID,
    OAuthToken,
    UserProfile,
)
from app.models.domain import (
    HRZone,
    PlannedVsActual,
    ProgressionPoint,
    Split,
    WorkoutType,
)
from app.models.periodization import (
    Macrociclo,
    Mesociclo,
    Microciclo,
    SesionPlanificada,
)
from app.models.workout import (
    CardioDetail,
    StrengthDetail,
    Workout,
    recompute_strength_summary,
)

__all__ = [
    "DEFAULT_HR_MAX_BPM",
    "USER_PROFILE_SINGLETON_ID",
    "CardioDetail",
    "HRZone",
    "Macrociclo",
    "Mesociclo",
    "Microciclo",
    "OAuthToken",
    "PlannedVsActual",
    "ProgressionPoint",
    "SesionPlanificada",
    "Split",
    "StrengthDetail",
    "UserProfile",
    "Workout",
    "WorkoutType",
    "recompute_strength_summary",
]
