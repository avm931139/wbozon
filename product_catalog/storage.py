from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests

from app.config import (
    PRODUCT_MEDIA_DOWNLOAD_TIMEOUT_SECONDS,
    PRODUCT_MEDIA_MAX_FILE_BYTES,
    PRODUCT_MEDIA_STORAGE_DIR,
)


SAFE_PART = re.compile(r"[^A-Za-zА-Яа-яЁё0-9._+() -]+")
CONTENT_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/avif": "avif",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
}


@dataclass(frozen=True)
class StoredMedia:
    relative_path: str
    file_name: str
    extension: str
    content_type: str
    size: int
    sha256: str


class ProductMediaStorage:
    def __init__(
        self,
        root: str | Path = PRODUCT_MEDIA_STORAGE_DIR,
        *,
        max_file_bytes: int = PRODUCT_MEDIA_MAX_FILE_BYTES,
        timeout: int = PRODUCT_MEDIA_DOWNLOAD_TIMEOUT_SECONDS,
        session_factory: Callable[[], Any] = requests.Session,
    ) -> None:
        if max_file_bytes < 1 or timeout < 1:
            raise ValueError("media size and timeout limits must be positive")
        self.root = Path(root).expanduser().resolve()
        self.max_file_bytes = max_file_bytes
        self.timeout = timeout
        self.session_factory = session_factory

    def download(
        self,
        *,
        url: str,
        marketplace: str,
        article: str,
        external_product_id: str,
        media_type: str,
        position: int,
        source_key: str,
    ) -> StoredMedia:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("media URL must use HTTP or HTTPS")
        directory = self._directory(marketplace, article, external_product_id)
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".media-", dir=directory)
        digest = hashlib.sha256()
        size = 0
        session = self.session_factory()
        try:
            with os.fdopen(descriptor, "wb") as handle:
                response = session.get(url, stream=True, timeout=self.timeout)
                response.raise_for_status()
                content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
                self._validate_content_type(content_type, media_type, parsed.path)
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > self.max_file_bytes:
                    raise ValueError("media file exceeds configured size limit")
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > self.max_file_bytes:
                        raise ValueError("media file exceeds configured size limit")
                    handle.write(chunk)
                    digest.update(chunk)
                if not size:
                    raise ValueError("media response is empty")
                handle.flush()
                os.fsync(handle.fileno())
            extension = self._extension(content_type, parsed.path, media_type)
            file_name = f"{position:03d}_{source_key[:16]}.{extension}"
            target = (directory / file_name).resolve()
            self._assert_confined(target)
            os.replace(temporary_name, target)
            return StoredMedia(
                relative_path=target.relative_to(self.root).as_posix(),
                file_name=file_name,
                extension=extension,
                content_type=content_type,
                size=size,
                sha256=digest.hexdigest(),
            )
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        finally:
            close = getattr(session, "close", None)
            if close:
                close()

    def verify(self, relative_path: str, *, size: int | None, sha256: str | None) -> bool:
        try:
            target = (self.root / relative_path).resolve(strict=True)
            self._assert_confined(target)
            if not target.is_file() or (size is not None and target.stat().st_size != size):
                return False
            if sha256:
                digest = hashlib.sha256()
                with target.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                return digest.hexdigest() == sha256
            return True
        except (OSError, RuntimeError, ValueError):
            return False

    def _directory(self, marketplace: str, article: str, external_id: str) -> Path:
        path = self.root / self._safe(marketplace, "marketplace") / self._safe(article, "article") / self._safe(external_id, "product")
        resolved = path.resolve()
        self._assert_confined(resolved)
        return resolved

    def _assert_confined(self, path: Path) -> None:
        if path != self.root and self.root not in path.parents:
            raise ValueError("media path escapes storage directory")

    @staticmethod
    def _safe(value: str, fallback: str) -> str:
        cleaned = SAFE_PART.sub("_", str(value)).strip(" .")
        while ".." in cleaned:
            cleaned = cleaned.replace("..", "_")
        return cleaned[:120] or fallback

    @staticmethod
    def _validate_content_type(content_type: str, media_type: str, path: str) -> None:
        if content_type.startswith("text/html"):
            raise ValueError("media URL returned HTML")
        if media_type == "image" and content_type.startswith("video/"):
            raise ValueError("image URL returned video content")
        if media_type == "video" and content_type.startswith("image/"):
            raise ValueError("video URL returned image content")
        if not content_type and not Path(path).suffix:
            raise ValueError("media response has neither content type nor extension")

    @staticmethod
    def _extension(content_type: str, path: str, media_type: str) -> str:
        if content_type in CONTENT_EXTENSIONS:
            return CONTENT_EXTENSIONS[content_type]
        extension = Path(path).suffix.lower().lstrip(".")
        if re.fullmatch(r"[a-z0-9]{1,10}", extension):
            return extension
        guessed = mimetypes.guess_extension(content_type or "")
        if guessed:
            return guessed.lstrip(".").replace("jpe", "jpg")
        return "mp4" if media_type == "video" else "bin"
