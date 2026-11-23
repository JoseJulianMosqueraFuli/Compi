"""Imported workouts become manual records only after a user confirms a match."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from app.db import get_session
from app.models.health_schemas import HealthBatchIn
from app.models.workout import ExerciseSet, Workout, WorkoutExercise
from app.routers.health_workouts import router
from app.services.healthkit import apply_batch

BASE = "/api/healthkit/workouts"
SOURCE = "com.test.watch"
SECOND_SOURCE = "com.test.phone"


def sample(activity="strength", source=SOURCE, **changes):
    return {
        "sample_id": str(uuid4()), "source_bundle": source, "start": "2026-01-01T08:00:00-05:00",
        "end": "2026-01-01T08:30:00-05:00", "value": activity, "duration_s": 1500, **changes,
    }


@pytest.fixture
def history(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'confirm.db'}")
    SQLModel.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(router)

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    stream_id = str(uuid4())

    def ingest(sequence, upserts=(), deletions=()):
        batch = HealthBatchIn(
            kind="workout", stream_id=stream_id, sequence=sequence, upserts=upserts, deletions=deletions,
        )
        with Session(engine) as session:
            apply_batch(session, batch, datetime.now(UTC))

    with TestClient(app) as client:
        yield client, ingest, engine
    engine.dispose()


def test_reconcile_two_sources_and_preserve_manual_sets(history):
    client, ingest, engine = history
    watch = sample()
    phone = sample(source=SECOND_SOURCE)
    ingest(1, [watch, phone])
    with Session(engine) as session:
        original = Workout(
            external_id="manual-id", type="strength", subtype="strength", duration_s=1900,
            start_time=datetime(2026, 1, 1, 13, 5, tzinfo=UTC), notes="synthetic notes",
        )
        exercise = WorkoutExercise(order_index=1, name="Press")
        exercise.sets = [ExerciseSet(order_index=1, reps=5, weight_kg=10)]
        original.exercises = [exercise]
        session.add(original)
        session.commit()
        target = original.id
    for origin in (watch, phone):
        url = f"{BASE}/{origin['sample_id']}/confirm"
        assert client.post(url, json={"workout_id": target}).json() == {"workout_id": target}
        assert client.post(url, json={}).json() == {"workout_id": target}
        assert client.post(url, json={"workout_id": target + 1}).status_code == 409
    listed = client.get(BASE, params={"source": SOURCE, "limit": 1}).json()
    assert len(listed) == 1
    assert listed[0]["sample_id"] == watch["sample_id"] and listed[0]["workout_id"] == target
    with Session(engine) as session:
        actual = session.exec(select(Workout)).one()
        assert actual.notes == "synthetic notes" and actual.duration_s == 1900
        assert actual.exercises[0].sets[0].reps == 5


def test_confirmed_snapshot_survives_source_correction_and_deletion(history):
    client, ingest, engine = history
    run = sample("run")
    ingest(1, [run])
    url = f"{BASE}/{run['sample_id']}/confirm"
    assert client.get(BASE, params={"source": SOURCE}).json()[0]["workout_id"] is None
    target = client.post(url, json={}).json()["workout_id"]
    corrected = run | {"end": "2026-01-01T09:00:00-05:00", "value": "walk"}
    ingest(2, [corrected])
    listed = client.get(BASE, params={"source": SOURCE}).json()[0]
    assert listed["activity"] == "walk" and listed["workout_id"] == target
    ingest(3, deletions=[run["sample_id"]])
    assert client.get(BASE, params={"source": SOURCE}).json() == []
    assert client.post(url, json={}).json() == {"workout_id": target}
    ingest(4, [corrected])
    assert client.post(url, json={}).json() == {"workout_id": target}
    with Session(engine) as session:
        actual = session.exec(select(Workout)).one()
        assert actual.type == "cardio" and actual.subtype == "run"
        assert actual.duration_s == 1800 and actual.start_time.hour == 13


def test_rejects_unknown_or_incompatible_workouts(history):
    client, ingest, engine = history
    run, walk, lifting, other = (sample(activity) for activity in ("run", "walk", "strength", "other"))
    ingest(1, [run, walk, lifting, other])
    assert client.get(BASE, params={"source": SOURCE, "limit": 0}).status_code == 422
    assert client.post(f"{BASE}/{uuid4()}/confirm", json={}).status_code == 404
    assert client.post(f"{BASE}/{other['sample_id']}/confirm", json={}).status_code == 422
    run_url = f"{BASE}/{run['sample_id']}/confirm"
    assert client.post(run_url, json={"workout_id": 999}).status_code == 404
    target = client.post(run_url, json={}).json()["workout_id"]
    for incompatible in (walk, lifting):
        response = client.post(f"{BASE}/{incompatible['sample_id']}/confirm", json={"workout_id": target})
        assert response.status_code == 409
    with Session(engine) as session:
        assert len(session.exec(select(Workout)).all()) == 1


def test_simultaneous_confirmations_create_one_snapshot(history):
    client, ingest, engine = history
    workout = sample()
    ingest(1, [workout])
    barrier = Barrier(2)

    def confirm():
        barrier.wait(timeout=5)
        response = client.post(f"{BASE}/{workout['sample_id']}/confirm", json={})
        assert response.status_code == 200
        return response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [pool.submit(confirm) for _ in range(2)]
        assert requests[0].result() == requests[1].result()
    with Session(engine) as session:
        assert len(session.exec(select(Workout)).all()) == 1
