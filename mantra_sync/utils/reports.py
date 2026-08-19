# matra_sync/utils/reports.py
from datetime import datetime, timedelta
from sqlalchemy import func
from core.db.connection import get_db_session
from core.db.models import WbCard, OzonCard
from bot import send_telegram_message
from settings import Config


def get_new_products_stats(period_days: int = None):
    """
    Получает статистику по новым товарам за вчерашний день
    :param period_days: если указан, возвращает за N дней до вчера
    """
    # Вчерашний день (начало и конец)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today - timedelta(days=1)
    yesterday_end = today - timedelta(microseconds=1)  # 23:59:59.999999

    with get_db_session() as db:
        stats = {
            'date': yesterday_start.strftime('%Y-%m-%d'),
            'yesterday_start': yesterday_start.isoformat(),
            'yesterday_end': yesterday_end.isoformat(),
            'wb': {},
            'ozon': {},
            'total': {}
        }

        if period_days:
            # Статистика за определенный период до вчерашнего дня
            period_start = yesterday_start - timedelta(days=period_days - 1)
            period_start = period_start.replace(hour=0, minute=0, second=0)

            stats['wb']['period'] = db.query(WbCard).filter(
                WbCard.id_ul == Config.DEFAULT_UL_ID,
                WbCard.created_at >= period_start,
                WbCard.created_at <= yesterday_end
            ).count()

            stats['ozon']['period'] = db.query(OzonCard).filter(
                OzonCard.id_ul == Config.DEFAULT_UL_ID,
                OzonCard.created_at >= period_start,
                OzonCard.created_at <= yesterday_end
            ).count()

            stats['total']['period'] = stats['wb']['period'] + stats['ozon']['period']
            stats['period_days'] = period_days
            stats['period_start'] = period_start.strftime('%Y-%m-%d')

        else:
            # Стандартная статистика за вчерашний день
            week_start = yesterday_start - timedelta(days=7)
            month_start = yesterday_start - timedelta(days=30)

            # Wildberries за вчера
            stats['wb']['yesterday'] = db.query(WbCard).filter(
                WbCard.id_ul == Config.DEFAULT_UL_ID,
                WbCard.created_at >= yesterday_start,
                WbCard.created_at <= yesterday_end
            ).count()

            # Wildberries за неделю (7 дней до вчера)
            stats['wb']['week'] = db.query(WbCard).filter(
                WbCard.id_ul == Config.DEFAULT_UL_ID,
                WbCard.created_at >= week_start,
                WbCard.created_at <= yesterday_end
            ).count()

            # Wildberries за месяц (30 дней до вчера)
            stats['wb']['month'] = db.query(WbCard).filter(
                WbCard.id_ul == Config.DEFAULT_UL_ID,
                WbCard.created_at >= month_start,
                WbCard.created_at <= yesterday_end
            ).count()

            # Ozon за вчера
            stats['ozon']['yesterday'] = db.query(OzonCard).filter(
                OzonCard.id_ul == Config.DEFAULT_UL_ID,
                OzonCard.created_at >= yesterday_start,
                OzonCard.created_at <= yesterday_end
            ).count()

            # Ozon за неделю
            stats['ozon']['week'] = db.query(OzonCard).filter(
                OzonCard.id_ul == Config.DEFAULT_UL_ID,
                OzonCard.created_at >= week_start,
                OzonCard.created_at <= yesterday_end
            ).count()

            # Ozon за месяц
            stats['ozon']['month'] = db.query(OzonCard).filter(
                OzonCard.id_ul == Config.DEFAULT_UL_ID,
                OzonCard.created_at >= month_start,
                OzonCard.created_at <= yesterday_end
            ).count()

            # Итого за вчера
            stats['total']['yesterday'] = stats['wb']['yesterday'] + stats['ozon']['yesterday']
            stats['total']['week'] = stats['wb']['week'] + stats['ozon']['week']
            stats['total']['month'] = stats['wb']['month'] + stats['ozon']['month']

        return stats


def send_daily_report():
    """Отправляет ежедневный отчет за вчерашний день"""
    stats = get_new_products_stats()

    yesterday_str = stats['date']

    # Общий отчет
    general_message = (
        f"📊 *Ежедневный отчет по новым товарам*\n"
        f"📅 За вчера: {yesterday_str}\n\n"
        f"*Wildberries*\n"
        f"  • За вчера: {stats['wb']['yesterday']}\n"
        f"  • За 7 дней: {stats['wb']['week']}\n"
        f"  • За 30 дней: {stats['wb']['month']}\n\n"
        f"*Ozon*\n"
        f"  • За вчера: {stats['ozon']['yesterday']}\n"
        f"  • За 7 дней: {stats['ozon']['week']}\n"
        f"  • За 30 дней: {stats['ozon']['month']}\n\n"
        f"*ИТОГО:*\n"
        f"  • За вчера: {stats['total']['yesterday']}\n"
        f"  • За 7 дней: {stats['total']['week']}\n"
        f"  • За 30 дней: {stats['total']['month']}"
    )

    # Отправляем в основную группу
    send_telegram_message(general_message, Config.GROUP_MANTRA_ID, "Markdown")

    # Отправляем специализированные отчеты, если есть соответствующие группы
    if hasattr(Config, 'GROUP_WB_ID') and Config.GROUP_WB_ID:
        wb_message = (
            f"📦 *WB: отчет по новым товарам*\n"
            f"📅 За вчера: {yesterday_str}\n\n"
            f"  • За вчера: {stats['wb']['yesterday']}\n"
            f"  • За 7 дней: {stats['wb']['week']}\n"
            f"  • За 30 дней: {stats['wb']['month']}"
        )
        send_telegram_message(wb_message, Config.GROUP_WB_ID, "Markdown")

    if hasattr(Config, 'GROUP_OZON_ID') and Config.GROUP_OZON_ID:
        ozon_message = (
            f"🛒 *Ozon: отчет по новым товарам*\n"
            f"📅 За вчера: {yesterday_str}\n\n"
            f"  • За вчера: {stats['ozon']['yesterday']}\n"
            f"  • За 7 дней: {stats['ozon']['week']}\n"
            f"  • За 30 дней: {stats['ozon']['month']}"
        )
        send_telegram_message(ozon_message, Config.GROUP_OZON_ID, "Markdown")

    return stats


def send_weekly_report():
    """Отправляет еженедельный отчет за последние 7 дней (до вчера)"""
    stats = get_new_products_stats(7)

    message = (
        f"📆 *Еженедельный отчет по новым товарам*\n"
        f"📅 За период: {stats['period_start']} - {stats['date']}\n\n"
        f"*Wildberries:* {stats['wb']['period']} новых товаров\n"
        f"*Ozon:* {stats['ozon']['period']} новых товаров\n"
        f"*ИТОГО:* {stats['total']['period']} новых товаров"
    )

    send_telegram_message(message, Config.GROUP_MANTRA_ID, "Markdown")
    return stats


def send_monthly_report():
    """Отправляет ежемесячный отчет за последние 30 дней (до вчера)"""
    stats = get_new_products_stats(30)

    message = (
        f"📈 *Ежемесячный отчет по новым товарам*\n"
        f"📅 За период: {stats['period_start']} - {stats['date']}\n\n"
        f"*Wildberries:* {stats['wb']['period']} новых товаров\n"
        f"*Ozon:* {stats['ozon']['period']} новых товаров\n"
        f"*ИТОГО:* {stats['total']['period']} новых товаров"
    )

    send_telegram_message(message, Config.GROUP_MANTRA_ID, "Markdown")
    return stats

