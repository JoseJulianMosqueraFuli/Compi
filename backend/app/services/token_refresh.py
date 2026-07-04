"""Pure helper to decide if an OAuth token should be refreshed (Req 6.4, Property 11)."""
from datetime import UTC, datetime, timedelta


def needs_refresh(
    expires_at: datetime | None,
    now: datetime,
    margin_s: int = 60,
) -> bool:
    """Return True iff the token is missing, expired, or within `margin_s` of expiry.

    The `margin_s` lets callers refresh proactively before the token actually
    expires, avoiding races with the next request.
    """
    if expires_at is None:
        return True
    aware_expires = expires_at if expires_at.tzinfo is not None else expires_at.replace(
        tzinfo=UTC
    )
    aware_now = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    return aware_expires <= aware_now + timedelta(seconds=margin_s)
