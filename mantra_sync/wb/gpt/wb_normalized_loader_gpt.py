from datetime import datetime
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from core.db.models import (
    WBNormalizedProduct,
    WBNormalizedCharacteristic
)


class WBNormalizedLoader:
    """
    Загрузка результата GPT в нормализованные таблицы WB
    """

    # -------------------------------------------------
    # MAIN ENTRY
    # -------------------------------------------------

    def save(self, db: Session, product_id_ms: str, gpt_result: Dict[str, Any]) -> WBNormalizedProduct:
        """
        Сохраняет нормализованный продукт + характеристики
        """

        product = self._get_or_create_product(db, product_id_ms, gpt_result)

        self._update_product_fields(product, gpt_result)

        # очищаем старые характеристики (если повторный прогон)
        product.characteristics.clear()

        # загружаем новые характеристики
        self._save_characteristics(
            db=db,
            product=product,
            characteristics=gpt_result.get("wb_characteristics", [])
        )

        db.add(product)
        db.commit()
        db.refresh(product)

        return product

    # -------------------------------------------------
    # PRODUCT UPSERT
    # -------------------------------------------------

    def _get_or_create_product(
        self,
        db: Session,
        product_id_ms: str,
        gpt_result: Dict[str, Any]
    ) -> WBNormalizedProduct:

        product = (
            db.query(WBNormalizedProduct)
            .filter(WBNormalizedProduct.product_id_ms == product_id_ms)
            .first()
        )

        if product:
            return product

        return WBNormalizedProduct(
            product_id_ms=product_id_ms,
            subject_id=gpt_result.get("subject_id", 0),
            vendor_code="",
            wb_title="",
            status="draft"
        )

    # -------------------------------------------------
    # UPDATE PRODUCT FIELDS
    # -------------------------------------------------

    def _update_product_fields(self, product: WBNormalizedProduct, data: Dict[str, Any]) -> None:

        product.vendor_code = data.get("vendor_code") or product.vendor_code
        product.wb_title = data.get("wb_title") or product.wb_title
        product.wb_description = data.get("wb_description")
        product.wb_model = data.get("wb_model")

        product.status = data.get("status", "draft")

        dims = data.get("dimensions") or {}

        product.length = dims.get("length") or 0
        product.width = dims.get("width") or 0
        product.height = dims.get("height") or 0
        product.weight = dims.get("weight") or 0.0

        product.updated_at = datetime.now()

    # -------------------------------------------------
    # CHARACTERISTICS
    # -------------------------------------------------

    def _save_characteristics(
        self,
        db: Session,
        product: WBNormalizedProduct,
        characteristics: List[Dict[str, Any]]
    ) -> None:

        for c in characteristics:
            if c.get("value") is None:
                continue  # пропускаем пустые значения

            char = WBNormalizedCharacteristic(
                product=product,
                charc_id=c["char_id"],
                charc_name=c.get("char_name"),
                value=self._normalize_value(c["value"]),
                value_type=self._detect_type(c["value"]),
                source_char_id=c.get("source_char_id")
            )

            db.add(char)

    # -------------------------------------------------
    # HELPERS
    # -------------------------------------------------

    def _normalize_value(self, value: Any) -> str:
        """
        Приведение значения к строке (WB-safe)
        """
        if isinstance(value, list):
            return "; ".join(map(str, value))
        return str(value)

    def _detect_type(self, value: Any) -> str:
        """
        Определение типа значения
        """
        if isinstance(value, list):
            return "array"
        if isinstance(value, (int, float)):
            return "number"
        return "string"