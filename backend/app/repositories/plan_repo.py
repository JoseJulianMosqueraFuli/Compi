"""Data-access layer for the periodization hierarchy (Req 4.1, 4.2, 4.3, 7.3)."""
from collections.abc import Sequence

from sqlmodel import Session, select

from app.models.periodization import (
    Macrociclo,
    Mesociclo,
    Microciclo,
    SesionPlanificada,
)
from app.models.workout import Workout


class PlanNotFoundError(LookupError):
    """Raised when a plan node is queried by id and does not exist (Req 7.4)."""


class PlanRepository:
    """Repository for macro/meso/microciclo and planned sessions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_macrociclo(self, macrociclo: Macrociclo) -> Macrociclo:
        self._session.add(macrociclo)
        self._session.flush()
        return macrociclo

    def create_mesociclo(self, mesociclo: Mesociclo) -> Mesociclo:
        self._session.add(mesociclo)
        self._session.flush()
        return mesociclo

    def create_microciclo(self, microciclo: Microciclo) -> Microciclo:
        self._session.add(microciclo)
        self._session.flush()
        return microciclo

    def create_sesion(self, sesion: SesionPlanificada) -> SesionPlanificada:
        """Persist a planned session linked to a microciclo (Req 4.3)."""
        self._session.add(sesion)
        self._session.flush()
        return sesion

    def link_sesion_to_workout(self, sesion_id: int, workout: Workout) -> SesionPlanificada:
        """Associate an existing planned session with a real workout (Req 4.2)."""
        sesion = self._session.get(SesionPlanificada, sesion_id)
        if sesion is None:
            raise PlanNotFoundError(sesion_id)
        sesion.workout = workout
        self._session.add(sesion)
        self._session.flush()
        return sesion

    def get_macrociclo(self, macrociclo_id: int) -> Macrociclo:
        macro = self._session.get(Macrociclo, macrociclo_id)
        if macro is None:
            raise PlanNotFoundError(macrociclo_id)
        return macro

    def get_microciclos(self, mesociclo_id: int) -> Sequence[Microciclo]:
        stmt = (
            select(Microciclo)
            .where(Microciclo.mesociclo_id == mesociclo_id)
            .order_by(Microciclo.order_index)
        )
        return self._session.exec(stmt).all()

    def list_macrociclos(self) -> Sequence[Macrociclo]:
        return self._session.exec(select(Macrociclo)).all()

    def get_sesion(self, sesion_id: int) -> SesionPlanificada:
        sesion: SesionPlanificada | None = self._session.get(SesionPlanificada, sesion_id)
        if sesion is None:
            raise PlanNotFoundError(sesion_id)
        return sesion
