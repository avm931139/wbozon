from __future__ import annotations

import re
import unicodedata
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import text

from app.config import OZON_CLIENT_ID
from app.db import SessionLocal
from app.models import (
    MarketplaceProductLink,
    MasterProduct,
    OzonProduct,
    ProductMappingRun,
    WBProduct,
    YandexMarketOffer,
)


TEST_SUFFIX_RE = re.compile(
    r"(?:[\s_-]+(?:OLD|TEST\d*|ТЕСТ\d*|D(?:D|\d*)))$",
    re.IGNORECASE,
)
LOCK_ID = zlib.crc32(b"wbozon:product-master-mapping")


@dataclass(frozen=True)
class SourceProduct:
    marketplace: str
    account_id: str
    external_product_id: str
    offer_id: str
    article: str
    name: str | None


def normalize_article(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().upper()
    return " ".join(normalized.split())


def match_article(article: str, known_articles: set[str]) -> tuple[str, str]:
    """Return an exact article or a known base after a conservative test suffix."""
    candidate = TEST_SUFFIX_RE.sub("", article).rstrip(" _-")
    if candidate and candidate != article and candidate in known_articles:
        return candidate, "suffix"
    return article, "exact"


class ProductMappingAlreadyRunning(RuntimeError):
    pass


class ProductMappingService:
    def __init__(self, *, session_factory: Callable[..., Any] = SessionLocal) -> None:
        self.session_factory = session_factory

    def run(self) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        with self.session_factory() as lock_session:
            if not self._acquire_lock(lock_session):
                raise ProductMappingAlreadyRunning("product mapping is already running")
            self._create_run(run_id)
            try:
                result = self._sync()
                self._finish_run(run_id, "completed", result=result)
                return {"run_id": run_id, "status": "completed", "result": result}
            except Exception as exc:
                self._finish_run(
                    run_id,
                    "failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise
            finally:
                self._release_lock(lock_session)

    def _source_products(self) -> list[SourceProduct]:
        rows: list[SourceProduct] = []
        with self.session_factory() as session:
            for item in session.query(WBProduct).filter(WBProduct.vendor_code.is_not(None)):
                if str(item.vendor_code).strip():
                    rows.append(SourceProduct(
                        marketplace="wb",
                        account_id="",
                        external_product_id=str(item.nm_id),
                        offer_id=str(item.vendor_code),
                        article=str(item.vendor_code),
                        name=item.title,
                    ))
            for item in session.query(OzonProduct).filter(OzonProduct.offer_id.is_not(None)):
                if str(item.offer_id).strip():
                    rows.append(SourceProduct(
                        marketplace="ozon",
                        account_id=str(OZON_CLIENT_ID or ""),
                        external_product_id=str(item.product_id),
                        offer_id=str(item.offer_id),
                        article=str(item.offer_id),
                        name=item.name,
                    ))
            for item in session.query(YandexMarketOffer):
                if str(item.offer_id).strip():
                    rows.append(SourceProduct(
                        marketplace="yandex_market",
                        account_id=str(item.business_id),
                        external_product_id=str(item.offer_id),
                        offer_id=str(item.offer_id),
                        article=str(item.offer_id),
                        name=item.name,
                    ))
        return rows

    def _sync(self) -> dict[str, int]:
        sources = self._source_products()
        known_articles = {normalize_article(item.article) for item in sources}
        matched = []
        for item in sources:
            normalized = normalize_article(item.article)
            canonical, method = match_article(normalized, known_articles)
            matched.append((item, normalized, canonical, method))

        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            masters = {row.article: row for row in session.query(MasterProduct).all()}
            names: dict[str, list[tuple[int, str]]] = {}
            priorities = {"wb": 0, "ozon": 1, "yandex_market": 2}
            for item, _, canonical, _ in matched:
                if item.name:
                    names.setdefault(canonical, []).append(
                        (priorities[item.marketplace], item.name)
                    )
                if canonical not in masters:
                    master = MasterProduct(
                        article=canonical,
                        name=None,
                        active=True,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(master)
                    masters[canonical] = master
            session.flush()

            for canonical, candidates in names.items():
                master = masters[canonical]
                master.name = sorted(candidates, key=lambda value: value[0])[0][1]
                master.updated_at = now

            existing = {
                (row.marketplace, row.account_id, row.external_product_id): row
                for row in session.query(MarketplaceProductLink).all()
            }
            seen: set[tuple[str, str, str]] = set()
            exact_links = 0
            suffix_links = 0
            for item, normalized, canonical, method in matched:
                key = (item.marketplace, item.account_id, item.external_product_id)
                seen.add(key)
                link = existing.get(key)
                if link is None:
                    link = MarketplaceProductLink(
                        marketplace=item.marketplace,
                        account_id=item.account_id,
                        external_product_id=item.external_product_id,
                        master_product_id=masters[canonical].id,
                    )
                    session.add(link)
                elif link.match_method != "manual":
                    link.master_product_id = masters[canonical].id
                effective_method = link.match_method if link.match_method == "manual" else method
                link.offer_id = item.offer_id
                link.source_article = item.article
                link.normalized_article = normalized
                link.match_method = effective_method
                link.is_test_variant = effective_method == "suffix"
                link.product_name = item.name
                link.active = True
                link.matched_at = now
                if effective_method == "suffix":
                    suffix_links += 1
                else:
                    exact_links += 1

            inactive_links = 0
            for key, link in existing.items():
                if key not in seen and link.active:
                    link.active = False
                    link.matched_at = now
                    inactive_links += 1

            session.flush()
            active_master_ids = {
                value for value, in session.query(MarketplaceProductLink.master_product_id).filter_by(
                    active=True
                ).distinct()
            }
            for master in masters.values():
                master.active = master.id in active_master_ids
                master.updated_at = now
            session.commit()
            active_masters = sum(master.active for master in masters.values())

        return {
            "source_rows": len(sources),
            "master_products": active_masters,
            "exact_links": exact_links,
            "suffix_links": suffix_links,
            "inactive_links": inactive_links,
        }

    def _create_run(self, run_id: str) -> None:
        with self.session_factory() as session:
            session.add(ProductMappingRun(
                id=run_id,
                started_at=datetime.now(timezone.utc),
                status="running",
            ))
            session.commit()

    def _finish_run(
        self,
        run_id: str,
        status: str,
        *,
        result: dict[str, int] | None = None,
        error: str | None = None,
    ) -> None:
        result = result or {}
        with self.session_factory() as session:
            row = session.get(ProductMappingRun, run_id)
            if row is None:
                return
            row.finished_at = datetime.now(timezone.utc)
            row.status = status
            row.source_rows = result.get("source_rows", 0)
            row.master_products = result.get("master_products", 0)
            row.exact_links = result.get("exact_links", 0)
            row.suffix_links = result.get("suffix_links", 0)
            row.inactive_links = result.get("inactive_links", 0)
            row.error = error
            session.commit()

    @staticmethod
    def _acquire_lock(session: Any) -> bool:
        if session.get_bind().dialect.name != "postgresql":
            return True
        return bool(session.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": LOCK_ID}
        ).scalar())

    @staticmethod
    def _release_lock(session: Any) -> None:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": LOCK_ID})
