from __future__ import annotations

import calendar
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable

from app.config import (
    OZON_HISTORY_FROM,
    WB_ANALYTICS_BASE_URL,
    YANDEX_MARKET_CAMPAIGN_IDS,
    YANDEX_MARKET_HISTORY_FROM,
)
from app.models import (
    OzonFBOSupplyAct,
    OzonFBOSupplyActItem,
    OzonFBOSupplyDeclaredItem,
    OzonSupply,
    WBFbwSupply,
    WBFbwSupplyGood,
    WBProduct,
)
from ozon.client import OzonClient
from wb.client import WBClient
from wb.exceptions import WBRateLimitError
from yandex_market.client import YandexMarketClient
from yandex_market.exceptions import YandexMarketHTTPError


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def _month_chunks(start: date, end: date):
    cursor = start
    while cursor <= end:
        last = date(cursor.year, cursor.month, calendar.monthrange(cursor.year, cursor.month)[1])
        chunk_end = min(last, end)
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def wb_supplies(session: Any) -> list[dict[str, Any]]:
    products = {row.nm_id: row for row in session.query(WBProduct).all()}
    rows = session.query(WBFbwSupplyGood, WBFbwSupply).join(WBFbwSupply).order_by(
        WBFbwSupply.supply_date, WBFbwSupply.supply_wb_id, WBFbwSupplyGood.vendor_code
    ).all()
    return [{
        "Поставка": supply.supply_wb_id or f"preorder:{supply.preorder_wb_id}",
        "Статус": supply.status_id,
        "Создана": _iso(supply.create_date),
        "Дата отправки/поставки": _iso(supply.supply_date),
        "Фактическая приёмка": _iso(supply.fact_date),
        "Склад плановый": supply.warehouse_name,
        "Склад фактический": supply.actual_warehouse_name,
        "Артикул": item.vendor_code,
        "nmID/SKU": item.nm_id,
        "Баркод": item.barcode,
        "Наименование": (products.get(item.nm_id).title if products.get(item.nm_id) else None) or (item.raw_data or {}).get("subjectName") or (item.raw_data or {}).get("name"),
        "Размер": item.tech_size,
        "Отправлено, шт.": item.quantity,
        "Принято, шт.": item.accepted_quantity,
        "Готово к продаже, шт.": item.ready_for_sale_quantity,
        "На разгрузке, шт.": item.unloading_quantity,
        "Расхождение, шт.": (item.accepted_quantity or 0) - (item.quantity or 0),
        "Причина отклонения": supply.reject_reason,
        "Обновлено": _iso(supply.source_updated_date),
    } for item, supply in rows]


def wb_returns(session: Any, today: date, start_override: date | None = None) -> list[dict[str, Any]]:
    products = {row.nm_id: row for row in session.query(WBProduct).all()}
    client = WBClient(base_url=WB_ANALYTICS_BASE_URL)
    earliest = session.query(WBFbwSupply.create_date).order_by(WBFbwSupply.create_date).first()
    start = start_override or (earliest[0].date() if earliest and earliest[0] else date(today.year, 1, 1))
    result = []
    for chunk_start, chunk_end in _month_chunks(start, today):
        for attempt in range(3):
            try:
                payload = client.get("/api/v1/analytics/goods-return", params={"dateFrom": chunk_start.isoformat(), "dateTo": chunk_end.isoformat()})
                break
            except WBRateLimitError:
                if attempt == 2: raise
                time.sleep(65)
        for item in (payload.get("report", []) if isinstance(payload, dict) else []):
            product = products.get(item.get("nmId"))
            result.append({
                "Возврат/заказ": item.get("orderId") or item.get("srid"),
                "Тип": item.get("returnType"), "Статус": item.get("status"),
                "Заказан": item.get("orderDt"), "Готов к возврату": item.get("readyToReturnDt"),
                "Возвращён/завершён": item.get("completedDt"), "Срок возврата": item.get("expiredDt"),
                "Артикул": product.vendor_code if product else None,
                "nmID/SKU": item.get("nmId"), "Баркод": item.get("barcode"),
                "Наименование": (product.title if product else None) or item.get("subjectName"),
                "Размер": item.get("techSize"), "Количество, шт.": 1,
                "Причина": item.get("reason"), "Адрес возврата": item.get("dstOfficeAddress"),
                "Офис возврата": item.get("dstOfficeId"), "ШК единицы": item.get("shkId"),
            })
    return result


def ozon_supplies(session: Any) -> list[dict[str, Any]]:
    declared = session.query(OzonFBOSupplyDeclaredItem).all()
    supplies = {row.supply_order_id: row for row in session.query(OzonSupply).all()}
    acts = session.query(OzonFBOSupplyActItem, OzonFBOSupplyAct).outerjoin(
        OzonFBOSupplyAct, OzonFBOSupplyAct.act_id == OzonFBOSupplyActItem.act_id
    ).all()
    accepted: dict[tuple[int, int, int], dict[str, Any]] = {}
    for item, act in acts:
        key = (item.supply_order_id, item.supply_id, item.sku)
        data = accepted.setdefault(key, {"accepted": 0, "approved": 0, "defect": 0, "surplus": 0, "shortage": 0, "acts": set(), "dates": set()})
        kind = (item.act_type or "").upper()
        if kind == "ACCEPTANCE": data["accepted"] += item.fact_quantity or 0; data["approved"] += item.approved_quantity or 0
        elif kind == "DEFECT": data["defect"] += item.fact_quantity or 0
        elif kind == "SURPLUS": data["surplus"] += item.fact_quantity or 0
        elif kind == "SHORTCOMING": data["shortage"] += item.fact_quantity or 0
        if act:
            data["acts"].add(act.act_number or str(act.act_id))
            if act.act_created_date: data["dates"].add(act.act_created_date.isoformat())
    result = []
    for item in sorted(declared, key=lambda x: (x.supply_order_id, x.supply_id, x.sku)):
        data = accepted.get((item.supply_order_id, item.supply_id, item.sku), {})
        supply = supplies.get(item.supply_order_id)
        result.append({
            "Заявка": item.supply_order_id, "Поставка": item.supply_id, "Bundle": item.bundle_id,
            "Номер заявки": supply.supply_order_number if supply else None,
            "Статус": item.supply_state, "Создана": _iso(supply.created_at) if supply else None,
            "Дата отправки/поставки с": _iso(supply.supply_date_from) if supply else None,
            "Дата отправки/поставки по": _iso(supply.supply_date_to) if supply else None,
            "Дата фактической приёмки/акта": ", ".join(sorted(data.get("dates", set()))),
            "Акты": ", ".join(sorted(data.get("acts", set()))), "Склад": item.storage_warehouse_name,
            "Артикул": item.offer_id, "SKU": item.sku, "Product ID": item.product_id,
            "Баркод": item.barcode, "Наименование": item.name,
            "Отправлено, шт.": item.declared_quantity, "Принято, шт.": data.get("accepted", 0),
            "Согласовано, шт.": data.get("approved", 0), "Брак, шт.": data.get("defect", 0),
            "Излишек, шт.": data.get("surplus", 0), "Недостача, шт.": data.get("shortage", 0),
            "Расхождение, шт.": data.get("accepted", 0) - (item.declared_quantity or 0),
            "Тип отгрузки": item.shipment_type, "Зона размещения": item.placement_zone,
            "Обновлено": _iso(item.fetched_at),
        })
    return result


def ozon_returns(_session: Any, today: date) -> list[dict[str, Any]]:
    client = OzonClient(); start = date.fromisoformat(OZON_HISTORY_FROM); result = []
    for source, endpoint in (("Со склада FBO", "/v1/removal/from-stock/list"), ("Из поставки FBO", "/v1/removal/from-supply/list")):
        for chunk_start, chunk_end in _month_chunks(start, today):
            last_id = ""
            while True:
                payload = client.post(endpoint, json_body={"date_from": chunk_start.isoformat(), "date_to": chunk_end.isoformat(), "last_id": last_id, "limit": 500}) or {}
                rows = payload.get("returns_summary_report_rows") or []
                for item in rows:
                    result.append({
                        "Возврат": item.get("return_id"), "Источник": source, "Статус": item.get("return_state"),
                        "Создан": item.get("return_created_at"), "Выдан": item.get("given_out_date"),
                        "Доставка": item.get("delivery_date"), "Утилизация": item.get("utilization_date"),
                        "Артикул": item.get("offer_id"), "SKU": item.get("sku"), "Баркод": item.get("barcode"),
                        "Наименование": item.get("name"), "К возврату, шт.": item.get("quantity_for_return"),
                        "Фактически, шт.": item.get("quant_count"), "Тип стока": item.get("stock_type"),
                        "Автовозврат": item.get("is_auto_return"), "Склад комплектации": item.get("clearing_warehouse_name"),
                        "Склад назначения": item.get("destination_warehouse_name"), "Адрес назначения": item.get("destination_warehouse_address"),
                        "Тип доставки": item.get("delivery_type"), "Предв. стоимость": item.get("preliminary_delivery_price"),
                        "Короб": item.get("box_id"), "Статус короба": item.get("box_state"),
                    })
                next_id = payload.get("last_id") or ""
                if not rows or not next_id or next_id == last_id: break
                last_id = next_id
    return result


def yandex_movements(_session: Any, _today: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    client = YandexMarketClient(); start = date.fromisoformat(YANDEX_MARKET_HISTORY_FROM)
    supplies, returns, warnings = [], [], []
    campaigns = [int(value) for value in YANDEX_MARKET_CAMPAIGN_IDS]
    for campaign_id in campaigns:
        token = None
        while True:
            body = {"requestDateFrom": f"{start.isoformat()}T00:00:00Z", "sorting": {"direction": "ASC", "attribute": "ID"}}
            try:
                payload = client.post(f"/v2/campaigns/{campaign_id}/supply-requests", params={"pageToken": token} if token else None, json_body=body)
            except YandexMarketHTTPError as exc:
                if "CAMPAIGN_TYPE_NOT_SUPPORTED" in str(exc):
                    warnings.append(f"Кампания {campaign_id}: заявки поставок недоступны для этой модели (ожидается FBS)")
                    break
                raise
            section = payload.get("result") or {}
            for request in section.get("requests") or []:
                identity = request.get("id") or {}; request_id = identity.get("id")
                item_token = None
                while True:
                    item_payload = client.post(f"/v2/campaigns/{campaign_id}/supply-requests/items", params={"pageToken": item_token} if item_token else None, json_body={"requestId": request_id})
                    item_section = item_payload.get("result") or {}
                    for item in item_section.get("items") or []:
                        counters = item.get("counters") or {}; target = request.get("targetLocation") or {}; transit = request.get("transitLocation") or {}
                        row = {
                            "Заявка API": request_id, "Заявка кабинета": identity.get("marketplaceRequestId"),
                            "Заявка склада": identity.get("warehouseRequestId"), "Тип": request.get("type"),
                            "Подтип": request.get("subtype"), "Статус": request.get("status"),
                            "Дата отправки/поставки": target.get("requestedDate") or transit.get("requestedDate"),
                            "Склад": target.get("name"), "Транзитный склад": transit.get("name"),
                            "Артикул": item.get("offerId"), "Наименование": item.get("name"),
                            "Отправлено/план, шт.": counters.get("planCount"), "Принято/факт, шт.": counters.get("factCount"),
                            "Излишек, шт.": counters.get("surplusCount"), "Недостача, шт.": counters.get("shortageCount"),
                            "Брак, шт.": counters.get("defectCount"),
                            "Расхождение, шт.": (counters.get("factCount") or 0) - (counters.get("planCount") or 0),
                            "Обновлено": request.get("updatedAt"), "Кампания": campaign_id,
                        }
                        (supplies if request.get("type") == "SUPPLY" else returns).append(row)
                    new_item_token = (item_section.get("paging") or {}).get("nextPageToken")
                    if not new_item_token or new_item_token == item_token: break
                    item_token = new_item_token
            new_token = (section.get("paging") or {}).get("nextPageToken")
            if not new_token or new_token == token: break
            token = new_token
    return supplies, returns, warnings
