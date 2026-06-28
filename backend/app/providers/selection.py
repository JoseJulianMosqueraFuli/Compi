"""Deterministic provider selection (Req 1.4, 11.1).

This is a pure function so it can be tested with PBT (Property 9).
"""
from enum import Enum

from app.config import Settings
from app.providers.base import WorkoutProvider
from app.providers.mock import MockProvider


class ProviderKind(str, Enum):
    """Identifier of which provider implementation is currently active."""

    MOCK = "mock"
    HUAWEI = "huawei"


def select_provider_kind(huawei_configured: bool, has_refresh_token: bool) -> ProviderKind:
    """Return the active provider kind given config and token presence.

    Rule (Req 1.4, 11.1):
      - Without Huawei credentials -> MOCK.
      - With credentials and a persisted refresh token -> HUAWEI.
      - With credentials but no token yet -> MOCK (OAuth flow not completed).
    """
    if not huawei_configured:
        return ProviderKind.MOCK
    if not has_refresh_token:
        return ProviderKind.MOCK
    return ProviderKind.HUAWEI


def build_provider(settings: Settings, has_refresh_token: bool) -> WorkoutProvider:
    """Instantiate the active provider (factory) for use by the sync service."""
    kind = select_provider_kind(settings.huawei_configured, has_refresh_token)
    if kind is ProviderKind.MOCK:
        return MockProvider()
    # Lazy import to avoid pulling httpx into mock-only environments.
    from app.providers.huawei import HuaweiProvider

    return HuaweiProvider(  # pragma: no cover - stub until task 12.2
        client_id=settings.huawei_client_id,
        client_secret=settings.huawei_client_secret,
        redirect_uri=settings.huawei_redirect_uri,
    )
