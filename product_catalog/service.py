from __future__ import annotations

import hashlib
import json
import uuid
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from sqlalchemy import text

from app.config import (
    OZON_CLIENT_ID,
    PRODUCT_MEDIA_DOWNLOAD_LIMIT,
    PRODUCT_MEDIA_DOWNLOAD_WORKERS,
)
from app.db import SessionLocal
from app.models import (
    MarketplaceProductAttribute,
    MarketplaceProductCatalogSnapshot,
    MarketplaceProductLink,
    MarketplaceProductMedia,
    OzonProduct,
    ProductCatalogSyncRun,
    WBProduct,
    YandexMarketOffer,
)
from product_catalog.storage import ProductMediaStorage, StoredMedia


LOCK_ID = zlib.crc32(b"wbozon:product-catalog-media")


@dataclass(frozen=True)
class MediaCandidate:
    media_type: str
    role: str
    position: int
    url: str
    raw_data: dict[str, Any]


@dataclass(frozen=True)
class AttributeCandidate:
    source_key: str
    name: str
    value: Any


@dataclass(frozen=True)
class CatalogProduct:
    marketplace: str
    account_id: str
    external_product_id: str
    offer_id: str
    product_name: str | None
    master_product_id: int | None
    raw_data: dict[str, Any]
    media: tuple[MediaCandidate, ...]
    attributes: tuple[AttributeCandidate, ...]


def _source_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _urls(value: Any) -> Iterable[str]:
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _urls(item)
    elif isinstance(value, dict):
        preferred = value.get("url") or value.get("src") or value.get("href")
        if preferred:
            yield from _urls(preferred)
        else:
            for item in value.values():
                yield from _urls(item)


def _video_candidates(value: Any, path: str = "") -> Iterable[MediaCandidate]:
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}".strip(".")
            if "video" in str(key).lower():
                for position, url in enumerate(dict.fromkeys(_urls(item))):
                    yield MediaCandidate("video", child[-50:], position, url, {"path": child})
            yield from _video_candidates(item, child)
    elif isinstance(value, list):
        for item in value:
            yield from _video_candidates(item, path)


def _generic_attributes(value: Any, path: str = "") -> Iterable[AttributeCandidate]:
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}".strip(".")
            if str(key).lower() in {
                "attributes", "characteristics", "params", "parameters", "parametervalues"
            } and isinstance(item, list):
                for index, attribute in enumerate(item):
                    if not isinstance(attribute, dict):
                        continue
                    identifier = attribute.get("id") or attribute.get("attribute_id") or attribute.get("name") or index
                    name = str(attribute.get("name") or attribute.get("attributeName") or identifier)
                    result = attribute.get("values")
                    if result is None:
                        result = attribute.get("value")
                    yield AttributeCandidate(f"{child}:{identifier}", name, result)
            yield from _generic_attributes(item, child)
    elif isinstance(value, list):
        for item in value:
            yield from _generic_attributes(item, path)


class ProductCatalogAlreadyRunning(RuntimeError):
    pass


class ProductCatalogService:
    def __init__(
        self,
        *,
        session_factory: Callable[..., Any] = SessionLocal,
        storage: ProductMediaStorage | None = None,
        workers: int = PRODUCT_MEDIA_DOWNLOAD_WORKERS,
        download_limit: int = PRODUCT_MEDIA_DOWNLOAD_LIMIT,
    ) -> None:
        if workers < 1 or download_limit < 0:
            raise ValueError("workers must be positive and download_limit must not be negative")
        self.session_factory = session_factory
        self.storage = storage or ProductMediaStorage()
        self.workers = workers
        self.download_limit = download_limit

    def run(self, *, download: bool = True) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        with self.session_factory() as lock_session:
            if not self._acquire_lock(lock_session):
                raise ProductCatalogAlreadyRunning("product catalog sync is already running")
            self._create_run(run_id)
            try:
                products = self._products()
                normalized = self._normalize(run_id, products)
                files = self._download_missing() if download else {
                    "downloaded": 0, "existing": 0, "failed": 0, "bytes": 0
                }
                result = {**normalized, **files}
                status = "partial" if files["failed"] else "completed"
                self._finish_run(run_id, status, result=result)
                return {"run_id": run_id, "status": status, "result": result}
            except Exception as exc:
                self._finish_run(run_id, "failed", error=f"{type(exc).__name__}: {exc}")
                raise
            finally:
                self._release_lock(lock_session)

    def _products(self) -> list[CatalogProduct]:
        result: list[CatalogProduct] = []
        with self.session_factory() as session:
            links = {
                (row.marketplace, row.account_id, row.external_product_id): row.master_product_id
                for row in session.query(MarketplaceProductLink).filter_by(active=True)
            }
            for row in session.query(WBProduct).all():
                external = str(row.nm_id)
                media = []
                for photo in row.photos:
                    for role, url in (
                        ("big", photo.big_url), ("c246x328", photo.c246x328_url),
                        ("c516x688", photo.c516x688_url), ("hq", photo.hq_url),
                        ("square", photo.square_url), ("tm", photo.tm_url),
                    ):
                        if url:
                            media.append(MediaCandidate("image", role, photo.position, url, {}))
                media.extend(_video_candidates(row.raw_data or {}))
                attributes = [
                    AttributeCandidate(str(item.characteristic.wb_id), item.characteristic.name, item.value)
                    for item in row.characteristic_values
                ]
                result.append(CatalogProduct(
                    "wb", "", external, str(row.vendor_code or row.nm_id), row.title,
                    links.get(("wb", "", external)), row.raw_data or {},
                    self._deduplicate_media(media), tuple(attributes),
                ))
            for row in session.query(OzonProduct).all():
                external = str(row.product_id)
                raw = row.raw_data or {}
                media = []
                for role in ("primary_image", "color_image", "images", "images360"):
                    for position, url in enumerate(dict.fromkeys(_urls(raw.get(role)))):
                        media.append(MediaCandidate("image", role, position, url, {"field": role}))
                media.extend(_video_candidates(raw))
                result.append(CatalogProduct(
                    "ozon", str(OZON_CLIENT_ID or ""), external,
                    str(row.offer_id or row.product_id), row.name,
                    self._find_master(links, "ozon", external), raw,
                    self._deduplicate_media(media), tuple(self._deduplicate_attributes(_generic_attributes(raw))),
                ))
            for row in session.query(YandexMarketOffer).all():
                account = str(row.business_id)
                external = str(row.offer_id)
                raw = row.raw_data or {}
                media = [
                    MediaCandidate("image", "picture", position, url, {})
                    for position, url in enumerate(dict.fromkeys(_urls(row.pictures or [])))
                ]
                media.extend(_video_candidates(raw))
                result.append(CatalogProduct(
                    "yandex_market", account, external, external, row.name,
                    links.get(("yandex_market", account, external)), raw,
                    self._deduplicate_media(media), tuple(self._deduplicate_attributes(_generic_attributes(raw))),
                ))
        return result

    @staticmethod
    def _find_master(links: dict[tuple[str, str, str], int], marketplace: str, external: str) -> int | None:
        matches = [value for (mp, _, ext), value in links.items() if mp == marketplace and ext == external]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _deduplicate_media(items: Iterable[MediaCandidate]) -> tuple[MediaCandidate, ...]:
        result: dict[str, MediaCandidate] = {}
        for item in items:
            result.setdefault(item.url, item)
        return tuple(result.values())

    @staticmethod
    def _deduplicate_attributes(items: Iterable[AttributeCandidate]) -> list[AttributeCandidate]:
        result: dict[str, AttributeCandidate] = {}
        for item in items:
            result[item.source_key] = item
        return list(result.values())

    def _normalize(self, run_id: str, products: list[CatalogProduct]) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        media_seen: set[tuple[str, str, str, str]] = set()
        attribute_seen: set[tuple[str, str, str, str]] = set()
        snapshots_created = 0
        with self.session_factory() as session:
            media_existing = {
                (r.marketplace, r.account_id, r.external_product_id, r.source_key): r
                for r in session.query(MarketplaceProductMedia).all()
            }
            attribute_existing = {
                (r.marketplace, r.account_id, r.external_product_id, r.source_key): r
                for r in session.query(MarketplaceProductAttribute).all()
            }
            for product in products:
                media_payload = []
                for item in product.media:
                    key_hash = _source_key(item.url)
                    key = (product.marketplace, product.account_id, product.external_product_id, key_hash)
                    media_seen.add(key)
                    row = media_existing.get(key)
                    if row is None:
                        row = MarketplaceProductMedia(
                            marketplace=product.marketplace,
                            account_id=product.account_id,
                            external_product_id=product.external_product_id,
                            source_key=key_hash,
                            first_seen_at=now,
                            download_status="pending",
                        )
                        session.add(row)
                    row.master_product_id = product.master_product_id
                    row.offer_id = product.offer_id
                    row.media_type = item.media_type
                    row.role = item.role
                    row.position = item.position
                    row.source_url = item.url
                    row.raw_data = item.raw_data
                    row.active = True
                    row.last_seen_at = now
                    media_payload.append(asdict(item))
                attribute_payload = []
                for item in product.attributes:
                    key = (product.marketplace, product.account_id, product.external_product_id, item.source_key)
                    attribute_seen.add(key)
                    row = attribute_existing.get(key)
                    if row is None:
                        row = MarketplaceProductAttribute(
                            marketplace=product.marketplace,
                            account_id=product.account_id,
                            external_product_id=product.external_product_id,
                            source_key=item.source_key,
                            first_seen_at=now,
                        )
                        session.add(row)
                    row.master_product_id = product.master_product_id
                    row.offer_id = product.offer_id
                    row.name = item.name
                    row.value = item.value
                    row.active = True
                    row.last_seen_at = now
                    attribute_payload.append(asdict(item))
                snapshot_data = {
                    "catalog": product.raw_data,
                    "media": media_payload,
                    "attributes": attribute_payload,
                }
                encoded = json.dumps(snapshot_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
                content_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
                exists = session.query(MarketplaceProductCatalogSnapshot.id).filter_by(
                    marketplace=product.marketplace,
                    account_id=product.account_id,
                    external_product_id=product.external_product_id,
                    content_hash=content_hash,
                ).first()
                if exists is None:
                    session.add(MarketplaceProductCatalogSnapshot(
                        run_id=run_id,
                        master_product_id=product.master_product_id,
                        marketplace=product.marketplace,
                        account_id=product.account_id,
                        external_product_id=product.external_product_id,
                        offer_id=product.offer_id,
                        product_name=product.product_name,
                        content_hash=content_hash,
                        captured_at=now,
                        data=snapshot_data,
                    ))
                    snapshots_created += 1
            for key, row in media_existing.items():
                if key not in media_seen:
                    row.active = False
                    row.last_seen_at = now
            for key, row in attribute_existing.items():
                if key not in attribute_seen:
                    row.active = False
                    row.last_seen_at = now
            session.commit()
        return {
            "source_rows": len(products),
            "media_rows": len(media_seen),
            "attribute_rows": len(attribute_seen),
            "snapshots_created": snapshots_created,
        }

    def _download_missing(self) -> dict[str, int]:
        with self.session_factory() as session:
            rows = session.query(MarketplaceProductMedia).filter(
                MarketplaceProductMedia.active.is_(True)
            ).order_by(MarketplaceProductMedia.id).all()
        totals = {"downloaded": 0, "existing": 0, "failed": 0, "bytes": 0}
        tasks = []
        for row in rows:
            if (
                row.download_status == "downloaded"
                and row.local_path
                and self.storage.verify(
                    row.local_path, size=row.file_size, sha256=row.file_sha256
                )
            ):
                totals["existing"] += 1
                continue
            tasks.append({
                "id": row.id,
                "url": row.source_url,
                "marketplace": row.marketplace,
                "article": row.offer_id,
                "external_product_id": row.external_product_id,
                "media_type": row.media_type,
                "position": row.position,
                "source_key": row.source_key,
            })
        if self.download_limit:
            tasks = tasks[:self.download_limit]
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {executor.submit(self.storage.download, **{k: v for k, v in task.items() if k != "id"}): task for task in tasks}
            for future in as_completed(futures):
                task = futures[future]
                try:
                    stored = future.result()
                except Exception as exc:
                    self._record_download_error(task["id"], exc)
                    totals["failed"] += 1
                    continue
                self._record_download(task["id"], stored)
                totals["downloaded"] += 1
                totals["bytes"] += stored.size
        return totals

    def _record_download(self, row_id: int, stored: StoredMedia) -> None:
        with self.session_factory() as session:
            row = session.get(MarketplaceProductMedia, row_id)
            row.local_path = stored.relative_path
            row.file_name = stored.file_name
            row.file_extension = stored.extension
            row.content_type = stored.content_type
            row.file_size = stored.size
            row.file_sha256 = stored.sha256
            row.download_status = "downloaded"
            row.download_attempts += 1
            row.download_error = None
            row.downloaded_at = datetime.now(timezone.utc)
            session.commit()

    def _record_download_error(self, row_id: int, exc: Exception) -> None:
        with self.session_factory() as session:
            row = session.get(MarketplaceProductMedia, row_id)
            row.download_status = "error"
            row.download_attempts += 1
            row.download_error = f"{type(exc).__name__}: {exc}"[:4000]
            session.commit()

    def _create_run(self, run_id: str) -> None:
        with self.session_factory() as session:
            session.add(ProductCatalogSyncRun(id=run_id, started_at=datetime.now(timezone.utc), status="running"))
            session.commit()

    def _finish_run(self, run_id: str, status: str, *, result: dict[str, int] | None = None, error: str | None = None) -> None:
        result = result or {}
        with self.session_factory() as session:
            row = session.get(ProductCatalogSyncRun, run_id)
            row.finished_at = datetime.now(timezone.utc)
            row.status = status
            for field in ("source_rows", "media_rows", "attribute_rows", "snapshots_created"):
                setattr(row, field, result.get(field, 0))
            row.files_downloaded = result.get("downloaded", 0)
            row.files_existing = result.get("existing", 0)
            row.files_failed = result.get("failed", 0)
            row.bytes_downloaded = result.get("bytes", 0)
            row.error = error
            session.commit()

    @staticmethod
    def _acquire_lock(session: Any) -> bool:
        if session.get_bind().dialect.name != "postgresql":
            return True
        return bool(session.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": LOCK_ID}).scalar())

    @staticmethod
    def _release_lock(session: Any) -> None:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": LOCK_ID})
