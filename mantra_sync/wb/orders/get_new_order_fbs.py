import time
import logging
import sys
import requests
from typing import Tuple, Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from bot import send_telegram_message

from wb.orders.set import SetOrder
from wb.orders.save_orders import save_orders_to_db, mark_order_as_sent, get_for_send_orders
from wb.orders.notify_order import notify_new_orders

# настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("wb_fbs_loader")


@dataclass
class FetchResult:
    """Результат выполнения запроса к API"""
    success: bool  # Успешен ли запрос
    orders: Optional[List[Dict]] = None  # Список заказов (при успехе)
    error_message: Optional[str] = None  # Сообщение об ошибке (при неудаче)
    error_code: Optional[int] = None  # HTTP статус код ошибки
    timestamp: datetime = None  # Время запроса

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


def notify(message: str, level: str = "INFO", target_chat: str = None):
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


def fetch_new_orders() -> FetchResult:
    """
    Выполняет GET-запрос к /api/v3/orders/new

    Returns:
        FetchResult: Объект с результатом запроса (успех/ошибка и данные)
    """
    headers = {
        "Authorization": SetOrder.WB_API_KEY
    }

    logger.info("Запрос к WB API (GET /orders/new)")

    try:
        response = requests.get(
            SetOrder.WB_API_URL,
            headers=headers,
            timeout=SetOrder.REQUEST_TIMEOUT
        )

        # 200 OK – успех
        if response.status_code == 200:
            data = response.json()
            orders = data.get("orders", [])
            logger.info(f"Успешно получено {len(orders)} новых заказов")

            # Логируем пример заказа для отладки
            if orders:
                sample = orders[0]
                logger.debug(f"Пример заказа: id={sample.get('id')}, orderUid={sample.get('orderUid')}")

            return FetchResult(
                success=True,
                orders=orders,
                error_message=None,
                error_code=200
            )

        # 401 Unauthorized – неверный или отсутствует API-ключ
        elif response.status_code == 401:
            error_msg = "🔴 *Ошибка авторизации WB API (401)*\n\n"
            error_msg += "Неверный или отсутствует API-ключ.\n"
            error_msg += "Проверьте переменную окружения `WB_API_KEY`.\n"
            error_msg += f"Время: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"

            logger.critical(error_msg)
            return FetchResult(
                success=False,
                orders=None,
                error_message=error_msg,
                error_code=401
            )

        # 403 Forbidden – доступ запрещён
        elif response.status_code == 403:
            error_msg = "🟠 *Доступ запрещён (403)*\n\n"
            error_msg += "API-ключ не имеет прав для доступа к этому методу.\n"
            error_msg += "Проверьте настройки прав доступа в личном кабинете WB.\n"
            error_msg += f"Время: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"

            logger.error(error_msg)
            return FetchResult(
                success=False,
                orders=None,
                error_message=error_msg,
                error_code=403
            )

        # 429 Too Many Requests – превышен лимит
        elif response.status_code == 429:
            wait_time = SetOrder.RATE_LIMIT_SLEEP
            error_msg = "⚠️ *Превышен лимит запросов к API (429)*\n\n"
            error_msg += f"Сделан перерыв на `{wait_time}` секунд.\n"
            error_msg += "Рекомендуется увеличить интервал между запросами.\n"
            error_msg += f"Время: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"

            logger.warning(error_msg)
            time.sleep(wait_time)

            return FetchResult(
                success=False,
                orders=None,
                error_message=error_msg,
                error_code=429
            )

        # Другие ошибки (4xx, 5xx)
        else:
            error_msg = f"🟡 *Неожиданная ошибка API ({response.status_code})*\n\n"
            error_msg += f"Статус: `{response.status_code}`\n"
            error_msg += f"Ответ сервера:\n```\n{response.text[:300]}\n```\n"
            error_msg += f"Время: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"

            logger.error(error_msg)
            return FetchResult(
                success=False,
                orders=None,
                error_message=error_msg,
                error_code=response.status_code
            )

    except requests.exceptions.Timeout:
        error_msg = "⏰ *Таймаут соединения с API WB*\n\n"
        error_msg += f"Превышено время ожидания ({SetOrder.REQUEST_TIMEOUT} сек).\n"
        error_msg += "Проверьте скорость интернет-соединения.\n"
        error_msg += f"Время: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"

        logger.error(error_msg)
        return FetchResult(
            success=False,
            orders=None,
            error_message=error_msg,
            error_code=None
        )

    except requests.exceptions.ConnectionError:
        error_msg = "🔌 *Ошибка соединения с API WB*\n\n"
        error_msg += "Не удалось установить соединение с сервером.\n"
        error_msg += "Проверьте:\n"
        error_msg += "• Интернет-соединение\n"
        error_msg += "• Доступность API Wildberries\n"
        error_msg += f"• Настройки прокси (если используются)\n"
        error_msg += f"Время: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"

        logger.error(error_msg)
        return FetchResult(
            success=False,
            orders=None,
            error_message=error_msg,
            error_code=None
        )

    except Exception as e:
        error_msg = f"💥 *Непредвиденная ошибка*\n\n"
        error_msg += f"Тип: `{type(e).__name__}`\n"
        error_msg += f"Сообщение: `{str(e)}`\n\n"
        error_msg += f"Время: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"

        logger.exception(f"Непредвиденная ошибка: {e}")
        return FetchResult(
            success=False,
            orders=None,
            error_message=error_msg,
            error_code=None
        )




def fetch_and_save_orders():
    """Получает заказы из API и сохраняет в БД"""
    orders_data = fetch_new_orders()

    if orders_data.success:
        saved_count = save_orders_to_db(orders_data.orders)
        logger.info(f"Сохранено {saved_count} новых заказов в БД")

        # Отправляем уведомление о новых заказах в Telegram
        if saved_count > 0:
            sended = notify_new_orders(orders_data.orders, SetOrder.TG_GROUP)
            # Ставим метку что отправлено в ТГ
            if sended:
                mark_order_as_sent(orders_data.orders)
            else:
                order_for_send = get_for_send_orders()
                sended = notify_new_orders(order_for_send, SetOrder.TG_GROUP)

                # Ставим метку что отправлено в ТГ
                if sended:
                    mark_order_as_sent(order_for_send)


        return orders_data.orders
    else:
        if orders_data.error_message:
            notify(orders_data.error_message, "ERROR", SetOrder.TG_GROUP)
        return []

def main():
    """Основной цикл микросервиса"""
    logger.info("=== Запуск микросервиса загрузки заказов WB FBS ===")

    if not SetOrder.WB_API_KEY:
        logger.critical("WB_API_KEY не задан. Завершение работы.")
        return

    logger.info(f"Интервал запросов: {SetOrder.SLEEP_INTERVAL} сек")

    try:
        while True:
            orders = fetch_and_save_orders()


            if orders is not None:
                logger.info(f"Получено {len(orders)} заказов (обработка завершена)")



            logger.info(f"Ожидание {SetOrder.SLEEP_INTERVAL} секунд...")
            time.sleep(SetOrder.SLEEP_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки. Завершение микросервиса.")
        return


if __name__ == "__main__":
    main()