# matra_sync/bot.py
import requests
import re
from settings import Config


def escape_markdown(text: str) -> str:
    """
    Экранирует специальные символы для Telegram MarkdownV2
    """
    if not text:
        return text

    # Список символов для экранирования в Telegram MarkdownV2
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']

    # Экранируем каждый спецсимвол обратным слешем
    for char in special_chars:
        text = text.replace(char, f'\\{char}')

    return text


def send_telegram_message(text: str, chat_id: str = None, parse_mode: str = None):
    """
    Отправляет сообщение в Telegram группу
    """
    target_chat_id = chat_id if chat_id else Config.GROUP_MANTRA_ID

    if not target_chat_id:
        print("❌ Не указан chat_id для отправки сообщения")
        return None

    url = f"https://api.telegram.org/bot{Config.BOT_MANTRA_API_KEY}/sendMessage"

    # Базовая очистка текста
    if text:
        # Заменяем множественные переносы строк
        text = re.sub(r'\n{3,}', '\n\n', text)

    # Пробуем отправить с Markdown если указан
    if parse_mode:
        # Для MarkdownV2 нужно экранировать больше символов
        if parse_mode.upper() == 'MARKDOWNV2':
            escaped_text = escape_markdown(text)
            payload = {
                'chat_id': target_chat_id,
                'text': escaped_text,
                'parse_mode': 'MarkdownV2',
                'disable_web_page_preview': True
            }
        else:
            # Для обычного Markdown не экранируем (он сам обрабатывает)
            payload = {
                'chat_id': target_chat_id,
                'text': text,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }
    else:
        # Без форматирования
        payload = {
            'chat_id': target_chat_id,
            'text': text,
            'disable_web_page_preview': True
        }

    try:
        print(f"📤 Отправка сообщения в чат {target_chat_id}...")
        response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            print("✅ Сообщение успешно отправлено")
            return response.json()
        else:
            print(f"❌ Ошибка {response.status_code}: {response.text}")

            # Если ошибка с Markdown, пробуем без него
            if parse_mode:
                print("🔄 Пробуем отправить без форматирования...")
                return send_telegram_message(text, chat_id, None)
            return None

    except requests.exceptions.Timeout:
        print("❌ Таймаут при отправке в Telegram")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка при отправке в Telegram: {e}")
        return None
    except Exception as e:
        print(f"❌ Непредвиденная ошибка: {e}")
        return None


def send_telegram_message_safe(text: str, chat_id: str = None, parse_mode: str = None):
    """
    Безопасная отправка сообщения с автоматическим определением проблемы
    """
    # Сначала пробуем отправить как есть
    result = send_telegram_message(text, chat_id, parse_mode)

    # Если не получилось и был указан parse_mode, пробуем без него
    if not result and parse_mode:
        print("🔄 Повторная отправка без форматирования...")
        result = send_telegram_message(text, chat_id, None)

    return result


def send_telegram_message_to_chat(text: str, chat_id: str, parse_mode: str = None):
    """Отправляет сообщение в конкретный чат"""
    return send_telegram_message(text, chat_id, parse_mode)


def send_telegram_message_to_admin(text: str, parse_mode: str = None):
    """Отправляет сообщение администратору"""
    admin_chat_id = getattr(Config, 'ADMIN_CHAT_ID', None)
    if admin_chat_id:
        return send_telegram_message(text, admin_chat_id, parse_mode)
    else:
        print("⚠️ ADMIN_CHAT_ID не указан в настройках")
        return None