"""Exercise the two ASGI applications on a disposable, already migrated PostgreSQL instance."""
import os
from secrets import token_urlsafe
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import mobile
from app.config import get_settings
from app.db import engine
from app.main import create_app


@pytest.mark.skipif(os.getenv("COMPI_TEST_POSTGRES") != "1", reason="requires the disposable CI database")
def test_postgres_healthkit_ingestion_and_coverage(monkeypatch):
    assert engine.dialect.name == "postgresql" and engine.url.database == "compi_ci"
    token = token_urlsafe(32)
    monkeypatch.setenv("HEALTHKIT_SYNC_TOKEN", token)
    get_settings.cache_clear()
    sample = {
        "sample_id": str(uuid4()),
        "source_bundle": "org.example.compi-ci",
        "start": "2026-01-01T10:00:00Z",
        "end": "2026-01-01T10:10:00Z",
        "value": "walk",
    }
    page = {"stream_id": str(uuid4()), "kind": "workout", "sequence": 1, "upserts": [sample], "deletions": []}
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with (
            TestClient(mobile.app, base_url="https://compi.test") as phone,
            TestClient(create_app(), base_url="http://localhost") as desk,
        ):
            assert phone.post("/api/healthkit/batches", json=page, headers=headers).json() == {
                "sequence": 1, "applied": True,
            }
            assert phone.post("/api/healthkit/batches", json=page, headers=headers).json()["applied"] is False
            overview = desk.get("/api/healthkit/coverage")
            assert overview.status_code == 200
            workouts = next(row for row in overview.json() if row["kind"] == "workout")
            assert workouts["samples"] == 1 and workouts["sources"] == [sample["source_bundle"]]
            assert workouts["last_batch"]
    finally:
        get_settings.cache_clear()
