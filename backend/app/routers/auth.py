"""Auth router: Huawei OAuth start and callback (Req 1.2, 1.3)."""
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.providers.huawei import HuaweiAuthError, HuaweiProvider
from app.repositories.token_repo import TokenRepository

router = APIRouter(prefix="/api/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/huawei/login")
def huawei_login() -> RedirectResponse:
    """Start the OAuth flow: redirect the user to Huawei's authorize endpoint."""
    settings = get_settings()
    if not settings.huawei_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Huawei credentials not configured",
        )
    provider = HuaweiProvider(
        client_id=settings.huawei_client_id,  # type: ignore[arg-type]
        client_secret=settings.huawei_client_secret,  # type: ignore[arg-type]
        redirect_uri=settings.huawei_redirect_uri,  # type: ignore[arg-type]
    )
    state = secrets.token_urlsafe(16)
    # NOTE: `state` should be persisted in a short-lived store tied to the
    # session cookie; the MVP keeps the provider stateless for simplicity.
    return RedirectResponse(provider.build_authorize_url(state))


@router.get("/huawei/callback")
def huawei_callback(
    code: str = Query(..., min_length=1),
    session: SessionDep = ...,  # type: ignore[assignment]
) -> dict[str, str]:
    """Trade the authorization code for tokens and persist the refresh token (Req 1.3)."""
    settings = get_settings()
    if not settings.huawei_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Huawei credentials not configured",
        )
    provider = HuaweiProvider(
        client_id=settings.huawei_client_id,  # type: ignore[arg-type]
        client_secret=settings.huawei_client_secret,  # type: ignore[arg-type]
        redirect_uri=settings.huawei_redirect_uri,  # type: ignore[arg-type]
    )
    try:
        result = provider.exchange_code(code)
    except HuaweiAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth callback failed"
        ) from exc
    if not result.success or result.refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth did not return a refresh token"
        )
    TokenRepository(session).upsert(
        provider="huawei",
        refresh_token=result.refresh_token,
        access_token=result.access_token,
        expires_at=result.expires_at,
    )
    session.commit()
    return {"status": "ok"}
