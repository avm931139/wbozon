"""
Модуль выгрузки новых товаров на Wildberries
Использует эндпоинт: POST /content/v2/cards/upload
"""

import json
import re
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

import requests
from loguru import logger
from sqlalchemy.orm import Session, joinedload

from core.db.connection import get_db_session
from core.db.models import (
    WBNormalizedProduct,
    WBNormalizedSize,
    WBNormalizedCharacteristic,
    WBCharacteristic
)
from settings import Config


@dataclass
class UploadResult:
    """Результат выгрузки одного товара"""
    product_id: int
    vendor_code: str
    success: bool
    wb_nm_id: Optional[int] = None
    wb_imt_id: Optional[int] = None
    error_text: Optional[str] = None


class WBContentAPI:
    """Клиент для работы с Content API Wildberries"""

    BASE_URL = "https://content-api.wildberries.ru"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def upload_cards(self, cards: List[Dict]) -> tuple[bool, str, Optional[Dict]]:
        """Отправляет карточки на создание"""
        url = f"{self.BASE_URL}/content/v2/cards/upload"

        try:
            if not isinstance(cards, list):
                logger.error(f"cards должен быть массивом, получен {type(cards)}")
                return False, "cards должен быть массивом", None

            logger.info(f"Отправка {len(cards)} карточек на WB")
            logger.debug(f"Payload: {json.dumps(cards, ensure_ascii=False, indent=2)[:2000]}")

            response = requests.post(url, headers=self.headers, json=cards, timeout=60)

            if response.status_code == 200:
                data = response.json()
                if data.get("error") is False:
                    logger.info("Запрос на создание карточек принят WB")
                    return True, "", data
                else:
                    error_text = data.get("errorText") or str(data.get("errors", "Неизвестная ошибка WB"))
                    logger.error(f"Ошибка WB: {error_text}")
                    return False, error_text, data
            elif response.status_code == 400:
                error_text = "Ошибка валидации 400"
                logger.error(error_text)
                logger.error(f"Response: {response.text}")
                return False, error_text, None
            elif response.status_code == 401:
                error_text = "Ошибка авторизации: неверный API ключ"
                logger.error(error_text)
                return False, error_text, None
            else:
                error_text = f"HTTP {response.status_code}: {response.text}"
                logger.error(error_text)
                return False, error_text, None

        except requests.exceptions.RequestException as e:
            error_text = f"Ошибка сети: {str(e)}"
            logger.error(error_text)
            return False, error_text, None
        except Exception as e:
            error_text = f"Неизвестная ошибка: {str(e)}"
            logger.exception(error_text)
            return False, error_text, None


class ProductUploader:
    """Загрузчик товаров на Wildberries"""

    # Список числовых характеристик (id, которые должны быть числами)
    NUMBER_CHAR_IDS = {
        90611,   # Количество ламп
        90630,   # Высота предмета
        90652,   # Глубина предмета
        90673,   # Ширина предмета
        169011,  # Световой поток
        355429,  # Мощность
        355430,  # Мощность макс
        354602,  # Площадь освещения
    }

    # Недопустимые значения цветов (нужно заменить)
    COLOR_MAPPING = {
        "золото": "золотой",
        "серебро": "серебристый",
        "бронза": "бронзовый",
        "хром": "хромированный",
        "медь": "медный",
        "черный": "черный",
        "белый": "белый",
        "серый": "серый",
        "бежевый": "бежевый",
        "коричневый": "коричневый",
        "красный": "красный",
        "синий": "синий",
        "зеленый": "зеленый",
        "желтый": "желтый",
        "розовый": "розовый",
        "фиолетовый": "фиолетовый",
        "оранжевый": "оранжевый",
    }

    def __init__(self, api_key: str, batch_size: int = 50):
        self.api = WBContentAPI(api_key)
        self.batch_size = min(batch_size, 100)
        self._char_types_cache = {}
        self._db_session = None

    def _get_db_session(self) -> Session:
        if self._db_session is None:
            self._db_session = get_db_session()
        return self._db_session

    def _get_char_type(self, subject_id: int, char_id: int) -> str:
        """Получает тип характеристики из кэша или БД"""
        cache_key = (subject_id, char_id)

        if cache_key not in self._char_types_cache:
            try:
                session = self._get_db_session()
                wb_char = session.query(WBCharacteristic).filter(
                    WBCharacteristic.subject_id == subject_id,
                    WBCharacteristic.char_id == char_id
                ).first()

                char_type = wb_char.char_type if wb_char else 'string'
                self._char_types_cache[cache_key] = char_type
            except Exception as e:
                logger.warning(f"Не удалось получить тип для char_id={char_id}: {e}")
                self._char_types_cache[cache_key] = 'string'

        return self._char_types_cache[cache_key]

    def get_products_to_upload(self, session: Session, limit: Optional[int] = None) -> List[WBNormalizedProduct]:
        """Получает товары, готовые к выгрузке"""
        query = session.query(WBNormalizedProduct).filter(
            WBNormalizedProduct.status.in_(['ready upload']),
            WBNormalizedProduct.wb_nm_id.is_(None)
        ).options(
            joinedload(WBNormalizedProduct.sizes),
            joinedload(WBNormalizedProduct.characteristics)
        )

        if limit:
            query = query.limit(limit)

        return query.all()

    def _clean_vendor_code(self, vendor_code: str, product_id: int) -> str:
        """
        Очищает vendorCode для WB:
        - Максимальная длина 71 символ
        """
        if not vendor_code:
            return f"TEMP_{product_id}"

        cleaned = vendor_code

        # Обрезаем до 71 символа (ограничение WB)
        if len(vendor_code) > 71:
            cleaned = vendor_code[:71]
            # Убираем подчеркивание в конце если появилось
            cleaned = cleaned.rstrip('_')

        # Если после очистки пусто - генерируем
        if not cleaned:
            cleaned = f"TEMP_{product_id}"

        return cleaned


    def build_wb_variant(self, product: WBNormalizedProduct) -> Optional[Dict]:
        """Строит объект варианта товара для WB API"""

        if not product.vendor_code:
            logger.warning(f"Товар {product.id}: нет vendor_code")
            return None

        if not product.wb_title:
            logger.warning(f"Товар {product.id}: нет wb_title")
            return None

        if not product.subject_id:
            logger.warning(f"Товар {product.id}: нет subject_id")
            return None

        vendor_code = self._clean_vendor_code(product.vendor_code, product.id)
        variant = {
            "vendorCode": vendor_code,
            "wholesale": {
                "enabled": False,
                "quantum": 1
            },
            "title": product.wb_title[:60],
        }

        # Описание
        if product.wb_description:
            description = product.wb_description[:5000]
            variant["description"] = description

        # Бренд
        if product.wb_brand:
            brand = product.wb_brand[:100]
            variant["brand"] = brand

        # Габариты - integer
        variant["dimensions"] = {
            "length": int(round(product.length or 1)),
            "width": int(round(product.width or 1)),
            "height": int(round(product.height or 1)),
            "weightBrutto": float(product.weight or 0.1)
        }

        # Характеристики
        if product.characteristics:
            variant["characteristics"] = self._build_characteristics(
                product.characteristics,
                product.subject_id
            )
        else:
            variant["characteristics"] = []

        # Размеры - для безразмерного товара без wbSize
        if product.sizes:
            variant["sizes"] = self._build_sizes(product.sizes)
        else:
            variant["sizes"] = [{
                "techSize": "0",
                "price": 0,
                "skus": []
            }]

        return variant

    def _build_characteristics(self, characteristics: List[WBNormalizedCharacteristic], subject_id: int) -> List[Dict]:
        """Формирует массив характеристик для WB"""
        if not characteristics:
            return []

        result = []
        for char in characteristics:
            if not char.charc_id:
                continue

            value = char.value
            char_id = char.charc_id


            # Пропускаем пустые значения
            if not value or (isinstance(value, str) and not value.strip()):
                continue

            # Получаем тип характеристики
            char_type = self._get_char_type(subject_id, char_id)
            if char_type == 'size':
                # size - число (int/float)
                try:
                    if isinstance(value, (int, float)):
                        val = value
                    elif isinstance(value, str):
                        # Извлекаем число из строки
                        num_match = re.search(r'\d+[\.,]?\d*', value)
                        if num_match:
                            num_str = num_match.group().replace(',', '.')
                            val = float(num_str) if '.' in num_str else int(num_str)
                        else:
                            val = 0
                    else:
                        val = 0
                except:
                    val = 0

                char_obj = {"id": char_id, "value": val}

            else:  # string
                # string - строка
                if isinstance(value, list):
                    val = ", ".join(str(v).strip() for v in value if v)
                else:
                    val = str(value).strip()

                if not val:
                    continue

                char_obj = {"id": char_id, "value": val}

            result.append(char_obj)

        return result

    def _build_sizes(self, sizes: List[WBNormalizedSize]) -> List[Dict]:
        """
        Формирует массив размеров для WB

        ВАЖНО: Для безразмерного товара НЕ передаем wbSize
        """
        result = []

        for size in sizes:
            tech_size = size.tech_size or "0"
            is_dimensionless = (tech_size == "0" or not tech_size)

            # Для безразмерного товара - минимальный объект
            if is_dimensionless:
                size_obj = {
                    "techSize": "0",
                    "price": 0,
                    "skus": []
                }


            # skus
            if size.barcode and str(size.barcode).strip():
                clean_barcode = re.sub(r'[^0-9]', '', str(size.barcode))
                if clean_barcode and len(clean_barcode) >= 8:
                    size_obj["skus"] = [clean_barcode]
                else:
                    size_obj["skus"] = []
            else:
                size_obj["skus"] = []

            result.append(size_obj)

        return result


    def build_wb_payload(self, products: List[WBNormalizedProduct]) -> List[Dict]:
        """Строит полный payload для WB API"""
        groups: Dict[int, List[WBNormalizedProduct]] = {}
        for product in products:
            if not product.subject_id:
                logger.warning(f"Товар {product.id}: нет subject_id, пропускаем")
                continue

            if product.subject_id not in groups:
                groups[product.subject_id] = []
            groups[product.subject_id].append(product)

        payload = []
        for subject_id, products_in_group in groups.items():
            variants = []
            for product in products_in_group:
                variant = self.build_wb_variant(product)
                if variant:
                    variants.append(variant)

            if variants:
                payload.append({
                    "subjectID": subject_id,
                    "variants": variants
                })

        return payload

    def update_product_after_upload(self, session: Session, product: WBNormalizedProduct,
                                    result: UploadResult):
        """Обновляет данные товара в БД после выгрузки"""
        if result.success and result.wb_nm_id:
            product.status = "uploaded"
            product.wb_nm_id = result.wb_nm_id
            product.wb_imt_id = result.wb_imt_id
            product.uploaded_at = datetime.now()
            logger.info(f"Товар {product.vendor_code} успешно выгружен, nmID={result.wb_nm_id}")
        elif result.success:
            product.status = "processing"
            product.validation_errors = "Товар отправлен на обработку, ждет обновления mn_id после обмена"
            logger.info(f"Товар {product.vendor_code} отправлен на обработку")
        else:
            product.status = "error"
            product.validation_errors = json.dumps({
                "upload_error": result.error_text,
                "timestamp": int(time.time())
            }, ensure_ascii=False)
            logger.error(f"Товар {product.vendor_code} не выгружен: {result.error_text}")

        session.add(product)

    def run(self, limit: Optional[int] = None) -> List[UploadResult]:
        """Запускает процесс выгрузки"""
        results = []

        with get_db_session() as session:
            self._db_session = session

            products = self.get_products_to_upload(session, limit)

            if not products:
                logger.info("Нет товаров для выгрузки")
                return results

            logger.info(f"Найдено {len(products)} товаров для выгрузки")

            for i in range(0, len(products), self.batch_size):
                batch = products[i:i + self.batch_size]
                logger.info(f"Обработка батча {i // self.batch_size + 1}, товаров: {len(batch)}")

                payload = self.build_wb_payload(batch)

                if not payload:
                    logger.warning("Не удалось построить payload для батча")
                    for product in batch:
                        result = UploadResult(
                            product_id=product.id,
                            vendor_code=product.vendor_code,
                            success=False,
                            error_text="Ошибка формирования данных"
                        )
                        results.append(result)
                        self.update_product_after_upload(session, product, result)
                    session.commit()
                    continue

                success, error_text, response_data = self.api.upload_cards(payload)

                if success:
                    for product in batch:
                        result = UploadResult(
                            product_id=product.id,
                            vendor_code=product.vendor_code,
                            success=True,
                            error_text=None
                        )

                        if response_data and 'data' in response_data:
                            data = response_data['data']
                            if 'cards' in data:
                                for card in data['cards']:
                                    if card.get('vendorCode') == product.vendor_code:
                                        result.wb_nm_id = card.get('nmID')
                                        result.wb_imt_id = card.get('imtID')
                                        break
                            elif 'nmID' in data:
                                result.wb_nm_id = data.get('nmID')
                                result.wb_imt_id = data.get('imtID')

                        results.append(result)
                        self.update_product_after_upload(session, product, result)
                else:
                    for product in batch:
                        result = UploadResult(
                            product_id=product.id,
                            vendor_code=product.vendor_code,
                            success=False,
                            error_text=error_text
                        )
                        results.append(result)
                        self.update_product_after_upload(session, product, result)

                session.commit()
                self._char_types_cache.clear()

                if i + self.batch_size < len(products):
                    time.sleep(1)

        return results


def main():
    """Точка входа для запуска выгрузки"""
    logger.add("logs/wb_upload.log", rotation="1 day", retention="30 days")

    api_key = Config.API_KEY_WB_CONTENT
    if not api_key:
        logger.error("Не найден API_KEY_WB в настройках")
        return

    uploader = ProductUploader(api_key=api_key, batch_size=30)
    results = uploader.run(limit=100)

    success_count = sum(1 for r in results if r.success)
    error_count = len(results) - success_count

    logger.info(f"Выгрузка завершена. Успешно: {success_count}, Ошибок: {error_count}")

    if error_count > 0:
        logger.warning("Список ошибок:")
        for r in results:
            if not r.success:
                logger.warning(f"  {r.vendor_code}: {r.error_text}")


if __name__ == "__main__":
    main()