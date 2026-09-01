from __future__ import annotations

import hashlib
import io
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import requests

from app.config import (
    OZON_ACCOUNTING_MAX_FILE_BYTES,
    OZON_ACCOUNTING_STORAGE_DIR,
    OZON_REPORT_ALLOWED_HOST_SUFFIXES,
    OZON_TIMEOUT_SECONDS,
)


_UNSAFE = re.compile(r"[^\w.() -]+", re.UNICODE)
_FILENAME = re.compile(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", re.IGNORECASE)
_EXTENSION = re.compile(r"^[a-z0-9]{1,30}$")


@dataclass(frozen=True)
class DownloadedReport:
    content: bytes
    file_name: str
    content_type: str | None
    source_url: str


@dataclass(frozen=True)
class StoredOzonReport:
    relative_path: str
    file_name: str
    extension: str
    content_type: str | None
    size: int
    sha256: str


class OzonReportDownloader:
    """Download a signed report URL without forwarding Seller API credentials."""

    def __init__(
        self,
        *,
        allowed_host_suffixes: tuple[str, ...] = OZON_REPORT_ALLOWED_HOST_SUFFIXES,
        timeout: int = OZON_TIMEOUT_SECONDS,
        session: Any = None,
    ) -> None:
        if not allowed_host_suffixes:
            raise ValueError("allowed_host_suffixes must not be empty")
        self.allowed_host_suffixes = tuple(value.lower().lstrip(".") for value in allowed_host_suffixes)
        self.timeout = timeout
        self.session = session or requests.Session()

    def download(self, url: str) -> DownloadedReport:
        current_url = url
        response = None
        for _ in range(6):
            self._validate_url(current_url)
            response = self.session.get(
                current_url,
                headers={"Accept": "application/octet-stream,*/*"},
                timeout=self.timeout,
                allow_redirects=False,
            )
            if response.status_code not in {301, 302, 303, 307, 308}:
                break
            location = response.headers.get("Location")
            if not location:
                raise ValueError("Ozon report redirect does not contain Location")
            current_url = urljoin(current_url, location)
        else:
            raise ValueError("Ozon report URL has too many redirects")
        if response is None:
            raise RuntimeError("Ozon report download did not start")
        response.raise_for_status()
        self._validate_url(str(response.url))
        disposition = response.headers.get("Content-Disposition", "")
        match = _FILENAME.search(disposition)
        file_name = unquote(match.group(1).strip()) if match else Path(urlparse(str(response.url)).path).name
        return DownloadedReport(
            content=bytes(response.content),
            file_name=file_name or "report.xlsx",
            content_type=response.headers.get("Content-Type"),
            source_url=str(response.url),
        )

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host or parsed.username or parsed.password:
            raise ValueError("Ozon report URL must be an HTTPS URL without credentials")
        if not any(host == suffix or host.endswith(f".{suffix}") for suffix in self.allowed_host_suffixes):
            raise ValueError(f"Ozon report URL host is not allowed: {host}")


class OzonAccountingStorage:
    def __init__(
        self,
        root: str | Path = OZON_ACCOUNTING_STORAGE_DIR,
        *,
        max_file_bytes: int = OZON_ACCOUNTING_MAX_FILE_BYTES,
    ) -> None:
        if max_file_bytes < 1:
            raise ValueError("max_file_bytes must be positive")
        self.root = Path(root).expanduser().resolve()
        self.max_file_bytes = max_file_bytes

    def save(self, report_type: str, code: str, downloaded: DownloadedReport) -> StoredOzonReport:
        content = downloaded.content
        if not content:
            raise ValueError("Ozon report file is empty")
        if len(content) > self.max_file_bytes:
            raise ValueError(
                f"Ozon report exceeds the configured limit of {self.max_file_bytes} bytes"
            )
        safe_type = self._safe_part(report_type, "report")
        safe_code = self._safe_part(code, "unknown")
        supplied = downloaded.file_name.replace("\\", "/").rsplit("/", 1)[-1]
        stem = self._safe_part(Path(supplied).stem, safe_code)
        extension = Path(supplied).suffix.lower().lstrip(".")
        if not _EXTENSION.fullmatch(extension):
            extension = self._detect_extension(content)
        self._validate_content(extension, content)
        file_name = f"{stem}.{extension}"

        directory = self.root / safe_type / safe_code
        directory.mkdir(parents=True, exist_ok=True)
        target = (directory / file_name).resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError("Ozon report path escapes storage directory")
        descriptor, temporary_name = tempfile.mkstemp(prefix=".ozon-report-", dir=directory)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, target)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        return StoredOzonReport(
            relative_path=target.relative_to(self.root).as_posix(),
            file_name=file_name,
            extension=extension,
            content_type=downloaded.content_type,
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

    def verify(self, relative_path: str, *, size: int, sha256: str) -> bool:
        try:
            target = (self.root / relative_path).resolve(strict=True)
        except (FileNotFoundError, OSError, RuntimeError):
            return False
        if (self.root != target and self.root not in target.parents) or not target.is_file():
            return False
        try:
            if target.stat().st_size != size:
                return False
            digest = hashlib.sha256()
            with target.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest() == sha256
        except OSError:
            return False

    @staticmethod
    def _detect_extension(content: bytes) -> str:
        if content.startswith(b"%PDF-"):
            return "pdf"
        if zipfile.is_zipfile(io.BytesIO(content)):
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
            if "[Content_Types].xml" in names and "xl/workbook.xml" in names:
                return "xlsx"
            return "zip"
        return "csv"

    @staticmethod
    def _validate_content(extension: str, content: bytes) -> None:
        if extension == "pdf" and not content.startswith(b"%PDF-"):
            raise ValueError("Ozon report is not a valid PDF file")
        if extension in {"zip", "xlsx"} and not zipfile.is_zipfile(io.BytesIO(content)):
            raise ValueError(f"Ozon report is not a valid {extension.upper()} file")
        if extension == "xlsx":
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise ValueError("Ozon report ZIP payload is not an XLSX workbook")

    @staticmethod
    def _safe_part(value: str, fallback: str) -> str:
        cleaned = _UNSAFE.sub("_", value).strip(" .")
        return cleaned[:180] or fallback
