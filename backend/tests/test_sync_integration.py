"""Integration test for SyncService using the MockProvider (Req 5.4, 6.1, 6.2, 6.3)."""
from datetime import UTC, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.workout import Workout
from app.providers.mock import MockProvider
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
