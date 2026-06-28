"""Data-access layer for persisted OAuth tokens (Req 1.3, 6.4)."""
from datetime import datetime

from sqlmodel import Session, select

from app.models.auth import OAuthToken


class TokenRepository:
    """Repository for OAuthToken rows. Provider is unique (Req 1.3)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        provider: str,
        refresh_token: str,
        access_token: str | None = None,
        expires_at: datetime | None = None,
    ) -> OAuthToken:
        """Insert or update the token for a given provider (Req 1.3, 6.4)."""
        existing = self.get_by_provider(provider)
        if existing is None:
            token = OAuthToken(
                provider=provider,
                refresh_token=refresh_token,
                access_token=access_token,
                expires_at=expires_at,
            )
            self._session.add(token)
        else:
            existing.refresh_token = refresh_token
            existing.access_token = access_token
            existing.expires_at = expires_at
            token = existing
        self._session.flush()
        return token

    def get_by_provider(self, provider: str) -> OAuthToken | None:
        stmt = select(OAuthToken).where(OAuthToken.provider == provider)
        return self._session.exec(stmt).first()

    def delete(self, provider: str) -> None:
        token = self.get_by_provider(provider)
        if token is not None:
            self._session.delete(token)
            self._session.flush()
