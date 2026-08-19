# matra_sync/utils/stock_report.py
from datetime import datetime, timedelta
from sqlalchemy import and_, func
from core.db.connection import get_db_session
from core.db.models import WbStock, OzonStockSeller, WbCard, OzonCard
from bot import send_telegram_message
from settings import Config


def get_stock_report_data():
    """
    Получает данные о количестве SKU с остатками за вчерашний день
    Возвращает статистику по FBO и FBS для WB и Ozon
    """
    # Вчерашний день
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today - timedelta(days=1)
    yesterday_end = today - timedelta(microseconds=1)

    with get_db_session() as db:
        stats = {
            'date': yesterday_start.strftime('%Y-%m-%d'),
            'wb': {
                'fbo': {'sku_count': 0, 'total_quantity': 0},
                'fbs': {'sku_count': 0, 'total_quantity': 0},
                'total': {'sku_count': 0, 'total_quantity': 0}
            },
            'ozon': {
                'fbo': {'sku_count': 0, 'total_quantity': 0},
                'fbs': {'sku_count': 0, 'total_quantity': 0},
                'total': {'sku_count': 0, 'total_quantity': 0}
            }
        }

        # ==================== WILDBERRIES ====================
        # FBO остатки
        wb_fbo = db.query(WbStock).filter(
            and_(
                WbStock.type_wharehouse == 'fbo',
                WbStock.updated_at >= yesterday_start,
                WbStock.updated_at <= yesterday_end,
                WbStock.pcs > 0
            )
        ).all()

        # Уникальные SKU для FBO
        wb_fbo_skus = set()
        wb_fbo_total = 0
        for stock in wb_fbo:
            wb_fbo_skus.add(stock.nm_id_wb)
            wb_fbo_total += stock.pcs

        stats['wb']['fbo']['sku_count'] = len(wb_fbo_skus)
        stats['wb']['fbo']['total_quantity'] = wb_fbo_total

        # FBS остатки
        wb_fbs = db.query(WbStock).filter(
            and_(
                WbStock.type_wharehouse == 'fbs',
                WbStock.updated_at >= yesterday_start,
                WbStock.updated_at <= yesterday_end,
                WbStock.pcs > 0
            )
        ).all()

        # Уникальные SKU для FBS
        wb_fbs_skus = set()
        wb_fbs_total = 0
        for stock in wb_fbs:
            wb_fbs_skus.add(stock.nm_id_wb)
            wb_fbs_total += stock.pcs

        stats['wb']['fbs']['sku_count'] = len(wb_fbs_skus)
        stats['wb']['fbs']['total_quantity'] = wb_fbs_total

        # Общее по WB
        all_wb_skus = wb_fbo_skus.union(wb_fbs_skus)
        stats['wb']['total']['sku_count'] = len(all_wb_skus)
        stats['wb']['total']['total_quantity'] = wb_fbo_total + wb_fbs_total

        # ==================== OZON ====================
        # Получаем остатки Ozon за вчера
        ozon_stocks = db.query(OzonStockSeller).filter(
            and_(
                OzonStockSeller.updated_at >= yesterday_start,
                OzonStockSeller.updated_at <= yesterday_end,
                OzonStockSeller.present > 0
            )
        ).all()

        # Разделяем по source (типу склада)
        ozon_fbo_skus = set()
        ozon_fbs_skus = set()
        ozon_fbo_total = 0
        ozon_fbs_total = 0

        for stock in ozon_stocks:
            if stock.source and stock.source.lower() == 'fbo':
                ozon_fbo_skus.add(stock.offer_id)
                ozon_fbo_total += stock.present
            elif stock.source and stock.source.lower() == 'fbs':
                ozon_fbs_skus.add(stock.offer_id)
                ozon_fbs_total += stock.present
            else:
                # Если source не указан, считаем как FBS (по умолчанию)
                ozon_fbs_skus.add(stock.offer_id)
                ozon_fbs_total += stock.present

        stats['ozon']['fbo']['sku_count'] = len(ozon_fbo_skus)
        stats['ozon']['fbo']['total_quantity'] = ozon_fbo_total
        stats['ozon']['fbs']['sku_count'] = len(ozon_fbs_skus)
        stats['ozon']['fbs']['total_quantity'] = ozon_fbs_total

        # Общее по Ozon
        all_ozon_skus = ozon_fbo_skus.union(ozon_fbs_skus)
        stats['ozon']['total']['sku_count'] = len(all_ozon_skus)
        stats['ozon']['total']['total_quantity'] = ozon_fbo_total + ozon_fbs_total

        return stats


def send_stock_report():
    """
    Отправляет отчет по остаткам в Telegram
    """
    stats = get_stock_report_data()

    # Формируем сообщение
    message = (
        f"📊 *Отчет по остаткам товаров*\n"
        f"📅 На вчера: {stats['date']}\n\n"
        f"*Wildberries*\n"
        f"  • FBO: {stats['wb']['fbo']['sku_count']} SKU ({stats['wb']['fbo']['total_quantity']:,} шт.)\n"
        f"  • FBS: {stats['wb']['fbs']['sku_count']} SKU ({stats['wb']['fbs']['total_quantity']:,} шт.)\n"
        f"  • Всего: {stats['wb']['total']['sku_count']} SKU ({stats['wb']['total']['total_quantity']:,} шт.)\n\n"
        f"*Ozon*\n"
        f"  • FBO: {stats['ozon']['fbo']['sku_count']} SKU ({stats['ozon']['fbo']['total_quantity']:,} шт.)\n"
        f"  • FBS: {stats['ozon']['fbs']['sku_count']} SKU ({stats['ozon']['fbs']['total_quantity']:,} шт.)\n"
        f"  • Всего: {stats['ozon']['total']['sku_count']} SKU ({stats['ozon']['total']['total_quantity']:,} шт.)\n\n"
        f"*ИТОГО:*\n"
        f"  • Всего SKU с остатками: {stats['wb']['total']['sku_count'] + stats['ozon']['total']['sku_count']}\n"
        f"  • Всего единиц товара: {(stats['wb']['total']['total_quantity'] + stats['ozon']['total']['total_quantity']):,} шт."
    )

    # Отправляем в Telegram
    send_telegram_message(message, parse_mode="Markdown")

    return stats


def send_stock_report_simple():
    """
    Отправляет сокращенный отчет (только количество SKU)
    """
    stats = get_stock_report_data()

    message = (
        f"📊 *Остатки товаров на {stats['date']}*\n\n"
        f"*WB:* FBO {stats['wb']['fbo']['sku_count']} | FBS {stats['wb']['fbs']['sku_count']} | Всего {stats['wb']['total']['sku_count']}\n"
        f"*Ozon:* FBO {stats['ozon']['fbo']['sku_count']} | FBS {stats['ozon']['fbs']['sku_count']} | Всего {stats['ozon']['total']['sku_count']}\n"
        f"*ИТОГО:* {stats['wb']['total']['sku_count'] + stats['ozon']['total']['sku_count']} SKU"
    )

    send_telegram_message(message, parse_mode="Markdown")
    return stats


# Функция для добавления в расписание
def stock_report_job():
    """
    Задача для отправки отчета по остаткам
    """
    from main import run_with_retry
    return run_with_retry(send_stock_report, "Отчет по остаткам товаров")

stock_report_job()