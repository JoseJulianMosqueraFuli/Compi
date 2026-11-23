"""Background sync service: fetch -> dedup -> persist (Req 6.1, 6.2, 6.3, 6.4)."""
import logging
from contextlib import closing
from datetime import UTC, datetime
from time import monotonic

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlmodel import Session

from app.config import Settings, get_settings
from app.db import engine
from app.models.workout import CardioDetail
from app.providers.base import WorkoutProvider
from app.providers.huawei import HuaweiAuthError, HuaweiFetchError, HuaweiProvider
from app.providers.mapping import external_to_workout
from app.providers.selection import ProviderUnavailableError, build_provider
from app.repositories.token_repo import TokenRepository
from app.repositories.workout_repo import WorkoutRepository
from app.services.dedup import partition_new_workouts
from app.services.token_refresh import needs_refresh

logger = logging.getLogger(__name__)


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
        try:
            if isinstance(self._provider, HuaweiProvider):
                self._restore_authorization(self._provider)
            workouts = self._provider.fetch_workouts(self._last_sync)
            repo = WorkoutRepository(self._session)
            existing = repo.existing_external_ids(ext.external_id for ext in workouts)
            new, skipped = partition_new_workouts(existing, workouts)
            for ext in new:
                workout = external_to_workout(ext)
                if ext.cardio is not None:
                    workout.cardio_detail = CardioDetail(**ext.cardio.model_dump())
                repo.insert(workout)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return len(new), len(skipped)

    def _restore_authorization(self, provider: HuaweiProvider) -> None:
        repo = TokenRepository(self._session)
        token = repo.get_by_provider("huawei", for_update=True)
        if token is None or not token.refresh_token:
            raise HuaweiAuthError("authorization required")
        provider.restore_tokens(token.access_token, token.refresh_token, token.expires_at)
        if not token.access_token or needs_refresh(token.expires_at, self._now or datetime.now(UTC)):
            refreshed = provider.authenticate()
            if not refreshed.success or not refreshed.access_token:
                raise HuaweiAuthError("refresh failed")
            repo.upsert(
                "huawei",
                refreshed.refresh_token or token.refresh_token,
                refreshed.access_token,
                refreshed.expires_at,
            )
        # Release the token lock and retain a rotated credential even if the workout fetch fails.
        self._session.commit()

    def close(self) -> None:
        self._provider.close()


def build_sync_service(
    session: Session,
    settings: Settings | None = None,
    last_sync: datetime | None = None,
) -> SyncService:
    """Factory: build the SyncService with the active provider (Req 1.4, 5.4)."""
    s = settings or get_settings()
    has_token = (
        s.legacy_sync_mode == "huawei"
        and TokenRepository(session).get_by_provider("huawei") is not None
    )
    provider = build_provider(s, has_token)
    return SyncService(provider=provider, session=session, last_sync=last_sync)


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
    """Report one outcome and let APScheduler record failures and retry at the next interval."""
    started = monotonic()
    mode = get_settings().legacy_sync_mode
    try:
        with Session(engine) as session, closing(build_sync_service(session)) as service:
            inserted, skipped = service.run_once()
    except Exception as exc:
        # Known provider messages contain only controlled categories or a numeric HTTP status.
        # Database and validation exceptions may embed parameters or individual measurements.
        known_errors = (HuaweiFetchError, HuaweiAuthError, ProviderUnavailableError)
        reason = str(exc) if isinstance(exc, known_errors) else type(exc).__name__
        logger.error(
            "sync_failed source=%s reason=%s duration_ms=%d", mode, reason, (monotonic() - started) * 1000,
        )
        raise RuntimeError("legacy sync failed") from None
    logger.info(
        "sync_completed source=%s inserted=%d skipped=%d duration_ms=%d",
        mode, inserted, skipped, (monotonic() - started) * 1000,
    )
