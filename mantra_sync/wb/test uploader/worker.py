import time
from typing import List, Dict, Any

from sqlalchemy.orm import Session

from core.db.models import ParserProduct
from wb_prepared_product_service import WBPreparedProductService
from wb_repository import WbRepository


class WBWorker:
    """
    Оркестратор полного WB pipeline:

    ParserProduct → WBPreparedProduct → WB API
    """

    def __init__(
        self,
        db: Session,
        wb_repo: WbRepository,
        prepared_service: WBPreparedProductService
    ):
        self.db = db
        self.wb_repo = wb_repo
        self.prepared_service = prepared_service

    # =========================
    # FETCH SOURCE PRODUCTS
    # =========================
    def fetch_products(self, limit: int = 1000) -> List[ParserProduct]:
        """
        Получаем товары, готовые к обработке
        """
        return (
            self.db.query(ParserProduct)
            .filter(ParserProduct.status == "ready")
            .limit(limit)
            .all()
        )

    # =========================
    # SINGLE PIPELINE STEP
    # =========================
    def process_single(self, product_id_ms: str):
        """
        ParserProduct → WBPreparedProduct
        """
        return self.prepared_service.build_and_save(product_id_ms)

    # =========================
    # PREPARE BATCH
    # =========================
    def prepare_batch(self, limit: int = 1000) -> Dict[str, int]:
        """
        Формирование WBPreparedProduct для всех товаров
        """

        products = self.fetch_products(limit)

        result = {
            "processed": 0,
            "errors": 0
        }

        for p in products:
            try:
                self.process_single(p.id_ms)
                result["processed"] += 1

            except Exception:
                result["errors"] += 1

            time.sleep(0.05)  # защита от нагрузки

        return result

    # =========================
    # SEND BATCH TO WB
    # =========================
    def send_batch(self, limit: int = 1000) -> Dict[str, int]:
        """
        Отправка готовых товаров в WB
        """
        return self.wb_repo.process_batch(limit=limit)

    # =========================
    # FULL PIPELINE
    # =========================
    def run_full_pipeline(self, limit: int = 1000) -> Dict[str, Any]:
        """
        Полный цикл:

        1. ParserProduct → WBPreparedProduct
        2. WBPreparedProduct → WB API
        """

        print("=== START PREPARE PHASE ===")
        prep_result = self.prepare_batch(limit=limit)
        print("PREPARE DONE:", prep_result)

        print("=== START SEND PHASE ===")
        send_result = self.send_batch(limit=limit)
        print("SEND DONE:", send_result)

        return {
            "prepare": prep_result,
            "send": send_result
        }

    # =========================
    # RETRY FAILED
    # =========================
    def retry_failed(self):
        """
        Повторная отправка ошибок WB
        """
        return self.wb_repo.retry_failed()