from __future__ import annotations

from datetime import date
from typing import Any

from app.config import WB_DOCUMENTS_BASE_URL
from wb.base import WBAPIBase
from wb.client import WBClient
from wb.endpoints import WBDocumentsEndpoints
from wb.exceptions import WBParseError


class DocumentsAPI(WBAPIBase):
    """Read-only access to seller accounting documents."""

    def __init__(self, client: WBClient | None = None):
        super().__init__(client or WBClient(base_url=WB_DOCUMENTS_BASE_URL))

    def categories(self, locale: str = "ru") -> list[dict[str, Any]]:
        self._validate_locale(locale)
        payload = self.client.get(WBDocumentsEndpoints.CATEGORIES, params={"locale": locale}, retries=8)
        data = self._response_data(payload, "document categories")
        rows = data.get("categories")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise WBParseError("WB document categories response has invalid categories")
        return rows

    def list(
        self,
        begin_time: date | None = None,
        end_time: date | None = None,
        *,
        locale: str = "ru",
        sort: str | None = None,
        order: str | None = None,
        category: str | None = None,
        service_name: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self._validate_locale(locale)
        if (begin_time is None) != (end_time is None):
            raise ValueError("begin_time and end_time must be specified together")
        if begin_time and end_time and begin_time > end_time:
            raise ValueError("begin_time must not be after end_time")
        if (sort is None) != (order is None):
            raise ValueError("sort and order must be specified together")
        if sort not in (None, "date", "category"):
            raise ValueError("sort must be 'date' or 'category'")
        if order not in (None, "asc", "desc"):
            raise ValueError("order must be 'asc' or 'desc'")
        if sort == "category" and locale != "ru":
            raise ValueError("category sorting is available only for locale='ru'")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")

        params: dict[str, Any] = {"locale": locale, "limit": limit}
        if begin_time:
            params.update(beginTime=begin_time.isoformat(), endTime=end_time.isoformat())
        if sort:
            params.update(sort=sort, order=order)
        if category:
            params["category"] = category
        if service_name:
            params["serviceName"] = service_name

        result: list[dict[str, Any]] = []
        offset = 0
        page_signatures: set[tuple[str, ...]] = set()
        while True:
            payload = self.client.get(
                WBDocumentsEndpoints.LIST,
                params={**params, "offset": offset},
                retries=8,
            )
            data = self._response_data(payload, "documents list")
            page = data.get("documents")
            if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
                raise WBParseError("WB documents list response has invalid documents")
            if len(page) > limit:
                raise WBParseError("WB documents list returned more rows than requested")
            signature = tuple(str(row.get("serviceName") or "") for row in page)
            if page and signature in page_signatures:
                raise WBParseError("WB documents pagination repeated the same page")
            page_signatures.add(signature)
            result.extend(page)
            if len(page) < limit:
                return result
            offset += len(page)

    def download(self, service_name: str, extension: str) -> dict[str, Any]:
        service_name, extension = self._validate_document_ref(service_name, extension)
        payload = self.client.get(
            WBDocumentsEndpoints.DOWNLOAD,
            params={"serviceName": service_name, "extension": extension},
            retries=8,
        )
        return self._download_data(payload, "document")

    def download_all(self, documents: list[dict[str, str]]) -> dict[str, Any]:
        if not 1 <= len(documents) <= 50:
            raise ValueError("documents must contain between 1 and 50 items")
        normalized: list[dict[str, str]] = []
        for item in documents:
            if not isinstance(item, dict):
                raise ValueError("each document reference must be an object")
            service_name, extension = self._validate_document_ref(
                item.get("serviceName", ""),
                item.get("extension", ""),
            )
            normalized.append({"serviceName": service_name, "extension": extension})
        payload = self.client.post(
            WBDocumentsEndpoints.DOWNLOAD_ALL,
            json_body={"params": normalized},
            retries=8,
        )
        return self._download_data(payload, "documents archive")

    @staticmethod
    def _validate_locale(locale: str) -> None:
        if locale not in {"ru", "en", "zh"}:
            raise ValueError("locale must be 'ru', 'en' or 'zh'")

    @staticmethod
    def _validate_document_ref(service_name: str, extension: str) -> tuple[str, str]:
        if not isinstance(service_name, str) or not isinstance(extension, str):
            raise ValueError("service_name and extension must be strings")
        normalized_name = service_name.strip()
        normalized_extension = extension.strip().lstrip(".").lower()
        if not normalized_name or not normalized_extension:
            raise ValueError("service_name and extension are required")
        if len(normalized_name) > 255 or any(ord(char) < 32 for char in normalized_name):
            raise ValueError("service_name is invalid")
        if (
            len(normalized_extension) > 30
            or not normalized_extension.isascii()
            or not normalized_extension.replace("_", "").isalnum()
        ):
            raise ValueError("extension is invalid")
        return normalized_name, normalized_extension

    @staticmethod
    def _response_data(payload: Any, name: str) -> dict[str, Any]:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise WBParseError(f"WB {name} response does not contain a data object")
        return payload["data"]

    @classmethod
    def _download_data(cls, payload: Any, name: str) -> dict[str, Any]:
        data = cls._response_data(payload, name)
        if not all(isinstance(data.get(key), str) and data[key] for key in ("fileName", "extension", "document")):
            raise WBParseError(f"WB {name} response has incomplete file data")
        return data
