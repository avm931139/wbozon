# matra_sync/main.py
import schedule
import time
import os
import sys
from datetime import datetime
from pathlib import Path

# Добавляем путь к проекту для импортов
sys.path.append(str(Path(__file__).parent))

from wb.wb_remains_report import get_wb_remains_report_job
from bot import send_telegram_message
from tools.goods_stocks import get_wb_stocks
from wb.get_product import get_product_wb
from ozon.get_ozon_data.get_product import get_ozon_products
from utils.reports import send_daily_report, send_weekly_report, send_monthly_report
from settings import Config

from wb.analytics.wb_sales_funnel_report import wb_sales_funnel_job

from utils.stock_report import send_stock_report, stock_report_job

# Константы
VERSION = "2.0.0"
START_TIME = datetime.now()
DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'

print(f"🔧 DEBUG_MODE = {DEBUG_MODE}")  # Отладка


def wb_remains_report_job():
    """Получение отчета об остатках WB"""
    run_with_retry(get_wb_remains_report_job, "Отчет об остатках WB")


def notify(message: str, level: str = "INFO", chat_id: str = None):
    """Отправка уведомления в консоль и Telegram с эмодзи"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Эмодзи в зависимости от уровня
    emoji = {
        "INFO": "ℹ️",
        "SUCCESS": "✅",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "START": "🚀",
        "STOP": "🛑",
        "SCHEDULE": "📅",
        "WB": "📦",
        "OZON": "🛒"
    }.get(level, "📌")

    text = f"{emoji} [{ts}] {message}"
    print(text)

    # Определяем, в какой чат отправлять
    target_chat = chat_id
    if not target_chat:
        if level == "ERROR":
            target_chat = getattr(Config, 'GROUP_ERRORS_ID', Config.GROUP_MANTRA_ID)
        elif level == "WB":
            target_chat = getattr(Config, 'GROUP_WB_ID', Config.GROUP_MANTRA_ID)
        elif level == "OZON":
            target_chat = getattr(Config, 'GROUP_OZON_ID', Config.GROUP_MANTRA_ID)
        else:
            target_chat = Config.GROUP_MANTRA_ID

    # В Telegram отправляем только важные сообщения
    if level in ["SUCCESS", "ERROR", "START", "STOP", "WARNING", "WB", "OZON"]:
        try:
            # Для сообщений START используем Markdown, для остальных - обычный текст
            if level == "START":
                send_telegram_message(text, chat_id=target_chat, parse_mode="Markdown")
            else:
                send_telegram_message(text, chat_id=target_chat, parse_mode=None)
        except Exception as e:
            print(f"Ошибка отправки в Telegram: {e}")


def run_with_retry(func, name: str, retries: int = 3, delay: int = 60):
    """Запуск функции с повторными попытками при ошибке"""
    start_time = datetime.now()

    for attempt in range(1, retries + 1):
        try:
            notify(f"▶️ Старт: {name} (попытка {attempt}/{retries})", "INFO")
            result = func()
            execution_time = (datetime.now() - start_time).total_seconds()
            notify(f"✅ Успех: {name} (выполнено за {execution_time:.2f} сек)", "SUCCESS")
            return result
        except Exception as e:
            error_msg = f"❌ Ошибка в {name} (попытка {attempt}/{retries}): {e}"
            notify(error_msg, "ERROR")

            if attempt < retries:
                notify(f"⏳ Повтор через {delay} секунд...", "WARNING")
                time.sleep(delay)
            else:
                notify(f"🔥 Модуль {name} не выполнился после {retries} попыток", "ERROR")

    return False


def get_uptime() -> str:
    """Возвращает время работы сервиса"""
    uptime = datetime.now() - START_TIME
    days = uptime.days
    hours = uptime.seconds // 3600
    minutes = (uptime.seconds % 3600) // 60

    if days > 0:
        return f"{days}д {hours}ч {minutes}м"
    else:
        return f"{hours}ч {minutes}м"

def stock_report_job():
    """Отправка отчета по остаткам товаров"""
    notify("📊 Отправка отчета по остаткам...", "INFO")
    return run_with_retry(send_stock_report, "Отчет по остаткам товаров")


def status_job():
    """Отправка статуса сервиса (каждый час)"""
    uptime = get_uptime()
    status_msg = (
        f"📊 *Статус сервиса*\n"
        f"• Версия: {VERSION}\n"
        f"• Время работы: {uptime}\n"
        f"• Режим: {'ОТЛАДКА' if DEBUG_MODE else 'РАБОЧИЙ'}\n"
        f"• WB: {'✅' if Config.API_KEY_WB else '❌'}\n"
        f"• Ozon: {'✅' if Config.OZON_CLIENT_ID else '❌'}"
    )
    notify(status_msg, "INFO")
    return True


def check_midnight_job():
    """Проверка и сброс счетчиков в полночь"""
    notify("🌙 Наступила полночь, обновление статистики...", "INFO")
    return True


# === Задачи ===
def wb_cards_job():
    """Обновление карточек WB"""
    notify("📦 Начинаем обновление карточек WB...", "INFO")
    return run_with_retry(get_product_wb, "Обновление товаров WB (карточки)")


def wb_stocks_job():
    """Обновление остатков WB"""
    notify("📊 Начинаем обновление остатков FBS WB...", "INFO")
    return run_with_retry(get_wb_stocks, "Обновление остатков WB")


def ozon_products_job():
    """Обновление товаров Ozon"""
    notify("📦 Начинаем обновление товаров Ozon...", "INFO")
    return run_with_retry(get_ozon_products, "Обновление товаров Ozon")



def daily_report_job():
    """Отправка ежедневного отчета"""
    notify("📅 Отправка ежедневного отчета...", "INFO")
    return run_with_retry(send_daily_report, "Ежедневный отчет по новым товарам")


def weekly_report_job():
    """Отправка еженедельного отчета (каждый понедельник)"""
    notify("📆 Отправка еженедельного отчета...", "INFO")
    return run_with_retry(send_weekly_report, "Еженедельный отчет")


def monthly_report_job():
    """Отправка ежемесячного отчета (1-го числа)"""
    notify("📈 Отправка ежемесячного отчета...", "INFO")
    return run_with_retry(send_monthly_report, "Ежемесячный отчет")


def test_all_jobs():
    """Тестовый запуск всех задач"""
    notify("🧪 ТЕСТОВЫЙ ЗАПУСК ВСЕХ ЗАДАЧ", "WARNING")

    jobs = [
        ("WB карточки", get_product_wb),
        ("WB остатки", get_wb_stocks),
        ("Ozon товары", get_ozon_products),
        # ("Ozon остатки", get_ozon_stocks),
        ("Ежедневный отчет", send_daily_report),
    ]

    results = []
    for name, job in jobs:
        print("\n" + "=" * 60)
        print(f"ТЕСТ: {name}")
        print("=" * 60)
        try:
            result = job()
            results.append((name, "✅ УСПЕХ", result))
        except Exception as e:
            results.append((name, "❌ ОШИБКА", str(e)))

    print("\n" + "=" * 60)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 60)
    for name, status, details in results:
        print(f"{status} {name}: {details}")

    notify("✅ Тестовый запуск завершен", "SUCCESS")
    return results


def check_and_run_monthly_report():
    """Проверяет, что сегодня 1-е число, и запускает месячный отчет"""
    if datetime.now().day == 1:
        notify("📅 Сегодня 1-е число, запускаем месячный отчет", "INFO")
        return monthly_report_job()
    return None


def setup_schedule():
    """Настройка расписания задач"""

    if DEBUG_MODE:
        notify("🔧 РЕЖИМ ОТЛАДКИ: задачи запускаются часто", "WARNING")
        schedule.every(2).minutes.do(wb_cards_job)
        schedule.every(3).minutes.do(ozon_products_job)
        schedule.every(5).minutes.do(daily_report_job)
        schedule.every(30).minutes.do(status_job)
    else:
        notify("⚙️ РАБОЧИЙ РЕЖИМ: настройка расписания", "INFO")

        # СОРТИРУЕМ ПО ВРЕМЕНИ -2 ЧАСА ОТ МОСКВЫ!!!   (от меньшего к большему)
        schedule.every().day.at("05:28").do(ozon_products_job)  # Ozon товары остатки
        schedule.every().day.at("05:30").do(wb_cards_job)  # WB карточки
        schedule.every().day.at("05:35").do(wb_stocks_job)  # WB остатки FBS
        schedule.every().day.at("05:45").do(wb_remains_report_job)  # Отчет об остатках WB FBO

        schedule.every().day.at("06:03").do(stock_report_job)  # Отчет по остаткам в 06:00
        schedule.every().day.at("06:00").do(daily_report_job)  # Ежедневный отчет

        schedule.every(60).minutes.do(wb_sales_funnel_job)


        # Еженедельные
        # schedule.every().monday.at("10:00").do(weekly_report_job)

        # Ежемесячные
        # schedule.every().day.at("11:00").do(check_and_run_monthly_report)

        # Статус и проверки
        schedule.every().hour.do(status_job)
        schedule.every().day.at("00:00").do(check_midnight_job)

    # Выводим расписание для проверки
    print("\n📋 ТЕКУЩЕЕ РАСПИСАНИЕ:")
    jobs = schedule.get_jobs()
    if not jobs:
        print("  ⚠️ Нет запланированных задач!")
    else:
        # Сортируем задачи по времени для красивого вывода
        def get_job_time(job):
            job_str = str(job)
            if 'at ' in job_str:
                try:
                    return job_str.split('at ')[1].split(' ')[0]
                except:
                    return '00:00'
            return '00:00'

        sorted_jobs = sorted(jobs, key=get_job_time)
        for job in sorted_jobs:
            print(f"  • {job}")
    print("")


# === MAIN ===
if __name__ == "__main__":
    # Очищаем консоль
    os.system('cls' if os.name == 'nt' else 'clear')

    print("=" * 60)
    print(f"🚀 СЕРВИС МОНИТОРИНГА МАРКЕТПЛЕЙСОВ v{VERSION}")
    print("=" * 60)

    # Проверка конфигурации
    print("\n🔍 ПРОВЕРКА КОНФИГУРАЦИИ:")
    print(f"• Wildberries API: {'✅' if Config.API_KEY_WB else '❌'}")
    print(f"• Ozon API: {'✅' if Config.OZON_CLIENT_ID else '❌'}")
    print(f"• Telegram Bot: {'✅' if Config.BOT_MANTRA_API_KEY else '❌'}")
    print(f"• База данных: {'✅' if Config.DATABASE_URL else '❌'}")
    print(f"• Режим отладки: {'✅' if DEBUG_MODE else '❌'}")
    print(f"• Текущее время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Отправляем стартовое сообщение
    start_msg = (
        f"🚀 *Сервис мониторинга маркетплейсов запущен*\n"
        f"• Версия: {VERSION}\n"
        f"• Режим: {'ОТЛАДКА' if DEBUG_MODE else 'РАБОЧИЙ'}\n"
        f"• Время запуска: {START_TIME.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    print(start_msg)
    notify(start_msg, "START")

    # Настройка расписания
    setup_schedule()

    print("\n⏳ Ожидание задач по расписанию...")
    print("=" * 60 + "\n")

    # Основной цикл
    last_minute = -1
    last_second = -1

    while True:
        try:
            schedule.run_pending()

            current_time = datetime.now()
            current_second = current_time.second

            # Показываем время каждые 30 секунд
            if current_second % 30 == 0 and current_second != last_second:
                # print(f"⏱️ {current_time.strftime('%H:%M:%S')} - ожидание...")
                last_second = current_second

            time.sleep(1)  # Проверяем каждую секунду для точности

        except KeyboardInterrupt:
            stop_msg = f"🛑 Сервис остановлен пользователем. Время работы: {get_uptime()}"
            print("\n" + "=" * 60)
            notify(stop_msg, "STOP")
            print("=" * 60)
            break

        except Exception as e:
            notify(f"⚠️ Ошибка в основном цикле: {e}", "ERROR")
            time.sleep(60)