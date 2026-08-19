import logging
import time
from typing import Any

import requests
from requests import Response

from app.config import WB_API_KEY, WB_BASE_URL, WB_TIMEOUT_SECONDS
from wb.exceptions import WBAuthError, WBHTTPError, WBParseError, WBRateLimitError
from wb.sync_logging import report_exception

logger = logging.getLogger(__name__)


class WBClient:
    """Базовый клиент для WB API."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: int | None = None):
        self.api_key = api_key or WB_API_KEY
        self.base_url = (base_url or WB_BASE_URL).rstrip("/")
        self.timeout = timeout or WB_TIMEOUT_SECONDS
        self.session = requests.Session()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.api_key or "",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _raise_exchange_error(
        self,
        exc: Exception,
        *,
        method: str,
        path: str,
        attempt: int,
        status_code: int | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> None:
        try:
            raise exc
        except Exception as raised:
            report_exception(
                raised,
                phase="exchange",
                details={
                    "method": method.upper(),
                    "base_url": self.base_url,
                    "path": path,
                    "status_code": status_code,
                    "attempt": attempt,
                    "params": params,
                    "json_body": json_body,
                },
            )
            raise

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, json_body: dict[str, Any] | None = None, retries: int = 3) -> Any:
        if not self.api_key:
            self._raise_exchange_error(WBAuthError("WB API key is not configured"), method=method, path=path, attempt=0)

        url = f"{self.base_url}/{path.lstrip('/')}"
        last_error: Exception | None = None

        for attempt in range(retries):
            try:
                response = self.session.request(
                    method=method.upper(),
                    url=url,
                    headers=self._headers(),
                    params=params,
                    json=json_body,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("WB request failed: %s", exc)
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                error = WBHTTPError(f"Request failed: {exc}")
                self._raise_exchange_error(error, method=method, path=path, attempt=attempt + 1, params=params, json_body=json_body)

            if response.status_code == 401:
                self._raise_exchange_error(WBAuthError("WB API authentication failed"), method=method, path=path, attempt=attempt + 1, status_code=401, params=params, json_body=json_body)
            if response.status_code == 403:
                self._raise_exchange_error(WBAuthError("WB API access forbidden"), method=method, path=path, attempt=attempt + 1, status_code=403, params=params, json_body=json_body)
            if response.status_code == 429:
                if attempt < retries - 1:
                    logger.warning("WB rate limit hit, retrying...")
                    try:
                        retry_after = float(response.headers.get("Retry-After", "20"))
                    except (TypeError, ValueError):
                        retry_after = 20.0
                    time.sleep(max(1.0, retry_after))
                    continue
                self._raise_exchange_error(WBRateLimitError("WB API rate limit exceeded"), method=method, path=path, attempt=attempt + 1, status_code=429, params=params, json_body=json_body)
            if response.status_code >= 500:
                if attempt < retries - 1:
                    logger.warning("WB server error HTTP %s, retrying...", response.status_code)
                    time.sleep(1.5 * (attempt + 1))
                    continue
                self._raise_exchange_error(WBHTTPError(f"WB API returned HTTP {response.status_code}: {response.text}"), method=method, path=path, attempt=attempt + 1, status_code=response.status_code, params=params, json_body=json_body)
            if response.status_code >= 400:
                self._raise_exchange_error(WBHTTPError(f"WB API returned HTTP {response.status_code}: {response.text}"), method=method, path=path, attempt=attempt + 1, status_code=response.status_code, params=params, json_body=json_body)

            if response.status_code == 204 or not response.content:
                return None

            try:
                return response.json()
            except ValueError as exc:
                report_exception(exc, phase="exchange_parse", details={"method": method.upper(), "base_url": self.base_url, "path": path, "status_code": response.status_code, "attempt": attempt + 1})
                raise WBParseError("WB API returned invalid JSON") from exc

        if last_error is not None:
            raise WBHTTPError(f"WB request failed after retries: {last_error}")
        raise WBHTTPError("Unexpected WB client error")

    def get(self, path: str, *, params: dict[str, Any] | None = None, retries: int = 3) -> Any:
        return self._request("GET", path, params=params, retries=retries)

    def post(self, path: str, *, json_body: dict[str, Any] | None = None, retries: int = 3) -> Any:
        return self._request("POST", path, json_body=json_body, retries=retries)
