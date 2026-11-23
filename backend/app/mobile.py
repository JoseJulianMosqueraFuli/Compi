"""LAN receiver for the paired iPhone. The personal dashboard runs on loopback separately."""

import logging
from secrets import compare_digest
from time import perf_counter
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry import metrics, trace
from sqlalchemy import false
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.models.health import HealthObservation, HealthSyncCursor
from app.routers import healthkit

logger = logging.getLogger("uvicorn.error")
tracer = trace.get_tracer("compi.ingestion")
meter = metrics.get_meter("compi.ingestion")
batch_time = meter.create_histogram("compi.healthkit.batch.duration", unit="ms")
batch_count = meter.create_counter("compi.healthkit.batch.requests")
MAX_BATCH_BYTES = 1024 * 1024
CONNECTION_PATH = "/api/healthkit/connection"
RECEIVER_ROUTES = {("GET", CONNECTION_PATH), ("POST", "/api/healthkit/batches")}
PRIVATE_HEADERS = {"Cache-Control": "no-store"}
app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, redirect_slashes=False)
app.include_router(healthkit.router)


def _error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status_code, headers=PRIVATE_HEADERS)


@app.get(CONNECTION_PATH)
def check_connection(session: Annotated[Session, Depends(get_session)]) -> JSONResponse:
    # Both tables and their mapped columns must exist. The false predicate reads no samples.
    session.exec(select(HealthSyncCursor, HealthObservation).join(HealthObservation).where(false())).close()
    return JSONResponse({"status": "ready", "protocol_version": 1}, headers=PRIVATE_HEADERS)


@app.middleware("http")
async def paired_receiver(request: Request, call_next):
    if (request.method, request.url.path) not in RECEIVER_ROUTES:
        return _error(404, "not found")
    if request.url.scheme != "https":
        return _error(403, "HTTPS required")
    secret = get_settings().healthkit_sync_token
    token = secret.get_secret_value() if secret else ""
    if len(token) < 32:
        return _error(503, "pairing unavailable")
    authorization = request.headers.get("authorization", "").encode()
    if not compare_digest(authorization, f"Bearer {token}".encode()):
        return _error(401, "pairing required")
    if request.method == "GET":
        return await call_next(request)
    length = request.headers.get("content-length", "")
    if not length.isascii() or not length.isdecimal():
        return _error(411, "content length required")
    if len(length) > 7 or int(length) > MAX_BATCH_BYTES:
        return _error(413, "batch too large")
    started = perf_counter()
    status_code = 500
    with tracer.start_as_current_span(
        "healthkit.batch",
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["Cache-Control"] = "no-store"
            return response
        finally:
            elapsed_ms = (perf_counter() - started) * 1000
            attributes = {"http.response.status_code": status_code}
            span.set_attributes(attributes)
            batch_count.add(1, attributes)
            batch_time.record(elapsed_ms, attributes)
            logger.info("healthkit.batch status=%d duration_ms=%.1f", status_code, elapsed_ms)


@app.exception_handler(SQLAlchemyError)
async def storage_unavailable(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    return _error(503, "storage unavailable")


@app.exception_handler(RequestValidationError)
async def invalid_batch(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error(422, "invalid HealthKit batch")
