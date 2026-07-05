"""FastAPI application entrypoint: routers, lifespan, scheduler, error handlers (Req 1.4, 6.1, 7.4, 11.1)."""
import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.models.auth import DEFAULT_HR_MAX_BPM, USER_PROFILE_SINGLETON_ID, UserProfile
from app.routers import metrics, plans, workouts
from app.services.sync_service import start_scheduler

_scheduler: BackgroundScheduler | None = None


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Boot the scheduler and ensure the UserProfile singleton exists (Req 1.4, 6.1)."""
    global _scheduler
    settings = get_settings()

    # Ensure UserProfile singleton with a default hr_max_bpm if absent.
    from sqlmodel import Session

    from app.db import engine

    with Session(engine) as session:
        existing = session.get(UserProfile, USER_PROFILE_SINGLETON_ID)
        if existing is None:
            session.add(UserProfile(hr_max_bpm=DEFAULT_HR_MAX_BPM))
            session.commit()

    _scheduler = start_scheduler(settings)
    app.state.scheduler = _scheduler
    app.state.started_at = datetime.now(UTC)
    try:
        yield
    finally:
        if _scheduler is not None:
            _scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Compi Training Platform",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(workouts.router)
    app.include_router(metrics.router)
    app.include_router(plans.router)

    @app.exception_handler(IntegrityError)
    async def _on_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "integrity constraint violated"},
        )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
