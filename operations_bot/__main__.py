from __future__ import annotations

import argparse
import json
import logging

from app.config import (
    OPERATIONS_TG_BOT_TOKEN,
    OPERATIONS_TG_PROXY_URL,
    WB_TG_REQUEST_TIMEOUT_SECONDS,
)
from operations_bot.service import OperationsNotificationService
from telegram_bot.client import TelegramClient


def private_chats(updates: list[dict]) -> list[dict]:
    """Extract unique private chats from Telegram getUpdates payloads."""
    result: dict[str, dict] = {}
    for update in updates:
        for key in (
            "message",
            "edited_message",
            "channel_post",
            "edited_channel_post",
            "my_chat_member",
        ):
            payload = update.get(key)
            chat = payload.get("chat") if isinstance(payload, dict) else None
            if not isinstance(chat, dict) or chat.get("type") != "private" or "id" not in chat:
                continue
            chat_id = str(chat["id"])
            result[chat_id] = {
                "chat_id": chat_id,
                "first_name": chat.get("first_name"),
                "username": chat.get("username"),
            }
    return list(result.values())


def show_chat_ids() -> None:
    if not OPERATIONS_TG_BOT_TOKEN:
        raise RuntimeError("OPERATIONS_TG_BOT_TOKEN or WB_TG_BOT_TOKEN must be configured")
    client = TelegramClient(
        OPERATIONS_TG_BOT_TOKEN,
        "0",
        timeout=WB_TG_REQUEST_TIMEOUT_SECONDS,
        proxy_url=OPERATIONS_TG_PROXY_URL,
    )
    chats = private_chats(client.get_updates())
    print(json.dumps(chats, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send a private digest of completed wbozon operations"
    )
    parser.add_argument(
        "--show-chat-ids",
        action="store_true",
        help="show private chats that recently sent a message to the bot",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.show_chat_ids:
        show_chat_ids()
        return
    result = OperationsNotificationService().run()
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
