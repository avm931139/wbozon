# wb/card_updater.py
import requests
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from core.classes import Wb
from settings import Config
from wb.endpoind_wb import update_foto_cards_wb_endp, content_api_base_url_wb
from core.db.models import WbCard
from core.db.models import WBNormalizedProduct, WBNormalizedProductImage

logger = logging.getLogger(__name__)


class WbCardUpdaterFoto:
    """
    Класс для обновления карточек товаров на Wildberries
    Поддерживает обновление фото и может быть расширен для других полей
    """

    def __init__(self, db_session: Session):
        self.db = db_session
        self.wb_client = Wb()
        self.base_url = content_api_base_url_wb
        self.update_endpoint = update_foto_cards_wb_endp  #

    def get_headers(self) -> Dict[str, str]:
        """Получение заголовков для API запросов"""
        return self.wb_client.get_headers_for_content()

    # ======================== ФОТО ========================

    def get_new_photos_from_normalized(self, vendor_code: str) -> List[Dict[str, Any]]:
        """
        Получает новые фото из таблицы WBNormalizedProductImage
        Возвращает формат для API WB
        """
        # Ищем нормализованный продукт по vendor_code
        normalized = self.db.query(WBNormalizedProduct).filter(
            WBNormalizedProduct.vendor_code == vendor_code
        ).first()

        if not normalized:
            logger.warning(f"Нет нормализованных данных для vendor_code: {vendor_code}")
            return []

        # Получаем фото
        images = self.db.query(WBNormalizedProductImage).filter(
            WBNormalizedProductImage.product_id_ms == normalized.product_id_ms
        ).order_by(WBNormalizedProductImage.position).all()

        if not images:
            logger.info(f"Нет фото для vendor_code: {vendor_code}")
            return []

        # Формируем структуру для WB API
        photos = []
        for idx, img in enumerate(images):
            photos.append({
                "url": img.url,
                "isMain": (idx == 0),  # Первое фото - главное
                "order": idx + 1
            })

        return photos

    def build_update_payload_for_photos(self, nm_id: int, vendor_code: str, photos: List[str]) -> Dict[str, Any]:
        """
        Формирует payload для обновления фото
        Для метода /content/v3/media/save
        """
        return {
            "nmId": int(nm_id),  # Внимание: nmId, а не nmID!
            "data": photos  # Массив строк URL
        }

    def check_image_url(self, url: str) -> bool:
        """Проверяет доступность изображения для WB"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                return content_type.startswith('image/')
            return False
        except:
            return False

    def build_update_payload_for_photos(self, nm_id: int, vendor_code: str, photos: List[Dict[str, Any]]) -> Dict[
        str, Any]:
        photo_urls = []

        for photo_dict in photos:
            if "url" in photo_dict:
                urls = photo_dict["url"].split(';')
                for url in urls:
                    cleaned = url.strip()
                    if cleaned and self.check_image_url(cleaned):  # <-- проверка
                        photo_urls.append(cleaned)
                    else:
                        logger.warning(f"Фото недоступно: {cleaned}")

        if not photo_urls:
            raise ValueError("Нет доступных фото для загрузки")

        return {
            "nmId": int(nm_id),
            "data": photo_urls
        }

    def send_update_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Отправляет запрос на обновление карточки
        """
        url = f"{self.base_url}{self.update_endpoint}"
        headers = self.get_headers()

        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            print(response.status_code, result)
            if response.status_code == 200:
                logger.info(f"Успешно отправлено обновление: {result}")
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при отправке запроса: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Ответ WB: {e.response.text}")
            raise

    def update_card_photos(self, nm_id: int, vendor_code: str) -> Dict[str, Any]:
        """
        Основной метод: обновляет фото для одной карточки
        """
        # 1. Получаем новые фото из нормализованных данных
        new_photos = self.get_new_photos_from_normalized(vendor_code)

        if not new_photos:
            return {"status": "skipped", "reason": "no_photos", "nm_id": nm_id}

        # 2. Формируем payload
        payload = self.build_update_payload_for_photos(nm_id, vendor_code, new_photos)

        # 3. Отправляем запрос
        result = self.send_update_request(payload)


        return {"status": "success", "nm_id": nm_id, "result": result}


# ======================== ИСПОЛЬЗОВАНИЕ ========================
# Пример запуска:
#
from core.db.connection import get_db_session

with get_db_session() as db:
    updater = WbCardUpdaterFoto(db)

# Обновить фото для одной карточки
    result = updater.update_card_photos(nm_id=934497869, vendor_code="91e8f00c*0031377 Бра Lightstar Siena 720667")
