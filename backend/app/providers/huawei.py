"""HuaweiProvider: real WorkoutProvider implementation against Huawei Health Kit (Req 5.3, 6.4)."""
import logging
from datetime import UTC, datetime

import httpx

from app.models.domain import WorkoutType
from app.providers.base import (
    AuthResult,
    CardioPayload,
    ExternalWorkout,
    StrengthSummaryPayload,
    WorkoutProvider,
)

logger = logging.getLogger(__name__)

DEFAULT_HUAWEI_AUTH_URL = "https://oauth-login.cloud.huawei.com/oauth2/v3/authorize"
DEFAULT_HUAWEI_TOKEN_URL = "https://oauth-login.cloud.huawei.com/oauth2/v3/token"
DEFAULT_HUAWEI_API_BASE = "https://health-api.cloud.huawei.com"


class HuaweiAuthError(RuntimeError):
    """Raised when the OAuth flow fails (Req 1.3 - 400 callback)."""


class HuaweiProvider(WorkoutProvider):
    """WorkoutProvider that talks to Huawei Health Kit via OAuth (Req 5.3)."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        auth_url: str = DEFAULT_HUAWEI_AUTH_URL,
        token_url: str = DEFAULT_HUAWEI_TOKEN_URL,
        api_base: str = DEFAULT_HUAWEI_API_BASE,
        http_client: httpx.Client | None = None,
        clock=None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._auth_url = auth_url
        self._token_url = token_url
        self._api_base = api_base
        self._http = http_client or httpx.Client(timeout=15.0)
        self._owns_http = http_client is None
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: datetime | None = None
        self._clock = clock or (lambda: datetime.now(UTC))

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def build_authorize_url(self, state: str) -> str:
        """Compose the URL the user must visit to start the OAuth flow (Req 1.2)."""
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": "https://www.huawei.com/healthkit/step.read",
            "state": state,
        }
        return f"{self._auth_url}?{httpx.QueryParams(params)}"

    def exchange_code(self, code: str) -> AuthResult:
        """Trade the authorization code for tokens (Req 1.2)."""
        try:
            response = self._http.post(
                self._token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "code": code,
                    "redirect_uri": self._redirect_uri,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HuaweiAuthError(f"token exchange failed: {exc}") from exc
        return self._store(response.json())

    def authenticate(self) -> AuthResult:
        """Force a fresh token using the stored refresh_token (Req 6.4)."""
        if self._refresh_token is None:
            return AuthResult(success=False)
        try:
            response = self._http.post(
                self._token_url,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._refresh_token,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HuaweiAuthError(f"refresh failed: {exc}") from exc
        return self._store(response.json())

    def _store(self, payload: dict) -> AuthResult:
        self._access_token = payload.get("access_token")
        self._refresh_token = payload.get("refresh_token") or self._refresh_token
        expires_in = payload.get("expires_in")
        if expires_in is not None:
            self._expires_at = self._clock().fromtimestamp(
                self._clock().timestamp() + int(expires_in)
            )
        return AuthResult(
            success=True,
            access_token=self._access_token,
            refresh_token=self._refresh_token,
            expires_at=self._expires_at,
        )

    def is_authenticated(self) -> bool:
        return self._access_token is not None

    def fetch_workouts(self, since: datetime) -> list[ExternalWorkout]:
        """GET /v1/workouts with since, mapping the response to ExternalWorkout (Req 6.1, 6.2)."""
        if not self.is_authenticated():
            raise HuaweiAuthError("not authenticated")
        url = f"{self._api_base}/v1/workouts"
        try:
            response = self._http.get(
                url,
                params={"startTime": int(since.timestamp() * 1000)},
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("huawei fetch_workouts failed: %s", exc)
            return []
        return [self._map_workout(item) for item in response.json().get("workouts", [])]

    def _map_workout(self, item: dict) -> ExternalWorkout:
        """Map a Huawei workout dict to ExternalWorkout (Req 5.3, 6.2)."""
        wtype = WorkoutType.STRENGTH if item.get("type") == "strength" else WorkoutType.CARDIO
        ext = ExternalWorkout(
            external_id=str(item["id"]),
            type=wtype,
            start_time=datetime.fromtimestamp(item["startTime"] / 1000, tz=UTC),
            duration_s=int(item.get("duration", 0)),
            avg_hr=item.get("avgHr"),
            max_hr=item.get("maxHr"),
            calories=item.get("calories"),
        )
        if wtype == WorkoutType.CARDIO:
            ext = ext.model_copy(
                update={
                    "cardio": CardioPayload(
                        gps_polyline=item.get("polyline"),
                        avg_pace_s_per_km=item.get("avgPace"),
                        splits=item.get("splits", []),
                    )
                }
            )
        else:
            ext = ext.model_copy(
                update={
                    "strength_summary": StrengthSummaryPayload(
                        total_volume_kg=float(item.get("totalVolume", 0.0)),
                        total_sets=int(item.get("totalSets", 0)),
                        exercises_count=int(item.get("exercises", 0)),
                    )
                }
            )
        return ext
