"""Periodization hierarchy: Macrociclo -> Mesociclo -> Microciclo -> SesionPlanificada (Req 4.1, 4.2)."""  # noqa: E501
from datetime import date
from typing import Optional

from sqlalchemy.orm import Mapped
from sqlmodel import Field, Relationship, SQLModel

from app.models.domain import WorkoutType


class Macrociclo(SQLModel, table=True):
    """Top-level planning period (Req 4.1)."""

    __tablename__ = "macrociclo"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    start_date: date
    end_date: date

    mesociclos: Mapped[list["Mesociclo"]] = Relationship(
        back_populates="macrociclo",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class Mesociclo(SQLModel, table=True):
    """Mid-level planning period (Req 4.1, 9.1)."""

    __tablename__ = "mesociclo"

    id: int | None = Field(default=None, primary_key=True)
    macrociclo_id: int = Field(foreign_key="macrociclo.id", index=True)
    name: str
    order_index: int = Field(ge=1)
    start_date: date
    end_date: date
    weekly_increment_pct: float | None = Field(
        default=None,
        description="Weekly load increase applied to subsequent microciclos (Req 9.1).",
    )

    macrociclo: Mapped["Macrociclo"] = Relationship(back_populates="mesociclos")
    microciclos: Mapped[list["Microciclo"]] = Relationship(
        back_populates="mesociclo",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class Microciclo(SQLModel, table=True):
    """Short planning period (typically one week) (Req 4.1, 9.2)."""

    __tablename__ = "microciclo"

    id: int | None = Field(default=None, primary_key=True)
    mesociclo_id: int = Field(foreign_key="mesociclo.id", index=True)
    order_index: int = Field(ge=1)
    start_date: date
    end_date: date
    is_deload: bool = Field(default=False)
    base_load: float | None = Field(
        default=None,
        ge=0,
        description="Seed for the first microciclo of a mesociclo (Design - Progresion).",
    )

    mesociclo: Mapped["Mesociclo"] = Relationship(back_populates="microciclos")
    sesiones_planificadas: Mapped[list["SesionPlanificada"]] = Relationship(
        back_populates="microciclo",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class SesionPlanificada(SQLModel, table=True):
    """Planned session within a microciclo, optionally linked to a real Workout (Req 4.1, 4.2, 4.3)."""  # noqa: E501

    __tablename__ = "sesion_planificada"

    id: int | None = Field(default=None, primary_key=True)
    microciclo_id: int = Field(foreign_key="microciclo.id", index=True)
    planned_type: WorkoutType
    planned_load: float = Field(ge=0)
    planned_volume: float | None = Field(default=None, ge=0)
    workout_id: int | None = Field(default=None, foreign_key="workout.id", index=True)

    microciclo: Mapped["Microciclo"] = Relationship(back_populates="sesiones_planificadas")
    workout: Mapped[Optional["Workout"]] = Relationship(back_populates="sesiones_planificadas")
