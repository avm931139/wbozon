from __future__ import annotations

import time
from typing import Any

import requests

from app.config import OZON_PERFORMANCE_BASE_URL, OZON_PERFORMANCE_CLIENT_ID, OZON_PERFORMANCE_CLIENT_SECRET, OZON_TIMEOUT_SECONDS
from ozon.exceptions import OzonAuthError, OzonHTTPError, OzonParseError, OzonRateLimitError


class OzonPerformanceClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
        session: Any = None,
    ) -> None:
        self.base_url = (base_url or OZON_PERFORMANCE_BASE_URL).rstrip("/")
        self.client_id = client_id or OZON_PERFORMANCE_CLIENT_ID
        self.client_secret = client_secret or OZON_PERFORMANCE_CLIENT_SECRET
        self.timeout = timeout or OZON_TIMEOUT_SECONDS
        self.session = session or requests.Session()
        self.token: str | None = None

    def authenticate(self) -> None:
        if not self.client_id or not self.client_secret:
            raise OzonAuthError("Ozon Performance API credentials are not configured")
        try:
            response = self.session.post(
                self.base_url + "/api/client/token",
                json={"client_id": self.client_id, "client_secret": self.client_secret, "grant_type": "client_credentials"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise OzonHTTPError(f"Performance authentication request failed: {exc}") from exc
        if response.status_code >= 400:
            raise OzonAuthError(f"Performance authentication failed: HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise OzonParseError("Performance API returned invalid authentication JSON") from exc
        self.token = payload.get("access_token") if isinstance(payload, dict) else None
        if not self.token:
            raise OzonAuthError("Performance API did not return an access token")

    def request(self, method: str, path: str, *, json_body: dict[str, Any] | None = None, params: dict[str, Any] | None = None, retries: int = 4) -> Any:
        if retries < 1:
            raise ValueError("retries must be positive")
        if not self.token:
            self.authenticate()
        for attempt in range(retries):
            try:
                response = self.session.request(method, self.base_url + path, headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"}, json=json_body, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise OzonHTTPError(f"Performance API request failed: {exc}") from exc
            if response.status_code == 401 and attempt == 0:
                self.authenticate(); continue
            if response.status_code == 429 and attempt < retries - 1:
                try:
                    retry_after = max(2, int(response.headers.get("Retry-After", "2")))
                except (TypeError, ValueError):
                    retry_after = 2
                time.sleep(retry_after); continue
            if response.status_code == 429:
                raise OzonRateLimitError("Performance API rate limit exceeded")
            if response.status_code >= 500 and attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1)); continue
            if response.status_code >= 400:
                raise OzonHTTPError(f"Performance API returned HTTP {response.status_code}: {response.text}")
            if not response.content:
                return None
            try:
                return response.json()
            except ValueError as exc:
                raise OzonParseError("Performance API returned invalid JSON") from exc
        raise OzonHTTPError("Performance API request failed after retries")
