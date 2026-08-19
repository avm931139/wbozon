from __future__ import annotations

from typing import Any

import requests


class TelegramError(RuntimeError):
    pass


def split_text(text: str, limit: int = 3900) -> list[str]:
    """Split on lines where possible and always stay below Telegram's limit."""
    if limit < 1:
        raise ValueError("limit must be positive")
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            chunks.append(line[:limit].rstrip())
            line = line[limit:]
        if current and len(current) + len(line) > limit:
            chunks.append(current.rstrip())
            current = ""
        current += line
    if current.strip() or not chunks:
        chunks.append(current.rstrip())
    return chunks


class TelegramClient:
    def __init__(self, token: str, chat_id: str, *, timeout: int = 30, session: Any = None) -> None:
        if not token or not chat_id:
            raise ValueError("WB_TG_BOT_TOKEN and WB_TG_CHAT_ID must be set")
        self.chat_id = str(chat_id)
        self.timeout = timeout
        self.session = session or requests.Session()
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.url = f"{self.base_url}/sendMessage"

    def send_text(self, text: str) -> list[int]:
        message_ids: list[int] = []
        for chunk in split_text(text):
            try:
                response = self.session.post(
                    self.url,
                    json={"chat_id": self.chat_id, "text": chunk, "disable_web_page_preview": True},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError) as exc:
                raise TelegramError(f"Telegram transport error: {exc}") from exc
            if not payload.get("ok"):
                raise TelegramError(f"Telegram API rejected message: {payload.get('description', 'unknown error')}")
            message_ids.append(int(payload["result"]["message_id"]))
        return message_ids

    def send_document(
        self,
        filename: str,
        content: bytes,
        *,
        caption: str | None = None,
        content_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ) -> int:
        if not filename or not content:
            raise ValueError("filename and content must not be empty")
        data = {"chat_id": self.chat_id}
        if caption:
            data["caption"] = caption
        try:
            response = self.session.post(
                f"{self.base_url}/sendDocument",
                data=data,
                files={"document": (filename, content, content_type)},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise TelegramError(f"Telegram transport error: {exc}") from exc
        if not payload.get("ok"):
            raise TelegramError(f"Telegram API rejected document: {payload.get('description', 'unknown error')}")
        return int(payload["result"]["message_id"])
