"""Periodization endpoints (Req 7.3, 4.1, 4.3, 9.1, 9.3)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db import get_session
from app.models.periodization import Mesociclo, Microciclo, SesionPlanificada
from app.repositories.plan_repo import PlanNotFoundError, PlanRepository
from app.routers.schemas import (
    MacrocicloIn,
    MacrocicloOut,
    MesocicloIn,
    MesocicloOut,
    MicrocicloIn,
    MicrocicloOut,
    ProgressionOut,
    ProgressionPointOut,
    SesionIn,
    SesionOut,
)
from app.services.plan_service import PlanService, PlanValidationError
from app.services.progression_service import compute_progression

router = APIRouter(prefix="/api/plans", tags=["plans"])

SessionDep = Annotated[Session, Depends(get_session)]


def _service(session: SessionDep) -> PlanService:
    return PlanService(PlanRepository(session))


@router.get("/macrocycles", response_model=list[MacrocicloOut])
def list_macrocycles(session: SessionDep) -> list[MacrocicloOut]:
    repo = PlanRepository(session)
    return [MacrocicloOut.model_validate(m) for m in repo.list_macrociclos()]


@router.post(
    "/macrocycles", response_model=MacrocicloOut, status_code=status.HTTP_201_CREATED
)
def create_macrociclo(payload: MacrocicloIn, session: SessionDep) -> MacrocicloOut:
    try:
        macro = _service(session).create_macrociclo(
            payload.name, payload.start_date, payload.end_date
        )
    except PlanValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return MacrocicloOut.model_validate(macro)


@router.post(
    "/mesocycles", response_model=MesocicloOut, status_code=status.HTTP_201_CREATED
)
def create_mesociclo(macrociclo_id: int, payload: MesocicloIn, session: SessionDep) -> MesocicloOut:
    try:
        meso = _service(session).create_mesociclo(
            macrociclo_id,
            payload.name,
            payload.order_index,
            payload.start_date,
            payload.end_date,
            payload.weekly_increment_pct,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="macrociclo not found") from exc
    except PlanValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return MesocicloOut.model_validate(meso)


@router.post(
    "/microcycles", response_model=MicrocicloOut, status_code=status.HTTP_201_CREATED
)
def create_microciclo(mesociclo_id: int, payload: MicrocicloIn, session: SessionDep) -> MicrocicloOut:
    try:
        micro = _service(session).create_microciclo(
            mesociclo_id,
            payload.order_index,
            payload.start_date,
            payload.end_date,
            payload.is_deload,
            payload.base_load,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mesociclo not found") from exc
    except PlanValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return MicrocicloOut.model_validate(micro)


@router.post("/sessions", response_model=SesionOut, status_code=status.HTTP_201_CREATED)
def create_sesion(payload: SesionIn, session: SessionDep) -> SesionOut:
    try:
        sesion = _service(session).create_sesion(
            payload.microciclo_id,
            SesionPlanificada(
                microciclo_id=payload.microciclo_id,
                planned_type=payload.planned_type,
                planned_load=payload.planned_load,
                planned_volume=payload.planned_volume,
                workout_id=payload.workout_id,
            ),
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="microciclo not found") from exc
    except PlanValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return SesionOut.model_validate(sesion)


@router.get("/{macrociclo_id}/progression", response_model=ProgressionOut)
def macrociclo_progression(macrociclo_id: int, session: SessionDep) -> ProgressionOut:
    repo = PlanRepository(session)
    try:
        macro = repo.get_macrociclo(macrociclo_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="macrociclo not found") from exc
    # Concatenate microciclos of all mesociclos in order_index.
    all_micros: list[Microciclo] = []
    for meso in macro.mesociclos:
        meso_loaded = session.get(Mesociclo, meso.id)
        if meso_loaded is not None:
            all_micros.extend(repo.get_microciclos(meso_loaded.id))  # type: ignore[arg-type]
    points = compute_progression(all_micros)
    return ProgressionOut(
        macrociclo_id=macrociclo_id,
        points=[
            ProgressionPointOut(
                microciclo_id=p.microciclo_id, target_load=p.target_load, is_deload=p.is_deload
            )
            for p in points
        ],
    )
