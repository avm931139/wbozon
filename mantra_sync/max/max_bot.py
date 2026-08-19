import asyncio
import logging
import sys
import asyncio as asyncio_module

# Хак для Python 3.10
if sys.version_info < (3, 11):
    try:
        from async_timeout import timeout

        asyncio_module.timeout = timeout
        print("✅ Совместимость с Python 3.10 включена")
    except ImportError:
        print("⚠️ Установите async-timeout: pip install async-timeout")

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


def extract_chat_info(message: Message) -> dict:
    """
    Извлекает информацию о чате из сообщения.
    """
    info = {
        'chat_id': None,
        'chat_name': 'Unknown',
        'is_group': False,
        'from_name': 'Unknown',
        'from_id': None,
        'text': message.text or ''
    }

    # Пробуем получить информацию из разных полей
    # Вариант 1: через chat
    if hasattr(message, 'chat') and message.chat:
        chat = message.chat
        if hasattr(chat, 'id'):
            info['chat_id'] = chat.id
        if hasattr(chat, 'name'):
            info['chat_name'] = chat.name
        if hasattr(chat, 'is_group'):
            info['is_group'] = chat.is_group
        if hasattr(chat, 'type'):
            info['is_group'] = info['is_group'] or (chat.type == 'group')

    # Вариант 2: прямой доступ к полям
    if info['chat_id'] is None:
        if hasattr(message, 'chat_id'):
            info['chat_id'] = message.chat_id
        elif hasattr(message, 'peer_id'):
            info['chat_id'] = message.peer_id

    # Информация об отправителе
    if hasattr(message, 'sender') and message.sender:
        sender = message.sender
        if hasattr(sender, 'first_name'):
            info['from_name'] = sender.first_name
        elif hasattr(sender, 'name'):
            info['from_name'] = sender.name
        if hasattr(sender, 'id'):
            info['from_id'] = sender.id
    elif hasattr(message, 'from_id'):
        info['from_id'] = message.from_id

    # Определяем, группа это или нет
    if info['chat_id'] and info['from_id']:
        # Если chat_id не равен from_id и чат не личный
        if info['chat_id'] != info['from_id']:
            info['is_group'] = True

    return info


@dp.message()
async def handle_all_messages(message: Message, max_api: MaxApi):
    """
    Обрабатывает ВСЕ сообщения.
    """
    # Логируем сырое сообщение для отладки (только первые 500 символов)
    raw_str = str(message)[:500]
    logger.info(f"📨 [RAW] {raw_str}...")

    info = extract_chat_info(message)

    logger.info(f"👤 [PARSED] chat_id={info['chat_id']}, chat_name={info['chat_name']}, "
                f"is_group={info['is_group']}, from={info['from_name']}, text={info['text'][:50]}")

    # Если нет chat_id, не можем ответить
    if not info['chat_id']:
        logger.warning("⚠️ Не удалось определить chat_id, пропускаем")
        return

    # Обработка команд
    if info['text'] == '/help':
        await max_api.send_message(
            chat_id=info['chat_id'],
            text="📋 **Доступные команды:**\n/help - это сообщение\n/info - информация"
        )
        return

    if info['text'] == '/info':
        await max_api.send_message(
            chat_id=info['chat_id'],
            text=f"📊 **Информация**\n"
                 f"🆔 Chat ID: {info['chat_id']}\n"
                 f"📛 Название: {info['chat_name']}\n"
                 f"👥 Тип: {'ГРУППА' if info['is_group'] else 'ЛИЧНЫЙ'}\n"
                 f"👤 Отправитель: {info['from_name']}\n"
                 f"🆔 Sender ID: {info['from_id']}"
        )
        return

    # Эхо для всех остальных сообщений (опционально, закомментируйте если не нужно)
    # await max_api.send_message(
    #     chat_id=info['chat_id'],
    #     text=f"Эхо: {info['text']}"
    # )


async def main():
    """Главная функция запуска бота."""
    logger.info("🚀 Запуск группового бота для MAX...")

    # Создаем экземпляр API (при первом запуске потребуется QR-код)
    bot = await MaxApi()

    logger.info("✅ Бот авторизован и готов к работе")
    logger.info("👂 Начинаем прослушивание сообщений...")

    # Запускаем обработку сообщений
    await bot.reload_if_connection_broke(dp)


if __name__ == "__main__":
    asyncio.run(main())