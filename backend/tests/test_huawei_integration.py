"""Integration tests for Huawei OAuth flow and HuaweiProvider (Req 1.2, 5.3, 6.4)."""
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings
from app.db import get_session
from app.models.auth import OAuthToken
from app.providers.huawei import HuaweiAuthError, HuaweiProvider
from app.providers.selection import build_provider
from app.routers import auth as auth_router


class _FakeTransport(httpx.BaseTransport):
    """In-memory httpx transport for testing the OAuth flow (Req 1.2)."""

    def __init__(self) -> None:
        self.token_payload: dict[str, Any] = {
            "access_token": "at-1",
            "refresh_token": "rt-1",
            "expires_in": 3600,
        }
        self.code: str | None = "auth-code-1"
        self.token_calls: int = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "token" in str(request.url):
            self.token_calls += 1
            return httpx.Response(200, json=self.token_payload)
        return httpx.Response(404, json={"error": "not found"})


@pytest.fixture
def huawei_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HUAWEI_CLIENT_ID", "test-client")
    monkeypatch.setenv("HUAWEI_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("HUAWEI_REDIRECT_URI", "https://app.test/callback")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_build_provider_returns_huawei_when_configured(huawei_env) -> None:
    """build_provider returns a real HuaweiProvider once env and token are present."""
    settings = get_settings()
    provider = build_provider(settings, has_refresh_token=True)
    assert isinstance(provider, HuaweiProvider)
    provider.close()


def test_build_provider_returns_mock_when_unconfigured(monkeypatch) -> None:
    """Without Huawei env vars, build_provider returns the MockProvider (Req 1.4)."""
    from app.providers.mock import MockProvider

    monkeypatch.delenv("HUAWEI_CLIENT_ID", raising=False)
    monkeypatch.delenv("HUAWEI_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("HUAWEI_REDIRECT_URI", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    provider = build_provider(settings, has_refresh_token=True)
    assert isinstance(provider, MockProvider)
    get_settings.cache_clear()


def test_huawei_provider_exchange_code_stores_tokens(huawei_env) -> None:
    """exchange_code should call the token endpoint and populate credentials (Req 1.2, 1.3)."""
    fake = _FakeTransport()
    client = httpx.Client(transport=fake)
    provider = HuaweiProvider(
        client_id="test-client",
        client_secret="test-secret",
        redirect_uri="https://app.test/callback",
        http_client=client,
    )
    result = provider.exchange_code("auth-code-1")
    assert result.success is True
    assert provider.is_authenticated() is True
    assert fake.token_calls == 1
    provider.close()


def test_huawei_provider_authenticate_uses_refresh(huawei_env) -> None:
    """authenticate() must use the stored refresh_token to get a new access token (Req 6.4)."""
    fake = _FakeTransport()
    fake.token_payload = {
        "access_token": "at-2",
        "refresh_token": "rt-2",
        "expires_in": 7200,
    }
    client = httpx.Client(transport=fake)
    provider = HuaweiProvider(
        client_id="test-client",
        client_secret="test-secret",
        redirect_uri="https://app.test/callback",
        http_client=client,
    )
    provider.exchange_code("auth-code-1")  # get initial tokens
    fake.token_payload = {
        "access_token": "at-3",
        "refresh_token": "rt-3",
        "expires_in": 7200,
    }
    result = provider.authenticate()
    assert result.success is True
    assert result.access_token == "at-3"
    assert fake.token_calls == 2
    provider.close()


def test_huawei_provider_authenticate_without_refresh_returns_failure(huawei_env) -> None:
    """Without a stored refresh token, authenticate() reports failure (Req 6.4)."""
    client = httpx.Client(transport=_FakeTransport())
    provider = HuaweiProvider(
        client_id="test-client",
        client_secret="test-secret",
        redirect_uri="https://app.test/callback",
        http_client=client,
    )
    result = provider.authenticate()
    assert result.success is False
    provider.close()


def test_huawei_provider_exchange_code_raises_on_http_error(huawei_env) -> None:
    """An HTTP error during exchange must raise HuaweiAuthError (Design - Error Handling)."""
    class _BadTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

    client = httpx.Client(transport=_BadTransport())
    provider = HuaweiProvider(
        client_id="test-client",
        client_secret="test-secret",
        redirect_uri="https://app.test/callback",
        http_client=client,
    )
    with pytest.raises(HuaweiAuthError):
        provider.exchange_code("auth-code-1")
    provider.close()


def test_huawei_provider_fetch_workouts_maps_response(huawei_env) -> None:
    """fetch_workouts must parse a Huawei response and yield ExternalWorkout (Req 5.3)."""

    class _WorkoutsTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.token_calls = 0

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            if request.method == "POST" and "token" in str(request.url):
                self.token_calls += 1
                return httpx.Response(
                    200,
                    json={
                        "access_token": "at-x",
                        "refresh_token": "rt-x",
                        "expires_in": 3600,
                    },
                )
            return httpx.Response(
                200,
                json={
                    "workouts": [
                        {
                            "id": "ext-cardio-1",
                            "type": "cardio",
                            "startTime": 1_700_000_000_000,
                            "duration": 3600,
                            "avgHr": 150,
                            "maxHr": 175,
                            "calories": 450.0,
                            "polyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@",
                            "avgPace": 300.0,
                            "splits": [{"distance_m": 1000, "duration_s": 300}],
                        },
                        {
                            "id": "ext-strength-1",
                            "type": "strength",
                            "startTime": 1_700_086_400_000,
                            "duration": 1800,
                            "avgHr": 120,
                            "maxHr": 160,
                            "calories": 250.0,
                            "totalVolume": 2500.0,
                            "totalSets": 5,
                            "exercises": 3,
                        },
                    ]
                },
            )

    transport = _WorkoutsTransport()
    client = httpx.Client(transport=transport)
    provider = HuaweiProvider(
        client_id="test-client",
        client_secret="test-secret",
        redirect_uri="https://app.test/callback",
        http_client=client,
    )
    provider.exchange_code("auth-code-1")
    workouts = provider.fetch_workouts(datetime(2026, 1, 1, tzinfo=UTC))
    assert len(workouts) == 2
    cardio, strength = workouts
    assert cardio.type.value == "cardio"
    assert cardio.cardio is not None
    assert cardio.strength_summary is None
    assert strength.type.value == "strength"
    assert strength.strength_summary is not None
    assert strength.cardio is None
    provider.close()


def test_huawei_provider_fetch_workouts_requires_auth(huawei_env) -> None:
    """fetch_workouts without an access token raises HuaweiAuthError."""
    client = httpx.Client(transport=_FakeTransport())
    provider = HuaweiProvider(
        client_id="test-client",
        client_secret="test-secret",
        redirect_uri="https://app.test/callback",
        http_client=client,
    )
    with pytest.raises(HuaweiAuthError):
        provider.fetch_workouts(datetime(2026, 1, 1, tzinfo=UTC))
    provider.close()


def test_huawei_provider_authorize_url_contains_params(huawei_env) -> None:
    """The authorize URL must include the OAuth params (Req 1.2)."""
    provider = HuaweiProvider(
        client_id="test-client",
        client_secret="test-secret",
        redirect_uri="https://app.test/callback",
        http_client=httpx.Client(transport=_FakeTransport()),
    )
    url = provider.build_authorize_url("state-1")
    assert "client_id=test-client" in url
    assert "redirect_uri=https%3A%2F%2Fapp.test%2Fcallback" in url
    assert "state=state-1" in url
    assert "response_type=code" in url
    provider.close()


# ---- Auth router tests ----


@pytest.fixture
def auth_engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def auth_app(auth_engine, huawei_env):
    app = FastAPI()
    app.include_router(auth_router.router)

    def _override() -> Annotated[Session, Depends]:
        s = Session(auth_engine)
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    return app


def test_auth_callback_persists_refresh_token(auth_app, auth_engine) -> None:
    """POST-style callback via TestClient persists the refresh token (Req 1.3)."""
    fake = _FakeTransport()
    app_with_transport = FastAPI()
    app_with_transport.include_router(auth_router.router)

    def _override() -> Annotated[Session, Depends]:
        s = Session(auth_engine)
        try:
            yield s
        finally:
            s.close()

    app_with_transport.dependency_overrides[get_session] = _override
    # Patch the provider's httpx client by monkeypatching the module-level call.
    from app.routers import auth as auth_module

    real_init = HuaweiProvider.__init__

    def _patched_init(self, *args, **kwargs):  # noqa: ANN001
        kwargs["http_client"] = httpx.Client(transport=fake)
        real_init(self, *args, **kwargs)

    auth_module.HuaweiProvider.__init__ = _patched_init  # type: ignore[assignment]
    try:
        with TestClient(app_with_transport) as c:
            response = c.get("/api/auth/huawei/callback?code=auth-code-1")
            assert response.status_code == 200, response.text
    finally:
        auth_module.HuaweiProvider.__init__ = real_init  # type: ignore[assignment]

    with Session(auth_engine) as s:
        token = s.exec(  # noqa: PD009
            __import__("sqlmodel").select(OAuthToken).where(OAuthToken.provider == "huawei")
        ).first()
        assert token is not None
        assert token.refresh_token == "rt-1"
        assert token.access_token == "at-1"


def test_auth_callback_without_credentials_returns_400(auth_app) -> None:
    """Without Huawei env vars, the callback should refuse with 400 (Design - Error Handling)."""
    # Drop the env vars for this test.
    import os

    for key in ("HUAWEI_CLIENT_ID", "HUAWEI_CLIENT_SECRET", "HUAWEI_REDIRECT_URI"):
        os.environ.pop(key, None)
    get_settings.cache_clear()
    try:
        with TestClient(auth_app) as c:
            r = c.get("/api/auth/huawei/callback?code=anything")
            assert r.status_code == 400
    finally:
        get_settings.cache_clear()


def test_auth_login_redirects_when_configured(auth_app) -> None:
    """/api/auth/huawei/login must return a 307/302 to the Huawei authorize URL."""
    import os

    os.environ["HUAWEI_CLIENT_ID"] = "test-client"
    os.environ["HUAWEI_CLIENT_SECRET"] = "test-secret"
    os.environ["HUAWEI_REDIRECT_URI"] = "https://app.test/callback"
    get_settings.cache_clear()
    try:
        with TestClient(auth_app, follow_redirects=False) as c:
            r = c.get("/api/auth/huawei/login")
            assert r.status_code in (302, 307)
            assert "oauth-login.cloud.huawei.com" in r.headers["location"]
    finally:
        get_settings.cache_clear()
