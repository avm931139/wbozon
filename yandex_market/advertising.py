from __future__ import annotations

import io
import ipaddress
import json
import time
import zipfile
from datetime import date
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import requests

from yandex_market.client import YandexMarketClient
from yandex_market.endpoints import AD_REPORT_PATHS, REPORT_INFO
from yandex_market.exceptions import YandexMarketHTTPError, YandexMarketParseError


class YandexMarketAdvertisingAPI:
    """Generate and download read-only Yandex Market marketing reports."""

    def __init__(
        self,
        client: YandexMarketClient | None = None,
        *,
        download_session: Any = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client or YandexMarketClient()
        self.download_session = download_session or requests.Session()
        self.sleeper = sleeper

    def generate(self, source: str, *, business_id: int, stat_date: date) -> str:
        try:
            path = AD_REPORT_PATHS[source]
        except KeyError as exc:
            raise ValueError(f"unknown Yandex Market advertising source: {source}") from exc
        body: dict[str, Any] = {
            "businessId": business_id,
            "dateFrom": stat_date.isoformat(),
            "dateTo": stat_date.isoformat(),
        }
        if source in {"shows_boost", "shelves"}:
            body["attributionType"] = "CLICKS"
        payload = self.client.post(
            path,
            params={"format": "JSON", "sourceType": "SELLER"},
            json_body=body,
        )
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        report_id = result.get("reportId")
        if not report_id:
            raise YandexMarketParseError("Yandex Market report response has no reportId")
        return str(report_id)

    def wait(self, report_id: str, *, attempts: int, pause_seconds: float) -> dict[str, Any]:
        if attempts < 1:
            raise ValueError("attempts must be positive")
        for attempt in range(attempts):
            payload = self.client.get(
                REPORT_INFO.format(report_id=report_id),
                params={"sourceType": "SELLER"},
            )
            result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
            status = str(result.get("status") or "")
            substatus = str(result.get("subStatus") or "")
            if substatus == "NO_DATA":
                return {"status": "NO_DATA", "rows": []}
            if status == "DONE":
                url = result.get("file")
                if not url:
                    raise YandexMarketParseError("completed Yandex Market report has no file URL")
                return {"status": "DONE", "rows": self.download_json(str(url))}
            if status == "FAILED":
                raise YandexMarketHTTPError(
                    f"Yandex Market report generation failed: {substatus or 'unknown reason'}"
                )
            if attempt < attempts - 1:
                self.sleeper(pause_seconds)
        raise YandexMarketHTTPError("Yandex Market report generation timed out")

    def download_json(self, url: str) -> list[tuple[str, list[dict[str, Any]]]]:
        current = url
        for _ in range(5):
            self._validate_download_url(current)
            response = self.download_session.get(
                current,
                headers={"Accept": "application/zip,application/octet-stream,*/*"},
                timeout=self.client.timeout,
                allow_redirects=False,
            )
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                if not location:
                    raise YandexMarketHTTPError("Yandex Market report redirect has no location")
                current = urljoin(current, location)
                continue
            if response.status_code >= 400:
                raise YandexMarketHTTPError(
                    f"Yandex Market report download returned HTTP {response.status_code}"
                )
            content = response.content
            if len(content) > 50 * 1024 * 1024:
                raise YandexMarketParseError("Yandex Market advertising report is too large")
            return self._read_json_archive(content)
        raise YandexMarketHTTPError("too many Yandex Market report redirects")

    @staticmethod
    def _validate_download_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Yandex Market report URL must use HTTPS")
        try:
            ip = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            ip = None
        if ip is not None and not ip.is_global:
            raise ValueError("Yandex Market report URL points to a private address")
        hostname = parsed.hostname.lower()
        allowed = ("yandex.ru", "yandex.net", "yandexcloud.net")
        if not any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in allowed):
            raise ValueError("Yandex Market report host is not allowed")

    @staticmethod
    def _read_json_archive(content: bytes) -> list[tuple[str, list[dict[str, Any]]]]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise YandexMarketParseError("Yandex Market report is not a ZIP archive") from exc
        result: list[tuple[str, list[dict[str, Any]]]] = []
        with archive:
            for info in archive.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".json"):
                    continue
                if info.file_size > 50 * 1024 * 1024:
                    raise YandexMarketParseError("Yandex Market report member is too large")
                try:
                    payload = json.loads(archive.read(info).decode("utf-8-sig"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise YandexMarketParseError("Yandex Market report contains invalid JSON") from exc
                rows = YandexMarketAdvertisingAPI._rows(payload)
                result.append((info.filename, rows))
        if not result:
            raise YandexMarketParseError("Yandex Market report archive has no JSON files")
        return result

    @staticmethod
    def _rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            for key in ("rows", "items", "data", "result"):
                value = payload.get(key)
                if isinstance(value, (list, dict)):
                    rows = YandexMarketAdvertisingAPI._rows(value)
                    if rows or value == []:
                        return rows
        raise YandexMarketParseError("Yandex Market report JSON has no row collection")
