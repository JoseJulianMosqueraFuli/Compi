"""Unit tests for repositories (Req 1.3, 3.4, 3.5, 4.2, 4.3)."""
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from app.models.auth import OAuthToken
from app.models.domain import WorkoutType
from app.models.periodization import (
    Macrociclo,
    Mesociclo,
    Microciclo,
    SesionPlanificada,
)
from app.models.workout import (
    CardioDetail,
    StrengthDetail,
    Workout,
    recompute_strength_summary,
)
from app.repositories.plan_repo import PlanNotFoundError, PlanRepository
from app.repositories.token_repo import TokenRepository
from app.repositories.workout_repo import WorkoutNotFoundError, WorkoutRepository


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


def _make_workout(external_id: str = "w-1", type_: WorkoutType = WorkoutType.STRENGTH) -> Workout:
    return Workout(
        external_id=external_id,
        type=type_,
        start_time=datetime.now(UTC),
        duration_s=1800,
    )


def test_workout_repository_exists_and_insert(session: Session) -> None:
    repo = WorkoutRepository(session)
    assert repo.exists("w-1") is False
    repo.insert(_make_workout("w-1"))
    session.commit()
    assert repo.exists("w-1") is True


def test_workout_repository_get_raises_not_found(session: Session) -> None:
    repo = WorkoutRepository(session)
    with pytest.raises(WorkoutNotFoundError):
        repo.get(999)


def test_workout_repository_attach_strength_detail(session: Session) -> None:
    repo = WorkoutRepository(session)
    w = repo.insert(_make_workout("s-1", WorkoutType.STRENGTH))
    detail = StrengthDetail(exercise="Squat", sets=5, reps=5, weight_kg=100.0)
    recompute_strength_summary(w, detail)
    repo.attach_strength_detail(w.id, detail)  # type: ignore[arg-type]
    session.commit()

    reloaded = repo.get(w.id)  # type: ignore[arg-type]
    assert reloaded.strength_detail is not None
    assert reloaded.strength_total_volume_kg == 2500.0


def test_workout_repository_attach_cardio_detail(session: Session) -> None:
    repo = WorkoutRepository(session)
    w = repo.insert(_make_workout("c-1", WorkoutType.CARDIO))
    repo.attach_cardio_detail(
        w.id,  # type: ignore[arg-type]
        CardioDetail(avg_pace_s_per_km=300.0, splits=[{"distance_m": 1000.0, "duration_s": 300.0}]),
    )
    session.commit()
    reloaded = repo.get(w.id)  # type: ignore[arg-type]
    assert reloaded.cardio_detail is not None
    assert reloaded.cardio_detail.avg_pace_s_per_km == 300.0


def test_workout_repository_list_filters_by_type(session: Session) -> None:
    repo = WorkoutRepository(session)
    repo.insert(_make_workout("s-1", WorkoutType.STRENGTH))
    repo.insert(_make_workout("s-2", WorkoutType.STRENGTH))
    repo.insert(_make_workout("c-1", WorkoutType.CARDIO))
    session.commit()

    strengths = repo.list(workout_type=WorkoutType.STRENGTH)
    assert len(strengths) == 2
    assert all(w.type == WorkoutType.STRENGTH for w in strengths)


def test_plan_repository_create_full_hierarchy(session: Session) -> None:
    repo = PlanRepository(session)
    macro = repo.create_macrociclo(
        Macrociclo(name="Q1", start_date=date(2026, 1, 1), end_date=date(2026, 3, 31))
    )
    meso = repo.create_mesociclo(
        Mesociclo(
            macrociclo_id=macro.id,  # type: ignore[arg-type]
            name="Base",
            order_index=1,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
    )
    micro = repo.create_microciclo(
        Microciclo(
            mesociclo_id=meso.id,  # type: ignore[arg-type]
            order_index=1,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
            is_deload=False,
            base_load=100.0,
        )
    )
    sesion = repo.create_sesion(
        SesionPlanificada(
            microciclo_id=micro.id,  # type: ignore[arg-type]
            planned_type=WorkoutType.STRENGTH,
            planned_load=100.0,
        )
    )
    session.commit()

    assert sesion.microciclo is not None
    assert sesion.microciclo.mesociclo is not None
    assert sesion.microciclo.mesociclo.macrociclo.name == "Q1"


def test_plan_repository_link_sesion_to_workout(session: Session) -> None:
    plan_repo = PlanRepository(session)
    workout_repo = WorkoutRepository(session)

    macro = plan_repo.create_macrociclo(
        Macrociclo(name="Q1", start_date=date(2026, 1, 1), end_date=date(2026, 3, 31))
    )
    meso = plan_repo.create_mesociclo(
        Mesociclo(
            macrociclo_id=macro.id,  # type: ignore[arg-type]
            name="Base",
            order_index=1,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
    )
    micro = plan_repo.create_microciclo(
        Microciclo(
            mesociclo_id=meso.id,  # type: ignore[arg-type]
            order_index=1,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
        )
    )
    sesion = plan_repo.create_sesion(
        SesionPlanificada(
            microciclo_id=micro.id,  # type: ignore[arg-type]
            planned_type=WorkoutType.STRENGTH,
            planned_load=100.0,
        )
    )
    w = workout_repo.insert(_make_workout("s-1", WorkoutType.STRENGTH))
    plan_repo.link_sesion_to_workout(sesion.id, w)  # type: ignore[arg-type]
    session.commit()

    reloaded = plan_repo.get_sesion(sesion.id)  # type: ignore[arg-type]
    assert reloaded.workout_id == w.id


def test_plan_repository_link_unknown_sesion_raises(session: Session) -> None:
    plan_repo = PlanRepository(session)
    w = WorkoutRepository(session).insert(_make_workout("x"))
    with pytest.raises(PlanNotFoundError):
        plan_repo.link_sesion_to_workout(999, w)


def test_token_repository_upsert_and_get(session: Session) -> None:
    repo = TokenRepository(session)
    repo.upsert("huawei", refresh_token="rt-1", access_token="at-1")
    session.commit()

    fetched = repo.get_by_provider("huawei")
    assert fetched is not None
    assert fetched.refresh_token == "rt-1"

    repo.upsert("huawei", refresh_token="rt-2")
    session.commit()

    fetched2 = repo.get_by_provider("huawei")
    assert fetched2 is not None
    assert fetched2.refresh_token == "rt-2"


def test_token_repository_get_missing_returns_none(session: Session) -> None:
    repo = TokenRepository(session)
    assert repo.get_by_provider("nope") is None


def test_oauth_token_unique_provider(session: Session) -> None:
    """Direct insert guard test: two tokens with the same provider violate unique."""
    session.add(OAuthToken(provider="huawei", refresh_token="rt-1"))
    session.commit()
    session.add(OAuthToken(provider="huawei", refresh_token="rt-2"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
