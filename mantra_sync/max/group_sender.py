import asyncio
import logging
from typing import Any, Optional, Callable, Awaitable
from datetime import datetime
from pyromax.api import MaxApi
from pyromax.api.observer import Dispatcher
from pyromax.types import Message

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

dp = Dispatcher()


class DataSender:
    """
    Класс для периодической отправки данных в группу MAX.
    Проверяет наличие данных каждые 15 секунд и отправляет, если данные есть.
    """

    def __init__(self, chat_id: int, check_interval: int = 15):
        """
        Args:
            chat_id: ID группы в MAX
            check_interval: интервал проверки в секундах (по умолчанию 15)
        """
        self.chat_id = chat_id
        self.check_interval = check_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._max_api: Optional[MaxApi] = None
        self._data_provider: Optional[Callable[[], Awaitable[Optional[Any]]]] = None
        self._formatter: Optional[Callable[[Any], str]] = None

    def set_data_provider(self, provider: Callable[[], Awaitable[Optional[Any]]]):
        """
        Устанавливает асинхронную функцию, которая возвращает данные для отправки.

        Args:
            provider: асинхронная функция, возвращающая данные или None если данных нет
        """
        self._data_provider = provider

    def set_formatter(self, formatter: Callable[[Any], str]):
        """
        Устанавливает функцию форматирования данных в текст сообщения.

        Args:
            formatter: функция, преобразующая данные в строку для отправки
        """
        self._formatter = formatter

    async def send_message(self, text: str):
        """Отправляет сообщение в группу"""
        if not self._max_api:
            logger.error("MaxApi не инициализирован")
            return False

        try:
            await self._max_api.send_message(
                chat_id=self.chat_id,
                text=text
            )
            logger.info(f"✅ Сообщение отправлено в группу {self.chat_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False

    async def _check_and_send(self):
        """Проверяет данные и отправляет, если есть"""
        if not self._data_provider:
            logger.warning("Не установлен провайдер данных")
            return

        try:
            data = await self._data_provider()

            if data is not None:
                # Форматируем данные
                if self._formatter:
                    text = self._formatter(data)
                else:
                    text = str(data)

                # Отправляем
                await self.send_message(text)

        except Exception as e:
            logger.error(f"Ошибка при проверке данных: {e}")

    async def _run(self):
        """Основной цикл отправки"""
        logger.info(f"🔄 Запущен периодическая отправка (интервал: {self.check_interval}с)")

        while self._running:
            await self._check_and_send()
            await asyncio.sleep(self.check_interval)

        logger.info("⏹️ Периодическая отправка остановлена")

    async def start(self, max_api: MaxApi):
        """Запускает периодическую отправку"""
        if self._running:
            logger.warning("Отправка уже запущена")
            return

        self._max_api = max_api
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("🚀 Отправка данных запущена")

    async def stop(self):
        """Останавливает периодическую отправку"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Отправка данных остановлена")


# ============================================================
# ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ
# ============================================================

# ---- Пример 1: Отправка простых данных (счетчик) ----
class CounterProvider:
    """Пример провайдера данных - счетчик"""

    def __init__(self):
        self.count = 0

    async def get_data(self):
        self.count += 1
        if self.count % 3 == 0:  # Отправляем каждое 3-е значение
            return f"Счётчик: {self.count}"
        return None


# ---- Пример 2: Отправка данных из базы/API ----
class DatabaseProvider:
    """Пример провайдера данных из БД"""

    def __init__(self):
        self.last_id = 0

    async def get_new_records(self):
        """
        Здесь должна быть реальная логика получения новых записей из БД.
        Возвращает список новых записей или None.
        """
        # Имитация получения данных
        import random
        if random.random() > 0.7:  # 30% вероятность новых данных
            self.last_id += 1
            return {
                'id': self.last_id,
                'message': f'Новое событие #{self.last_id}',
                'time': datetime.now().strftime('%H:%M:%S')
            }
        return None


# ---- Пример 3: Отправка системных метрик ----
class MetricsProvider:
    """Пример провайдера системных метрик"""

    async def get_metrics(self):
        import psutil  # нужен pip install psutil
        return {
            'cpu': psutil.cpu_percent(),
            'memory': psutil.virtual_memory().percent,
            'time': datetime.now().strftime('%H:%M:%S')
        }

#
# # ============================================================
# # ГЛАВНАЯ ФУНКЦИЯ ЗАПУСКА
# # ============================================================
#
# async def main():
#     # ID вашей группы (замените на реальный)
#     GROUP_ID = 280717082  # ← ВАШ ID ГРУППЫ
#
#     # Создаём экземпляр провайдера данных
#     # Вариант 1: Счетчик
#     provider = CounterProvider()
#
#     # Вариант 2: База данных
#     # provider = DatabaseProvider()
#
#     # Создаём отправитель
#     sender = DataSender(
#         chat_id=GROUP_ID,
#         check_interval=15  # проверка каждые 15 секунд
#     )
#
#     # Устанавливаем провайдера данных
#     sender.set_data_provider(provider.get_data)
#
#     # Опционально: устанавливаем форматтер (если данные нужно красиво оформить)
#     def format_message(data):
#         return f"""
# 📢 **Новые данные!**
# ━━━━━━━━━━━━━━━━━
# {data}
# ━━━━━━━━━━━━━━━━━
# 🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
# """
#
#     sender.set_formatter(format_message)
#
#     # Запускаем бота MAX
#     logger.info("🚀 Запуск бота MAX...")
#     bot = await MaxApi()
#
#     # Запускаем периодическую отправку
#     await sender.start(bot)
#
#     # Держим бота активным
#     try:
#         await bot.reload_if_connection_broke(dp)
#     except KeyboardInterrupt:
#         logger.info("Получен сигнал остановки")
#         await sender.stop()
#
#
# # ---- Альтернативный запуск без диспетчера (только отправка) ----
# async def main_simple():
#     """Простой запуск - только отправка, без приёма сообщений"""
#     GROUP_ID = 280717082
#
#     provider = CounterProvider()
#     sender = DataSender(chat_id=GROUP_ID, check_interval=15)
#     sender.set_data_provider(provider.get_data)
#
#     # Подключаемся к MAX
#     bot = await MaxApi()
#
#     # Запускаем отправку
#     await sender.start(bot)
#
#     # Держим запущенным
#     try:
#         while True:
#             await asyncio.sleep(1)
#     except KeyboardInterrupt:
#         await sender.stop()
#
#
# if __name__ == "__main__":
#     asyncio.run(main())