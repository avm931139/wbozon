# wb/card_updater.py
import requests
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_, cast, String

from core.classes import Wb
from settings import Config
from wb.endpoind_wb import update_foto_cards_wb_endp, content_api_base_url_wb
from core.db.models import WbCard
from core.db.models import WBNormalizedProduct, WBNormalizedProductImage

logger = logging.getLogger(__name__)


class WbCardUpdaterFoto:
    """
    Класс для обновления фото карточек товаров на Wildberries
    Использует метод /content/v3/media/save

    Логика работы:
    1. Находит карточки в WbCard с пустым полем photos
    2. По vendor_code находит WBNormalizedProduct
    3. По product_id_ms получает фото из WBNormalizedProductImage
    4. Отправляет фото на WB
    5. Обновляет поле photos в WbCard
    """

    def __init__(self, db_session: Session):
        self.db = db_session
        self.wb_client = Wb()
        self.base_url = content_api_base_url_wb
        self.update_endpoint = update_foto_cards_wb_endp  # /content/v3/media/save

    def get_headers(self) -> Dict[str, str]:
        """Получение заголовков для API запросов"""
        return self.wb_client.get_headers_for_content()

    # ======================== ПОЛУЧЕНИЕ КАРТОЧЕК ========================

    def get_cards_without_photos(self, limit: Optional[int] = None) -> List[WbCard]:
        """
        Получает карточки из WbCard, у которых нет фото
        Для PostgreSQL используем cast к строке
        """
        query = self.db.query(WbCard).filter(
            or_(
                WbCard.photos.is_(None),
                cast(WbCard.photos, String) == '{}',
                cast(WbCard.photos, String) == 'null'
            )
        )

        if limit:
            query = query.limit(limit)

        return query.all()

    # ======================== ПОЛУЧЕНИЕ ФОТО ========================

    def get_photos_from_normalized(self, vendor_code: str) -> List[Dict[str, Any]]:
        """
        Получает фото из таблицы WBNormalizedProductImage по vendor_code
        Возвращает список словарей с полями url, isMain, order
        """
        # 1. Ищем нормализованный продукт по vendor_code
        unique_vendor_part = vendor_code.split()[0] if ' ' in vendor_code else vendor_code

        normalized = self.db.query(WBNormalizedProduct).filter(
            WBNormalizedProduct.vendor_code.like(f"{unique_vendor_part}%")
        ).first()

        if not normalized:
            logger.warning(f"Нет нормализованных данных для vendor_code: {vendor_code}")
            return []

        # 2. Получаем фото по product_id_ms
        images = self.db.query(WBNormalizedProductImage).filter(
            WBNormalizedProductImage.product_id_ms == normalized.product_id_ms
        ).order_by(WBNormalizedProductImage.position).all()

        if not images:
            logger.info(f"Нет фото для product_id_ms: {normalized.product_id_ms}")
            return []

        # 3. Возвращаем список словарей
        photos = []
        for idx, img in enumerate(images):
            photos.append({
                "url": img.url,
                "isMain": (idx == 0),
                "order": idx + 1
            })

        return photos

    # ======================== ПРОВЕРКА ФОТО ========================

    def check_image_url(self, url: str) -> bool:
        """Проверяет доступность изображения для WB"""
        # Очищаем URL от лишних пробелов и символов
        url = url.strip()
        if not url:
            return False

        # Пропускаем явно битые ссылки (содержат разделители внутри)
        if ';' in url:
            return False

        # Проверяем расширение файла
        allowed_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        if not any(ext in url.lower() for ext in allowed_extensions):
            logger.warning(f"Неподдерживаемый формат фото: {url}")
            return False

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            # Используем HEAD запрос для проверки
            response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                return content_type.startswith('image/')
            return False
        except Exception as e:
            logger.debug(f"Ошибка проверки URL {url}: {e}")
            return False

    def filter_valid_urls(self, photos: List[Dict[str, Any]]) -> List[str]:
        """
        Фильтрует только рабочие URL из списка словарей
        Поддерживает строки с разделителями ; внутри url
        """
        valid_urls = []

        for photo_dict in photos:
            if not isinstance(photo_dict, dict) or "url" not in photo_dict:
                continue

            raw_url = photo_dict["url"].strip()
            if not raw_url:
                continue

            # Разбиваем строку по точке с запятой (если есть несколько URL)
            parts = raw_url.split(';')

            for part in parts:
                cleaned = part.strip()
                if not cleaned:
                    continue

                # Дополнительная очистка от мусора
                if ';' in cleaned:
                    cleaned = cleaned.split(';')[0].strip()

                # Проверяем, что URL выглядит как ссылка на изображение
                if cleaned.startswith('http') and any(
                        ext in cleaned.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                    if self.check_image_url(cleaned):
                        valid_urls.append(cleaned)
                    else:
                        logger.warning(f"Фото недоступно (404): {cleaned}")
                else:
                    logger.warning(f"Некорректная ссылка на фото: {cleaned}")

        return valid_urls

    # ======================== ФОРМИРОВАНИЕ PAYLOAD ========================

    def build_update_payload(self, nm_id: int, photo_urls: List[str]) -> Dict[str, Any]:
        """
        Формирует payload для обновления фото
        Для метода /content/v3/media/save
        """
        return {
            "nmId": int(nm_id),
            "data": photo_urls
        }

    # ======================== ОТПРАВКА ЗАПРОСА ========================

    def send_update_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Отправляет запрос на обновление фото"""
        url = f"{self.base_url}{self.update_endpoint}"
        headers = self.get_headers()

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            logger.info(
                f"Успешно отправлено обновление для nmId={payload.get('nmId')}, фото: {len(payload.get('data', []))}")
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при отправке запроса: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Ответ WB: {e.response.text}")
            raise

    # ======================== ОСНОВНЫЕ МЕТОДЫ ========================

    def update_card_photos(self, nm_id: int, vendor_code: str, save_to_db: bool = True) -> Dict[str, Any]:
        """
        Обновляет фото для одной карточки
        """
        # 1. Получаем фото из нормализованных данных
        photos = self.get_photos_from_normalized(vendor_code)

        if not photos:
            return {"status": "skipped", "reason": "no_photos", "nm_id": nm_id}

        # 2. Проверяем доступность фото и извлекаем валидные URL
        valid_urls = self.filter_valid_urls(photos)

        if not valid_urls:
            return {"status": "failed", "reason": "no_valid_photos", "nm_id": nm_id}

        # 3. Формируем и отправляем payload
        payload = self.build_update_payload(nm_id, valid_urls)

        try:
            result = self.send_update_request(payload)

            # ✅ ВОТ ЗДЕСЬ - добавляем возврат при успехе
            return {
                "status": "success",
                "reason": None,
                "nm_id": nm_id,
                "photos_count": len(valid_urls),
                "result": result
            }

        except Exception as e:
            return {"status": "failed", "reason": f"request_error: {str(e)}", "nm_id": nm_id}



    def update_all_cards_without_photos(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Массовое обновление фото для всех карточек без фото

        Args:
            limit: Максимальное количество карточек для обновления

        Returns:
            Dict со статистикой обновления
        """
        cards = self.get_cards_without_photos(limit)

        if not cards:
            logger.info("Нет карточек без фото для обновления")
            return {
                "total": 0,
                "success": [],
                "failed": [],
                "skipped": []
            }

        results = {
            "total": len(cards),
            "success": [],
            "failed": [],
            "skipped": []
        }

        for card in cards:
            try:
                if card.nm_id == '939649958':
                    a = 0
                result = self.update_card_photos(card.nm_id, card.vendor_code)

                if result["status"] == "success":
                    results["success"].append({
                        "nm_id": card.nm_id,
                        "vendor_code": card.vendor_code,
                        "photos_count": result.get("photos_count", 0)
                    })
                elif result["status"] == "skipped":
                    results["skipped"].append({
                        "nm_id": card.nm_id,
                        "vendor_code": card.vendor_code,
                        "reason": result.get("reason")
                    })
                else:
                    results["failed"].append({
                        "nm_id": card.nm_id,
                        "vendor_code": card.vendor_code,
                        "reason": result.get("reason")
                    })

            except Exception as e:
                logger.error(f"Ошибка при обновлении карточки {card.nm_id}: {e}")
                results["failed"].append({
                    "nm_id": card.nm_id,
                    "vendor_code": card.vendor_code,
                    "error": str(e)
                })

        logger.info(f"Обновление завершено. Успешно: {len(results['success'])}, "
                    f"Пропущено: {len(results['skipped'])}, Ошибок: {len(results['failed'])}")

        return results



# ======================== ИСПОЛЬЗОВАНИЕ ========================
if __name__ == "__main__":
    from core.db.connection import get_db_session

    with get_db_session() as db:
        updater = WbCardUpdaterFoto(db)


        # Вариант 1: Обновить одну карточку по nm_id и vendor_code
        # result = updater.update_card_photos(
        #     nm_id=934497869,
        #     vendor_code="91e8f00c*0031377 Бра Lightstar Siena 720667"
        # )
        # print(result)

        # Вариант 2: Обновить все карточки без фото (первые 100)
        result = updater.update_all_cards_without_photos(limit=100)
        print(f"Успешно: {len(result['success'])}")
        print(f"Пропущено: {len(result['skipped'])}")
        print(f"Ошибок: {len(result['failed'])}")

        # Вывести детали ошибок если есть
        if result['failed']:
            print("\nОшибки:")
            for fail in result['failed']:
                print(f"  nm_id={fail['nm_id']}: {fail.get('reason', fail.get('error', 'unknown'))}")



