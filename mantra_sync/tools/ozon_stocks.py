# matra_sync/tools/ozon_stocks.py
from datetime import datetime
from core.classes import Ozon
from bot import send_telegram_message


def notify(step: str, success: bool = True, error: Exception = None):
    """Отправка сообщения в Telegram и логирование в консоль."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if success:
        message = f"✅ [{timestamp}] {step} успешно выполнен"
    else:
        message = f"❌ [{timestamp}] {step} завершился с ошибкой: {error}"
    print(message)
    try:
        send_telegram_message(message)
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")


def get_ozon_stocks():
    """
    Загружает остатки с Ozon
    """
    ozon = Ozon()

    try:
        # Получаем остатки
        stocks = ozon.get_stocks()

        if stocks:
            ozon.save_stocks(stocks)
            notify(f"Загружено {len(stocks)} остатков Ozon")
            return len(stocks)
        else:
            notify("Нет данных об остатках Ozon", False)
            return 0

    except Exception as e:
        notify("Ошибка при загрузке остатков Ozon", False, e)
        return 0