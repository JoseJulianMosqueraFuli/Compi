"""Selection for the optional legacy workout pull job."""
from enum import Enum

from app.config import Settings
from app.providers.base import WorkoutProvider
from app.providers.mock import MockProvider


class ProviderKind(str, Enum):
    """Identifier of which provider implementation is currently active."""

    MOCK = "mock"
    HUAWEI = "huawei"


class ProviderUnavailableError(RuntimeError):
    """The selected source cannot run with the current configuration."""


def select_provider_kind(mode: str, huawei_configured: bool, has_refresh_token: bool) -> ProviderKind:
    if mode == "demo":
        return ProviderKind.MOCK
    if mode != "huawei":
        raise ProviderUnavailableError("Legacy sync is disabled")
    if not huawei_configured or not has_refresh_token:
        raise ProviderUnavailableError("Huawei sync requires configuration and authorization")
    return ProviderKind.HUAWEI


def build_provider(settings: Settings, has_refresh_token: bool) -> WorkoutProvider:
    """Instantiate the active provider (factory) for use by the sync service."""
    kind = select_provider_kind(settings.legacy_sync_mode, settings.huawei_configured, has_refresh_token)
    if kind is ProviderKind.MOCK:
        return MockProvider()
    # Lazy import to avoid pulling httpx into mock-only environments.
    from app.providers.huawei import HuaweiProvider

    return HuaweiProvider(
        client_id=settings.huawei_client_id,
        client_secret=settings.huawei_client_secret,
        redirect_uri=settings.huawei_redirect_uri,
    )
