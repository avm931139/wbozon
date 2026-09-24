from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

from sqlalchemy import delete, func

from app.config import OZON_CLIENT_ID
from app.models import (
    FactAdvertisingDaily,
    FactProductEconomicsControl,
    FactProductEconomicsDaily,
    MarketplaceProductLink,
    MasterProduct,
    OzonAdDailyStat,
    OzonFinanceAccrual,
    OzonFinanceAccrualType,
    OzonProduct,
    WBAdvertDailyStat,
    WBAdvertProductDailyStat,
    WBFinancialSalesReport,
    WBFinancialSalesRow,
    YandexMarketAdDailyStat,
    YandexMarketFinanceTransaction,
)


CALCULATION_VERSION = "product-economics-v1"
WB_SALES = {"Продажа", "Бронирование товара через самовывоз"}
WB_RETURNS = {"Возврат"}


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _kopecks(value: Any) -> int:
    return int((_decimal(value) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def allocate_kopecks(total: int, weights: dict[str, int]) -> dict[str, int]:
    positive = {key: max(int(value), 0) for key, value in weights.items()}
    denominator = sum(positive.values())
    if not denominator:
        return {key: 0 for key in weights}
    sign = -1 if total < 0 else 1
    absolute = abs(int(total))
    result: dict[str, int] = {}
    remainders: list[tuple[int, str]] = []
    for key, weight in positive.items():
        value, remainder = divmod(absolute * weight, denominator)
        result[key] = value * sign
        remainders.append((remainder, key))
    residual = absolute - sum(abs(value) for value in result.values())
    for _, key in sorted(remainders, key=lambda item: (-item[0], item[1]))[:residual]:
        result[key] += sign
    return result


def allocate_ozon_advertising(
    total: int,
    weights: dict[str, int],
    direct: dict[str, int],
    preallocated: dict[str, int] | None = None,
) -> tuple[dict[str, int], int, str]:
    """Keep SKU-level spend and allocate only campaign-level spend by revenue."""
    preallocated = preallocated or {}
    advertising = {
        key: int(direct.get(key, 0)) + int(preallocated.get(key, 0))
        for key in weights
    }
    direct_total = sum(int(direct.get(key, 0)) for key in weights)
    preallocated_total = sum(int(preallocated.get(key, 0)) for key in weights)
    unmatched = int(direct.get("unallocated", 0)) + int(
        preallocated.get("unallocated", 0)
    )
    residual = int(total) - direct_total - preallocated_total - unmatched
    allocated = allocate_kopecks(residual, weights)
    for key, value in allocated.items():
        advertising[key] += value
    unallocated = int(total) - sum(advertising.values())
    if preallocated_total and residual:
        method = "product_weight_plus_revenue"
    elif preallocated_total and direct_total:
        method = "direct_plus_product_weight"
    elif preallocated_total:
        method = "allocated_by_product_weight"
    elif direct_total and residual:
        method = "direct_plus_revenue"
    elif direct_total:
        method = "direct_product_report"
    else:
        method = "allocated_by_revenue"
    return advertising, unallocated, method


def _dates(first: date, last: date) -> Iterable[date]:
    current = first
    while current <= last:
        yield current
        current += timedelta(days=1)


def _is_logistics(label: str) -> bool:
    value = label.casefold()
    return any(pattern in value for pattern in (
        "логист", "достав", "delivery", "перевоз", "crossdock", "кросс-док",
        "возврат", "return", "обратн",
    ))


def _nested_fees(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if "type_id" in value and "accrued" in value:
            yield value
        for child in value.values():
            yield from _nested_fees(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nested_fees(child)


class ProductEconomicsBuilder:
    """Persist daily SKU economics; dashboard code reads only these facts."""

    def __init__(self, marketplace: str) -> None:
        self.marketplace = marketplace

    @staticmethod
    def _product_key(values: dict[str, Any]) -> str:
        master_id = values.get("master_product_id")
        if master_id is not None:
            return f"m:{master_id}"
        source = values.get("seller_sku") or values.get("offer_id") or values.get("marketplace_sku") or "unmatched"
        return f"source:{source}"

    def _base_rows(self, pending_values: list[dict[str, Any]]) -> dict[tuple[str, date, str], dict[str, Any]]:
        grouped: dict[tuple[str, date, str], dict[str, Any]] = {}
        for values in pending_values:
            account = str(values.get("account_id") or "")
            business_date = values["business_date"]
            product_key = self._product_key(values)
            key = (account, business_date, product_key)
            row = grouped.setdefault(key, {
                "account_id": account, "business_date": business_date,
                "product_key": product_key,
                "master_product_id": values.get("master_product_id"),
                "seller_sku": values.get("seller_sku") or values.get("offer_id") or values.get("marketplace_sku"),
                "product_name": values.get("seller_sku") or values.get("offer_id") or values.get("marketplace_sku"),
                "quantity": 0, "sales_revenue_kopecks": 0, "cost_kopecks": 0,
                "missing_cost_rows": 0,
            })
            row["quantity"] += int(values.get("quantity") or 0)
            row["sales_revenue_kopecks"] += int(values.get("net_revenue_kopecks") or 0)
            row["cost_kopecks"] += int(values.get("cost_amount_kopecks") or 0)
            row["missing_cost_rows"] += values.get("cost_status") != "matched"
        return grouped

    def _targets(self, session: Any, base: dict[tuple[str, date, str], dict[str, Any]]) -> dict[tuple[str, date], dict[str, int]]:
        raw_by_day: dict[tuple[str, date], dict[str, int]] = defaultdict(lambda: {"revenue": 0, "cost": 0})
        for (account, business_date, _), row in base.items():
            raw_by_day[(account, business_date)]["revenue"] += row["sales_revenue_kopecks"]
            raw_by_day[(account, business_date)]["cost"] += row["cost_kopecks"]
        targets: dict[tuple[str, date], dict[str, int]] = defaultdict(
            lambda: {"revenue": 0, "expense": 0, "logistics": 0, "cost": 0}
        )
        if self.marketplace == "wb":
            reports = session.query(WBFinancialSalesReport).filter(
                WBFinancialSalesReport.details_synced_at.isnot(None)
            ).all()
            for report in reports:
                for day in _dates(report.date_from.date(), report.date_to.date()):
                    targets[("", day)]
            aggregates: dict[date, dict[str, Decimal]] = defaultdict(
                lambda: {"revenue": Decimal("0"), "net": Decimal("0"), "logistics": Decimal("0")}
            )
            for row in session.query(WBFinancialSalesRow).filter(WBFinancialSalesRow.rr_date.isnot(None)):
                day = row.rr_date.date()
                values = aggregates[day]
                quantity = _decimal(row.quantity)
                retail = _decimal(row.retail_price_with_discount) * quantity
                for_pay = _decimal(row.for_pay)
                additional = _decimal(row.additional_payment)
                operation = row.seller_operation_name
                if operation in WB_SALES:
                    values["revenue"] += retail
                    values["net"] += for_pay
                elif operation in WB_RETURNS:
                    values["revenue"] -= retail
                    values["net"] -= for_pay
                else:
                    values["revenue"] += for_pay
                    values["net"] += for_pay
                values["revenue"] += additional
                values["net"] += additional - sum((_decimal(item) for item in (
                    row.delivery_service, row.penalty, row.paid_storage,
                    row.paid_acceptance, row.deduction,
                    (row.raw_data or {}).get("paymentSchedule"),
                )), Decimal("0"))
                values["logistics"] += _decimal(row.delivery_service)
            for day, values in aggregates.items():
                target = targets[("", day)]
                target["revenue"] = _kopecks(values["revenue"])
                target["expense"] = _kopecks(values["revenue"] - values["net"])
                target["logistics"] = _kopecks(values["logistics"])
        elif self.marketplace == "ozon":
            account = str(OZON_CLIENT_ID or "")
            accruals = session.query(OzonFinanceAccrual).all()
            if accruals:
                for day in _dates(min(row.accrual_date for row in accruals), max(row.accrual_date for row in accruals)):
                    targets[(account, day)]
            type_names = {
                row.type_id: f"{row.name or ''} {row.description or ''}"
                for row in session.query(OzonFinanceAccrualType).all()
            }
            net: dict[date, Decimal] = defaultdict(Decimal)
            compensation: dict[date, Decimal] = defaultdict(Decimal)
            logistics: dict[date, Decimal] = defaultdict(Decimal)
            for row in accruals:
                net[row.accrual_date] += _decimal(row.amount)
                if row.accrual_type == "NON_ITEM" and _decimal(row.amount) > 0:
                    compensation[row.accrual_date] += _decimal(row.amount)
                for fee in _nested_fees(row.raw_data):
                    label = type_names.get(int(fee.get("type_id") or 0), "")
                    if _is_logistics(label):
                        accrued = fee.get("accrued") or {}
                        logistics[row.accrual_date] += _decimal(accrued.get("amount"))
            for key, target in targets.items():
                _, day = key
                raw = raw_by_day[key]["revenue"]
                target["revenue"] = raw + _kopecks(compensation[day])
                target["expense"] = target["revenue"] - _kopecks(net[day])
                target["logistics"] = max(-_kopecks(logistics[day]), 0)
        else:
            transactions = session.query(YandexMarketFinanceTransaction).all()
            by_account: dict[str, list[YandexMarketFinanceTransaction]] = defaultdict(list)
            for row in transactions:
                by_account[str(row.business_id)].append(row)
            for account, account_rows in by_account.items():
                first = min(row.transaction_at.date() for row in account_rows)
                last = max(row.transaction_at.date() for row in account_rows)
                for day in _dates(first, last):
                    targets[(account, day)]
            services: dict[tuple[str, date], Decimal] = defaultdict(Decimal)
            logistics: dict[tuple[str, date], Decimal] = defaultdict(Decimal)
            for row in transactions:
                key = (str(row.business_id), row.transaction_at.date())
                is_product = row.transaction_type in {"Начисление", "Возврат"} and int(row.quantity or 0) > 0
                if not is_product:
                    services[key] += _decimal(row.amount)
                    if _is_logistics(f"{row.product_or_service or ''} {row.transaction_source or ''}"):
                        logistics[key] += _decimal(row.amount)
            for key, target in targets.items():
                target["revenue"] = raw_by_day[key]["revenue"]
                target["expense"] = max(-_kopecks(services[key]), 0)
                target["logistics"] = max(-_kopecks(logistics[key]), 0)
        for key, target in targets.items():
            target["cost"] = raw_by_day[key]["cost"]
        return targets

    def _advertising(
        self,
        session: Any,
        links: dict[tuple[str, str, str], MarketplaceProductLink],
    ) -> tuple[
        dict[tuple[str, date], int],
        dict[tuple[str, date, str], int],
        dict[tuple[str, date, str], dict[str, Any]],
        dict[tuple[str, date, str], int],
    ]:
        totals: dict[tuple[str, date], int] = defaultdict(int)
        products: dict[tuple[str, date, str], int] = defaultdict(int)
        details: dict[tuple[str, date, str], dict[str, Any]] = defaultdict(
            lambda: {
                "views": 0, "clicks": 0, "orders": 0,
                "attributed_revenue_kopecks": 0,
                "seller_sku": None, "marketplace_sku": None,
            }
        )
        preallocated: dict[tuple[str, date, str], int] = defaultdict(int)
        if self.marketplace == "wb":
            daily_query = session.query(
                func.date(WBAdvertDailyStat.stat_date),
                func.sum(WBAdvertDailyStat.spend),
            ).group_by(func.date(WBAdvertDailyStat.stat_date)).yield_per(1000)
            for stat_date, spend in daily_query:
                business_date = (
                    stat_date if isinstance(stat_date, date)
                    else date.fromisoformat(str(stat_date))
                )
                totals[("", business_date)] += _kopecks(spend)
            product_query = session.query(
                func.date(WBAdvertDailyStat.stat_date),
                WBAdvertProductDailyStat.nm_id,
                func.sum(WBAdvertProductDailyStat.views),
                func.sum(WBAdvertProductDailyStat.clicks),
                func.sum(WBAdvertProductDailyStat.orders),
                func.sum(WBAdvertProductDailyStat.spend),
                func.sum(WBAdvertProductDailyStat.order_sum),
            ).join(
                WBAdvertDailyStat,
                WBAdvertDailyStat.id == WBAdvertProductDailyStat.daily_stat_id,
            ).group_by(
                func.date(WBAdvertDailyStat.stat_date),
                WBAdvertProductDailyStat.nm_id,
            ).yield_per(2000)
            for (
                stat_date, nm_id, views, clicks, orders, spend, order_sum
            ) in product_query:
                business_date = (
                    stat_date if isinstance(stat_date, date)
                    else date.fromisoformat(str(stat_date))
                )
                link = links.get(("wb", "", str(nm_id)))
                key = f"m:{link.master_product_id}" if link else "unallocated"
                products[("", business_date, key)] += _kopecks(spend)
                detail = details[("", business_date, key)]
                detail["views"] += int(views or 0)
                detail["clicks"] += int(clicks or 0)
                detail["orders"] += int(orders or 0)
                detail["attributed_revenue_kopecks"] += _kopecks(order_sum)
                detail["seller_sku"] = link.offer_id if link else None
                detail["marketplace_sku"] = str(nm_id)
        elif self.marketplace == "ozon":
            account = str(OZON_CLIENT_ID or "")
            sku_product = {str(row.sku): row for row in session.query(OzonProduct).filter(OzonProduct.sku.isnot(None))}
            for row in session.query(OzonAdDailyStat).all():
                if int(row.sku or 0) == 0:
                    totals[(account, row.stat_date)] += _kopecks(row.spend)
                    continue
                product = sku_product.get(str(row.sku))
                link = links.get(("ozon", account, str(product.product_id))) if product else None
                key = f"m:{link.master_product_id}" if link else "unallocated"
                products[(account, row.stat_date, key)] += _kopecks(row.spend)
                detail = details[(account, row.stat_date, key)]
                detail["views"] += int(row.views or 0)
                detail["clicks"] += int(row.clicks or 0)
                detail["orders"] += int(row.orders or 0)
                detail["attributed_revenue_kopecks"] += _kopecks(row.orders_money)
                detail["seller_sku"] = product.offer_id if product else None
                detail["marketplace_sku"] = str(row.sku)
            product_day_totals: dict[tuple[str, date], int] = defaultdict(int)
            for (row_account, day, _), spend in products.items():
                product_day_totals[(row_account, day)] += spend
            for day_key, spend in product_day_totals.items():
                if day_key not in totals:
                    totals[day_key] = spend
        else:
            source_totals: dict[tuple[str, date, str], int] = defaultdict(int)
            source_weights: dict[tuple[str, date, str, str], int] = defaultdict(int)
            for row in session.query(YandexMarketAdDailyStat).all():
                account = str(row.business_id)
                totals[(account, row.stat_date)] += _kopecks(row.spend)
                source_totals[(account, row.stat_date, row.source)] += _kopecks(row.spend)
                if not row.offer_id and row.source == "sales_boost":
                    for item in (row.raw_data or {}).get("rows") or []:
                        offer_id = str(item.get("shopSku") or "")
                        if not offer_id:
                            continue
                        link = links.get(("yandex_market", account, offer_id))
                        key = f"m:{link.master_product_id}" if link else "unallocated"
                        products[(account, row.stat_date, key)] += _kopecks(
                            item.get("billedAmount")
                        )
                        detail = details[(account, row.stat_date, key)]
                        detail["views"] += int(item.get("showsWithFee") or 0)
                        detail["clicks"] += int(item.get("clicksVendorWithFee") or 0)
                        detail["orders"] += int(item.get("orderItemsDeliveredWithFee") or 0)
                        detail["attributed_revenue_kopecks"] += _kopecks(
                            item.get("ordersGvmDeliveredWithFee")
                        )
                        detail["seller_sku"] = offer_id
                        detail["marketplace_sku"] = offer_id
                    continue
                if not row.offer_id:
                    continue
                link = links.get(("yandex_market", account, str(row.offer_id)))
                key = f"m:{link.master_product_id}" if link else "unallocated"
                if row.source == "shows_boost":
                    calculated_cost = sum(
                        _kopecks(item.get("cost"))
                        for item in (row.raw_data or {}).get("rows") or []
                    )
                    source_weights[(account, row.stat_date, row.source, key)] += calculated_cost
                    detail = details[(account, row.stat_date, key)]
                    detail["views"] += int(row.views or 0)
                    detail["clicks"] += int(row.clicks or 0)
                    detail["orders"] += int(row.orders or 0)
                    detail["attributed_revenue_kopecks"] += _kopecks(row.attributed_revenue)
                    detail["seller_sku"] = str(row.offer_id)
                    detail["marketplace_sku"] = str(row.offer_id)
                    continue
                products[(account, row.stat_date, key)] += _kopecks(row.spend)
                detail = details[(account, row.stat_date, key)]
                detail["views"] += int(row.views or 0)
                detail["clicks"] += int(row.clicks or 0)
                detail["orders"] += int(row.orders or 0)
                detail["attributed_revenue_kopecks"] += _kopecks(row.attributed_revenue)
                detail["seller_sku"] = str(row.offer_id)
                detail["marketplace_sku"] = str(row.offer_id)
            source_days = {(account, day, source) for account, day, source, _ in source_weights}
            for account, day, source in source_days:
                weights = {
                    key: value
                    for (row_account, row_day, row_source, key), value in source_weights.items()
                    if (row_account, row_day, row_source) == (account, day, source)
                }
                allocated = allocate_kopecks(source_totals[(account, day, source)], weights)
                for key, value in allocated.items():
                    preallocated[(account, day, key)] += value
        return totals, products, details, preallocated

    def build(
        self,
        session: Any,
        pending_values: list[dict[str, Any]],
        links: dict[tuple[str, str, str], MarketplaceProductLink],
        normalized_at: Any,
    ) -> tuple[int, int]:
        base = self._base_rows(pending_values)
        targets = self._targets(session, base)
        ad_totals, direct_ads, ad_details, preallocated_ads = self._advertising(
            session, links
        )
        session.execute(delete(FactProductEconomicsDaily).where(
            FactProductEconomicsDaily.marketplace == self.marketplace
        ))
        session.execute(delete(FactProductEconomicsControl).where(
            FactProductEconomicsControl.marketplace == self.marketplace
        ))
        session.execute(delete(FactAdvertisingDaily).where(
            FactAdvertisingDaily.marketplace == self.marketplace
        ))
        base_by_day: dict[tuple[str, date], dict[str, dict[str, Any]]] = defaultdict(dict)
        for (account, day, key), row in base.items():
            base_by_day[(account, day)][key] = row
        direct_keys_by_day: dict[tuple[str, date], set[str]] = defaultdict(set)
        for account, day, key in direct_ads:
            direct_keys_by_day[(account, day)].add(key)
        preallocated_keys_by_day: dict[tuple[str, date], set[str]] = defaultdict(set)
        for account, day, key in preallocated_ads:
            preallocated_keys_by_day[(account, day)].add(key)
        day_keys = set(targets) | set(ad_totals) | {(account, day) for account, day, _ in base}
        economics_count = 0
        for day_number, (account, business_date) in enumerate(sorted(day_keys), start=1):
            day_rows = {
                key: dict(row)
                for key, row in base_by_day.get((account, business_date), {}).items()
            }
            for key in direct_keys_by_day.get((account, business_date), set()):
                if key != "unallocated":
                    day_rows.setdefault(key, {
                        "account_id": account, "business_date": business_date,
                        "product_key": key,
                        "master_product_id": int(key[2:]) if key.startswith("m:") else None,
                        "seller_sku": None, "product_name": None, "quantity": 0,
                        "sales_revenue_kopecks": 0, "cost_kopecks": 0,
                        "missing_cost_rows": 0,
                    })
            for key in preallocated_keys_by_day.get((account, business_date), set()):
                if key != "unallocated":
                    day_rows.setdefault(key, {
                        "account_id": account, "business_date": business_date,
                        "product_key": key,
                        "master_product_id": int(key[2:]) if key.startswith("m:") else None,
                        "seller_sku": None, "product_name": None, "quantity": 0,
                        "sales_revenue_kopecks": 0, "cost_kopecks": 0,
                        "missing_cost_rows": 0,
                    })
            target = targets.get((account, business_date), {
                "revenue": sum(row["sales_revenue_kopecks"] for row in day_rows.values()),
                "expense": 0, "logistics": 0,
                "cost": sum(row["cost_kopecks"] for row in day_rows.values()),
            })
            weights = {key: max(int(row["sales_revenue_kopecks"]), 0) for key, row in day_rows.items()}
            if not sum(weights.values()):
                weights = {key: abs(int(row["sales_revenue_kopecks"])) for key, row in day_rows.items()}
            raw_revenue = sum(int(row["sales_revenue_kopecks"]) for row in day_rows.values())
            compensation = allocate_kopecks(int(target["revenue"]) - raw_revenue, weights)
            expenses = allocate_kopecks(int(target["expense"]), weights)
            logistics = allocate_kopecks(int(target["logistics"]), weights)
            if self.marketplace in {"ozon", "yandex_market"}:
                advertising, ad_unallocated, ad_method = allocate_ozon_advertising(
                    ad_totals.get((account, business_date), 0),
                    weights,
                    {
                        key: direct_ads.get((account, business_date, key), 0)
                        for key in day_rows
                    } | {
                        "unallocated": direct_ads.get(
                            (account, business_date, "unallocated"), 0
                        )
                    },
                    {
                        key: preallocated_ads.get((account, business_date, key), 0)
                        for key in day_rows
                    } | {
                        "unallocated": preallocated_ads.get(
                            (account, business_date, "unallocated"), 0
                        )
                    },
                )
            else:
                advertising = {
                    key: direct_ads.get((account, business_date, key), 0)
                    for key in day_rows
                }
                direct_unallocated = direct_ads.get(
                    (account, business_date, "unallocated"), 0
                )
                total_advertising = ad_totals.get((account, business_date), 0)
                residual = total_advertising - sum(advertising.values()) - direct_unallocated
                ad_unallocated = direct_unallocated + residual
                ad_method = "direct_product_report"
                if residual < 0 and (advertising or direct_unallocated):
                    reconciliation_weights = dict(advertising)
                    if direct_unallocated:
                        reconciliation_weights["unallocated"] = direct_unallocated
                    corrections = allocate_kopecks(residual, reconciliation_weights)
                    for key in advertising:
                        advertising[key] += corrections.get(key, 0)
                    ad_unallocated = direct_unallocated + corrections.get("unallocated", 0)
                    ad_method = "direct_reconciled"
            needs_unallocated = not day_rows and any((
                target["revenue"], target["expense"], target["logistics"],
                ad_totals.get((account, business_date), 0),
            ))
            if needs_unallocated or ad_unallocated:
                day_rows.setdefault("unallocated", {
                    "account_id": account, "business_date": business_date,
                    "product_key": "unallocated", "master_product_id": None,
                    "seller_sku": "НЕРАСПРЕДЕЛЕНО", "product_name": "Нераспределённые финансовые операции",
                    "quantity": 0, "sales_revenue_kopecks": 0, "cost_kopecks": 0,
                    "missing_cost_rows": 0,
                })
                if not weights:
                    compensation["unallocated"] = int(target["revenue"])
                    expenses["unallocated"] = int(target["expense"])
                    logistics["unallocated"] = int(target["logistics"])
                advertising["unallocated"] = advertising.get("unallocated", 0) + ad_unallocated
            for key, row in day_rows.items():
                revenue = int(row["sales_revenue_kopecks"]) + compensation.get(key, 0)
                expense = expenses.get(key, 0)
                cost = int(row["cost_kopecks"])
                session.add(FactProductEconomicsDaily(
                    marketplace=self.marketplace, account_id=account,
                    business_date=business_date, product_key=key,
                    master_product_id=row.get("master_product_id"),
                    seller_sku=row.get("seller_sku"), product_name=row.get("product_name"),
                    is_unallocated=key == "unallocated", quantity=row["quantity"],
                    sales_revenue_kopecks=row["sales_revenue_kopecks"],
                    compensation_kopecks=compensation.get(key, 0),
                    revenue_kopecks=revenue,
                    marketplace_expense_kopecks=expense,
                    logistics_kopecks=logistics.get(key, 0),
                    advertising_kopecks=advertising.get(key, 0),
                    cost_kopecks=cost, profit_kopecks=revenue - expense - cost,
                    missing_cost_rows=row["missing_cost_rows"],
                    expense_allocation_method="allocated_by_revenue",
                    advertising_allocation_method=ad_method,
                    calculation_version=CALCULATION_VERSION,
                    normalized_at=normalized_at,
                ))
                detail = ad_details.get((account, business_date, key), {})
                ad_spend = advertising.get(key, 0)
                direct_ad_spend = direct_ads.get((account, business_date, key), 0)
                if ad_spend or any(int(detail.get(field) or 0) for field in (
                    "views", "clicks", "orders", "attributed_revenue_kopecks"
                )):
                    session.add(FactAdvertisingDaily(
                        marketplace=self.marketplace,
                        account_id=account,
                        business_date=business_date,
                        product_key=key,
                        master_product_id=row.get("master_product_id"),
                        seller_sku=detail.get("seller_sku") or row.get("seller_sku"),
                        marketplace_sku=detail.get("marketplace_sku"),
                        is_unallocated=key == "unallocated",
                        views=int(detail.get("views") or 0),
                        clicks=int(detail.get("clicks") or 0),
                        orders=int(detail.get("orders") or 0),
                        spend_kopecks=ad_spend,
                        direct_spend_kopecks=direct_ad_spend,
                        allocated_spend_kopecks=ad_spend - direct_ad_spend,
                        attributed_revenue_kopecks=int(
                            detail.get("attributed_revenue_kopecks") or 0
                        ),
                        allocation_method=ad_method,
                        calculation_version=CALCULATION_VERSION,
                        normalized_at=normalized_at,
                    ))
                economics_count += 1
            actual_revenue = sum(
                int(row["sales_revenue_kopecks"]) + compensation.get(key, 0)
                for key, row in day_rows.items()
            )
            actual_expense = sum(expenses.get(key, 0) for key in day_rows)
            actual_cost = sum(int(row["cost_kopecks"]) for row in day_rows.values())
            session.add(FactProductEconomicsControl(
                marketplace=self.marketplace, account_id=account,
                business_date=business_date, revenue_kopecks=actual_revenue,
                marketplace_expense_kopecks=actual_expense,
                logistics_kopecks=sum(logistics.get(key, 0) for key in day_rows),
                advertising_kopecks=ad_totals.get((account, business_date), 0),
                advertising_unallocated_kopecks=ad_unallocated,
                cost_kopecks=actual_cost,
                profit_kopecks=actual_revenue - actual_expense - actual_cost,
                product_rows=len(day_rows),
                unmatched_rows=sum(row.get("master_product_id") is None and key != "unallocated" for key, row in day_rows.items()),
                source_complete=(account, business_date) in targets,
                calculation_version=CALCULATION_VERSION,
                normalized_at=normalized_at,
            ))
            if day_number % 20 == 0:
                session.flush()
        return economics_count, len(day_keys)
