"""Single-user path from the paired mobile receiver to desktop coverage and evaluation."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, SQLModel, create_engine

from app import mobile
from app.config import Settings
from app.db import get_session
from app.experiment import dataset_digest, track
from app.main import create_app
from app.reset_healthkit import clear_category
from app.services.duration_experiment import RecordedSession, evaluate_sessions

ENDPOINT = "/api/healthkit/batches"


@pytest.fixture
def clients(tmp_path, monkeypatch):
    token = "synthetic-pairing-key-for-local-tests"
    monkeypatch.setattr(mobile, "get_settings", lambda: Settings(healthkit_sync_token=token))
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)

    def sessions():
        with Session(engine) as session:
            yield session

    desktop = create_app()
    desktop.dependency_overrides[get_session] = sessions
    monkeypatch.setitem(mobile.app.dependency_overrides, get_session, sessions)
    phone = TestClient(
        mobile.app, base_url="https://compi.local", headers={"Authorization": f"Bearer {token}"}
    )
    # No desktop lifespan here: it starts the user's configured database.
    dashboard = TestClient(desktop, base_url="http://localhost")
    yield phone, dashboard
    dashboard.close()
    phone.close()
    engine.dispose()


def test_gateway_is_write_only_paired_and_validates_privately(clients, monkeypatch):
    phone, desktop = clients
    assert phone.get("/api/workouts").status_code == 404
    assert phone.get("/openapi.json").status_code == 404
    assert desktop.post(ENDPOINT, json={}).status_code == 404
    assert phone.post("http://compi.local" + ENDPOINT, json={}).status_code == 403
    assert phone.post(ENDPOINT, headers={"Authorization": "Bearer wrong"}, json={}).status_code == 401
    invalid = phone.post(ENDPOINT, json={"kind": "private-marker"})
    assert invalid.status_code == 422 and "private-marker" not in invalid.text
    monkeypatch.setattr(mobile, "get_settings", lambda: Settings(healthkit_sync_token=""))
    assert phone.post(ENDPOINT, json={}).status_code == 503


def test_import_replay_and_delete_update_dashboard_and_experiment(clients):
    phone, desktop = clients
    start = datetime(2026, 1, 1, tzinfo=UTC)
    source = "com.example.synthetic"
    samples = []
    for index, minutes in enumerate((20, 30, 40, 60)):
        day = start + timedelta(days=index)
        samples.append(
            dict(
                sample_id=str(uuid4()),
                source_bundle=source,
                start=day.isoformat(),
                end=(day + timedelta(minutes=minutes)).isoformat(),
                value="walk",
                duration_s=600,
            )
        )
    page = dict(stream_id=str(uuid4()), kind="workout", sequence=1, upserts=samples, deletions=[])
    assert phone.post(ENDPOINT, json=page).json()["applied"]
    assert not phone.post(ENDPOINT, json=page).json()["applied"]
    rows = desktop.get("/api/healthkit/coverage").json()
    workouts = next(row for row in rows if row["kind"] == "workout")
    assert workouts["samples"] == 4 and workouts["sources"] == [source] and workouts["last_batch"]
    assert all(row["last_batch"] is None for row in rows if row["kind"] != "workout")

    def evaluate():
        return desktop.post("/api/healthkit/duration-evaluation", json={"source": source}).json()

    result = evaluate()
    assert result["evaluated_sessions"] == 1
    assert result["by_activity"] == {"mae_minutes": 30, "underestimated": 1}
    assert result["baseline"] == result["by_activity"]
    page.update(sequence=2, deletions=[samples[-1]["sample_id"]], upserts=[])
    assert phone.post(ENDPOINT, json=page).status_code == 200
    assert evaluate()["baseline"] is None
    assert desktop.get("/ready").status_code == 200


def test_readiness_reports_database_outage():
    class Unavailable:
        def execute(self, statement):
            raise OperationalError("private statement", {}, Exception())

    desktop = create_app()
    desktop.dependency_overrides[get_session] = Unavailable
    response = TestClient(desktop, base_url="http://localhost").get("/ready")
    assert response.status_code == 503 and response.json() == {"status": "unavailable"}


def test_evaluation_uses_only_completed_sessions_and_matching_activity():
    day = datetime(2026, 1, 1, tzinfo=UTC)

    def record(offset, minutes, kind):
        start = day + timedelta(days=offset)
        return RecordedSession(start, start + timedelta(minutes=minutes), kind)

    records = [record(d, 15, "walk") for d in range(3)] + [record(d, 60, "run") for d in range(3, 6)]
    records.extend([record(6, 3000, "walk"), record(7, 16, "walk")])
    scores = evaluate_sessions(list(reversed(records)))
    assert scores.evaluated_sessions == 2
    assert scores.by_activity.mae_minutes == (2985 + 1) / 2
    assert scores.baseline.mae_minutes != scores.by_activity.mae_minutes


def test_tracking_only_sends_parameters_and_aggregate_scores():
    payloads = []

    def receive(request):
        payloads.append(json.loads(request.content))
        if request.url.path.endswith("/create"):
            return httpx.Response(200, json={"run": {"info": {"run_id": "test-run"}}})
        return httpx.Response(200, json={})

    records = [RecordedSession(datetime(2025, 2, 1, tzinfo=UTC), datetime(2025, 2, 1, 1, tzinfo=UTC), "run")]
    with httpx.Client(base_url="http://localhost/", transport=httpx.MockTransport(receive)) as client:
        run_id = track(client, "0", evaluate_sessions(records), dataset_digest(records), True)
    assert run_id == "test-run" and payloads[-1]["status"] == "FINISHED"
    assert "2025-02" not in json.dumps(payloads)
    assert {m["key"] for m in payloads[1]["metrics"]} == {"observed_sessions", "evaluated_sessions"}


def test_retiring_one_stream_preserves_the_other_categories(clients):
    phone, desktop = clients
    for kind, value in (("heart_rate", 58), ("body_mass", 70)):
        sample = dict(
            sample_id=str(uuid4()),
            source_bundle="com.example.test",
            value=value,
            start="2026-01-01T01:00:00Z",
            end="2026-01-01T01:00:00Z",
        )
        request = dict(kind=kind, stream_id=str(uuid4()), sequence=1, upserts=[sample], deletions=[])
        assert phone.post(ENDPOINT, json=request).status_code == 200
    sessions = desktop.app.dependency_overrides[get_session]()
    session = next(sessions)
    try:
        clear_category(session, "heart_rate")
    finally:
        sessions.close()
    rows = {row["kind"]: row for row in desktop.get("/api/healthkit/coverage").json()}
    assert rows["heart_rate"]["last_batch"] is None and rows["heart_rate"]["samples"] == 0
    assert rows["body_mass"]["last_batch"] and rows["body_mass"]["samples"] == 1


def test_timeline_uses_measurement_times_half_open_days_and_one_source(clients):
    phone, desktop = clients
    origin = "com.example.watch"
    source_day = "2026-01-03"

    def sample(hour, value, source=origin, end=None):
        start = f"{source_day}T{hour}:00:00-05:00"
        return dict(sample_id=str(uuid4()), source_bundle=source, start=start, end=end or start, value=value)

    points = [sample("08", 65), sample("14", 74), sample("12", 90, "com.example.other")]
    for kind, rows in (
        ("heart_rate", points),
        ("sleep", [sample("23", "deep", end="2026-01-04T02:00:00-05:00")]),
    ):
        body = dict(kind=kind, stream_id=str(uuid4()), sequence=1, upserts=rows, deletions=[])
        assert phone.post(ENDPOINT, json=body).status_code == 200
    query = dict(
        kind="heart_rate", source=origin, start="2026-01-03T08:00:00-05:00", end="2026-01-03T14:00:00-05:00"
    )
    data = desktop.post("/api/healthkit/timeline", json=query).json()
    assert [r["value"] for r in data["samples"]] == [65] and not data["has_more"]
    query.update(kind="sleep", start="2026-01-04T00:00:00-05:00", end="2026-01-05T00:00:00-05:00")
    sleep = desktop.post("/api/healthkit/timeline", json=query).json()["samples"]
    assert [r["value"] for r in sleep] == ["deep"]
    assert sleep[0]["start"] == "2026-01-04T04:00:00Z"
    assert sleep[0]["end"] == "2026-01-04T07:00:00Z"
    assert phone.post("/api/healthkit/timeline", json=query).status_code == 404


def test_empty_dashboard_keeps_unmeasured_totals_unknown(clients):
    _, desktop = clients
    assert desktop.get("/api/metrics/activity-totals").json() == {
        "strength_kg": None,
        "cardio_minutes": None,
        "estimated_load": None,
        "sessions_with_avg_hr": 0,
    }
