"""Property 12: unknown resource returns 404 across routers."""
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.routers import metrics, plans, workouts


@pytest.fixture
def engine_and_app():
    """Per-test fresh engine (shared connection pool) and FastAPI app."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)

    application = FastAPI()
    application.include_router(workouts.router)
    application.include_router(metrics.router)
    application.include_router(plans.router)

    def _override() -> Annotated[Session, Depends]:
        s = Session(eng)
        try:
            yield s
        finally:
            s.close()

    application.dependency_overrides[get_session] = _override
    return eng, application


@pytest.fixture
def client(engine_and_app):
    _eng, app = engine_and_app
    # No lifespan: avoid touching the background scheduler.
    with TestClient(app) as c:
        yield c


# Feature: compi-training-platform, Property 12: Recurso inexistente devuelve error


@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(workout_id=st.integers(min_value=1, max_value=100_000))
def test_unknown_workout_returns_404(engine_and_app, workout_id: int) -> None:
    """Property 12: GET /api/workouts/{id} returns 404 for any unknown id."""
    _eng, app = engine_and_app
    with TestClient(app) as c:
        response = c.get(f"/api/workouts/{workout_id}")
        assert response.status_code == 404


@settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    macrociclo_id=st.integers(min_value=1, max_value=100_000),
)
def test_unknown_macrociclo_progression_returns_404(engine_and_app, macrociclo_id: int) -> None:
    """Property 12: unknown macrociclo in progression endpoint also returns 404."""
    _eng, app = engine_and_app
    with TestClient(app) as c:
        response = c.get(f"/api/plans/{macrociclo_id}/progression")
        assert response.status_code == 404


# Smoke tests: routers metrics and plans return well-formed responses.


def test_metrics_volume_returns_total_field(client) -> None:
    r = client.get("/api/metrics/volume")
    assert r.status_code == 200
    assert "total" in r.json()


def test_metrics_load_returns_total_field(client) -> None:
    r = client.get("/api/metrics/load")
    assert r.status_code == 200
    assert "total" in r.json()


def test_create_full_plan_returns_201(client) -> None:
    macro = client.post(
        "/api/plans/macrocycles",
        json={"name": "Q1", "start_date": "2026-01-01", "end_date": "2026-03-31"},
    )
    assert macro.status_code == 201, macro.text
    macro_id = macro.json()["id"]

    meso = client.post(
        f"/api/plans/mesocycles?macrociclo_id={macro_id}",
        json={
            "name": "Base",
            "order_index": 1,
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "weekly_increment_pct": 0.05,
        },
    )
    assert meso.status_code == 201, meso.text
    meso_id = meso.json()["id"]

    micro = client.post(
        f"/api/plans/microcycles?mesociclo_id={meso_id}",
        json={
            "order_index": 1,
            "start_date": "2026-01-01",
            "end_date": "2026-01-07",
            "is_deload": False,
            "base_load": 100.0,
        },
    )
    assert micro.status_code == 201, micro.text
    micro_id = micro.json()["id"]

    sesion = client.post(
        "/api/plans/sessions",
        json={
            "microciclo_id": micro_id,
            "planned_type": "strength",
            "planned_load": 100.0,
        },
    )
    assert sesion.status_code == 201, sesion.text

    prog = client.get(f"/api/plans/{macro_id}/progression")
    assert prog.status_code == 200, prog.text
    body = prog.json()
    assert body["macrociclo_id"] == macro_id
    assert len(body["points"]) == 1
    assert body["points"][0]["target_load"] == 100.0


def test_create_mesociclo_outside_macrociclo_returns_400(client) -> None:
    macro = client.post(
        "/api/plans/macrocycles",
        json={"name": "Q1", "start_date": "2026-01-01", "end_date": "2026-03-31"},
    )
    macro_id = macro.json()["id"]
    bad = client.post(
        f"/api/plans/mesocycles?macrociclo_id={macro_id}",
        json={
            "name": "Bad",
            "order_index": 1,
            "start_date": "2025-12-01",
            "end_date": "2025-12-31",
        },
    )
    assert bad.status_code == 400
