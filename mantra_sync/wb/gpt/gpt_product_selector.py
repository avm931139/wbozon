from dataclasses import dataclass
from typing import List, Optional

from core.db.connection import get_db_session
from core.db.models import WBNormalizedProduct


@dataclass
class ProductSelectionConfig:
    status: str = "ready_for_gpt"


class GPTProductSelector:
    """
    Выбор товаров для GPT с использованием get_db_session()
    """

    def __init__(self, config: ProductSelectionConfig = ProductSelectionConfig()):
        self.config = config

    # -----------------------------
    # ЗАГРУЗКА ТОВАРОВ
    # -----------------------------

    def get_ready_products(self):
        with get_db_session() as db:
            products = (
                db.query(WBNormalizedProduct)
                .filter(WBNormalizedProduct.status == "ready_for_gpt") #"ready_for_gpt"
                .all()
            )

            # 🔥 ВАЖНО: принудительно выгружаем данные ДО выхода из session
            result = []
            for p in products:
                result.append({
                    "id": p.id,
                    "product_id_ms": p.product_id_ms,
                    "subject_id": p.subject_id,
                    "vendor_code": p.vendor_code,
                    "wb_title": p.wb_title,
                    "wb_description": p.wb_description,
                    "wb_brand": p.wb_brand,
                    "wb_model": p.wb_model,
                })

            return result

    # -----------------------------
    # ИНТЕРАКТИВНЫЙ ВЫБОР
    # -----------------------------

    def select_products_interactive(self) -> List[dict]:
        products = self.get_ready_products()

        if not products:
            print("No products with status = ready_for_gpt")
            return []

        print("\n=== READY PRODUCTS (GPT INPUT) ===")
        print(f"Total: {len(products)}")

        print("\nEnter → ALL products")
        print("Number → batch size")

        user_input = input("Select: ").strip()

        if not user_input:
            selected = products
        elif user_input.isdigit():
            selected = products[:int(user_input)]
        else:
            selected = products

        return selected

    # -----------------------------
    # БЛОКИРОВКА (ВАЖНО: ОТДЕЛЬНАЯ СЕССИЯ)
    # -----------------------------

    def lock_products(self, product_ids: List[int]) -> None:
        with get_db_session() as db:
            db.query(WBNormalizedProduct).filter(
                WBNormalizedProduct.id.in_(product_ids)
            ).update(
                {"status": "processing"},
                synchronize_session=False
            )

    # -----------------------------
    # ОШИБКИ
    # -----------------------------

    def mark_error(self, product_ids: List[int], error: str) -> None:
        with get_db_session() as db:
            db.query(WBNormalizedProduct).filter(
                WBNormalizedProduct.id.in_(product_ids)
            ).update(
                {
                    "status": "error",
                    "validation_errors": error
                },
                synchronize_session=False
            )