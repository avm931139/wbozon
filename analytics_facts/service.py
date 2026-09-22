from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import uuid
import zlib
from typing import Any, Callable

from sqlalchemy import delete, select, text

from app.config import OZON_CLIENT_ID
from app.db import SessionLocal
from app.models import (
    AnalyticsFactSyncRun,
    FactSale,
    FactSaleSource,
    MarketplaceProductLink,
    OzonFinanceAccrualType,
    OzonFinancePostingAccrual,
    OzonPosting,
    OzonProduct,
    ProductBarcode,
    ProductCostRecord,
    WBFinancialSalesReport,
    WBFinancialSalesRow,
    WBProduct,
    WBProductSize,
    WBSizeBarcode,
    YandexMarketFinanceTransaction,
    YandexMarketOffer,
)


CALCULATION_VERSION = "financial-sales-v1"
MARKETPLACES = ("wb", "ozon", "yandex_market")
WB_SALE_OPERATIONS = {"Продажа", "Бронирование товара через самовывоз"}
WB_RETURN_OPERATIONS = {"Возврат"}
MONEY_FIELDS = (
    ("gross_amount_exact", "gross_amount_kopecks"),
    ("discount_amount_exact", "discount_amount_kopecks"),
    ("marketplace_discount_exact", "marketplace_discount_kopecks"),
    ("customer_paid_exact", "customer_paid_kopecks"),
    ("sales_amount_exact", "sales_amount_kopecks"),
    ("return_amount_exact", "return_amount_kopecks"),
    ("compensation_amount_exact", "compensation_amount_kopecks"),
    ("net_revenue_exact", "net_revenue_kopecks"),
    ("cost_amount_exact", "cost_amount_kopecks"),
)


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def money_to_kopecks(value: Any) -> int:
    return int((_decimal(value) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _payload_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _as_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


@dataclass
class SourceReference:
    table: str
    record_id: str
    operation_key: str | None
    payload_hash: str | None


@dataclass
class PendingFact:
    values: dict[str, Any]
    sources: list[SourceReference]


class FinancialSalesFactAlreadyRunning(RuntimeError):
    pass


class FinancialSalesFactService:
    """Build a replaceable analytical layer from immutable financial evidence."""

    def __init__(
        self,
        marketplace: str,
        *,
        session_factory: Callable[..., Any] = SessionLocal,
    ) -> None:
        if marketplace not in MARKETPLACES:
            raise ValueError(f"unsupported marketplace: {marketplace}")
        self.marketplace = marketplace
        self.session_factory = session_factory
        self.lock_id = zlib.crc32(f"wbozon:analytics-facts:{marketplace}".encode())

    def run(self) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        with self.session_factory() as lock_session:
            if not self._acquire_lock(lock_session):
                raise FinancialSalesFactAlreadyRunning(
                    f"{self.marketplace} financial fact sync is already running"
                )
            self._create_run(run_id)
            try:
                result = self._sync()
                self._finish_run(run_id, "completed", result=result)
                return {
                    "run_id": run_id,
                    "marketplace": self.marketplace,
                    "status": "completed",
                    "result": result,
                }
            except Exception as exc:
                self._finish_run(
                    run_id, "failed", error=f"{type(exc).__name__}: {exc}"
                )
                raise
            finally:
                self._release_lock(lock_session)

    def _sync(self) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            links = self._links(session)
            costs = self._latest_costs(session)
            if self.marketplace == "wb":
                facts, source_rows = self._wb_facts(session, links, costs, now)
            elif self.marketplace == "ozon":
                facts, source_rows = self._ozon_facts(session, links, costs, now)
            else:
                facts, source_rows = self._yandex_facts(session, links, costs, now)

            self._assign_kopecks(facts)
            fact_ids = select(FactSale.id).where(
                FactSale.marketplace == self.marketplace
            )
            session.execute(
                delete(FactSaleSource).where(FactSaleSource.fact_sale_id.in_(fact_ids))
            )
            session.execute(
                delete(FactSale).where(FactSale.marketplace == self.marketplace)
            )
            session.execute(
                delete(ProductBarcode).where(
                    ProductBarcode.marketplace == self.marketplace
                )
            )

            lineage_rows = 0
            for pending in facts:
                row = FactSale(**pending.values)
                session.add(row)
                session.flush()
                for source in pending.sources:
                    session.add(FactSaleSource(
                        fact_sale_id=row.id,
                        source_table=source.table,
                        source_record_id=source.record_id,
                        source_operation_key=source.operation_key,
                        source_payload_hash=source.payload_hash,
                    ))
                    lineage_rows += 1
            barcode_rows = self._sync_barcodes(session, links, now)
            session.commit()

        return {
            "source_rows": source_rows,
            "facts_written": len(facts),
            "lineage_rows": lineage_rows,
            "barcode_rows": barcode_rows,
            "unmatched_products": sum(
                item.values.get("master_product_id") is None for item in facts
            ),
        }

    def _links(self, session: Any) -> dict[tuple[str, str, str], MarketplaceProductLink]:
        return {
            (row.marketplace, row.account_id, row.external_product_id): row
            for row in session.query(MarketplaceProductLink).filter_by(active=True)
        }

    @staticmethod
    def _latest_costs(session: Any) -> dict[int, ProductCostRecord]:
        costs: dict[int, ProductCostRecord] = {}
        rows = session.query(ProductCostRecord).order_by(
            ProductCostRecord.master_product_id,
            ProductCostRecord.effective_at.desc(),
            ProductCostRecord.id.desc(),
        )
        for row in rows:
            costs.setdefault(row.master_product_id, row)
        return costs

    @staticmethod
    def _link_values(link: MarketplaceProductLink | None) -> dict[str, Any]:
        return {
            "master_product_id": link.master_product_id if link else None,
            "marketplace_product_link_id": link.id if link else None,
        }

    @staticmethod
    def _apply_cost(
        values: dict[str, Any],
        costs: dict[int, ProductCostRecord],
    ) -> None:
        master_product_id = values.get("master_product_id")
        cost = costs.get(master_product_id) if master_product_id is not None else None
        if cost is None:
            values.update({
                "unit_cost_exact": None,
                "cost_amount_exact": None,
                "cost_record_id": None,
                "cost_status": "missing",
            })
            return
        if str(cost.currency or "RUB") != str(values.get("currency") or "RUB"):
            values.update({
                "unit_cost_exact": None,
                "cost_amount_exact": None,
                "cost_record_id": cost.id,
                "cost_status": "currency_mismatch",
            })
            return
        unit_cost = _decimal(cost.unit_cost)
        values.update({
            "unit_cost_exact": unit_cost,
            "cost_amount_exact": unit_cost * int(values["quantity"]),
            "cost_record_id": cost.id,
            "cost_status": "matched",
        })

    @staticmethod
    def _base_values(
        *,
        marketplace: str,
        account_id: str,
        event_type: str,
        quantity: int,
        amount: Decimal,
        unit_price: Decimal,
        source_event_key: str,
        source_table: str,
        source_record_id: str | None,
        source_operation_key: str,
        source_payload_hash: str,
        business_date: Any,
        event_at: datetime | None,
        loaded_at: datetime | None,
        normalized_at: datetime,
        currency: str | None,
    ) -> dict[str, Any]:
        is_return = event_type == "return"
        return {
            "marketplace": marketplace,
            "account_id": account_id,
            "event_type": event_type,
            "event_at": event_at,
            "business_date": business_date,
            "return_date": event_at if is_return else None,
            "quantity": quantity,
            "unit_price_exact": abs(unit_price),
            "gross_amount_exact": amount,
            "discount_amount_exact": Decimal("0"),
            "marketplace_discount_exact": Decimal("0"),
            "customer_paid_exact": Decimal("0"),
            "sales_amount_exact": Decimal("0") if is_return else amount,
            "return_amount_exact": amount if is_return else Decimal("0"),
            "compensation_amount_exact": Decimal("0"),
            "net_revenue_exact": amount,
            "currency": currency or "RUB",
            "source_event_key": source_event_key,
            "source_table": source_table,
            "source_record_id": source_record_id,
            "source_operation_key": source_operation_key,
            "source_payload_hash": source_payload_hash,
            "calculation_version": CALCULATION_VERSION,
            "is_financial": True,
            "is_preliminary": False,
            "loaded_at": loaded_at,
            "normalized_at": normalized_at,
        }

    def _wb_facts(
        self,
        session: Any,
        links: dict[tuple[str, str, str], MarketplaceProductLink],
        costs: dict[int, ProductCostRecord],
        now: datetime,
    ) -> tuple[list[PendingFact], int]:
        reports = {
            row.id: row for row in session.query(WBFinancialSalesReport).all()
        }
        rows = session.query(WBFinancialSalesRow).filter(
            WBFinancialSalesRow.seller_operation_name.in_(
                WB_SALE_OPERATIONS | WB_RETURN_OPERATIONS
            )
        ).all()
        facts: list[PendingFact] = []
        for row in rows:
            if row.rr_date is None:
                continue
            event_type = (
                "return" if row.seller_operation_name in WB_RETURN_OPERATIONS else "sale"
            )
            raw_quantity = abs(int(row.quantity or 0))
            if raw_quantity == 0:
                continue
            quantity = -raw_quantity if event_type == "return" else raw_quantity
            unit_price = abs(_decimal(row.retail_price_with_discount))
            amount = unit_price * quantity
            external_product_id = _as_string(row.nm_id)
            link = links.get(("wb", "", external_product_id or ""))
            payload_hash = _payload_hash(row.raw_data)
            report = reports.get(row.report_id)
            values = self._base_values(
                marketplace="wb", account_id="", event_type=event_type,
                quantity=quantity, amount=amount, unit_price=unit_price,
                source_event_key=f"rrd:{row.rrd_id}",
                source_table="wb_financial_sales_rows",
                source_record_id=str(row.id), source_operation_key=str(row.rrd_id),
                source_payload_hash=payload_hash,
                business_date=row.rr_date.date(), event_at=row.sale_date or row.rr_date,
                loaded_at=report.details_synced_at if report else None,
                normalized_at=now, currency=row.currency or (report.currency if report else None),
            )
            values.update(self._link_values(link))
            gross_amount = abs(_decimal(row.retail_price)) * quantity
            values.update({
                "store_id": report.seller_finance_name if report else None,
                "seller_sku": row.vendor_code or row.sku,
                "marketplace_sku": external_product_id,
                "offer_id": row.vendor_code or row.sku,
                "order_id": _as_string(row.order_id or row.order_uid or row.srid),
                "operation_id": str(row.rrd_id),
                "order_date": row.order_date,
                "delivery_date": row.sale_date if event_type == "sale" else None,
                "status": row.seller_operation_name,
                "gross_amount_exact": gross_amount or amount,
                "discount_amount_exact": (gross_amount - amount) if gross_amount else Decimal("0"),
                "customer_paid_exact": amount,
            })
            self._apply_cost(values, costs)
            facts.append(PendingFact(values, [SourceReference(
                "wb_financial_sales_rows", str(row.id), str(row.rrd_id), payload_hash
            )]))
        return facts, len(rows)

    def _ozon_facts(
        self,
        session: Any,
        links: dict[tuple[str, str, str], MarketplaceProductLink],
        costs: dict[int, ProductCostRecord],
        now: datetime,
    ) -> tuple[list[PendingFact], int]:
        account_id = str(OZON_CLIENT_ID or "")
        type_ids = {
            row.type_id for row in session.query(OzonFinanceAccrualType).filter_by(
                name="SaleCommission"
            )
        }
        rows = session.query(OzonFinancePostingAccrual).filter(
            OzonFinancePostingAccrual.type_id.in_(type_ids)
        ).all() if type_ids else []
        products = {
            int(row.sku): row
            for row in session.query(OzonProduct).filter(OzonProduct.sku.is_not(None))
        }
        links_by_offer: dict[tuple[str, str], MarketplaceProductLink | None] = {}
        for candidate in links.values():
            if candidate.marketplace != "ozon" or not candidate.offer_id:
                continue
            key = (candidate.account_id, candidate.offer_id)
            previous = links_by_offer.get(key)
            if previous is None and key not in links_by_offer:
                links_by_offer[key] = candidate
            elif previous is not None and previous.master_product_id != candidate.master_product_id:
                # An ambiguous seller article must never be guessed.
                links_by_offer[key] = None

        posting_products: dict[tuple[str, str], dict[str, Any] | None] = {}
        for posting in session.query(OzonPosting).all():
            for item in posting.products or []:
                if not isinstance(item, dict):
                    continue
                sku = _as_string(item.get("sku"))
                offer_id = _as_string(item.get("offer_id") or item.get("offerId"))
                if not sku or not offer_id:
                    continue
                key = (posting.posting_number, sku)
                value = {
                    "offer_id": offer_id,
                    "name": _as_string(item.get("name")),
                    "scheme": posting.scheme,
                }
                previous = posting_products.get(key)
                if previous is None and key not in posting_products:
                    posting_products[key] = value
                elif previous is not None and previous["offer_id"] != offer_id:
                    # The posting evidence is inconsistent, so leave the fact unmatched.
                    posting_products[key] = None
        facts: list[PendingFact] = []
        for row in rows:
            if row.accrual_date is None:
                continue
            raw_quantity = abs(int(row.quantity or 0))
            if raw_quantity == 0:
                continue
            seller_price = _decimal(row.seller_price)
            event_type = "return" if seller_price < 0 else "sale"
            quantity = -raw_quantity if event_type == "return" else raw_quantity
            unit_price = abs(seller_price)
            amount = unit_price * quantity
            product = products.get(int(row.sku)) if row.sku is not None else None
            posting_product = posting_products.get(
                (row.posting_number, _as_string(row.sku) or "")
            )
            offer_id = (
                product.offer_id if product else
                posting_product.get("offer_id") if posting_product else None
            )
            external_product_id = _as_string(product.product_id if product else None)
            link = links.get(("ozon", account_id, external_product_id or ""))
            if link is None and offer_id:
                link = links_by_offer.get((account_id, offer_id))
            payload_hash = _payload_hash(row.raw_data)
            event_at = datetime.combine(row.accrual_date, time.min, tzinfo=timezone.utc)
            values = self._base_values(
                marketplace="ozon", account_id=account_id, event_type=event_type,
                quantity=quantity, amount=amount, unit_price=unit_price,
                source_event_key=f"posting:{row.source_hash}",
                source_table="ozon_finance_posting_accruals",
                source_record_id=str(row.id), source_operation_key=row.source_hash,
                source_payload_hash=payload_hash, business_date=row.accrual_date,
                event_at=event_at, loaded_at=row.fetched_at,
                normalized_at=now, currency=row.currency,
            )
            values.update(self._link_values(link))
            values.update({
                "seller_sku": offer_id,
                "marketplace_sku": _as_string(row.sku),
                "offer_id": offer_id,
                "order_id": row.posting_number,
                "posting_id": row.posting_number,
                "operation_id": row.source_hash,
                "fulfillment_type": (
                    posting_product.get("scheme") if posting_product else None
                ),
                "status": "SaleCommission",
                "customer_paid_exact": amount,
            })
            self._apply_cost(values, costs)
            facts.append(PendingFact(values, [SourceReference(
                "ozon_finance_posting_accruals", str(row.id), row.source_hash,
                payload_hash,
            )]))
        return facts, len(rows)

    def _yandex_facts(
        self,
        session: Any,
        links: dict[tuple[str, str, str], MarketplaceProductLink],
        costs: dict[int, ProductCostRecord],
        now: datetime,
    ) -> tuple[list[PendingFact], int]:
        rows = session.query(YandexMarketFinanceTransaction).filter(
            YandexMarketFinanceTransaction.transaction_type.in_(("Начисление", "Возврат")),
            YandexMarketFinanceTransaction.quantity > 0,
        ).all()
        offers = {
            (str(row.business_id), row.offer_id): row
            for row in session.query(YandexMarketOffer).all()
        }
        grouped: dict[tuple[Any, ...], list[YandexMarketFinanceTransaction]] = defaultdict(list)
        for row in rows:
            grouped[(
                row.business_id, row.order_id, row.offer_id,
                row.transaction_at, row.transaction_type,
            )].append(row)
        facts: list[PendingFact] = []
        for (business_id, order_id, offer_id, event_at, transaction_type), parts in grouped.items():
            account_id = str(business_id)
            event_date = event_at.date()
            event_type = "return" if transaction_type == "Возврат" else "sale"
            raw_quantity = max(abs(int(part.quantity or 0)) for part in parts)
            if raw_quantity == 0:
                continue
            quantity = -raw_quantity if event_type == "return" else raw_quantity
            amount = sum((_decimal(part.amount) for part in parts), Decimal("0"))
            unit_price = abs(amount / raw_quantity)
            offer = offers.get((account_id, str(offer_id)))
            external_product_id = str(offer_id)
            link = links.get(("yandex_market", account_id, external_product_id))
            operation_key = (
                f"{business_id}:{order_id}:{offer_id}:{event_at.isoformat()}:{transaction_type}"
            )
            event_key = hashlib.sha256(operation_key.encode("utf-8")).hexdigest()
            hashes = sorted(_payload_hash(part.raw_data) for part in parts)
            payload_hash = _payload_hash(hashes)
            loaded_values = [part.fetched_at for part in parts if part.fetched_at]
            values = self._base_values(
                marketplace="yandex_market", account_id=account_id,
                event_type=event_type, quantity=quantity, amount=amount,
                unit_price=unit_price, source_event_key=event_key,
                source_table="yandex_market_finance_transactions",
                source_record_id=None, source_operation_key=operation_key,
                source_payload_hash=payload_hash, business_date=event_date,
                event_at=event_at,
                loaded_at=max(loaded_values) if loaded_values else None,
                normalized_at=now, currency="RUB",
            )
            values.update(self._link_values(link))
            values.update({
                "store_id": _as_string(next((
                    part.partner_id for part in parts if part.partner_id is not None
                ), None)),
                "seller_sku": str(offer_id),
                "marketplace_sku": _as_string(offer.market_sku if offer else None),
                "offer_id": str(offer_id),
                "order_id": _as_string(order_id),
                "operation_id": operation_key,
                "status": transaction_type,
                "marketplace_discount_exact": sum((
                    _decimal(part.amount) for part in parts
                    if "балл" in str(part.transaction_source or "").casefold()
                ), Decimal("0")),
                "customer_paid_exact": sum((
                    _decimal(part.amount) for part in parts
                    if "платеж" in str(part.transaction_source or "").casefold()
                    or "платёж" in str(part.transaction_source or "").casefold()
                ), Decimal("0")),
            })
            self._apply_cost(values, costs)
            sources = [SourceReference(
                "yandex_market_finance_transactions", str(part.id),
                _as_string(part.transaction_id), _payload_hash(part.raw_data),
            ) for part in parts]
            facts.append(PendingFact(values, sources))
        return facts, len(rows)

    @staticmethod
    def _assign_kopecks(facts: list[PendingFact]) -> None:
        for pending in facts:
            values = pending.values
            values["unit_price_kopecks"] = money_to_kopecks(values["unit_price_exact"])
            unit_cost = values.get("unit_cost_exact")
            values["unit_cost_kopecks"] = (
                money_to_kopecks(unit_cost) if unit_cost is not None else None
            )
            for exact_field, kopeck_field in MONEY_FIELDS:
                exact = values.get(exact_field)
                values[kopeck_field] = (
                    money_to_kopecks(exact) if exact is not None else None
                )

        groups: dict[tuple[Any, ...], list[PendingFact]] = defaultdict(list)
        for pending in facts:
            groups[(
                pending.values["account_id"],
                pending.values["business_date"],
                pending.values["currency"],
            )].append(pending)
        for rows in groups.values():
            for exact_field, kopeck_field in MONEY_FIELDS:
                FinancialSalesFactService._reconcile_kopecks(
                    rows, exact_field, kopeck_field
                )

    @staticmethod
    def _reconcile_kopecks(
        rows: list[PendingFact], exact_field: str, kopeck_field: str
    ) -> None:
        eligible = [row for row in rows if row.values.get(exact_field) is not None]
        if not eligible:
            return
        target = money_to_kopecks(sum(
            (_decimal(row.values[exact_field]) for row in eligible), Decimal("0")
        ))
        allocated = sum(int(row.values[kopeck_field]) for row in eligible)
        residual = target - allocated
        if residual == 0:
            return
        remainders = sorted(
            eligible,
            key=lambda row: (
                _decimal(row.values[exact_field]) * 100
                - Decimal(int(row.values[kopeck_field])),
                row.values["source_event_key"],
            ),
            reverse=residual > 0,
        )
        step = 1 if residual > 0 else -1
        for index in range(abs(residual)):
            row = remainders[index % len(remainders)]
            row.values[kopeck_field] += step

    def _sync_barcodes(
        self,
        session: Any,
        links: dict[tuple[str, str, str], MarketplaceProductLink],
        now: datetime,
    ) -> int:
        values: list[dict[str, Any]] = []
        if self.marketplace == "wb":
            rows = session.query(WBSizeBarcode, WBProductSize, WBProduct).join(
                WBProductSize, WBSizeBarcode.size_id == WBProductSize.id
            ).join(WBProduct, WBProductSize.product_id == WBProduct.id).all()
            for barcode, _, product in rows:
                link = links.get(("wb", "", str(product.nm_id)))
                if link and str(barcode.barcode).strip():
                    values.append(self._barcode_values(
                        link, str(barcode.barcode), False, "wb_size_barcodes",
                        str(barcode.id), None, now,
                    ))
        elif self.marketplace == "ozon":
            account_id = str(OZON_CLIENT_ID or "")
            for product in session.query(OzonProduct).all():
                link = links.get(("ozon", account_id, str(product.product_id)))
                if not link:
                    continue
                raw_barcodes = product.raw_data.get("barcodes") or []
                candidates: list[str] = []
                if product.barcode:
                    candidates.append(str(product.barcode))
                for item in raw_barcodes:
                    value = item.get("barcode") if isinstance(item, dict) else item
                    if value:
                        candidates.append(str(value))
                for barcode in dict.fromkeys(candidates):
                    values.append(self._barcode_values(
                        link, barcode, barcode == str(product.barcode),
                        "ozon_products", str(product.id), product.updated_at, now,
                    ))
        else:
            for offer in session.query(YandexMarketOffer).all():
                account_id = str(offer.business_id)
                link = links.get(("yandex_market", account_id, offer.offer_id))
                if not link:
                    continue
                for index, item in enumerate(offer.barcodes or []):
                    value = item.get("barcode") if isinstance(item, dict) else item
                    if value:
                        values.append(self._barcode_values(
                            link, str(value), index == 0, "yandex_market_offers",
                            str(offer.id), offer.fetched_at, now,
                        ))
        seen: dict[tuple[str, str], int] = {}
        for item in values:
            key = (item["account_id"], item["barcode"])
            if key in seen:
                if seen[key] != item["master_product_id"]:
                    raise ValueError(
                        f"barcode {item['barcode']} belongs to multiple "
                        f"{self.marketplace} products"
                    )
                continue
            seen[key] = item["master_product_id"]
            session.add(ProductBarcode(**item))
        return len(seen)

    def _barcode_values(
        self,
        link: MarketplaceProductLink,
        barcode: str,
        is_primary: bool,
        source_table: str,
        source_record_id: str,
        fetched_at: datetime | None,
        now: datetime,
    ) -> dict[str, Any]:
        return {
            "master_product_id": link.master_product_id,
            "marketplace_product_link_id": link.id,
            "marketplace": self.marketplace,
            "account_id": link.account_id,
            "external_product_id": link.external_product_id,
            "barcode": barcode.strip(),
            "barcode_type": "marketplace",
            "is_primary": is_primary,
            "active": True,
            "source_table": source_table,
            "source_record_id": source_record_id,
            "fetched_at": fetched_at,
            "normalized_at": now,
        }

    def _create_run(self, run_id: str) -> None:
        with self.session_factory() as session:
            session.add(AnalyticsFactSyncRun(
                id=run_id, marketplace=self.marketplace,
                started_at=datetime.now(timezone.utc), status="running",
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
            row = session.get(AnalyticsFactSyncRun, run_id)
            if row is None:
                return
            row.finished_at = datetime.now(timezone.utc)
            row.status = status
            row.source_rows = result.get("source_rows", 0)
            row.facts_written = result.get("facts_written", 0)
            row.lineage_rows = result.get("lineage_rows", 0)
            row.barcode_rows = result.get("barcode_rows", 0)
            row.unmatched_products = result.get("unmatched_products", 0)
            row.error = error
            session.commit()

    def _acquire_lock(self, session: Any) -> bool:
        if session.get_bind().dialect.name != "postgresql":
            return True
        return bool(session.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": self.lock_id},
        ).scalar())

    def _release_lock(self, session: Any) -> None:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": self.lock_id},
            )
