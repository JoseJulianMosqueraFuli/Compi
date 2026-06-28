"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend settings sourced from environment variables (Requirement 1.1, 2.3)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://compi:compi@localhost:5432/compi",
        description="SQLAlchemy/SQLModel connection string for PostgreSQL.",
    )

    huawei_client_id: str | None = Field(
        default=None,
        description="Huawei Health Kit OAuth client id. Absent -> MockProvider (Req 1.4).",
    )
    huawei_client_secret: str | None = Field(default=None)
    huawei_redirect_uri: str | None = Field(default=None)

    sync_interval_minutes: int = Field(
        default=60,
        ge=1,
        description="Background sync job interval in minutes (Req 6.1).",
    )

    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="Origins allowed by CORS middleware.",
    )

    @property
    def huawei_configured(self) -> bool:
        """True iff all Huawei credentials are present (Req 1.4)."""
        return bool(
            self.huawei_client_id
            and self.huawei_client_secret
            and self.huawei_redirect_uri
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor."""
    return Settings()
