import json
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from core.db.models import (
    WBNormalizedProduct,
    WBNormalizedCharacteristic,
    WBPreparedProduct
)


class WBPreparedValidator:
    """
    Валидация финального WB prepared слоя
    """

    @staticmethod
    def validate_dimensions(product: WBNormalizedProduct) -> List[str]:
        errors = []

        if not product.length or not product.width or not product.height:
            errors.append("missing_dimensions")

        if product.length <= 0 or product.width <= 0 or product.height <= 0:
            errors.append("invalid_dimensions_zero")

        if product.length > 300 or product.width > 300 or product.height > 300:
            errors.append("dimensions_too_large")

        return errors

    @staticmethod
    def validate_title(title: str) -> List[str]:
        errors = []

        if not title:
            errors.append("missing_title")

        if len(title) > 60:
            errors.append("title_exceeds_60_chars")

        return errors

    @staticmethod
    def validate_characteristics(chars: List[WBNormalizedCharacteristic]) -> List[str]:
        errors = []

        seen = set()

        for c in chars:
            key = (c.charc_id, str(c.value).strip().lower())

            if key in seen:
                errors.append(f"duplicate_characteristic:{c.charc_name}")
            else:
                seen.add(key)

        return errors


class WBPreparedProductService:
    """
    Сервис формирования WBPreparedProduct

    Делает:
    - выборку normalized данных
    - валидацию
    - сбор payload
    - upsert в WBPreparedProduct
    """

    def __init__(self, db: Session):
        self.db = db

    def fetch_normalized_product(self, product_id_ms: str) -> Optional[WBNormalizedProduct]:
        return (
            self.db.query(WBNormalizedProduct)
            .filter(WBNormalizedProduct.product_id_ms == product_id_ms)
            .first()
        )

    def fetch_characteristics(self, normalized_id: int) -> List[WBNormalizedCharacteristic]:
        return (
            self.db.query(WBNormalizedCharacteristic)
            .filter(WBNormalizedCharacteristic.product_id == normalized_id)
            .all()
        )

    def build_payload(
        self,
        product: WBNormalizedProduct,
        chars: List[WBNormalizedCharacteristic]
    ) -> Dict[str, Any]:

        return {
            "nmID": product.product_id_ms,
            "subjectId": product.subject_id,
            "title": product.wb_title,
            "description": product.wb_description,
            "brand": product.wb_brand,

            "dimensions": {
                "length": product.length,
                "width": product.width,
                "height": product.height,
                "weight": product.weight
            },

            "characteristics": [
                {
                    "id": c.charc_id,
                    "name": c.charc_name,
                    "value": c.value
                }
                for c in chars
            ]
        }

    def build_and_save(self, product_id_ms: str) -> WBPreparedProduct:

        # 1. GET NORMALIZED PRODUCT
        product = self.fetch_normalized_product(product_id_ms)
        if not product:
            raise ValueError("Normalized product not found")

        # 2. GET CHARACTERISTICS
        chars = self.fetch_characteristics(product.id)

        # 3. VALIDATION
        errors = []
        errors += WBPreparedValidator.validate_dimensions(product)
        errors += WBPreparedValidator.validate_title(product.wb_title)
        errors += WBPreparedValidator.validate_characteristics(chars)

        status = "valid" if not errors else "invalid"

        # 4. BUILD PAYLOAD
        payload = self.build_payload(product, chars)

        # 5. UPSERT prepared record
        prepared = (
            self.db.query(WBPreparedProduct)
            .filter(WBPreparedProduct.product_id_ms == product_id_ms)
            .first()
        )

        if not prepared:
            prepared = WBPreparedProduct(
                product_id_ms=product_id_ms,
                wb_normalized_product_id=product.id
            )

        # 6. WRITE DATA
        prepared.payload = json.dumps(payload, ensure_ascii=False)
        prepared.status = status
        prepared.validation_errors = json.dumps(errors, ensure_ascii=False) if errors else None

        # 7. SAVE
        self.db.add(prepared)
        self.db.commit()
        self.db.refresh(prepared)

        return prepared