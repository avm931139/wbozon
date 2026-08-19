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
    ParserProduct, ParserCharacteristics,
    WBSubject, WBCharacteristic,
    WBSubjectMapping, WBCharacteristicMapping,
    WBNormalizedProduct, WBNormalizedSize,
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
    def _process(self, product: ParserProduct) -> bool:

        domain = self._extract_domain(product.url)

        mapping = self.subject_map.get((domain, product.groupe_site))
        if not mapping:
            return False

        chars = self.db.query(ParserCharacteristics).filter(
            ParserCharacteristics.product_id_ms == product.id_ms
        ).all()

        dims = self._extract_dimensions(domain, mapping.subject_id, chars)

        normalized = WBNormalizedProduct(
            product_id_ms=product.id_ms,
            subject_mapping_id=mapping.id,
            subject_id=mapping.subject_id,
            subject_name=mapping.subject_name,
            vendor_code=product.code_ms,
            wb_title=(product.name_site or "")[:60],
            wb_description=(product.description or "")[:5000],
            wb_brand=(product.brand or "")[:100],
            length=dims["length"],
            width=dims["width"],
            height=dims["height"],
            weight=dims["weight"],
            status="ready"
        )

        self.db.add(normalized)
        self.db.flush()

        self.db.add(WBNormalizedSize(
            product_id=normalized.id,
            tech_size="0",
            barcode=product.code_ms,
            stock=0
        ))

        return True

    # =========================
    # CORE LOGIC
    # =========================
    def _extract_dimensions(self, domain, subject_id, characteristics):

        result = {
            "length": 0,
            "width": 0,
            "height": 0,
            "weight": 0
        }

        # === 1. точный mapping ===
        for char in characteristics:
            if not char.group:
                continue

            key = (domain, char.group.name, subject_id)
            mapping = self.char_map.get(key)

            if not mapping or mapping.charc_name == "__SKIP__":
                continue

            transformer = TRANSFORMERS.get(mapping.value_transformer, lambda x: x)
            val = ValueTransformer.extract_number(transformer(char.value))

            dim = mapping.charc_name

            if dim == "weight":
                if self.MIN_WEIGHT <= val <= self.MAX_WEIGHT:
                    result["weight"] = val
            else:
                if 0 < val <= self.MAX_DIM:
                    result[dim] = val

        # === 2. fallback по ключевым словам ===
        for char in characteristics:
            name = (char.group.name if char.group else "").lower()
            val = ValueTransformer.extract_number(char.value)

            for dim, keywords in self.KEYWORDS.items():
                if result[dim] != 0:
                    continue

                if any(k in name for k in keywords):
                    result[dim] = val

        # === 3. дефолты ===
        if result["weight"] == 0:
            result["weight"] = self.DEFAULT_WEIGHT

        for d in ["length", "width", "height"]:
            if result[d] == 0:
                result[d] = 30

        return result

    # =========================
    def _extract_domain(self, url: str) -> str:
        try:
            return urlparse(url).netloc.lower()
        except:
            return ""

class WBNormalizer_deepseek:
    """Нормализует спарсенные товары для загрузки на WB"""

    # Допустимые значения
    MAX_LENGTH_CM = 200   # см
    MAX_WIDTH_CM = 200    # см
    MAX_HEIGHT_CM = 200   # см
    MAX_WEIGHT_KG = 25    # кг
    MIN_WEIGHT_KG = 0.1   # кг
    DEFAULT_WEIGHT = 1  # вес по умолчанию

    def __init__(self, db: Session):
        self.db = db
        self.transformer = ValueTransformer()

    def normalize_products(self, limit: int = None):
        """
        Заполняет wb_normalized_product для всех товаров, у которых есть сопоставление группы
        """
        existing_ids = set(
            row[0] for row in self.db.query(WBNormalizedProduct.product_id_ms).all()
        )

        query = self.db.query(ParserProduct).filter(
            ParserProduct.id_ms.notin_(existing_ids) if existing_ids else True
        )

        if limit:
            query = query.limit(limit)

        products = query.all()

        if not products:
            print("✅ Все товары уже нормализованы")
            return

        # Фильтруем товары, у которых есть сопоставление группы
        valid_products = []
        skipped = []

        for product in products:
            domain = self._extract_domain(product.url)
            mapping = self.db.query(WBSubjectMapping).filter(
                WBSubjectMapping.domain == domain,
                WBSubjectMapping.site_group == product.groupe_site
            ).first()

            if mapping:
                valid_products.append((product, mapping))
            else:
                skipped.append((product.code_ms, product.groupe_site))

        if skipped:
            print(f"\n⚠️ Пропущено {len(skipped)} товаров без сопоставления группы:")
            for code, group in skipped[:10]:
                print(f"   - {code}: {group}")
            if len(skipped) > 10:
                print(f"   ... и еще {len(skipped) - 10}")

        if not valid_products:
            print("❌ Нет товаров для нормализации")
            return

        print(f"\n{'=' * 70}")
        print(f"ЭТАП 2: ЗАПОЛНЕНИЕ НОРМАЛИЗОВАННЫХ ТОВАРОВ")
        print(f"{'=' * 70}")
        print(f"\n📦 Начинаем нормализацию {len(valid_products)} товаров\n")

        success = 0
        errors = 0

        for idx, (product, mapping) in enumerate(valid_products, 1):
            print(f"\n{idx}. {product.code_ms} | {product.name_site[:50]}...")

            try:
                normalized = self._normalize_single_product(product, mapping)
                if normalized:
                    success += 1
                    print(f"   ✅ Нормализован (ID: {normalized.id})")
                else:
                    errors += 1
                    print(f"   ❌ Ошибка: не удалось нормализовать")
            except Exception as e:
                errors += 1
                print(f"   ❌ Ошибка: {e}")
                import traceback
                traceback.print_exc()
                continue

        print(f"\n{'=' * 70}")
        print(f"📊 Результаты нормализации:")
        print(f"   ✅ Успешно: {success}")
        print(f"   ❌ Ошибок: {errors}")
        print(f"   📦 Всего: {len(valid_products)}")
        print(f"{'=' * 70}")

    def _normalize_single_product(self, product: ParserProduct, mapping: WBSubjectMapping) -> Optional[WBNormalizedProduct]:
        """
        Нормализует один товар
        """
        domain = self._extract_domain(product.url)

        # 1. Получаем характеристики товара
        characteristics = self.db.query(ParserCharacteristics).filter(
            ParserCharacteristics.product_id_ms == product.id_ms
        ).all()

        # 2. Извлекаем значения характеристик с использованием WBCharacteristicMapping
        dimensions = self._extract_dimensions_with_mapping(
            domain, mapping.subject_id, characteristics, product.name_site
        )

        # 3. Проверка на нулевые значения
        if dimensions['length'] == 0 or dimensions['width'] == 0 or dimensions['height'] == 0:
            print(f"   ⚠️ Обнаружены нулевые габариты:")
            print(f"      Длина: {dimensions['length']} см, Ширина: {dimensions['width']} см, Высота: {dimensions['height']} см")
            dimensions = self._get_default_dimensions()

        if dimensions['weight'] == 0.0:
            print(f"   ⚠️ Вес не найден, установлен {self.DEFAULT_WEIGHT} кг")
            dimensions['weight'] = self.DEFAULT_WEIGHT

        # 4. Нормализуем текстовые поля
        wb_title = self._normalize_title(product.name_site)
        wb_description = self._normalize_description(product.description)
        wb_brand = self._normalize_brand(product.brand)

        # 5. Создаем нормализованный товар
        normalized = WBNormalizedProduct(
            product_id_ms=product.id_ms,
            subject_mapping_id=mapping.id,
            subject_id=mapping.subject_id,
            subject_name=mapping.subject_name,
            vendor_code=product.code_ms,
            wb_title=wb_title,
            wb_description=wb_description,
            wb_brand=wb_brand,
            length=dimensions['length'],
            width=dimensions['width'],
            height=dimensions['height'],
            weight=dimensions['weight'],
            status="ready"
        )

        self.db.add(normalized)
        self.db.flush()

        # 6. Сохраняем размер
        normalized_size = WBNormalizedSize(
            product_id=normalized.id,
            tech_size="0",
            barcode=product.code_ms,
            stock=0
        )
        self.db.add(normalized_size)

        self.db.commit()

        return normalized

    def _extract_dimensions_with_mapping(self, domain: str, subject_id: int,
                                         characteristics: List[ParserCharacteristics],
                                         product_name: str = None) -> Dict[str, float]:
        """
        Извлекает габариты используя сопоставление характеристик WBCharacteristicMapping
        """
        result = {
            'length': 0,
            'width': 0,
            'height': 0,
            'weight': 0.0
        }

        # Целевые характеристики WB для габаритов
        target_chars = {
            'length': {'keywords': ['длина', 'глубина', 'диаметр'], 'name': 'длину/глубину'},
            'width': {'keywords': ['ширина'], 'name': 'ширину'},
            'height': {'keywords': ['высота'], 'name': 'высоту'},
            'weight': {'keywords': ['вес', 'масса', 'вес брутто'], 'name': 'вес'}
        }

        # Собираем информацию о том, какие характеристики уже сопоставлены
        used_site_chars = set()
        used_wb_chars = set()

        # Сначала проверяем уже существующие сопоставления для этого домена и subject_id
        for char in characteristics:
            if not char.group:
                continue

            site_char_name = char.group.name
            site_char_value = char.value

            # Ищем сопоставление для этого домена, сайтовой характеристики и subject_id
            char_mapping = self.db.query(WBCharacteristicMapping).filter(
                WBCharacteristicMapping.domain == domain,
                WBCharacteristicMapping.site_characteristic == site_char_name,
                WBCharacteristicMapping.subject_id == subject_id
            ).first()

            if char_mapping:
                wb_char_name = char_mapping.charc_name.lower()
                transformer = char_mapping.value_transformer

                transformed_value = self._apply_transformer(site_char_value, transformer)

                # Ищем подходящий размер
                for dim, info in target_chars.items():
                    if any(kw in wb_char_name for kw in info['keywords']):
                        if dim == 'weight':
                            val = self._parse_float(transformed_value)
                            if self.MIN_WEIGHT_KG <= val <= self.MAX_WEIGHT_KG:
                                result[dim] = round(val, 3)
                                used_wb_chars.add(dim)
                                used_site_chars.add(site_char_name)
                                print(
                                    f"   📌 {dim}: '{site_char_name}' = {site_char_value} → {transformed_value} (из сопоставления)")
                        else:
                            val = self._parse_float(transformed_value)
                            if 0 < val <= self.MAX_LENGTH_CM:
                                result[dim] = int(round(val))
                                used_wb_chars.add(dim)
                                used_site_chars.add(site_char_name)
                                print(
                                    f"   📌 {dim}: '{site_char_name}' = {site_char_value} → {transformed_value} см (из сопоставления)")
                        break

        # Проверяем, какие размеры еще не определены
        missing_dims = [dim for dim in ['height', 'width', 'length', 'weight'] if result[dim] == 0]

        if not missing_dims:
            return result

        print(f"\n   ⚠️ Отсутствуют: {', '.join(missing_dims)}")
        print(f"   Использованные характеристики: {used_site_chars if used_site_chars else 'нет'}")

        # Собираем доступные характеристики, которые еще не использовались
        available_chars = []
        for char in characteristics:
            if not char.group:
                continue

            site_char_name = char.group.name
            site_char_value = char.value

            # Пропускаем уже использованные характеристики
            if site_char_name in used_site_chars:
                continue

            # Пропускаем пустые значения
            if not site_char_value or site_char_value.strip() == '':
                continue

            available_chars.append((site_char_name, site_char_value))

        if not available_chars:
            print("   ⚠️ Нет доступных характеристик")
            for dim in missing_dims:
                if dim == 'weight':
                    result[dim] = self.DEFAULT_WEIGHT
                else:
                    result[dim] = 0
            return result

        # Сортируем доступные характеристики: сначала те, которые вероятно подходят
        def relevance_score(item):
            name = item[0].lower()
            score = 0
            if any(kw in name for kw in ['длина', 'ширина', 'высота', 'глубина', 'диаметр', 'вес', 'масса']):
                score += 10
            if any(dim in name for dim in missing_dims):
                score += 5
            return -score  # отрицательный для сортировки по убыванию

        available_chars.sort(key=relevance_score)

        # По очереди запрашиваем недостающие параметры
        dims_order = ['height', 'width', 'length', 'weight']

        for dim in dims_order:
            if result[dim] != 0:
                continue

            if dim == 'weight':
                val = self._ask_for_weight(available_chars, domain, subject_id, product_name, used_site_chars)
                result[dim] = val
            else:
                dim_info = target_chars[dim]
                val = self._ask_for_dimension(dim, dim_info['name'], available_chars, domain, subject_id, product_name,
                                              used_site_chars)
                result[dim] = int(round(val)) if val > 0 else 0

        return result


    def _parse_float(self, value: Any) -> float:
        """Безопасное преобразование в float"""
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(re.sub(r'[^0-9.,]', '', str(value).replace(',', '.')))
        except:
            return 0.0

    def _ask_for_dimension(self, dim: str, dim_name: str, available_chars: List[Tuple[str, str]],
                           domain: str, subject_id: int, product_name: str = None,
                           used_site_chars: set = None) -> float:
        """
        Спрашивает пользователя, какую характеристику использовать для размера
        """
        if used_site_chars is None:
            used_site_chars = set()

        print(f"\n   📏 Выберите характеристику для {dim_name}:")

        if not available_chars:
            print("   ⚠️ Нет доступных характеристик")
            manual_value = input("   Введите значение в см (или 0 для пропуска): ").strip()
            try:
                return float(re.sub(r'[^0-9.,]', '', manual_value.replace(',', '.')))
            except:
                return 0.0

        # Показываем варианты
        options = []
        for i, (name, value) in enumerate(available_chars, 1):
            # Пропускаем уже использованные
            if name in used_site_chars:
                continue

            # Пробуем угадать, подходит ли характеристика
            is_match = any(kw in name.lower() for kw in [dim, 'длина', 'ширина', 'высота', 'глубина', 'диаметр'])
            marker = " 🔍 (возможно)" if is_match else ""
            print(f"      {i}. {name}: {value[:50]}{marker}")
            options.append((name, value))

        # Если после фильтрации не осталось вариантов
        if not options:
            print("   ⚠️ Нет доступных характеристик")
            manual_value = input("   Введите значение в см (или 0 для пропуска): ").strip()
            try:
                return float(re.sub(r'[^0-9.,]', '', manual_value.replace(',', '.')))
            except:
                return 0.0

        print(f"      {len(options) + 1}. Ввести значение вручную")
        print(f"      0. Пропустить (установить 0)")

        while True:
            try:
                choice = input(f"\n   Введите номер (1-{len(options) + 1} или 0): ").strip()

                if choice == "0":
                    return 0.0

                if choice.isdigit():
                    choice_num = int(choice)
                    if 1 <= choice_num <= len(options):
                        name, value = options[choice_num - 1]
                        print(f"\n   Выбрана характеристика: {name} = {value}")
                        need_convert = input("   Нужно преобразовать мм → см? (y/n, Enter - нет): ").strip().lower()

                        transformer = "mm_to_cm" if need_convert == 'y' else "direct"

                        # Сохраняем сопоставление
                        self._save_char_mapping(domain, name, subject_id, dim, transformer)

                        # Преобразуем значение
                        converted = self._apply_transformer(value, transformer)
                        val = self._parse_float(converted)
                        if val > 0:
                            print(f"   ✅ Значение: {val} см")
                            return val
                        else:
                            print(f"   ⚠️ Не удалось преобразовать значение")
                            return 0.0

                    elif choice_num == len(options) + 1:
                        manual_value = input("   Введите значение в см: ").strip()
                        try:
                            val = float(re.sub(r'[^0-9.,]', '', manual_value.replace(',', '.')))
                            if val > 0:
                                return val
                            else:
                                print("   ❌ Значение должно быть больше 0")
                                continue
                        except:
                            print("   ❌ Неверное значение")
                            continue

                print("   ❌ Неверный выбор")
            except KeyboardInterrupt:
                raise

    def _ask_for_weight(self, available_chars: List[Tuple[str, str]],
                        domain: str, subject_id: int, product_name: str = None,
                        used_site_chars: set = None) -> float:
        """
        Спрашивает пользователя, какую характеристику использовать для веса
        """
        if used_site_chars is None:
            used_site_chars = set()

        print(f"\n   ⚖️ Выберите характеристику для веса:")

        if not available_chars:
            print("   ⚠️ Нет доступных характеристик")
            manual_value = input(f"   Введите значение в кг (или 0 для {self.DEFAULT_WEIGHT} кг): ").strip()
            try:
                val = float(re.sub(r'[^0-9.,]', '', manual_value.replace(',', '.')))
                if val == 0:
                    return self.DEFAULT_WEIGHT
                if self.MIN_WEIGHT_KG <= val <= self.MAX_WEIGHT_KG:
                    return val
                else:
                    print(f"   ⚠️ Значение вне диапазона, установлен {self.DEFAULT_WEIGHT} кг")
                    return self.DEFAULT_WEIGHT
            except:
                return self.DEFAULT_WEIGHT

        # Показываем варианты
        options = []
        for i, (name, value) in enumerate(available_chars, 1):
            # Пропускаем уже использованные
            if name in used_site_chars:
                continue

            is_match = any(kw in name.lower() for kw in ['вес', 'масса', 'вес брутто'])
            marker = " 🔍 (возможно)" if is_match else ""
            print(f"      {i}. {name}: {value[:50]}{marker}")
            options.append((name, value))

        # Если после фильтрации не осталось вариантов
        if not options:
            print("   ⚠️ Нет доступных характеристик")
            manual_value = input(f"   Введите значение в кг (или 0 для {self.DEFAULT_WEIGHT} кг): ").strip()
            try:
                val = float(re.sub(r'[^0-9.,]', '', manual_value.replace(',', '.')))
                if val == 0:
                    return self.DEFAULT_WEIGHT
                if self.MIN_WEIGHT_KG <= val <= self.MAX_WEIGHT_KG:
                    return val
                else:
                    print(f"   ⚠️ Значение вне диапазона, установлен {self.DEFAULT_WEIGHT} кг")
                    return self.DEFAULT_WEIGHT
            except:
                return self.DEFAULT_WEIGHT

        print(f"      {len(options) + 1}. Ввести значение вручную")
        print(f"      0. Пропустить (установить {self.DEFAULT_WEIGHT} кг)")

        while True:
            try:
                choice = input(f"\n   Введите номер (1-{len(options) + 1} или 0): ").strip()

                if choice == "0":
                    return self.DEFAULT_WEIGHT

                if choice.isdigit():
                    choice_num = int(choice)
                    if 1 <= choice_num <= len(options):
                        name, value = options[choice_num - 1]
                        print(f"\n   Выбрана характеристика: {name} = {value}")
                        need_convert = input("   Нужно преобразовать г → кг? (y/n, Enter - нет): ").strip().lower()

                        transformer = "g_to_kg" if need_convert == 'y' else "direct"

                        # Сохраняем сопоставление
                        self._save_char_mapping(domain, name, subject_id, 'weight', transformer)

                        # Преобразуем значение
                        converted = self._apply_transformer(value, transformer)
                        val = self._parse_float(converted)

                        if self.MIN_WEIGHT_KG <= val <= self.MAX_WEIGHT_KG:
                            print(f"   ✅ Значение: {val} кг")
                            return val
                        elif val > 0:
                            print(
                                f"   ⚠️ Значение {val} кг вне диапазона ({self.MIN_WEIGHT_KG}-{self.MAX_WEIGHT_KG}), установлен {self.DEFAULT_WEIGHT} кг")
                            return self.DEFAULT_WEIGHT
                        else:
                            print(f"   ⚠️ Не удалось преобразовать значение, установлен {self.DEFAULT_WEIGHT} кг")
                            return self.DEFAULT_WEIGHT

                    elif choice_num == len(options) + 1:
                        manual_value = input(f"   Введите значение в кг (или 0 для {self.DEFAULT_WEIGHT} кг): ").strip()
                        try:
                            val = float(re.sub(r'[^0-9.,]', '', manual_value.replace(',', '.')))
                            if val == 0:
                                return self.DEFAULT_WEIGHT
                            if self.MIN_WEIGHT_KG <= val <= self.MAX_WEIGHT_KG:
                                return val
                            else:
                                print(
                                    f"   ⚠️ Значение {val} кг вне диапазона ({self.MIN_WEIGHT_KG}-{self.MAX_WEIGHT_KG}), установлен {self.DEFAULT_WEIGHT} кг")
                                return self.DEFAULT_WEIGHT
                        except:
                            print(f"   ❌ Неверное значение, установлен {self.DEFAULT_WEIGHT} кг")
                            return self.DEFAULT_WEIGHT

                print("   ❌ Неверный выбор")
            except KeyboardInterrupt:
                raise


    def _save_char_mapping(self, domain: str, site_char: str, subject_id: int,
                           target_dim: str, transformer: str):
        """
        Сохраняет сопоставление характеристики в WBCharacteristicMapping
        """
        # Проверяем, нет ли уже такого сопоставления
        existing = self.db.query(WBCharacteristicMapping).filter(
            WBCharacteristicMapping.domain == domain,
            WBCharacteristicMapping.site_characteristic == site_char,
            WBCharacteristicMapping.subject_id == subject_id
        ).first()

        if existing:
            print(f"   ℹ️ Сопоставление уже существует: {site_char} → {existing.charc_name}")
            return

        new_mapping = WBCharacteristicMapping(
            domain=domain,
            site_characteristic=site_char,
            subject_id=subject_id,
            charc_id=0,  # ID будет заполнен на этапе 3
            charc_name=target_dim,
            value_transformer=transformer
        )
        self.db.add(new_mapping)
        self.db.commit()
        print(f"   ✅ Сохранено сопоставление: '{site_char}' → '{target_dim}' (трансформатор: {transformer})")

    def _apply_transformer(self, value: str, transformer: str) -> Any:
        """Применяет трансформатор к значению"""
        if transformer == "mm_to_cm":
            return self.transformer.mm_to_cm(value)
        elif transformer == "g_to_kg":
            return self.transformer.g_to_kg(value)
        else:
            return self.transformer.direct(value)

    def _get_default_dimensions(self) -> Dict[str, float]:
        """Возвращает значения габаритов по умолчанию"""
        return {
            'length': 30,
            'width': 30,
            'height': 30,
            'weight': self.DEFAULT_WEIGHT
        }

    def _normalize_title(self, title: str) -> str:
        """Нормализует название товара для WB (макс 60 символов)"""
        if not title:
            return "Товар"

        title = ' '.join(title.split())

        if len(title) > 60:
            title = title[:57] + "..."

        return title

    def _normalize_description(self, description: str) -> str:
        """Нормализует описание товара для WB (макс 5000 символов)"""
        if not description:
            return ""

        description = ' '.join(description.split())

        if len(description) > 5000:
            description = description[:4997] + "..."

        return description

    def _normalize_brand(self, brand: str) -> str:
        """Нормализует бренд"""
        if not brand:
            return ""

        brand = ' '.join(brand.split())

        if len(brand) > 100:
            brand = brand[:100]

        return brand

    def _extract_domain(self, url: str) -> str:
        """Извлекает домен из URL"""
        if not url:
            return ""
        if '://' in url:
            start = url.find('://') + 3
            end = url.find('/', start)
            if end == -1:
                end = len(url)
            return url[start:end]
        return ""


def main():
    """Главная функция - этап 2"""
    print("\n" + "=" * 70)
    print("НОРМАЛИЗАЦИЯ ТОВАРОВ ДЛЯ WILDBERRIES - ЭТАП 2")
    print("=" * 70)
    print("\n🔹 Заполнение таблицы wb_normalized_product")
    print("   - Если нет сопоставления для размера/веса - спросит пользователя")
    print("   - Автоматическое сохранение сопоставлений в WBCharacteristicMapping")
    print("   - Конвертация мм → см, г → кг")
    print("   - Проверка на допустимые значения")
    print("=" * 70 + "\n")

    try:
        limit = input("Сколько товаров обработать (Enter - все): ").strip()
        limit = int(limit) if limit else None
    except:
        limit = None

    with get_db_session() as db:
        # normalizer = WBNormalizer(db)
        # normalizer.normalize_products(limit=limit)

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