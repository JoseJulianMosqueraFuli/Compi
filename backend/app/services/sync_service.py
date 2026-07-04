"""Background sync service: fetch -> dedup -> persist (Req 6.1, 6.2, 6.3, 6.4)."""
import contextlib
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlmodel import Session

from app.config import Settings, get_settings
from app.db import engine
from app.providers.base import WorkoutProvider
from app.providers.mock import MockProvider
from app.providers.selection import build_provider
from app.repositories.token_repo import TokenRepository
from app.repositories.workout_repo import WorkoutRepository
from app.services.dedup import partition_new_workouts
from app.services.token_refresh import needs_refresh


def _last_sync_default() -> datetime:
    """Epoch used when no sync has run yet (Req 6.1 first run)."""
    return datetime(1970, 1, 1, tzinfo=UTC)


class SyncService:
    """Orchestrates one synchronization cycle (Req 6.1–6.4)."""

    def __init__(
        self,
        provider: WorkoutProvider,
        session: Session,
        last_sync: datetime | None = None,
        now: datetime | None = None,
    ) -> None:
        self._provider = provider
        self._session = session
        self._last_sync = last_sync or _last_sync_default()
        self._now = now

    def run_once(self) -> tuple[int, int]:
        """Execute one sync cycle. Returns (inserted, skipped)."""
        if isinstance(self._provider, MockProvider) is False and isinstance(
            self._provider, object
        ):
            token_repo = TokenRepository(self._session)
            from app.providers.huawei import HuaweiProvider

            if isinstance(self._provider, HuaweiProvider):
                token = token_repo.get_by_provider("huawei")
                if token is not None and needs_refresh(
                    token.expires_at, self._now or datetime.now(UTC)
                ):
                    refreshed = self._provider.authenticate()
                    if refreshed.success:
                        token_repo.upsert(
                            "huawei",
                            refreshed.refresh_token or token.refresh_token,
                            refreshed.access_token,
                            refreshed.expires_at,
                        )

        workouts = self._provider.fetch_workouts(self._last_sync)
        repo = WorkoutRepository(self._session)
        existing = [w.external_id for w in repo.list(limit=10_000)]
        new, skipped = partition_new_workouts(existing, workouts)

        for ext in new:
            w = self._build_workout(ext)
            repo.insert(w)

        self._session.commit()
        return len(new), len(skipped)

    def _build_workout(self, ext):
        """Build a Workout from an ExternalWorkout via the pure mapping."""
        from app.providers.mapping import external_to_workout

        return external_to_workout(ext)


def build_sync_service(
    settings: Settings | None = None,
    session: Session | None = None,
    last_sync: datetime | None = None,
) -> SyncService:
    """Factory: build the SyncService with the active provider (Req 1.4, 5.4)."""
    s = settings or get_settings()
    sess = session or Session(engine)
    token_repo = TokenRepository(sess)
    has_token = token_repo.get_by_provider("huawei") is not None
    provider = build_provider(s, has_token)
    return SyncService(provider=provider, session=sess, last_sync=last_sync)


def start_scheduler(
    settings: Settings | None = None,
) -> BackgroundScheduler:
    """Start a background scheduler that triggers sync every N minutes (Req 6.1)."""
    s = settings or get_settings()
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _scheduled_job,
        trigger=IntervalTrigger(minutes=s.sync_interval_minutes),
        id="compi-sync",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    return scheduler


def _scheduled_job() -> None:
    """Job entrypoint used by APScheduler."""
    with contextlib.suppress(Exception):
        # Failures are retried on the next interval (design - Error Handling).
        build_sync_service().run_once()
