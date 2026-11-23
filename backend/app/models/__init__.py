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
    SessionKind,
    SessionStatus,
    Split,
    WorkoutType,
)
from app.models.health import HealthObservation, HealthSyncCursor
from app.models.periodization import (
    Macrociclo,
    Mesociclo,
    Microciclo,
    SesionPlanificada,
)
from app.models.training import (
    TRAINING_PREFERENCES_SINGLETON_ID,
    AvailabilityException,
    AvailabilityWindow,
    PlanChange,
    RecommendedSession,
    TrainingPreferences,
    WeekPlan,
)
from app.models.workout import (
    CardioDetail,
    ExerciseSet,
    Workout,
    WorkoutExercise,
    recompute_strength_summary,
)

__all__ = [
    "DEFAULT_HR_MAX_BPM",
    "TRAINING_PREFERENCES_SINGLETON_ID",
    "USER_PROFILE_SINGLETON_ID",
    "AvailabilityException",
    "AvailabilityWindow",
    "CardioDetail",
    "ExerciseSet",
    "HRZone",
    "HealthObservation",
    "HealthSyncCursor",
    "Macrociclo",
    "Mesociclo",
    "Microciclo",
    "OAuthToken",
    "PlanChange",
    "PlannedVsActual",
    "ProgressionPoint",
    "RecommendedSession",
    "SesionPlanificada",
    "SessionKind",
    "SessionStatus",
    "Split",
    "TrainingPreferences",
    "UserProfile",
    "WeekPlan",
    "Workout",
    "WorkoutExercise",
    "WorkoutType",
    "recompute_strength_summary",
]
