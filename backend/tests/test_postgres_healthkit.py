"""Exercise the two ASGI applications on a disposable, already migrated PostgreSQL instance."""
import os
from concurrent.futures import ThreadPoolExecutor
from secrets import token_urlsafe
from threading import Barrier
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
        "start": "2026-01-01T05:00:00-05:00",
        "end": "2026-01-01T05:10:00-05:00",
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
            assert workouts["latest_by_source"] == {sample["source_bundle"]: "2026-01-01T10:00:00Z"}
            timeline = desk.post("/api/healthkit/timeline", json={
                "kind": "workout", "source": sample["source_bundle"],
                "start": "2026-01-01T05:05:00-05:00", "end": "2026-01-01T05:15:00-05:00",
            })
            assert timeline.status_code == 200
            assert timeline.json() == {
                "has_more": False,
                "samples": [{
                    "sample_id": sample["sample_id"], "start": "2026-01-01T10:00:00Z",
                    "end": "2026-01-01T10:10:00Z", "value": "walk",
                }],
            }
            assert desk.get("/api/metrics/activity-totals").json()["cardio_minutes"] is None
            barrier = Barrier(2)

            def confirm():
                barrier.wait(timeout=5)
                response = desk.post(f"/api/healthkit/workouts/{sample['sample_id']}/confirm", json={})
                response.raise_for_status()
                return response.json()["workout_id"]

            with ThreadPoolExecutor(max_workers=2) as workers:
                concurrent = [workers.submit(confirm) for _ in range(2)]
                confirmed = [future.result() for future in concurrent]
            assert confirmed[0] == confirmed[1]
            source_rows = desk.get(
                "/api/healthkit/workouts", params={"source": sample["source_bundle"]}
            ).json()
            assert source_rows[0]["workout_id"] == confirmed[0]
            assert [item["id"] for item in desk.get("/api/workouts").json()] == [confirmed[0]]
            totals = desk.get("/api/metrics/activity-totals")
            assert totals.status_code == 200
            assert totals.json() == {
                "cardio_minutes": 10, "strength_kg": None, "estimated_load": None, "sessions_with_avg_hr": 0,
            }
    finally:
        get_settings.cache_clear()
