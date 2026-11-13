"""Clock dependency, so tests can pin the current time."""
from datetime import UTC, datetime


def get_now() -> datetime:
    """Current instant, timezone-aware in UTC."""
    return datetime.now(UTC)
