from sqlalchemy.orm import Session, selectinload
from core.db.models import ParserProduct, ParserProductStatus


import json
import time
import requests
from typing import Dict, Any, List

from sqlalchemy.orm import Session

from core.db.models import WBPreparedProduct


class WbRepository:
    """
    Боевой репозиторий отправки товаров в WB API.

    Функции:
    - выборка готовых товаров
    - отправка в WB
    - идемпотентность
    - обработка ошибок
    - retry механика
    - batch обработка
    """

    def __init__(self, db: Session, api_token: str, api_url: str):
        self.db = db
        self.api_token = api_token
        self.api_url = api_url.rstrip("/")
        self.session = requests.Session()

    # =========================
    # HEADERS
    # =========================
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": self.api_token,
            "Content-Type": "application/json"
        }

    # =========================
    # FETCH READY PRODUCTS
    # =========================
    def fetch_ready_products(self, limit: int = 1000) -> List[WBPreparedProduct]:
        """
        Берём только валидные и неотправленные товары
        """
        return (
            self.db.query(WBPreparedProduct)
            .filter(WBPreparedProduct.status == "valid")
            .limit(limit)
            .all()
        )

    # =========================
    # IDEMPOTENCY CHECK
    # =========================
    def is_already_sent(self, product_id_ms: str) -> bool:
        """
        Проверка, что товар уже отправлен
        """
        existing = (
            self.db.query(WBPreparedProduct)
            .filter(
                WBPreparedProduct.product_id_ms == product_id_ms,
                WBPreparedProduct.status == "sent"
            )
            .first()
        )
        return existing is not None

    # =========================
    # SEND SINGLE PRODUCT
    # =========================
    def send_product(self, prepared: WBPreparedProduct) -> Dict[str, Any]:
        """
        Отправка одного товара в WB
        """

        if prepared.status == "sent":
            return {
                "status": "skipped",
                "reason": "already_sent"
            }

        payload = json.loads(prepared.payload)

        url = f"{self.api_url}/cards/upload"  # WB endpoint (пример)

        try:
            response = self.session.post(
                url,
                headers=self._headers(),
                json=payload,
                timeout=30
            )

            if response.status_code in (200, 201):
                self._mark_sent(prepared, response.json())
                return {
                    "status": "success",
                    "response": response.json()
                }

            self._mark_error(prepared, response.text)

            return {
                "status": "error",
                "code": response.status_code,
                "response": response.text
            }

        except Exception as e:
            self._mark_error(prepared, str(e))
            return {
                "status": "exception",
                "error": str(e)
            }

    # =========================
    # MARK SENT
    # =========================
    def _mark_sent(self, prepared: WBPreparedProduct, response: dict):
        """
        Помечаем товар как успешно отправленный
        """
        prepared.status = "sent"

        prepared.wb_response = json.dumps(
            response,
            ensure_ascii=False
        )

        prepared.validation_errors = None

        self.db.add(prepared)
        self.db.commit()

    # =========================
    # MARK ERROR
    # =========================
    def _mark_error(self, prepared: WBPreparedProduct, error: str):
        """
        Помечаем ошибку отправки
        """
        prepared.status = "error"
        prepared.validation_errors = error

        self.db.add(prepared)
        self.db.commit()

    # =========================
    # RETRY FAILED
    # =========================
    def retry_failed(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Повторная отправка упавших товаров
        """

        failed = (
            self.db.query(WBPreparedProduct)
            .filter(WBPreparedProduct.status == "error")
            .limit(limit)
            .all()
        )

        results = []

        for item in failed:
            time.sleep(0.2)  # защита от лимитов WB
            results.append(self.send_product(item))

        return results

    # =========================
    # BATCH PROCESS
    # =========================
    def process_batch(self, limit: int = 1000) -> Dict[str, int]:
        """
        Основной батч-отправщик
        """

        products = self.fetch_ready_products(limit=limit)

        results = {
            "success": 0,
            "error": 0,
            "skipped": 0
        }

        for p in products:

            result = self.send_product(p)

            if result["status"] == "success":
                results["success"] += 1

            elif result["status"] == "skipped":
                results["skipped"] += 1

            else:
                results["error"] += 1

            time.sleep(0.1)  # rate limit защита

        return results