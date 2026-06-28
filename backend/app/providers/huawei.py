"""HuaweiProvider stub. Real implementation is added in task 12.2 (Req 5.3, 6.4)."""
from datetime import datetime

from app.providers.base import AuthResult, ExternalWorkout, WorkoutProvider


class HuaweiProvider(WorkoutProvider):
    """Placeholder. Raises until task 12.2 implements the real OAuth client."""

    def __init__(self, *args, **kwargs) -> None:  # noqa: D401, ANN002, ANN003
        raise NotImplementedError(
            "HuaweiProvider will be implemented in task 12.2 (design - Req 5.3, 6.4)."
        )

    def authenticate(self) -> AuthResult:  # pragma: no cover - stub
        raise NotImplementedError

    def is_authenticated(self) -> bool:  # pragma: no cover - stub
        raise NotImplementedError

    def fetch_workouts(self, since: datetime) -> list[ExternalWorkout]:  # pragma: no cover - stub
        raise NotImplementedError
