from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests

from app.config import (
    YANDEX_MARKET_API_KEY,
    YANDEX_MARKET_BASE_URL,
    YANDEX_MARKET_TIMEOUT_SECONDS,
)
from yandex_market.exceptions import (
    YandexMarketAuthError,
    YandexMarketHTTPError,
    YandexMarketParseError,
    YandexMarketRateLimitError,
)


logger = logging.getLogger(__name__)


class YandexMarketClient:
    """HTTP client for the Yandex Market Partner API using an API-Key token."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
        session: Any = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key or YANDEX_MARKET_API_KEY
        self.base_url = (base_url or YANDEX_MARKET_BASE_URL).rstrip("/")
        self.timeout = timeout or YANDEX_MARKET_TIMEOUT_SECONDS
        self.session = session or requests.Session()
        self.sleeper = sleeper

    def _headers(self) -> dict[str, str]:
        return {
            "Api-Key": self.api_key or "",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Connection": "close",
        }

    def post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        return self._request(
            "post",
            path,
            params=params,
            json_body=json_body,
            retries=retries,
        )

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        return self._request("get", path, params=params, retries=retries)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise YandexMarketAuthError("YANDEX_MARKET_API_KEY must be configured")
        if retries < 1:
            raise ValueError("retries must be positive")

        url = f"{self.base_url}/{path.lstrip('/')}"
        for attempt in range(retries):
            try:
                request = getattr(self.session, method)
                kwargs: dict[str, Any] = {
                    "headers": self._headers(),
                    "params": params,
                    "timeout": self.timeout,
                }
                if method != "get":
                    kwargs["json"] = json_body or {}
                response = request(
                    url,
                    **kwargs,
                )
            except requests.RequestException as exc:
                if attempt < retries - 1:
                    self.sleeper(1.5 * (attempt + 1))
                    continue
                raise YandexMarketHTTPError(f"Yandex Market request failed: {exc}") from None

            if response.status_code in {401, 403}:
                raise YandexMarketAuthError(
                    f"Yandex Market API authentication failed: HTTP {response.status_code}"
                )
            if response.status_code in {420, 429}:
                if attempt < retries - 1:
                    logger.warning("Yandex Market rate limit hit, retrying")
                    self.sleeper(self._retry_delay(response, attempt))
                    continue
                raise YandexMarketRateLimitError("Yandex Market API rate limit exceeded")
            if response.status_code >= 500 and attempt < retries - 1:
                self.sleeper(1.5 * (attempt + 1))
                continue
            if response.status_code >= 400:
                raise YandexMarketHTTPError(
                    f"Yandex Market API returned HTTP {response.status_code}: {response.text}"
                )
            try:
                payload = response.json()
            except ValueError:
                raise YandexMarketParseError("Yandex Market API returned invalid JSON") from None
            if not isinstance(payload, dict):
                raise YandexMarketParseError("Yandex Market API response is not an object")
            if payload.get("status") not in {None, "OK"}:
                raise YandexMarketHTTPError(
                    f"Yandex Market API rejected request: {self._error_summary(payload)}"
                )
            return payload
        raise YandexMarketHTTPError("Yandex Market request failed after retries")

    @staticmethod
    def _retry_delay(response: Any, attempt: int) -> float:
        value = response.headers.get("Retry-After") if hasattr(response, "headers") else None
        try:
            return max(float(value), 0.0) if value is not None else float(2**attempt)
        except (TypeError, ValueError):
            return float(2**attempt)

    @staticmethod
    def _error_summary(payload: dict[str, Any]) -> str:
        errors = payload.get("errors")
        if not isinstance(errors, list):
            return "unknown error"
        parts = []
        for item in errors[:5]:
            if isinstance(item, dict):
                parts.append(f"{item.get('code', 'ERROR')}: {item.get('message', 'unknown error')}")
        return "; ".join(parts) or "unknown error"
