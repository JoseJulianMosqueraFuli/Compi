"""Property-based tests for dedup (Property 1) and token refresh (Property 11)."""
from datetime import UTC, datetime, timedelta

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.providers.base import (
    CardioPayload,
    ExternalWorkout,
)
from app.services.dedup import partition_new_workouts
from app.services.token_refresh import needs_refresh

# Feature: compi-training-platform, Property 1: Deduplicación por partición de external_id


@st.composite
def external_workouts_with_ids(draw: st.DrawFn) -> list[ExternalWorkout]:
    """Strategy that generates a list of ExternalWorkout with unique external_ids."""
    n = draw(st.integers(min_value=0, max_value=30))
    items: list[ExternalWorkout] = []
    for i in range(n):
        start_naive = draw(
            st.datetimes(
                min_value=datetime(2020, 1, 1),
                max_value=datetime(2030, 1, 1),
            )
        )
        items.append(
            ExternalWorkout(
                external_id=f"ext-{i}-{draw(st.integers(min_value=0, max_value=10_000))}",
                type="cardio",
                start_time=start_naive.replace(tzinfo=UTC),
                duration_s=draw(st.integers(min_value=0, max_value=7200)),
                cardio=CardioPayload(),
            )
        )
    return items


@st.composite
def ids_from(draw: st.DrawFn, workouts: list[ExternalWorkout]) -> list[str]:
    """Strategy that picks any subset of workout external_ids (with possible duplicates)."""
    pool = [w.external_id for w in workouts]
    if not pool:
        return []
    n = draw(st.integers(min_value=0, max_value=len(pool) * 2))
    chosen: list[str] = []
    for _ in range(n):
        chosen.append(draw(st.sampled_from(pool)))
    return chosen


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(fetched=external_workouts_with_ids())
def test_partition_no_existing_inserts_all(fetched: list[ExternalWorkout]) -> None:
    """No existing ids: every fetched workout is new, nothing is skipped."""
    new, skipped = partition_new_workouts([], fetched)
    assert len(new) == len(fetched)
    assert skipped == []
    assert {w.external_id for w in new} == {w.external_id for w in fetched}


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(fetched=external_workouts_with_ids())
def test_partition_all_existing_skips_all(fetched: list[ExternalWorkout]) -> None:
    """All fetched ids already present: nothing new, all skipped."""
    existing = [w.external_id for w in fetched]
    new, skipped = partition_new_workouts(existing, fetched)
    assert new == []
    assert len(skipped) == len(fetched)
    assert {w.external_id for w in skipped} == set(existing)


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    fetched=external_workouts_with_ids(),
    extras=st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=20),
)
def test_partition_is_pure_set_partition(
    fetched: list[ExternalWorkout], extras: list[str]
) -> None:
    """Property 1: result ids == union; each fetched workout appears in exactly one bucket.

    Including random extra ids in `existing` exercises the cross-product case.
    """
    existing = [w.external_id for w in fetched] + extras
    new, skipped = partition_new_workouts(existing, fetched)

    new_ids = [w.external_id for w in new]
    skipped_ids = [w.external_id for w in skipped]
    fetched_ids = [w.external_id for w in fetched]

    # Order preserved within each bucket.
    assert new_ids + skipped_ids == fetched_ids
    # No overlap between buckets.
    assert set(new_ids).isdisjoint(set(skipped_ids))
    # New bucket == fetched ids that are NOT in the existing set.
    existing_set = set(existing)
    expected_new = [eid for eid in fetched_ids if eid not in existing_set]
    assert set(new_ids) == set(expected_new)
    # Skipped bucket == fetched ids that ARE in the existing set.
    expected_skipped = [eid for eid in fetched_ids if eid in existing_set]
    assert set(skipped_ids) == set(expected_skipped)


# Feature: compi-training-platform, Property 11: Decisión de refresco de token


datetime_strategy = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 1, 1),
)
offset_strategy = st.integers(min_value=-7200, max_value=7200)
margin_strategy = st.integers(min_value=0, max_value=600)


@settings(max_examples=100)
@given(
    now_naive=datetime_strategy,
    offset_s=offset_strategy,
    margin_s=margin_strategy,
)
def test_needs_refresh_iff_expired_or_close(
    now_naive: datetime, offset_s: int, margin_s: int
) -> None:
    """Property 11: needs_refresh is true iff expires_at <= now + margin_s."""
    now = now_naive.replace(tzinfo=UTC)
    expires_at = (now + timedelta(seconds=offset_s)).replace(tzinfo=UTC)
    expected = offset_s <= margin_s
    assert needs_refresh(expires_at, now, margin_s=margin_s) is expected


@settings(max_examples=50)
@given(now_naive=datetime_strategy)
def test_needs_refresh_none_expires_immediately(now_naive: datetime) -> None:
    """No expiry recorded -> always needs refresh."""
    now = now_naive.replace(tzinfo=UTC)
    assert needs_refresh(None, now) is True


@settings(max_examples=50)
@given(now_naive=datetime_strategy)
def test_needs_refresh_naive_datetime_is_treated_as_utc(now_naive: datetime) -> None:
    """A naive expires_at is interpreted as UTC."""
    now = now_naive.replace(tzinfo=UTC)
    future = (now_naive + timedelta(seconds=3600))  # naive
    past = (now_naive - timedelta(seconds=3600))  # naive
    assert needs_refresh(future, now) is False
    assert needs_refresh(past, now) is True
