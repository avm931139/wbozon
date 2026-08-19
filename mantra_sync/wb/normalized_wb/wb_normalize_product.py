"""
Модуль нормализации товаров для Wildberries
ЭТАП 2: Заполнение wb_normalized_product с использованием сопоставления характеристик
"""

import re
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Any
from sqlalchemy.orm import Session

from core.db.connection import get_db_session
from core.db.models import (
    ParserProduct, ParserCharacteristics, ParserGroupCharacteristics,
    WBSubject, WBCharacteristic,
    WBSubjectMapping, WBCharacteristicMapping,
    WBNormalizedProduct, WBNormalizedSize, WBNormalizedProductImage
)


class ValueTransformer_deppseek:
    """
    Класс для преобразования значений характеристик
    """

    @staticmethod
    def mm_to_cm(value: str) -> float:
        """Преобразует миллиметры в сантиметры"""
        try:
            num = float(re.sub(r'[^0-9.,]', '', str(value).replace(',', '.')))
            return round(num / 10, 1)
        except:
            return 0.0

    @staticmethod
    def g_to_kg(value: str) -> float:
        """Преобразует граммы в килограммы"""
        try:
            num = float(re.sub(r'[^0-9.,]', '', str(value).replace(',', '.')))
            return round(num / 1000, 3)
        except:
            return 0.0

    @staticmethod
    def direct(value: str) -> str:
        """Прямое преобразование без изменений"""
        return str(value).strip()

    @staticmethod
    def extract_number(value: str) -> float:
        """Извлекает число из строки"""
        try:
            return float(re.sub(r'[^0-9.,]', '', str(value).replace(',', '.')))
        except:
            return 0.0


import re
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from core.db.models import (
    ParserProduct, ParserCharacteristics,
    WBSubjectMapping, WBCharacteristicMapping,
    WBNormalizedProduct, WBNormalizedSize,
)

logger = logging.getLogger(__name__)


# =========================
# TRANSFORMERS
# =========================
class ValueTransformer:

    @staticmethod
    def extract_number(value: str) -> float:
        if not value:
            return 0.0
        match = re.search(r"\d+[.,]?\d*", str(value))
        if not match:
            return 0.0
        return float(match.group(0).replace(",", "."))

    @staticmethod
    def mm_to_cm(value: str) -> float:
        num = ValueTransformer.extract_number(value)
        return round(num / 10, 1) if num else 0.0

    @staticmethod
    def g_to_kg(value: str) -> float:
        num = ValueTransformer.extract_number(value)
        return round(num / 1000, 3) if num else 0.0


TRANSFORMERS = {
    "mm_to_cm": ValueTransformer.mm_to_cm,
    "g_to_kg": ValueTransformer.g_to_kg,
    "direct": lambda x: x
}


# =========================
# NORMALIZER
# =========================
class WBNormalizer:

    MAX_DIM = 200
    MAX_WEIGHT = 25
    MIN_WEIGHT = 0.1
    DEFAULT_WEIGHT = 1

    KEYWORDS = {
        "length": ["длина", "глубина", "диаметр"],
        "width": ["ширина"],
        "height": ["высота"],
        "weight": ["вес", "масса"]
    }

    # Ключевые слова для поиска штрихкода
    BARCODE_KEYWORDS = ["штрихкод", "штрих-код", "barcode", "ean", "штрих код", "баркод"]

    def __init__(self, db: Session, batch_size: int = 50):
        self.db = db
        self.batch_size = batch_size

        self.char_map = {}
        self.subject_map = {}

        self._load_mappings()

    # =========================
    # PRELOAD
    # =========================
    def _load_mappings(self):

        for m in self.db.query(WBCharacteristicMapping).all():
            key = (m.domain, m.site_characteristic, m.subject_id)
            self.char_map[key] = m

        for m in self.db.query(WBSubjectMapping).all():
            key = (m.domain, m.site_group)
            self.subject_map[key] = m

    # =========================
    # MAIN
    # =========================
    def normalize_products(self, limit: int = None):

        subquery = self.db.query(WBNormalizedProduct.product_id_ms)

        query = self.db.query(ParserProduct).filter(
            ~ParserProduct.id_ms.in_(subquery)
        )

        if limit:
            query = query.limit(limit)

        products = query.all()

        logger.info(f"Products to process: {len(products)}")

        success = 0

        for idx, product in enumerate(products, 1):

            try:
                if self._process(product):
                    success += 1

                if idx % self.batch_size == 0:
                    self.db.commit()
                    logger.info(f"Batch committed: {idx}")

            except Exception as e:
                logger.exception(f"Error: {product.code_ms} | {e}")

        self.db.commit()
        logger.info(f"Done. Success: {success}")

    # =========================
    def _get_barcode_from_characteristics(self, product: ParserProduct) -> Optional[str]:
        """
        Извлекает штрихкод из характеристик товара
        """
        try:
            # Получаем все характеристики товара
            characteristics = self.db.query(ParserCharacteristics).filter(
                ParserCharacteristics.product_id_ms == product.id_ms
            ).all()

            for char in characteristics:
                # Получаем название группы характеристики
                group = self.db.query(ParserGroupCharacteristics).filter(
                    ParserGroupCharacteristics.id == char.groupe_characteristics
                ).first()

                if group:
                    group_name_lower = group.name.lower().strip()
                    char_value = char.value.strip() if char.value else ""

                    # Проверяем, является ли эта группа характеристикой для штрихкода
                    for keyword in self.BARCODE_KEYWORDS:
                        if keyword in group_name_lower:
                            # Очищаем значение - оставляем только цифры
                            barcode = re.sub(r'[^0-9]', '', char_value)
                            if barcode and len(barcode) >= 8:  # Штрихкод обычно 8-14 цифр
                                logger.debug(f"Found barcode: {barcode} for product {product.code_ms}")
                                return barcode

            logger.debug(f"No barcode found for product {product.code_ms}")
            return None

        except Exception as e:
            logger.warning(f"Error getting barcode for {product.code_ms}: {e}")
            return None

    # =========================
    def _process(self, product: ParserProduct) -> bool:
        try:
            domain = self._extract_domain(product.url)

            mapping = self.subject_map.get((domain, product.groupe_site))
            if not mapping:
                logger.warning(f"No subject mapping for {domain} / {product.groupe_site}")
                return False

            ms_in = product.id_ms.split('-')
            code_in = product.code_ms[4:] if len(product.code_ms) > 4 else product.code_ms

            vendor_code = ms_in[0] + '*' + code_in + ' ' + (product.name_site or "")

            normalized = WBNormalizedProduct(
                product_id_ms=product.id_ms,
                subject_mapping_id=mapping.id,
                subject_id=mapping.subject_id,
                subject_name=mapping.subject_name,
                vendor_code=vendor_code[:300],
                wb_title=(product.name_site or "")[:60],
                wb_description=(product.description or "")[:5000],
                wb_brand=(product.brand or "")[:100],
                wb_model=(product.articul_site or "")[:300],
                status="ready_for_gpt"
            )

            self.db.add(normalized)
            self.db.flush()

            # Получаем штрихкод из характеристик
            barcode = self._get_barcode_from_characteristics(product)

            # Добавляем размер с штрихкодом
            self.db.add(WBNormalizedSize(
                product_id=normalized.id,
                tech_size="0",
                barcode=barcode or "",  # Если штрихкод не найден - пустая строка
                stock=0
            ))

            str_image = self._image_list(product)

            self.db.add(WBNormalizedProductImage(
                product_id_ms=product.id_ms,
                url=str_image,
            ))

            return True
        except Exception as e:
            logger.exception(f"Error in _process: {e}")
            return False

    def _image_list(self, product: ParserProduct) -> str:
        if not product or not product.images:
            return ""

        # убираем фигурные скобки
        cleaned = product.images.strip().strip("{}")

        # разбиваем по запятой
        urls = [u.strip() for u in cleaned.split(",") if u.strip()]

        # удаляем дубли с сохранением порядка
        unique_urls = list(dict.fromkeys(urls))

        # собираем через ;
        return ";".join(unique_urls)

    # =========================
    # CORE LOGIC
    # =========================

    # =========================
    def _extract_domain(self, url: str) -> str:
        try:
            return urlparse(url).netloc.lower()
        except:
            return ""


def main():
    """Главная функция - этап 2"""
    print("\n" + "=" * 70)
    print("НОРМАЛИЗАЦИЯ ТОВАРОВ ДЛЯ WILDBERRIES - ЭТАП 2")
    print("=" * 70)
    print("\n🔹 Заполнение таблицы wb_normalized_product")
    print("=" * 70 + "\n")

    try:
        limit = input("Сколько товаров обработать (Enter - все): ").strip()
        limit = int(limit) if limit else None
    except:
        limit = None

    with get_db_session() as db:
        normalizer = WBNormalizer(db)
        normalizer.normalize_products(limit=limit)

    print("\n✅ Нормализация товаров завершена!")
    input("\nНажмите Enter для выхода...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Программа остановлена пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()