from typing import Dict, Any, List, Optional
import json
from core.db.models import WBCharacteristic


class GPTPromptBuilder:

    # -------------------------------------------------
    # vendor_code
    # -------------------------------------------------

    def split_vendor_code(self, vendor_code: str) -> Dict[str, str]:
        parts = vendor_code.strip().split()

        base_code = parts[0] if parts else ""
        article = ""

        for p in reversed(parts):
            if any(c.isdigit() for c in p) and any(c.isalpha() for c in p):
                article = p
                break

        if not article and len(parts) > 1:
            article = parts[-1]

        return {
            "base_vendor_code": base_code,
            "article": article,
        }

    def build_vendor_code(self, vendor_code: str) -> str:
        parsed = self.split_vendor_code(vendor_code)
        return f"{parsed['base_vendor_code']} {parsed['article']}".strip()[:72]

    # -------------------------------------------------
    # WB schema
    # -------------------------------------------------

    def build_wb_schema(self, wb_characteristics: List[WBCharacteristic]) -> List[Dict]:
        return [
            {
                "char_id": w['char_id'],
                "char_name": w['char_name'],
                "char_type": w['type'],
                "is_required": w['required'],
                "unit_name": w['unit'],

            }
            for w in wb_characteristics
        ]

    def extract_required(self, wb_characteristics: List[WBCharacteristic]) -> List[Dict]:
        return [
            {
                "char_id": w['char_id'],
                "char_name": w['char_name'],
                "char_type": w['type'],
                "unit_name": w['unit'],
            }
            for w in wb_characteristics
            if w['required']
        ]

    # -------------------------------------------------
    # 🔥 NEW: SOURCE CONTEXT BUILDER
    # -------------------------------------------------

    def build_characteristics_source_map(self, characteristics: List[Dict]) -> str:
        grouped = {}

        for c in characteristics:
            raw_group = c.get("group")

            # 🔥 обязательно приводим к строке
            if hasattr(raw_group, "name"):
                group = raw_group.name
            else:
                group = str(raw_group) if raw_group else "unknown"

            if group not in grouped:
                grouped[group] = []

            grouped[group].append(c["value"])

        return json.dumps(grouped, ensure_ascii=False)

    # -------------------------------------------------
    # MAIN PROMPT
    # -------------------------------------------------

    def build_prompt(
        self,
        product: dict,
        characteristics: List[Dict],
        wb_characteristics: List[WBCharacteristic],
    ) -> Dict[str, Any]:

        parsed_vendor = self.split_vendor_code(product.get("vendor_code", ""))
        final_vendor_code = self.build_vendor_code(product.get("vendor_code", ""))

        wb_schema = self.build_wb_schema(wb_characteristics)
        required_chars = self.extract_required(wb_characteristics)

        # 🔥 НОВОЕ: структурированный источник для поиска значений
        characteristics_source_map = self.build_characteristics_source_map(characteristics)


        prompt = {
            "task": "WB_PRODUCT_MAPPING",

            # -------------------------------------------------
            # RULES
            # -------------------------------------------------
            "rules": [
                "STRICT: заполнить ВСЕ required характеристики WB",
                "STRICT: использовать ТОЛЬКО provided characteristics как источник данных",
                "Если значение не найдено → null",
                "НЕ выдумывать размеры - должны быть в см!, вес, очень внимательно их заполнять контролировать",
                "Размеры и вес брать только из упаковочных данных (если есть тара упаковка коробка и тд) если нет null",

                # VENDOR CODE RULES
                "vendor_code max 72 chars!",
                "STRICT vendor_code format:",
                "1. vendor_code ДОЛЖЕН начинаться с исходного кода (vendor_code_raw)",
                "2. НЕЛЬЗЯ дублировать vendor_code_raw",
                "3. После vendor_code_raw добавить артикул/модель товара",
                "4. Артикул брать из wb_model ИЛИ извлекать из названия товара",
                "5. Итоговый формат: '<vendor_code_raw> <article>'",
                "6. Если article уже содержится в vendor_code_raw → НЕ добавлять повторно",
                "7. Запрещено повторять одну и ту же часть дважды",
                "8. Итоговая строка должна быть осмысленной и читаемой",

                "title max 60 chars",
                "description max 2500 chars должно содержать лаконичное и продающее описание по ключам для товара",
                "Если missing required fields → status=review"
            ],

            # -------------------------------------------------
            # 🔥 REQUIRED FIELDS
            # -------------------------------------------------
            "required_wb_characteristics": required_chars,

            # -------------------------------------------------
            # FULL WB SCHEMA
            # -------------------------------------------------
            "wb_schema": wb_schema,

            # -------------------------------------------------
            # WHERE TO SEARCH VALUES
            # -------------------------------------------------
            "characteristics_source_map": characteristics_source_map,

            # -------------------------------------------------
            # PRODUCT
            # -------------------------------------------------
            "product": {
                "product_id_ms": product.get("product_id_ms"),
                "subject_id": product.get("subject_id"),
                "subject_name": product.get("subject_name"),

                "vendor_code_raw": product.get("vendor_code"),
                "vendor_code_target": final_vendor_code,

                "article_hint": parsed_vendor["article"],

                "name_site": product.get("name_site"),
                "wb_title": product.get("wb_title"),
                "wb_brand": product.get("wb_brand"),
                "wb_model": product.get("wb_model"),
            },

            # -------------------------------------------------
            # RAW INPUT
            # -------------------------------------------------
            "characteristics": json.dumps(characteristics),

            # -------------------------------------------------
            # OUTPUT CONTRACT
            # -------------------------------------------------
            "output_format": {
                "vendor_code": "string",
                "wb_title": "string",
                "wb_model": "string",
                "wb_description": "string",

                "wb_characteristics": [
                    {
                        "char_id": "int",
                        "value": "any"
                    }
                ],

                "dimensions": {
                    "length": "int | null",
                    "width": "int | null",
                    "height": "int | null",
                    "weight": "float | null"
                },

                "status": "ready | review"
            },

            "strict": True
        }

        print("characteristics_source_map" in prompt)

        return prompt