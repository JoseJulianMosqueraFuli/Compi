"""Auth router: Huawei OAuth start and callback (Req 1.2, 1.3)."""
import secrets
from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.providers.huawei import HuaweiAuthError, HuaweiProvider
from app.repositories.token_repo import TokenRepository

router = APIRouter(prefix="/api/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_session)]
STATE_COOKIE = "compi_huawei_state"
CALLBACK_PATH = "/api/auth/huawei/callback"


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
    state = secrets.token_urlsafe(32)
    with closing(provider):
        response = RedirectResponse(provider.build_authorize_url(state))
    response.set_cookie(
        STATE_COOKIE, state, max_age=600, path=CALLBACK_PATH, httponly=True,
        secure=settings.huawei_redirect_uri.startswith("https://"), samesite="lax",
    )
    return response


@router.get("/huawei/callback")
def huawei_callback(
    request: Request,
    response: Response,
    code: str = Query(..., min_length=1),
    state: str = Query(default="", max_length=128),
    session: SessionDep = ...,  # type: ignore[assignment]
) -> dict[str, str]:
    """Trade the authorization code for tokens and persist the refresh token (Req 1.3)."""
    settings = get_settings()
    if not settings.huawei_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Huawei credentials not configured",
        )
    expected = request.cookies.get(STATE_COOKIE, "")
    if not expected or not secrets.compare_digest(expected.encode(), state.encode()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")
    provider = HuaweiProvider(
        client_id=settings.huawei_client_id,  # type: ignore[arg-type]
        client_secret=settings.huawei_client_secret,  # type: ignore[arg-type]
        redirect_uri=settings.huawei_redirect_uri,  # type: ignore[arg-type]
    )
    try:
        with closing(provider):
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
    response.delete_cookie(STATE_COOKIE, path=CALLBACK_PATH)
    return {"status": "ok"}
