import requests
import time
from urllib.parse import urljoin
from settings import Config
from wb.endpoind_wb import content_api_base_url_wb, cards_upload_wb_endp


class WBClient:

    def __init__(self, token: str):
        self.token = token
        self.base_url = content_api_base_url_wb

    def _headers(self):
        return {
            "Authorization": self.token,
            "Content-Type": "application/json"
        }

    def _build_url(self):
        return urljoin(self.base_url, cards_upload_wb_endp)

    def upload_cards(self, payload: list):

        url = self._build_url()
        last_error = None

        for attempt in range(3):

            resp = requests.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=30
            )

            # ✔ успех
            if resp.status_code == 200:
                return resp.json()

            # ✔ WB rate limit
            if resp.status_code == 429:
                time.sleep(5 * (attempt + 1))
                last_error = resp.text
                continue

            # ✔ временные ошибки
            if resp.status_code >= 500:
                time.sleep(2 ** attempt)
                last_error = resp.text
                continue

            # ❌ критическая ошибка (валидация и т.д.)
            raise Exception(f"WB validation error: {resp.text}")

        raise Exception(f"WB upload failed after retries: {last_error}")