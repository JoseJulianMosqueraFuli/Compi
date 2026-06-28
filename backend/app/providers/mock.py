"""Deterministic mock provider for development without Huawei credentials (Req 5.2, 5.4)."""
from datetime import datetime, timedelta

from app.models.domain import WorkoutType
from app.providers.base import (
    AuthResult,
    CardioPayload,
    ExternalWorkout,
    StrengthSummaryPayload,
    WorkoutProvider,
)


def _deterministic_id(prefix: str, n: int) -> str:
    """Stable, reproducible external_id so dedup can be exercised (Req 6.2)."""
    return f"mock-{prefix}-{n:04d}"


class MockProvider(WorkoutProvider):
    """WorkoutProvider that returns synthetic, well-formed workouts (Req 5.2).

    The dataset is deterministic given (start_time, count) so deduplication
    behavior is reproducible in tests and PBT.
    """

    DEFAULT_COUNT = 5

    def __init__(self, count: int = DEFAULT_COUNT) -> None:
        self._count = count

    def authenticate(self) -> AuthResult:
        return AuthResult(success=True)

    def is_authenticated(self) -> bool:
        return True

    def fetch_workouts(self, since: datetime) -> list[ExternalWorkout]:
        """Return `count` workouts starting one day after `since`."""
        workouts: list[ExternalWorkout] = []
        for i in range(self._count):
            start = since + timedelta(days=i + 1)
            workouts.append(self._build_one(i, start))
        return workouts

    def _build_one(self, index: int, start: datetime) -> ExternalWorkout:
        if index % 2 == 0:
            return ExternalWorkout(
                external_id=_deterministic_id("cardio", index),
                type=WorkoutType.CARDIO,
                start_time=start,
                duration_s=3600,
                avg_hr=150,
                max_hr=175,
                calories=450.0,
                cardio=CardioPayload(
                    gps_polyline="_p~iF~ps|U_ulLnnqC_mqNvxq`@",
                    avg_pace_s_per_km=300.0,
                    splits=[{"distance_m": 1000.0, "duration_s": 300.0}],
                ),
            )
        return ExternalWorkout(
            external_id=_deterministic_id("strength", index),
            type=WorkoutType.STRENGTH,
            start_time=start,
            duration_s=1800,
            avg_hr=120,
            max_hr=160,
            calories=250.0,
            strength_summary=StrengthSummaryPayload(
                total_volume_kg=2500.0,
                total_sets=5,
                exercises_count=3,
            ),
        )


def make_mock_provider(count: int = MockProvider.DEFAULT_COUNT) -> MockProvider:
    """Factory helper used by the sync service and tests."""
    return MockProvider(count=count)


def get_mock_token_present() -> bool:
    """Helper: the mock provider is always considered authenticated."""
    return True


def get_mock_refresh_token_if_present() -> str | None:
    """No refresh token in mock mode; the provider never expires."""
    return None
