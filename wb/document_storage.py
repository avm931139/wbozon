from __future__ import annotations

import base64
import binascii
import hashlib
import io
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import WB_DOCUMENT_MAX_FILE_BYTES, WB_DOCUMENT_STORAGE_DIR


_UNSAFE = re.compile(r"[^\w.() -]+", re.UNICODE)
_EXTENSION = re.compile(r"^[a-z0-9_]{1,30}$")


@dataclass(frozen=True)
class StoredDocument:
    path: Path
    relative_path: str
    file_name: str
    extension: str
    size: int
    sha256: str


class DocumentStorage:
    """Decode WB base64 responses and atomically persist them under one root."""

    def __init__(
        self,
        root: str | Path = WB_DOCUMENT_STORAGE_DIR,
        *,
        max_file_bytes: int = WB_DOCUMENT_MAX_FILE_BYTES,
    ) -> None:
        if max_file_bytes < 1:
            raise ValueError("max_file_bytes must be positive")
        self.root = Path(root).expanduser().resolve()
        self.max_file_bytes = max_file_bytes

    def save(
        self,
        service_name: str,
        payload: dict[str, Any],
        *,
        expected_extension: str | None = None,
    ) -> StoredDocument:
        encoded = payload.get("document")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("WB document response does not contain base64 document data")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("WB document response contains invalid base64 data") from exc
        if not content:
            raise ValueError("WB document response contains an empty file")
        if len(content) > self.max_file_bytes:
            raise ValueError(
                f"WB document exceeds the configured limit of {self.max_file_bytes} bytes"
            )

        extension = str(payload.get("extension") or "").strip().lstrip(".").lower()
        if not _EXTENSION.fullmatch(extension):
            raise ValueError("WB document response contains an invalid extension")
        if expected_extension is not None:
            normalized_expected = expected_extension.strip().lstrip(".").lower()
            is_xlsx_package = normalized_expected == "xlsx" and extension == "zip"
            if extension != normalized_expected and not is_xlsx_package:
                raise ValueError(
                    f"WB document extension mismatch: requested {normalized_expected}, got {extension}"
                )
        self._validate_content(extension, content)
        if expected_extension is not None and normalized_expected == "xlsx" and extension == "zip":
            self._validate_xlsx_package(content)
        safe_service_name = self._safe_part(service_name, "document")
        supplied_name = str(payload.get("fileName") or safe_service_name).replace("\\", "/")
        supplied_leaf = supplied_name.rsplit("/", 1)[-1]
        stem = self._safe_part(Path(supplied_leaf).stem, safe_service_name)
        file_name = f"{stem}.{extension}"

        service_dir = self.root / safe_service_name
        service_dir.mkdir(parents=True, exist_ok=True)
        target = (service_dir / file_name).resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError("document path escapes storage directory")

        descriptor, temporary_name = tempfile.mkstemp(prefix=".wb-document-", dir=service_dir)
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

        return StoredDocument(
            path=target,
            relative_path=target.relative_to(self.root).as_posix(),
            file_name=file_name,
            extension=extension,
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

    def verify(
        self,
        relative_path: str,
        *,
        size: int | None = None,
        sha256: str | None = None,
    ) -> bool:
        """Verify that a recorded file remains inside the root and matches metadata."""
        try:
            target = (self.root / relative_path).resolve(strict=True)
        except (FileNotFoundError, OSError, RuntimeError):
            return False
        if self.root != target and self.root not in target.parents:
            return False
        if not target.is_file():
            return False
        try:
            if size is not None and target.stat().st_size != size:
                return False
            if sha256:
                digest = hashlib.sha256()
                with target.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != sha256:
                    return False
        except OSError:
            return False
        return True

    @staticmethod
    def _validate_content(extension: str, content: bytes) -> None:
        if extension == "pdf" and b"%PDF-" not in content[:1024]:
            raise ValueError("WB document is not a valid PDF file")
        if extension in {"zip", "xlsx"} and not zipfile.is_zipfile(io.BytesIO(content)):
            raise ValueError(f"WB document is not a valid {extension.upper()} file")
        if extension == "xlsx":
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    names = set(archive.namelist())
            except (OSError, zipfile.BadZipFile) as exc:
                raise ValueError("WB document is not a valid XLSX file") from exc
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise ValueError("WB document ZIP payload is not an XLSX workbook")

    @staticmethod
    def _validate_xlsx_package(content: bytes) -> None:
        """Validate the outer ZIP WB sometimes returns for a requested XLSX."""
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = archive.namelist()
        except (OSError, zipfile.BadZipFile) as exc:
            raise ValueError("WB XLSX package is not a valid ZIP file") from exc
        if not any(name.lower().endswith(".xlsx") for name in names):
            raise ValueError("WB XLSX package does not contain an XLSX file")

    @staticmethod
    def _safe_part(value: str, fallback: str) -> str:
        cleaned = _UNSAFE.sub("_", value).strip(" .")
        return cleaned[:180] or fallback
