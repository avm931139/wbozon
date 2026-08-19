from dataclasses import dataclass
from typing import Dict, List, Any, Tuple


@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str]


class NormalizedForUploadBuilder:

    """
    WB Rules Engine (FIXED):
    - strict_mode: если True → исправляет данные + валидирует
    - если False → только валидирует
    """

    MAX_DIMENSION_CM = 200
    MIN_DIMENSION_CM = 0.1

    MAX_WEIGHT_KG = 100
    MIN_WEIGHT_KG = 0.01

    SINGLE_VALUE_ATTRIBUTES = {
        "Цвет",
        "Бренд",
        "Страна производства",
        "Тип цоколя",
        "Напряжение",
        "Степень пылевлагозащиты",
        "Тип монтажа",
        "Гарантийный срок",
        "Стиль светильника",
    }

    MATERIAL_MAP = {
        "пластиковый": "Пластик",
        "пластик": "Пластик",
        "металл": "Металл",
        "metal": "Металл",
        "plastic": "Пластик",
    }

    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode

    # -----------------------------
    # MAIN
    # -----------------------------
    def build(self, product) -> Tuple[dict, ValidationResult]:

        errors = []

        characteristics = self._normalize_characteristics(product.characteristics, errors)
        dimensions = self._validate_dimensions(product.dimensions, errors)
        weight = self._validate_weight(product.dimensions, errors)

        result = {
            "id_ms": product.id_ms,
            "title": product.title,
            "description": product.description,
            "brand": product.brand,
            "subject_id": product.subject_id,
            "dimensions": {
                **dimensions,
                "weight": weight
            },
            "characteristics": characteristics,
            "images": self._normalize_images(product.images),
        }

        return result, ValidationResult(is_valid=len(errors) == 0, errors=errors)

    # -----------------------------
    # CHARACTERISTICS
    # -----------------------------
    def _normalize_characteristics(self, items: List[dict], errors: List[str]) -> List[dict]:

        by_id: Dict[int, List[dict]] = {}
        for ch in items:
            by_id.setdefault(ch["id"], []).append(ch)

        result = []

        for ch_id, values in by_id.items():

            name = values[0]["name"]

            # SINGLE VALUE
            if name in self.SINGLE_VALUE_ATTRIBUTES:

                unique = list({str(v["value"]).strip() for v in values})

                if len(unique) > 1:
                    errors.append(f"single_value_conflict:{name}:{unique}")

                value = unique[0]

                result.append({
                    "id": ch_id,
                    "name": name,
                    "value": value
                })
                continue

            # MATERIAL / MULTI VALUE WITH NORMALIZATION
            if name == "Материал изделия":

                seen = set()
                merged = []

                for v in values:
                    raw = str(v["value"]).strip().lower()

                    normalized = self.MATERIAL_MAP.get(raw, v["value"])

                    if normalized in seen:
                        continue

                    seen.add(normalized)
                    merged.append(normalized)

                # limit safety (WB-safe)
                merged = merged[:3]

                result.append({
                    "id": ch_id,
                    "name": name,
                    "value": merged
                })
                continue

            # DEFAULT RULE
            seen = set()

            for v in values:
                val = str(v["value"]).strip()

                if not val:
                    continue

                key = (ch_id, val)

                if key in seen:
                    continue

                seen.add(key)

                result.append({
                    "id": ch_id,
                    "name": name,
                    "value": val
                })

        return result

    # -----------------------------
    # DIMENSIONS
    # -----------------------------
    def _validate_dimensions(self, dims: dict, errors: List[str]) -> dict:

        l = float(dims.get("length", 0))
        w = float(dims.get("width", 0))
        h = float(dims.get("height", 0))

        if l <= 0 or w <= 0 or h <= 0:
            errors.append(f"invalid_dimensions_zero:{dims}")

        for name, val in [("length", l), ("width", w), ("height", h)]:

            if val < self.MIN_DIMENSION_CM:
                errors.append(f"dimension_too_small:{name}:{val}")

            if val > self.MAX_DIMENSION_CM:
                errors.append(f"dimension_too_large:{name}:{val}")

        # anomaly detection (soft rule)
        sorted_dims = sorted([l, w, h])

        if sorted_dims[2] > sorted_dims[0] * 50:
            errors.append(f"dimension_anomaly_ratio:{dims}")

        return {
            "length": l,
            "width": w,
            "height": h
        }

    # -----------------------------
    # WEIGHT (FIXED)
    # -----------------------------
    def _validate_weight(self, dims: dict, errors: List[str]) -> float:

        weight = float(dims.get("weight", 0))

        if weight <= 0:
            errors.append("invalid_weight_zero")

            if self.strict_mode:
                weight = 0.1  # SAFE FALLBACK

        if weight < self.MIN_WEIGHT_KG:
            errors.append(f"weight_too_small:{weight}")

            if self.strict_mode:
                weight = self.MIN_WEIGHT_KG

        if weight > self.MAX_WEIGHT_KG:
            errors.append(f"weight_too_large:{weight}")

        return weight

    # -----------------------------
    # IMAGES (FIXED)
    # -----------------------------
    def _normalize_images(self, images: List[str]) -> List[str]:

        seen = set()
        result = []

        for url in images or []:

            if not url:
                continue

            url = url.strip()

            if not url.startswith("http"):
                continue

            if url in seen:
                continue

            seen.add(url)
            result.append(url)

        return result