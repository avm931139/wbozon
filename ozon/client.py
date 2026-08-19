from __future__ import annotations

import logging
import time
from typing import Any

import requests

from app.config import OZON_API_KEY, OZON_BASE_URL, OZON_CLIENT_ID, OZON_TIMEOUT_SECONDS
from ozon.exceptions import OzonAuthError, OzonHTTPError, OzonParseError, OzonRateLimitError

logger = logging.getLogger(__name__)


class OzonClient:
    """HTTP client for Ozon Seller API using Client-Id and Api-Key headers."""

    def __init__(
        self,
        client_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
        session: Any = None,
    ) -> None:
        self.client_id = client_id or OZON_CLIENT_ID
        self.api_key = api_key or OZON_API_KEY
        self.base_url = (base_url or OZON_BASE_URL).rstrip("/")
        self.timeout = timeout or OZON_TIMEOUT_SECONDS
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        return {
            "Client-Id": self.client_id or "",
            "Api-Key": self.api_key or "",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def post(self, path: str, *, json_body: dict[str, Any] | None = None, retries: int = 3) -> Any:
        if not self.client_id or not self.api_key:
            raise OzonAuthError("OZON_CLIENT_ID and OZON_API_KEY must be configured")
        url = f"{self.base_url}/{path.lstrip('/')}"
        for attempt in range(retries):
            try:
                response = self.session.post(
                    url,
                    headers=self._headers(),
                    json=json_body or {},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise OzonHTTPError(f"Ozon request failed: {exc}") from exc

            if response.status_code in {401, 403}:
                raise OzonAuthError(f"Ozon API authentication failed: HTTP {response.status_code}")
            if response.status_code == 429:
                if attempt < retries - 1:
                    logger.warning("Ozon rate limit hit, retrying")
                    time.sleep(2**attempt)
                    continue
                raise OzonRateLimitError("Ozon API rate limit exceeded")
            if response.status_code >= 500 and attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            if response.status_code >= 400:
                raise OzonHTTPError(f"Ozon API returned HTTP {response.status_code}: {response.text}")
            if response.status_code == 204 or not response.content:
                return None
            try:
                return response.json()
            except ValueError as exc:
                raise OzonParseError("Ozon API returned invalid JSON") from exc
        raise OzonHTTPError("Ozon request failed after retries")
