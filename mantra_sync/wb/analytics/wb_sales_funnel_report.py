# wb_sales_funnel_report.py - только товары с активностью сегодня

import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from settings import Config
from bot import send_telegram_message


class WBSalesFunnelReporter:
    """Класс для сбора статистики воронки продаж WB"""

    WB_API_URL = "https://seller-analytics-api.wildberries.ru/api/analytics/v3/sales-funnel/products"

    def __init__(self, wb_api_key: str):
        self.wb_api_key = wb_api_key
        self.headers = {
            "Authorization": wb_api_key,
            "Content-Type": "application/json"
        }

    async def _fetch_stats_for_date(self, session: aiohttp.ClientSession, date_str: str,
                                    subject_ids: List[int] = None) -> List[Dict]:
        """Получает статистику за конкретную дату"""
        payload = {
            "selectedPeriod": {
                "start": date_str,
                "end": date_str
            },
            "skipDeletedNm": False,
            "limit": 1000,
            "offset": 0
        }

        if subject_ids:
            payload["subjectIds"] = subject_ids

        try:
            async with session.post(self.WB_API_URL, headers=self.headers, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", {}).get("products", [])
                else:
                    print(f"❌ Ошибка API WB за {date_str}: {response.status}")
                    return []
        except Exception as e:
            print(f"❌ Ошибка запроса за {date_str}: {e}")
            return []

    def _get_product_key(self, product: Dict) -> int:
        return product.get("product", {}).get("nmId")

    def _parse_product_stats(self, product: Dict) -> Dict:
        """Парсит статистику товара"""
        product_info = product.get("product", {})
        stats = product.get("statistic", {}).get("selected", {})

        return {
            "nm_id": product_info.get("nmId"),
            "title": product_info.get("title", "Без названия"),
            "brand_name": product_info.get("brandName", ""),
            "subject_name": product_info.get("subjectName", ""),
            "open_count": stats.get("openCount", 0),
            "cart_count": stats.get("cartCount", 0),
            "order_count": stats.get("orderCount", 0),
            "buyout_count": stats.get("buyoutCount", 0),
            "wishlist_count": stats.get("addToWishlist", 0),
        }

    def _has_any_metric(self, stats: Dict) -> bool:
        """Проверяет, есть ли хоть один ненулевой показатель"""
        return any([
            stats.get("open_count", 0) > 0,
            stats.get("cart_count", 0) > 0,
            stats.get("order_count", 0) > 0,
            stats.get("buyout_count", 0) > 0,
            stats.get("wishlist_count", 0) > 0
        ])

    def _format_product_line(self, today_stats: Dict) -> Optional[str]:
        """Форматирует строку товара - только сегодняшние показатели"""

        # Собираем только ненулевые показатели за сегодня
        metrics = []

        if today_stats["open_count"] > 0:
            metrics.append(f"👁️{today_stats['open_count']}")
        if today_stats["cart_count"] > 0:
            metrics.append(f"🛒{today_stats['cart_count']}")
        if today_stats["order_count"] > 0:
            metrics.append(f"📦{today_stats['order_count']}")
        if today_stats["buyout_count"] > 0:
            metrics.append(f"✅{today_stats['buyout_count']}")
        if today_stats["wishlist_count"] > 0:
            metrics.append(f"⭐{today_stats['wishlist_count']}")

        # Если сегодня нет активности - пропускаем
        if not metrics:
            return None

        # Название товара
        title = f"{today_stats['brand_name']} {today_stats['title']}"[:45]
        metrics_str = " ".join(metrics)

        return f"• {title} → {metrics_str}"


def send_wb_sales_funnel_report(subject_ids: List[int] = None, category_name: str = "товаров") -> bool:
    """
    Отправка отчёта по воронке продаж (только товары с активностью сегодня)
    """

    async def _async_send():
        reporter = WBSalesFunnelReporter(Config.API_KEY_WB_RO_ALL)

        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        today_str = today.strftime("%Y-%m-%d")
        yesterday_str = yesterday.strftime("%Y-%m-%d")

        print(f"📊 Формируем отчёт WB: {category_name}")
        print(f"   Сегодня: {today_str}")
        print(f"   Вчера: {yesterday_str}")

        async with aiohttp.ClientSession() as session:
            # Получаем данные за оба дня
            today_products, yesterday_products = await asyncio.gather(
                reporter._fetch_stats_for_date(session, today_str, subject_ids),
                reporter._fetch_stats_for_date(session, yesterday_str, subject_ids)
            )

            # Создаём словари по nmId
            today_dict = {}
            for p in today_products:
                stats = reporter._parse_product_stats(p)
                if reporter._has_any_metric(stats):
                    today_dict[stats["nm_id"]] = stats

            yesterday_dict = {}
            for p in yesterday_products:
                stats = reporter._parse_product_stats(p)
                yesterday_dict[stats["nm_id"]] = stats

            # Берём ТОЛЬКО товары, у которых есть активность СЕГОДНЯ
            active_today_ids = set(today_dict.keys())

            if not active_today_ids:
                send_telegram_message(
                    f"ℹ️ За сегодня ({today_str}) нет активности по {category_name}",
                    chat_id=Config.GROUP_MANTRA_ID
                )
                return True

            # Формируем список товаров (только с активностью сегодня)
            products_list = []
            for nm_id in active_today_ids:
                today_stats = today_dict.get(nm_id)
                yesterday_stats = yesterday_dict.get(nm_id, {
                    "open_count": 0, "cart_count": 0, "order_count": 0,
                    "buyout_count": 0, "wishlist_count": 0
                })

                products_list.append({
                    "nm_id": nm_id,
                    "title": today_stats["title"],
                    "brand_name": today_stats["brand_name"],
                    "today": today_stats,
                    "yesterday": yesterday_stats
                })

            # Сортируем по просмотрам сегодня
            products_list.sort(key=lambda x: x["today"]["open_count"], reverse=True)

            # Общая статистика за сегодня
            today_total = {
                "open": sum(p["today"]["open_count"] for p in products_list),
                "cart": sum(p["today"]["cart_count"] for p in products_list),
                "order": sum(p["today"]["order_count"] for p in products_list),
                "buyout": sum(p["today"]["buyout_count"] for p in products_list),
                "wishlist": sum(p["today"]["wishlist_count"] for p in products_list),
            }

            # Общая статистика за вчера (только по тем товарам, которые активны сегодня)
            yesterday_total = {
                "open": sum(p["yesterday"]["open_count"] for p in products_list),
                "cart": sum(p["yesterday"]["cart_count"] for p in products_list),
                "order": sum(p["yesterday"]["order_count"] for p in products_list),
                "buyout": sum(p["yesterday"]["buyout_count"] for p in products_list),
                "wishlist": sum(p["yesterday"]["wishlist_count"] for p in products_list),
            }

            # Формируем заголовок
            header = f"""📊 <b>ОТЧЁТ WB: {category_name}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📅 СЕГОДНЯ</b> ({today_str})  |  <b>ВЧЕРА</b> ({yesterday_str})
━━━━━━━━━━━━━━━━━━━━━━━━━━
👁️ <b>Просмотры:</b>   {today_total['open']:>6}  |  {yesterday_total['open']:>6}
🛒 <b>Корзина:</b>     {today_total['cart']:>6}  |  {yesterday_total['cart']:>6}
📦 <b>Заказы:</b>      {today_total['order']:>6}  |  {yesterday_total['order']:>6}
✅ <b>Выкупы:</b>      {today_total['buyout']:>6}  |  {yesterday_total['buyout']:>6}
⭐ <b>Избранное:</b>   {today_total['wishlist']:>6}  |  {yesterday_total['wishlist']:>6}
━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 <b>Активные товары сегодня:</b> {len(products_list)} шт.
"""

            send_telegram_message(header, chat_id=Config.GROUP_MANTRA_ID, parse_mode="HTML")

            # Формируем строки товаров (только сегодняшние показатели)
            product_lines = []
            for p in products_list[:15]:
                line = reporter._format_product_line(p["today"])
                if line:
                    product_lines.append(line)

            # Отправляем порциями по 7 товаров
            batch_size = 7
            for i in range(0, len(product_lines), batch_size):
                batch = product_lines[i:i + batch_size]
                message = "\n".join(batch)
                send_telegram_message(message, chat_id=Config.GROUP_MANTRA_ID, parse_mode=None)

                if i + batch_size < len(product_lines):
                    await asyncio.sleep(1.5)

            print(f"✅ Отчёт WB отправлен: {len(products_list)} товаров")
            return True

    try:
        return asyncio.run(_async_send())
    except Exception as e:
        error_msg = f"❌ Ошибка при отправке отчёта WB: {e}"
        print(error_msg)
        send_telegram_message(error_msg, chat_id=Config.GROUP_MANTRA_ID)
        return False


def wb_chandeliers_report_job():
    """Отчёт по люстрам (subjectId = 1158)"""
    return send_wb_sales_funnel_report(subject_ids=[1158], category_name="ЛЮСТРЫ")


def wb_sales_funnel_job():
    """Job для шедулера"""
    from main import run_with_retry, notify

    notify(f"📊 Запуск отчёта WB по люстрам", "WB")
    return run_with_retry(wb_chandeliers_report_job, "Отчёт WB по люстрам")

