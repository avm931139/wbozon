# wb/card_updater.py
import requests
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from core.classes import Wb
from settings import Config
from wb.endpoind_wb import update_cards_wb_endp, content_api_base_url_wb
from core.db.models import WbCard
from core.db.models import WBNormalizedProduct, WBNormalizedProductImage

logger = logging.getLogger(__name__)


class WbCardUpdater:
    """
    Класс для обновления карточек товаров на Wildberries
    Поддерживает обновление фото и может быть расширен для других полей
    """

    def __init__(self, db_session: Session):
        self.db = db_session
        self.wb_client = Wb()
        self.base_url = content_api_base_url_wb
        self.update_endpoint = update_cards_wb_endp  # /content/v2/cards/update

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

    def build_update_payload_for_photos(self, nm_id: int,vendor_code: str, photos: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Формирует payload для обновления фото
        """
        return  [
    {
        "nmID": nm_id,
        "vendorCode": vendor_code,
        "photos": self.parse_photos_to_wb_format(photos),
        "sizes": [
            {
                "techSize": "0",
                "price": 0,
                "skus": []
            }
        ]
    },

]

    def parse_photos_to_wb_format(self, photos_data: Optional[str]) -> List[Dict[str, Any]]:
        """
        Преобразует строку с URL (разделенных ;) в формат WB API

        Args:
            photos_data: строка вида "url1;url2;url3" или None

        Returns:
            list of dict: [{"url": "...", "isMain": bool, "order": int}]
        """
        if not photos_data[0]['url'] or not isinstance(photos_data[0]['url'], str):
            return []

        # Разделяем по точке с запятой
        urls = [url.strip() for url in photos_data[0]['url'].split(';') if url.strip()]

        if not urls:
            return []

        photos = []
        for urli in urls:
            photos.append( urli)

        return photos


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

        # 4. Обновляем статус в БД
        wb_card = self.db.query(WbCard).filter(WbCard.nm_id == nm_id).first()
        # if wb_card:
        #     # Сохраняем новые фото в JSON поле (как backup)
        #     wb_card.photos = {"updated_at": datetime.now().isoformat(), "photos": new_photos}
        #     wb_card.updated_at = datetime.now()
        #     self.db.commit()

        return {"status": "success", "nm_id": nm_id, "result": result}

    # ======================== МАССОВОЕ ОБНОВЛЕНИЕ ========================

    def get_cards_need_update(self, limit: Optional[int] = None) -> List[WbCard]:
        """
        Получает карточки, которые нужно обновить.
        Условия:
        - Есть соответствующий нормализованный продукт с новыми фото
        - Карточка существует на WB
        """
        # Подзапрос: vendor_code из нормализованных продуктов со статусом ready
        query = self.db.query(WbCard).join(
            WBNormalizedProduct,
            WbCard.vendor_code == WBNormalizedProduct.vendor_code
        ).filter(
            WBNormalizedProduct.status == "ready"
        )

        if limit:
            query = query.limit(limit)

        return query.all()

    def bulk_update_photos(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Массовое обновление фото для всех карточек, требующих обновления
        """
        cards = self.get_cards_need_update(limit)

        results = {
            "total": len(cards),
            "success": [],
            "failed": [],
            "skipped": []
        }

        for card in cards:
            try:
                # Проверяем наличие фото в нормализованных данных
                photos = self.get_new_photos_from_normalized(card.vendor_code)
                if not photos:
                    results["skipped"].append({
                        "nm_id": card.nm_id,
                        "vendor_code": card.vendor_code,
                        "reason": "no_photos"
                    })
                    continue

                # Обновляем
                update_result = self.update_card_photos(card.nm_id, card.vendor_code)
                results["success"].append({
                    "nm_id": card.nm_id,
                    "vendor_code": card.vendor_code,
                    "photos_count": len(photos)
                })

            except Exception as e:
                logger.error(f"Ошибка при обновлении карточки {card.nm_id}: {e}")
                results["failed"].append({
                    "nm_id": card.nm_id,
                    "vendor_code": card.vendor_code,
                    "error": str(e)
                })

        return results

    # ======================== РАСШИРЕНИЕ ДЛЯ ДРУГИХ ПОЛЕЙ ========================

    def build_update_payload_full(self, nm_id: int, **fields) -> Dict[str, Any]:
        """
        Универсальный метод для формирования payload с любыми полями
        Поддерживаемые поля: photos, video, dimensions, characteristics, sizes и т.д.
        """
        card_data = {"nmID": nm_id}

        # Добавляем только переданные поля
        for field_name, field_value in fields.items():
            if field_value is not None:
                card_data[field_name] = field_value

        return {"cards": [card_data]}

    def update_card(self, nm_id: int, **fields) -> Dict[str, Any]:
        """
        Универсальный метод обновления любых полей карточки
        Примеры:
        - update_card(123, photos=[{"url": "...", "isMain": True}])
        - update_card(123, video="https://...")
        - update_card(123, dimensions={"length": 10, "width": 20, "height": 30, "weight": 1.5})
        """
        payload = self.build_update_payload_full(nm_id, **fields)
        return self.send_update_request(payload)

# ======================== ИСПОЛЬЗОВАНИЕ ========================
# Пример запуска:
#
from core.db.connection import get_db_session

with get_db_session() as db:
    updater = WbCardUpdater(db)

# Обновить фото для одной карточки
    result = updater.update_card_photos(nm_id=934580828, vendor_code="dd320d44*0013357 Бра Omnilux OML-31901-01")

# # Массовое обновление (первые 100)
# bulk_result = updater.bulk_update_photos(limit=100)
#
# # Универсальное обновление
# updater.update_card(
#     nm_id=123456789,
#     photos=[{"url": "https://...", "isMain": True}],
#     video="https://youtu.be/..."
# )