"""SQLModel engine and session management."""
from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    echo=False,
    pool_pre_ping=True,
)


def init_db() -> None:
    """Create all tables. Used by Alembic-equivalent bootstrap; production uses migrations."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a transactional session."""
    with Session(engine) as session:
        yield session
