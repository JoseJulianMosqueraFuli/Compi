"""Authentication-related models: OAuthToken and UserProfile (Req 1.3, 6.4, 8.1)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

DEFAULT_HR_MAX_BPM = 190
USER_PROFILE_SINGLETON_ID = 1


def _utcnow() -> datetime:
    return datetime.now(UTC)


class OAuthToken(SQLModel, table=True):
    """Persisted OAuth refresh token for an external provider (Req 1.3, 6.4)."""

    __tablename__ = "oauth_token"

    id: int | None = Field(default=None, primary_key=True)
    provider: str = Field(unique=True, index=True, description="e.g. 'huawei'.")
    refresh_token: str
    access_token: str | None = Field(default=None)
    expires_at: datetime | None = Field(default=None)


class UserProfile(SQLModel, table=True):
    """Singleton user profile (MVP single-user, Req "Usuario unico").

    Stores the values needed to compute HR zones (Req 8.1).
    """

    __tablename__ = "user_profile"

    id: int = Field(
        default=USER_PROFILE_SINGLETON_ID,
        primary_key=True,
        description="Fixed to 1 to enforce singleton semantics.",
    )
    hr_max_bpm: int = Field(ge=100, le=250, default=DEFAULT_HR_MAX_BPM)
    hr_rest_bpm: int | None = Field(default=None, ge=30, le=120)
    updated_at: datetime = Field(default_factory=_utcnow)
