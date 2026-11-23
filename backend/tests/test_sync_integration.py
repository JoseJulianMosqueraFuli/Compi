"""Integration test for SyncService using the MockProvider (Req 5.4, 6.1, 6.2, 6.3)."""
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.workout import Workout
from app.providers.huawei import HuaweiFetchError, HuaweiProvider
from app.providers.mock import MockProvider
from app.repositories.token_repo import TokenRepository
from app.services.sync_service import SyncService


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


def test_sync_inserts_all_new_workouts(session: Session) -> None:
    """First sync with MockProvider inserts every fetched workout (Req 5.4, 6.3)."""
    provider = MockProvider(count=4)
    service = SyncService(provider=provider, session=session)

    inserted, skipped = service.run_once()

    assert inserted == 4
    assert skipped == 0
    rows = session.exec(select(Workout)).all()
    assert len(rows) == 4


def test_sync_second_run_is_idempotent(session: Session) -> None:
    """A second run with the same provider inserts 0 (all duplicates, Req 6.2)."""
    provider = MockProvider(count=4)
    SyncService(provider=provider, session=session).run_once()

    inserted2, skipped2 = SyncService(
        provider=provider, session=session, last_sync=datetime.now(UTC)
    ).run_once()

    assert inserted2 == 0
    assert skipped2 == 4
    rows = session.exec(select(Workout)).all()
    assert len(rows) == 4  # still 4, not 8


def test_sync_persists_cardio_and_strength(session: Session) -> None:
    """Both workout types end up persisted with the right `type` (Req 3.1)."""
    provider = MockProvider(count=6)
    SyncService(provider=provider, session=session).run_once()

    rows = session.exec(select(Workout)).all()
    types = {w.type.value for w in rows}
    assert types == {"cardio", "strength"}
    assert rows[0].cardio_detail.avg_pace_s_per_km == 300.0


def test_sync_uses_deterministic_external_ids(session: Session) -> None:
    """External ids are stable across runs (Property 10 + dedup reproducibility)."""
    p1 = MockProvider(count=3)
    p2 = MockProvider(count=3)
    SyncService(provider=p1, session=session).run_once()
    ids_first = {w.external_id for w in session.exec(select(Workout)).all()}

    with Session(session.get_bind()) as fresh:
        SyncService(provider=p2, session=fresh).run_once()
        ids_second = {w.external_id for w in fresh.exec(select(Workout)).all()}

    assert ids_first == ids_second


def test_duplicate_in_batch_and_old_id_outside_listing(session, monkeypatch) -> None:
    from sqlalchemy import insert

    now = datetime.now(UTC)
    provider = MockProvider(count=2)
    old, new = provider.fetch_workouts(now)
    session.execute(insert(Workout), [
        {"external_id": old.external_id, "type": old.type, "duration_s": 1, "start_time": now},
        *[
            {"external_id": f"seed-{n}", "type": old.type, "duration_s": 1,
             "start_time": now + timedelta(seconds=1)}
            for n in range(10_000)
        ],
    ])
    session.commit()
    monkeypatch.setattr(provider, "fetch_workouts", lambda since: [old, new, new])
    assert SyncService(provider, session).run_once() == (1, 2)


def test_failed_second_insert_rolls_back_whole_batch(session, monkeypatch) -> None:
    from app.repositories.workout_repo import WorkoutRepository

    original_insert = WorkoutRepository.insert

    def fail_at_strength(repo, workout):
        if workout.type == "strength":
            raise ValueError("interrupted")
        return original_insert(repo, workout)

    monkeypatch.setattr(WorkoutRepository, "insert", fail_at_strength)
    with pytest.raises(ValueError, match="interrupted"):
        SyncService(MockProvider(count=2), session).run_once()
    assert session.exec(select(Workout)).all() == []


def test_rotated_token_survives_fetch_failure_and_next_run_uses_it(session) -> None:
    now = datetime.now(UTC)
    repo = TokenRepository(session)
    repo.upsert("huawei", "old-refresh", "old-access", now - timedelta(hours=1))
    session.commit()

    def refresh_then_fail(request):
        if request.method == "POST":
            assert b"refresh_token=old-refresh" in request.content
            return httpx.Response(200, json={
                "access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600,
            })
        return httpx.Response(503, json={"error": "private upstream data"})

    def fetch_with_persisted_token(request):
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer new-access"
        return httpx.Response(200, json={"workouts": []})

    with httpx.Client(transport=httpx.MockTransport(refresh_then_fail)) as client:
        provider = HuaweiProvider("id", "secret", "redirect", http_client=client)
        with pytest.raises(HuaweiFetchError, match="503") as error:
            SyncService(provider, session, now=now).run_once()
        assert "private upstream data" not in str(error.value)
    assert repo.get_by_provider("huawei").refresh_token == "new-refresh"
    with httpx.Client(transport=httpx.MockTransport(fetch_with_persisted_token)) as client:
        provider = HuaweiProvider("id", "secret", "redirect", http_client=client)
        assert SyncService(provider, session, now=now).run_once() == (0, 0)


def test_scheduler_signals_failure_without_private_exception_text(engine, monkeypatch, caplog) -> None:
    from app.services import sync_service

    def fail_before_sync(session):
        raise ValueError("private user payload")

    monkeypatch.setattr(sync_service, "engine", engine)
    monkeypatch.setattr(sync_service, "build_sync_service", fail_before_sync)
    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError, match="legacy sync failed") as failure:
        sync_service._scheduled_job()
    assert failure.value.__suppress_context__
    assert "sync_failed" in caplog.text
    assert "private user payload" not in caplog.text
