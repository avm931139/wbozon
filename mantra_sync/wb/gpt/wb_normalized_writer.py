import json
from typing import Dict, Any, List

from core.db.connection import get_db_session
from core.db.models import (
    WBNormalizedProduct,
    WBNormalizedCharacteristic,
    WBCharacteristic
)


class WBNormalizedWriter:

    # -------------------------------------------------
    # MAIN ENTRY
    # -------------------------------------------------

    def save(self, product_id: int, product_id_ms: str, gpt_data: Dict[str, Any]):
        with get_db_session() as db:

            # 1. UPSERT PRODUCT
            product = self._upsert_product(db, product_id_ms, gpt_data)

            # 2. DELETE OLD CHARACTERISTICS
            self._delete_characteristics(db, product_id_ms)

            # 3. INSERT NEW CHARACTERISTICS
            self._insert_characteristics(db, product_id, product_id_ms, gpt_data.get("wb_characteristics", []))

            return product.id

    # -------------------------------------------------
    # PRODUCT UPSERT
    # -------------------------------------------------

    def _upsert_product(self, db, product_id_ms: str, data: Dict[str, Any]) -> WBNormalizedProduct:

        product = (
            db.query(WBNormalizedProduct)
            .filter(WBNormalizedProduct.product_id_ms == product_id_ms)
            .first()
        )

        dimensions = data.get("dimensions", {}) or {}

        if not product:
            product = WBNormalizedProduct(
                product_id_ms=product_id_ms
            )
            db.add(product)

        # --- update fields
        product.subject_id = data.get("subject_id") or product.subject_id
        # product.subject_name = data.get("subject_name")

        product.vendor_code = data.get("vendor_code", "")
        product.wb_title = data.get("wb_title", "")
        product.wb_description = data.get("wb_description")
        product.wb_model = data.get("wb_model")

        # бренд если есть
        # product.wb_brand = data.get("wb_brand")

        # --- dimensions
        product.length = self._to_int(dimensions.get("length"))
        product.width = self._to_int(dimensions.get("width"))
        product.height = self._to_int(dimensions.get("height"))
        product.weight = self._to_float(dimensions.get("weight"))

        if product.length == 0 or product.width == 0 or product.height == 0 or product.weight == 0:
            product.status = "rewiew"

        if product.length == None or product.width == None or product.height == None or product.weight == None:
            product.status = "rewiew"


        product.status = data.get("status", "draft")

        return product

    # -------------------------------------------------
    # CHARACTERISTICS
    # -------------------------------------------------

    def _delete_characteristics(self, db, product_id_ms: str):
        db.query(WBNormalizedCharacteristic).filter(
            WBNormalizedCharacteristic.product_id_ms == product_id_ms
        ).delete()

    def _insert_characteristics(self, db, product_id: int, product_id_ms:str, characteristics: List[Dict]):

        if not characteristics:
            return

        # подтянем названия характеристик WB
        char_ids = [c.get("char_id") for c in characteristics if c.get("char_id")]

        wb_chars = (
            db.query(WBCharacteristic)
            .filter(WBCharacteristic.char_id.in_(char_ids))
            .all()
        )

        char_name_map = {c.char_id: c.char_name for c in wb_chars}

        objects = []

        for c in characteristics:
            value = c.get("value")

            if value is None:
                continue

            obj = WBNormalizedCharacteristic(
                product_id=product_id,
                product_id_ms=product_id_ms,
                charc_id=c.get("char_id"),
                charc_name=char_name_map.get(c.get("char_id")),
                value=str(value),
                value_type=self._detect_type(value)
            )

            objects.append(obj)

        if objects:
            db.bulk_save_objects(objects)

    # -------------------------------------------------
    # HELPERS
    # -------------------------------------------------

    def _detect_type(self, value) -> str:
        if isinstance(value, (int, float)):
            return "number"
        if isinstance(value, list):
            return "array"
        return "string"

    def _to_int(self, v):
        try:
            return int(float(v)) if v is not None else 0
        except:
            return 0

    def _to_float(self, v):
        try:
            return float(v) if v is not None else 0.0
        except:
            return 0.0