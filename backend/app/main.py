"""FastAPI application entrypoint: routers, lifespan, scheduler, error handlers (Req 1.4, 6.1, 7.4, 11.1)."""
import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.db import get_session
from app.models.auth import DEFAULT_HR_MAX_BPM, USER_PROFILE_SINGLETON_ID, UserProfile
from app.routers import auth, availability, health_overview, metrics, plans, recommendations, workouts
from app.services.sync_service import start_scheduler

_scheduler: BackgroundScheduler | None = None


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Boot the scheduler and ensure the UserProfile singleton exists (Req 1.4, 6.1)."""
    global _scheduler
    settings = get_settings()

    # Ensure UserProfile singleton with a default hr_max_bpm if absent.
    from app.db import engine

    with Session(engine) as session:
        existing = session.get(UserProfile, USER_PROFILE_SINGLETON_ID)
        if existing is None:
            session.add(UserProfile(hr_max_bpm=DEFAULT_HR_MAX_BPM))
            session.commit()

    _scheduler = start_scheduler(settings) if settings.legacy_sync_mode != "off" else None
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
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]"])

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(workouts.router)
    app.include_router(metrics.router)
    app.include_router(plans.router)
    app.include_router(availability.router)
    app.include_router(recommendations.router)
    app.include_router(auth.router)
    app.include_router(health_overview.router)

    @app.exception_handler(IntegrityError)
    async def _on_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "integrity constraint violated"},
        )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["meta"])
    def ready(session: Annotated[Session, Depends(get_session)]) -> JSONResponse:
        try:
            session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ready"})

    return app


app = create_app()
