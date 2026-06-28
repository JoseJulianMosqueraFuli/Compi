"""Property-based tests for provider abstraction (Property 9 and 10)."""
from datetime import UTC, datetime

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.config import Settings
from app.providers.mock import MockProvider
from app.providers.selection import ProviderKind, select_provider_kind


# Feature: compi-training-platform, Property 10: Datos del MockProvider bien formados
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    since_naive=st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 1, 1),
    ),
    count=st.integers(min_value=1, max_value=20),
)
def test_mock_provider_returns_well_formed_workouts(since_naive: datetime, count: int) -> None:
    """Property 10: every fetched workout has non-empty external_id, valid type,
    non-negative duration, and the right payload variant for its type.
    """
    since = since_naive.replace(tzinfo=UTC)
    provider = MockProvider(count=count)
    workouts = provider.fetch_workouts(since)

    assert len(workouts) == count
    for w in workouts:
        assert w.external_id, "external_id must be non-empty"
        assert w.type in {"cardio", "strength"}
        assert w.duration_s >= 0
        if w.type == "cardio":
            assert w.cardio is not None
            assert w.strength_summary is None
        else:
            assert w.strength_summary is not None
            assert w.cardio is None
            assert w.strength_summary.total_volume_kg >= 0
            assert w.strength_summary.total_sets >= 0
            assert w.strength_summary.exercises_count >= 0


# Feature: compi-training-platform, Property 10: external_ids are deterministic
@settings(max_examples=50)
@given(count=st.integers(min_value=1, max_value=10))
def test_mock_provider_external_ids_are_deterministic(count: int) -> None:
    """Same call twice yields the same external_ids (Req 6.2 reproducibility)."""
    since = datetime(2026, 1, 1, tzinfo=UTC)
    p = MockProvider(count=count)
    a = [w.external_id for w in p.fetch_workouts(since)]
    b = [w.external_id for w in p.fetch_workouts(since)]
    assert a == b
    assert len(set(a)) == count, "external_ids must be unique within a batch"


# Feature: compi-training-platform, Property 9: Selección de proveedor según configuración
@settings(max_examples=100)
@given(
    huawei_configured=st.booleans(),
    has_refresh_token=st.booleans(),
)
def test_select_provider_kind_deterministic(
    huawei_configured: bool, has_refresh_token: bool
) -> None:
    """Property 9: the rule is deterministic and matches the design."""
    kind = select_provider_kind(huawei_configured, has_refresh_token)

    if not huawei_configured or not has_refresh_token:
        assert kind is ProviderKind.MOCK
    else:
        assert kind is ProviderKind.HUAWEI


# Feature: compi-training-platform, Property 9: select_provider_kind agrees with Settings
@settings(max_examples=50)
@given(
    huawei_client_id=st.one_of(st.none(), st.text(min_size=1, max_size=10)),
    huawei_client_secret=st.one_of(st.none(), st.text(min_size=1, max_size=10)),
    huawei_redirect_uri=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
    has_token=st.booleans(),
)
def test_select_provider_kind_matches_settings(
    huawei_client_id: str | None,
    huawei_client_secret: str | None,
    huawei_redirect_uri: str | None,
    has_token: bool,
) -> None:
    """When wired to Settings, the rule uses the real `huawei_configured` flag."""
    s = Settings(
        huawei_client_id=huawei_client_id,
        huawei_client_secret=huawei_client_secret,
        huawei_redirect_uri=huawei_redirect_uri,
    )
    kind = select_provider_kind(s.huawei_configured, has_token)

    if not s.huawei_configured or not has_token:
        assert kind is ProviderKind.MOCK
    else:
        assert kind is ProviderKind.HUAWEI
