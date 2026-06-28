"""Smoke tests for the SQLModel entities and the strength summary helper."""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import (
    DEFAULT_HR_MAX_BPM,
    USER_PROFILE_SINGLETON_ID,
    CardioDetail,
    Macrociclo,
    Mesociclo,
    Microciclo,
    OAuthToken,
    SesionPlanificada,
    StrengthDetail,
    UserProfile,
    Workout,
    WorkoutType,
    recompute_strength_summary,
)


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(eng)
    return eng


def test_models_importable() -> None:
    """All model classes are exposed and the WorkoutType enum is correct."""
    assert WorkoutType.CARDIO.value == "cardio"
    assert WorkoutType.STRENGTH.value == "strength"
    assert DEFAULT_HR_MAX_BPM == 190
    assert USER_PROFILE_SINGLETON_ID == 1


def test_user_profile_singleton_id_is_fixed(engine) -> None:
    with Session(engine) as s:
        s.add(UserProfile())
        s.commit()
        again = s.get(UserProfile, 1)
        assert again is not None
        assert again.hr_max_bpm == DEFAULT_HR_MAX_BPM


def test_workout_recompute_strength_summary() -> None:
    w = Workout(
        external_id="x1",
        type=WorkoutType.STRENGTH,
        start_time=datetime.now(UTC),
        duration_s=1800,
    )
    d = StrengthDetail(exercise="Squat", sets=5, reps=5, weight_kg=100.0)
    recompute_strength_summary(w, d)
    assert w.strength_total_sets == 5
    assert w.strength_total_volume_kg == 2500.0
    assert w.strength_exercises_count == 1


def test_recompute_strength_summary_rejects_cardio() -> None:
    w = Workout(
        external_id="x2",
        type=WorkoutType.CARDIO,
        start_time=datetime.now(UTC),
        duration_s=1800,
    )
    d = StrengthDetail(exercise="X", sets=1, reps=1, weight_kg=1.0)
    with pytest.raises(ValueError):
        recompute_strength_summary(w, d)


def test_periodization_hierarchy(engine) -> None:
    with Session(engine) as s:
        macro = Macrociclo(name="Q1", start_date=date(2026, 1, 1), end_date=date(2026, 3, 31))
        s.add(macro)
        s.flush()
        meso = Mesociclo(
            macrociclo_id=macro.id,
            name="Base",
            order_index=1,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            weekly_increment_pct=5.0,
        )
        s.add(meso)
        s.flush()
        micro = Microciclo(
            mesociclo_id=meso.id,
            order_index=1,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
            is_deload=False,
            base_load=100.0,
        )
        s.add(micro)
        s.flush()
        sesion = SesionPlanificada(
            microciclo_id=micro.id,
            planned_type=WorkoutType.STRENGTH,
            planned_load=100.0,
        )
        s.add(sesion)
        s.commit()

        loaded = s.exec(select(Macrociclo)).one()
        assert loaded.mesociclos[0].microciclos[0].sesiones_planificadas[0].planned_load == 100.0


def test_oauth_token_unique_provider(engine) -> None:
    with Session(engine) as s:
        s.add(OAuthToken(provider="huawei", refresh_token="rt-1"))
        s.commit()
        s.add(OAuthToken(provider="huawei", refresh_token="rt-2"))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()


def test_cardio_detail_one_per_workout(engine) -> None:
    with Session(engine) as s:
        w = Workout(
            external_id="c1",
            type=WorkoutType.CARDIO,
            start_time=datetime.now(UTC),
            duration_s=3600,
        )
        s.add(w)
        s.flush()
        s.add(CardioDetail(workout_id=w.id, avg_pace_s_per_km=300.0))
        s.commit()
        s.add(CardioDetail(workout_id=w.id))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
