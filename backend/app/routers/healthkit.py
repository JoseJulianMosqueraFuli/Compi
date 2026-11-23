"""Local incremental ingestion from the authorized iPhone."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.clock import get_now
from app.db import get_session
from app.models.health_schemas import HealthBatchAck, HealthBatchIn
from app.services.healthkit import HealthStreamConflictError, apply_batch

router = APIRouter(prefix="/api/healthkit", tags=["healthkit"])


@router.post("/batches", response_model=HealthBatchAck)
def receive_batch(
    payload: HealthBatchIn,
    session: Annotated[Session, Depends(get_session)],
    now: Annotated[datetime, Depends(get_now)],
) -> HealthBatchAck:
    try:
        applied = apply_batch(session, payload, now)
    except HealthStreamConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return HealthBatchAck(sequence=payload.sequence, applied=applied)
