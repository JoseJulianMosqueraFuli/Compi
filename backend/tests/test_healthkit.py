"""Synthetic HealthKit batches exercise the mobile contract and transaction boundaries."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from app.db import get_session
from app.models.health import HealthObservation, HealthSyncCursor
from app.models.health_schemas import HealthBatchIn
from app.routers import healthkit
from app.services.healthkit import apply_batch

ENDPOINT = "/api/healthkit/batches"
STREAM = "8e59d937-51a1-4323-875f-45ef08bfac52"
SAMPLE = {
    "sample_id": "5a345b27-72df-4f1c-90c0-f90e19231908",
    "source_bundle": "com.example.synthetic",
    "start": "2026-01-03T12:00:00-05:00",
    "end": "2026-01-03T12:00:00-05:00",
    "value": 80,
}


def page(**changes):
    return {
        "kind": "heart_rate",
        "stream_id": STREAM,
        "sequence": 1,
        "upserts": [SAMPLE],
        "deletions": [],
        **changes,
    }


@pytest.fixture()
def engine(tmp_path):
    # Separate connections exercise real database locking for concurrent requests.
    engine = create_engine(f"sqlite:///{tmp_path / 'health.db'}")
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def client(engine):
    app = FastAPI()
    app.include_router(healthkit.router)

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        yield client


def test_ingest_replay_correct_and_delete(client, engine):
    first = page()
    assert client.post(ENDPOINT, json=first).json() == {"sequence": 1, "applied": True}
    assert client.post(ENDPOINT, json=first).json() == {"sequence": 1, "applied": False}
    corrected = page(sequence=2, upserts=[SAMPLE | {"value": 83}])
    assert client.post(ENDPOINT, json=corrected).status_code == 200
    with Session(engine) as session:
        row = session.exec(select(HealthObservation)).one()
        assert row.numeric_value == 83
        assert row.source_bundle == SAMPLE["source_bundle"]
        assert row.start.hour == 17
    deleted = page(sequence=3, upserts=[], deletions=[SAMPLE["sample_id"]])
    assert client.post(ENDPOINT, json=deleted).json()["applied"]
    assert client.post(ENDPOINT, json=first).status_code == 409
    assert not client.post(ENDPOINT, json=deleted).json()["applied"]
    with Session(engine) as session:
        assert session.exec(select(HealthObservation)).all() == []
        assert session.get(HealthSyncCursor, "heart_rate").last_sequence == 3


def test_rejects_changed_retries_skipped_pages_and_other_writers(client, engine):
    assert client.post(ENDPOINT, json=page(sequence=2)).status_code == 409
    assert client.post(ENDPOINT, json=page()).status_code == 200
    invalid = [
        page(upserts=[SAMPLE | {"value": 1}]),
        page(sequence=3),
        page(sequence=2, stream_id=str(uuid4())),
        page(kind="body_mass"),
    ]
    for batch in invalid:
        assert client.post(ENDPOINT, json=batch).status_code == 409
    with Session(engine) as session:
        assert session.exec(select(HealthObservation)).one().numeric_value == 80
        assert session.exec(select(HealthSyncCursor)).one().last_sequence == 1


@pytest.mark.parametrize(("kind", "value"), [("body_mass", 75.5), ("sleep", "deep"), ("workout", "run")])
def test_stores_type_and_duration(client, engine, kind, value):
    sample = SAMPLE | {"value": value}
    if kind == "workout":
        sample.update(end="2026-01-03T13:00:00-05:00", duration_s=3000)
    assert client.post(ENDPOINT, json=page(kind=kind, upserts=[sample])).status_code == 200
    with Session(engine) as session:
        row = session.get(HealthObservation, (kind, UUID(sample["sample_id"])))
        assert (row.numeric_value, row.category_value) == (
            value if kind == "body_mass" else None,
            value if kind != "body_mass" else None,
        )
        assert row.duration_s == sample.get("duration_s")


@pytest.mark.parametrize(
    "batch",
    [
        page(upserts=[SAMPLE, SAMPLE]),
        page(deletions=[SAMPLE["sample_id"]]),
        page(upserts=[SAMPLE | {"value": "80"}]),
        page(upserts=[SAMPLE | {"value": True}]),
        page(upserts=[SAMPLE | {"start": "2026-01-03T12:00:00"}]),
        page(upserts=[SAMPLE | {"end": "2025-01-03T12:00:00Z"}]),
        page(kind="sleep"),
        page(upserts=[SAMPLE | {"duration_s": 10}]),
        page(kind="workout", upserts=[SAMPLE | {"value": "deep"}]),
    ],
)
def test_rejects_invalid_page_before_writing(client, engine, batch):
    assert client.post(ENDPOINT, json=batch).status_code == 422
    with Session(engine) as session:
        assert session.exec(select(HealthSyncCursor)).all() == []


def test_failed_storage_rolls_back_deletions_and_checkpoint(client, engine):
    assert client.post(ENDPOINT, json=page()).status_code == 200
    batch = page(sequence=2, deletions=[SAMPLE["sample_id"]], upserts=[SAMPLE | {"sample_id": str(uuid4())}])

    def fail_insert(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.startswith("INSERT INTO health_observation"):
            raise RuntimeError("simulated write failure")

    event.listen(engine, "before_cursor_execute", fail_insert)
    try:
        with pytest.raises(RuntimeError, match="simulated write failure"):
            client.post(ENDPOINT, json=batch)
    finally:
        event.remove(engine, "before_cursor_execute", fail_insert)
    with Session(engine) as session:
        assert session.exec(select(HealthObservation)).one().sample_id == UUID(SAMPLE["sample_id"])
        assert session.get(HealthSyncCursor, "heart_rate").last_sequence == 1
    assert client.post(ENDPOINT, json=batch).json() == {"sequence": 2, "applied": True}


def test_concurrent_initial_retries_apply_once(engine):
    batch = HealthBatchIn.model_validate(page())
    barrier = Barrier(2)

    def ingest():
        with Session(engine) as session:
            barrier.wait(timeout=5)
            return apply_batch(session, batch, datetime.now(UTC))

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(ingest) for _ in range(2)]
        assert sorted(future.result() for future in futures) == [False, True]
