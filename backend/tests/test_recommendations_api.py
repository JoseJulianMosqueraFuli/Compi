"""API tests for availability, preferences and the recommended week (week_service end to end)."""
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.clock import get_now
from app.db import get_session
from app.routers import availability, recommendations

MONDAY = date(2026, 11, 16)
NOW = datetime(2026, 11, 16, 6, 0, tzinfo=UTC)

# Gym evenings Mon/Wed/Fri, short mornings without gym Tue/Thu, a long Saturday at the gym,
# and a Sunday walk window.
WINDOWS = [
    {"weekday": 0, "start_time": "18:00", "end_time": "19:30", "gym_access": True},
    {"weekday": 1, "start_time": "07:00", "end_time": "08:00", "gym_access": False},
    {"weekday": 2, "start_time": "18:00", "end_time": "19:30", "gym_access": True},
    {"weekday": 3, "start_time": "07:00", "end_time": "08:00", "gym_access": False},
    {"weekday": 4, "start_time": "18:00", "end_time": "19:30", "gym_access": True},
    {"weekday": 5, "start_time": "09:00", "end_time": "11:00", "gym_access": True},
    {"weekday": 6, "start_time": "10:00", "end_time": "11:00", "gym_access": False},
]


@pytest.fixture
def clock() -> dict[str, datetime]:
    return {"now": NOW}


@pytest.fixture
def client(clock: dict[str, datetime]) -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(availability.router)
    app.include_router(recommendations.router)

    def _session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_now] = lambda: clock["now"]
    with TestClient(app) as c:
        yield c


def _week(client: TestClient) -> dict:
    assert client.put("/api/availability/windows", json=WINDOWS).status_code == 200
    r = client.post("/api/recommendations/week", json={"day": MONDAY.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


def _first(week: dict, kind: str) -> dict:
    return next(s for s in week["sessions"] if s["kind"] == kind and s["day"] is not None)


def _strength_log(session: dict, done_sets: int | None = None) -> dict:
    return {
        "duration_min": 55,
        "exercises": [
            {
                "exercise_key": e["key"],
                "sets": [
                    {"reps": s["reps"], "weight_kg": s["weight_kg"] or 20}
                    for s in e["sets"][: done_sets or len(e["sets"])]
                ],
            }
            for e in session["prescription"]["exercises"]
        ],
    }


def _windows_by_day() -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for w in WINDOWS:
        out.setdefault(w["weekday"], []).append(w)
    return out


# --- availability and preferences ----------------------------------------------------


def test_week_is_404_until_generated(client: TestClient) -> None:
    assert client.get("/api/recommendations/week").status_code == 404


def test_overlapping_windows_are_rejected(client: TestClient) -> None:
    payload = [
        {"weekday": 0, "start_time": "18:00", "end_time": "19:00"},
        {"weekday": 0, "start_time": "18:30", "end_time": "20:00"},
    ]
    assert client.put("/api/availability/windows", json=payload).status_code == 400


def test_preferences_round_trip_and_validation(client: TestClient) -> None:
    assert client.get("/api/preferences").json()["strength_sessions_per_week"] == 3
    r = client.put("/api/preferences", json={"run_sessions_per_week": 1, "timezone": "America/Bogota"})
    assert r.status_code == 200 and r.json()["run_sessions_per_week"] == 1
    assert client.put("/api/preferences", json={"timezone": "Mars/Base"}).status_code == 422
    assert client.put("/api/preferences", json={"excluded_exercises": ["nope"]}).status_code == 422


def test_exercise_catalog_is_listed(client: TestClient) -> None:
    keys = {e["key"] for e in client.get("/api/exercises").json()}
    assert {"squat", "bench", "rdl"} <= keys


def test_deleting_an_unknown_exception_is_404(client: TestClient) -> None:
    assert client.delete("/api/availability/exceptions/999").status_code == 404


# --- generating the week -------------------------------------------------------------


def test_generated_week_respects_windows_and_spacing(client: TestClient) -> None:
    week = _week(client)
    assert week["week_start"] == MONDAY.isoformat()
    kinds = [s["kind"] for s in week["sessions"]]
    assert kinds.count("strength") == 3 and kinds.count("run") == 2 and kinds.count("walk") == 2
    # Seven windows, seven sessions: every one of them has a place.
    assert all(s["day"] is not None for s in week["sessions"])

    windows = _windows_by_day()
    seen: set[tuple[str, str]] = set()
    for s in (s for s in week["sessions"] if s["day"] is not None):
        day = date.fromisoformat(s["day"])
        window = next(
            w for w in windows[day.weekday()]
            if w["start_time"] <= s["start_time"][:5] < w["end_time"]
        )
        assert s["end_time"][:5] <= window["end_time"]
        if s["kind"] == "strength":
            assert window["gym_access"]
        assert (s["kind"], s["day"]) not in seen
        seen.add((s["kind"], s["day"]))

    strength_days = sorted(
        date.fromisoformat(s["day"]) for s in week["sessions"] if s["kind"] == "strength" and s["day"]
    )
    assert all((b - a).days >= 2 for a, b in zip(strength_days, strength_days[1:], strict=False))
    assert client.get("/api/recommendations/week").json()["id"] == week["id"]


def test_generating_twice_returns_the_same_week(client: TestClient) -> None:
    week = _week(client)
    again = client.post("/api/recommendations/week", json={"day": MONDAY.isoformat()}).json()
    assert again["id"] == week["id"]
    assert [s["id"] for s in again["sessions"]] == [s["id"] for s in week["sessions"]]


# --- logging, skipping, reopening ----------------------------------------------------


def test_logging_a_full_strength_session_marks_it_done(client: TestClient) -> None:
    session = _first(_week(client), "strength")
    url = f"/api/recommendations/sessions/{session['id']}/log"
    r = client.post(url, json=_strength_log(session))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done" and body["workout_id"] is not None
    assert body["comparison"]["adherence"] == 1.0
    # The recommendation itself is left as it was.
    assert body["prescription"] == session["prescription"]
    assert client.post(url, json=_strength_log(session)).status_code == 409


def test_logging_fewer_sets_is_partial(client: TestClient) -> None:
    session = _first(_week(client), "strength")
    r = client.post(
        f"/api/recommendations/sessions/{session['id']}/log", json=_strength_log(session, 1)
    )
    assert r.json()["status"] == "partial"
    assert 0 < r.json()["comparison"]["adherence"] < 1


def test_strength_log_without_exercises_is_rejected(client: TestClient) -> None:
    session = _first(_week(client), "strength")
    r = client.post(
        f"/api/recommendations/sessions/{session['id']}/log", json={"duration_min": 50}
    )
    assert r.status_code == 400


def test_logging_cardio_by_duration(client: TestClient) -> None:
    run = _first(_week(client), "run")
    target = run["prescription"]["target_minutes"]
    r = client.post(
        f"/api/recommendations/sessions/{run['id']}/log",
        json={"duration_min": target, "distance_km": 5},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"


def test_skip_and_reopen(client: TestClient) -> None:
    session = _first(_week(client), "walk")
    base = f"/api/recommendations/sessions/{session['id']}"
    assert client.post(f"{base}/reopen").status_code == 409
    r = client.post(f"{base}/skip", json={"reason": "lluvia"})
    assert r.status_code == 200 and r.json()["status"] == "skipped"
    assert client.post(f"{base}/skip", json={}).status_code == 409
    week = client.post(f"{base}/reopen").json()
    reopened = next(s for s in week["sessions"] if s["id"] == session["id"])
    assert reopened["status"] == "pending" and reopened["skip_reason"] is None


def test_unknown_session_is_404(client: TestClient) -> None:
    assert client.get("/api/recommendations/sessions/999").status_code == 404
    assert client.post("/api/recommendations/week/999/recalculate").status_code == 404


def test_regenerate_keeps_logged_sessions(client: TestClient) -> None:
    week = _week(client)
    session = _first(week, "strength")
    client.post(f"/api/recommendations/sessions/{session['id']}/log", json=_strength_log(session))
    again = client.post(
        "/api/recommendations/week", json={"day": MONDAY.isoformat(), "regenerate": True}
    ).json()
    ids = {s["id"]: s for s in again["sessions"]}
    assert session["id"] in ids and ids[session["id"]]["status"] == "done"
    assert sum(1 for s in again["sessions"] if s["kind"] == "strength") == 3


# --- recalculating when availability changes -----------------------------------------


def test_blocking_a_day_moves_its_pending_session(client: TestClient) -> None:
    week = _week(client)
    session = _first(week, "strength")
    r = client.post(
        "/api/availability/exceptions", json={"day": session["day"], "note": "viaje"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["changes"], "the recalculation reports what changed"
    after = client.get("/api/recommendations/week").json()
    moved = next(s for s in after["sessions"] if s["id"] == session["id"])
    assert moved["day"] != session["day"]

    exception_id = r.json()["exceptions"][0]["id"]
    assert client.delete(f"/api/availability/exceptions/{exception_id}").status_code == 200


def test_past_windows_are_not_used_when_recalculating(client: TestClient, clock: dict) -> None:
    week = _week(client)
    clock["now"] = NOW + timedelta(days=3)  # Thursday morning
    after = client.post(f"/api/recommendations/week/{week['id']}/recalculate").json()
    placed = [s for s in after["sessions"] if s["status"] == "pending" and s["day"] is not None]
    assert placed, "Thursday to Sunday still has windows"
    assert all(date.fromisoformat(s["day"]) >= clock["now"].date() for s in placed)
    assert any(s["day"] is None for s in after["sessions"]), "four windows cannot hold seven"


# --- evaluation ----------------------------------------------------------------------


def test_evaluation_counts_logged_sessions(client: TestClient) -> None:
    session = _first(_week(client), "strength")
    client.post(f"/api/recommendations/sessions/{session['id']}/log", json=_strength_log(session))
    r = client.get("/api/recommendations/evaluation")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sessions"]["done"] == 1
    assert body["mean_adherence"] == 1.0
    assert body["durations"] and body["durations"][0]["actual_min"] == 55


# --- linking existing workouts -------------------------------------------------------


def test_linking_an_existing_workout_is_validated(client: TestClient) -> None:
    week = _week(client)
    runs = [s for s in week["sessions"] if s["kind"] == "run"]
    strength = _first(week, "strength")
    walk = _first(week, "walk")
    logged = client.post(
        f"/api/recommendations/sessions/{runs[0]['id']}/log", json={"duration_min": 30}
    ).json()
    workout_id = logged["workout_id"]

    def link(session_id: int, wid: int) -> int:
        return client.post(
            f"/api/recommendations/sessions/{session_id}/log", json={"workout_id": wid}
        ).status_code

    assert link(runs[1]["id"], 99_999) == 404
    assert link(strength["id"], workout_id) == 400, "a cardio workout cannot log strength"
    assert link(runs[1]["id"], workout_id) == 400, "a workout counts for one session only"
    # Cardio without a workout to link needs a duration.
    assert client.post(f"/api/recommendations/sessions/{walk['id']}/log", json={}).status_code == 400


# --- sessions that do not fit, shortened and carried over ----------------------------


def test_sessions_without_a_window_say_why(client: TestClient) -> None:
    client.put(
        "/api/availability/windows",
        json=[{"weekday": 0, "start_time": "18:00", "end_time": "19:30", "gym_access": True}],
    )
    week = client.post("/api/recommendations/week", json={"day": MONDAY.isoformat()}).json()
    strength = [s for s in week["sessions"] if s["kind"] == "strength"]
    assert sum(1 for s in strength if s["day"] is not None) == 1
    for s in (s for s in week["sessions"] if s["day"] is None):
        assert s["reasons"] and s["reasons"][0].startswith("Sin ventana esta semana.")
        assert s["planned_minutes"] is None


def test_short_window_shortens_and_carries_exercises_over(client: TestClient) -> None:
    client.put(
        "/api/availability/windows",
        json=[
            {"weekday": 0, "start_time": "18:00", "end_time": "18:35", "gym_access": True},
            {"weekday": 2, "start_time": "17:00", "end_time": "19:30", "gym_access": True},
            {"weekday": 4, "start_time": "17:00", "end_time": "19:30", "gym_access": True},
        ],
    )
    client.put("/api/preferences", json={"run_sessions_per_week": 0, "walk_sessions_per_week": 0})
    week = client.post("/api/recommendations/week", json={"day": MONDAY.isoformat()}).json()
    by_day = {s["day"]: s for s in week["sessions"]}
    monday = by_day[MONDAY.isoformat()]
    assert monday["planned_minutes"] <= 35 < monday["full_minutes"]
    carried = [
        e for s in week["sessions"] for e in s["prescription"]["exercises"] if e["carried_from"]
    ]
    assert carried, "what Monday could not hold moves to a session with spare time"
    assert all(e["carried_from"].startswith(monday["title"]) for e in carried)
    for s in week["sessions"]:
        assert s["planned_minutes"] <= 150


# --- learning across weeks -----------------------------------------------------------


def test_next_week_learns_from_what_was_done(client: TestClient) -> None:
    week = _week(client)
    for s in week["sessions"]:
        url = f"/api/recommendations/sessions/{s['id']}/log"
        if s["kind"] == "strength":
            body = _strength_log(s) | {"duration_min": round(s["planned_minutes"] * 1.5)}
        else:
            body = {"duration_min": s["prescription"]["target_minutes"]}
        assert client.post(url, json=body).json()["status"] == "done"

    next_week = client.post(
        "/api/recommendations/week", json={"day": (MONDAY + timedelta(days=7)).isoformat()}
    ).json()
    assert next_week["duration_factor"] == pytest.approx(1.5, abs=0.05)
    run_before = _first(week, "run")["prescription"]["target_minutes"]
    run_after = _first(next_week, "run")["prescription"]["target_minutes"]
    assert run_after > run_before, "runs grow after a week with every run completed"
    squat = next(
        e for s in next_week["sessions"] for e in s["prescription"]["exercises"]
        if e["key"] == "squat"
    )
    assert all(st["weight_kg"] is not None for st in squat["sets"]), "history sets the weight"
