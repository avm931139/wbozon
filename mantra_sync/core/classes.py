# matra_sync/ozon/classes.py
from core.db.models import (WbCard, WbWarehouseSellers, WbStock, OzonCard, OzonStockSeller, WBSubject, WBCharacteristic)
import requests
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from settings import Config
from core.db.connection import get_db_session
from bot import send_telegram_message


class Wb:
    def get_headers(self):
        """Получаем заголовки для конкретной организации по ID."""
        # Получаем токены для организации
        api_key = Config.API_KEY_WB_RO_ALL
        if api_key:
            return {
                "Authorization": api_key,
                "Content-Type": "application/json"
            }
        else:
            print(f"-----------API tokens not found --------")

    def get_headers_for_content(self):
        """Получаем заголовки для конкретной организации по ID."""
        # Получаем токены для организации
        api_key = Config.API_KEY_WB_CONTENT
        if api_key:
            return {
                "Authorization": api_key,
                "Content-Type": "application/json"
            }
        else:
            print(f"-----------API tokens not found --------")

    def get_all_cards(
            self,
            url: str,
            headers: dict,
            with_photo: int = -1,
            limit: int = 100
    ) -> list[dict]:
        """
        Получение всех карточек товаров из WB с пагинацией
        :param url: эндпоинт WB API (https://content-api.wildberries.ru/content/v2/get/cards/list)
        :param headers: заголовки с токеном
        :param with_photo: -1 = все, 0 = без фото, 1 = только с фото
        :param limit: количество карточек за один запрос (максимум 100)
        :return: список карточек
        """
        all_cards = []
        cursor = {"limit": limit}

        while True:
            payload = {
                "settings": {
                    "cursor": cursor,
                    "filter": {
                        "withPhoto": with_photo
                    }
                }
            }

            response = requests.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                print(f"Ошибка {response.status_code}: {response.text}")

            data = response.json()
            data_cards = data.get("cards", {})
            all_cards.extend(data_cards)

            total = data.get("cursor", {}).get("total", 0)
            print(f"Загружено карточек: {len(data_cards)} / {total}")

            # Проверка конца пагинации
            if len(data_cards) < limit:
                break

            # Новый курсор для следующего запроса
            cursor_data = data.get("cursor", {})
            updated_at = cursor_data.get("updatedAt")
            nm_id = cursor_data.get("nmID")

            if not updated_at or not nm_id:
                break

            cursor = {
                "limit": limit,
                "updatedAt": updated_at,
                "nmID": nm_id
            }

            # WB не любит частые запросы → добавляем паузу
            time.sleep(0.2)

        return all_cards

    def get_all_categories(self, url: str, headers, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Получает список всех категорий (предметов) Wildberries

        Args:
            url: Полный URL эндпоинта
            params: Параметры запроса (limit, offset, name, parentID)

        Returns:
            Словарь с данными от API или None в случае ошибки
        """


        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()  # Вызовет исключение для статусов 4xx/5xx

            data = response.json()

            # Проверяем наличие ошибки в ответе
            if data.get("error"):
                print(f"Ошибка API: {data.get('errorText')}")
                return None

            return data

        except requests.exceptions.RequestException as e:
            print(f"Ошибка запроса: {e}")
            return None
        except ValueError as e:
            print(f"Ошибка парсинга JSON: {e}")
            return None

    def save_categories_to_db(self, categories: List[Dict]):
        """
        Сохраняет категории в БД

        Args:

            categories: Список категорий из API
        """
          # Импортируйте вашу модель

        with get_db_session() as db_session:
            for cat in categories:
                subject = db_session.query(WBSubject).filter(
                    WBSubject.subject_id == cat["subjectID"]
                ).first()

                if subject:
                    # Обновляем существующую
                    subject.subject_name = cat["subjectName"]
                    subject.parent_id = cat.get("parentID")
                    subject.updated_at = datetime.now()
                else:
                    # Создаем новую
                    subject = WBSubject(
                        subject_id=cat["subjectID"],
                        subject_name=cat["subjectName"],
                        parent_id=cat.get("parentID"),
                        created_at=datetime.now()
                    )
                    db_session.add(subject)

            db_session.commit()
            print(f"✅ Сохранено {len(categories)} категорий в БД")

    def save_characteristics_to_db(self, subject_id: int, characteristics: List[Dict]):
        """
        Сохраняет характеристики предмета в БД
        """
        with get_db_session() as db_session:
            # Удаляем старые характеристики
            deleted = db_session.query(WBCharacteristic).filter(
                WBCharacteristic.subject_id == subject_id
            ).delete()
            print(f"  🗑️ Удалено {deleted} старых характеристик")

            # Сохраняем новые
            saved_count = 0
            for char in characteristics['data']:
                wb_char = WBCharacteristic(
                    subject_id=subject_id,
                    char_id=char.get("charcID", char.get("id")),  # может быть charcID или id
                    char_name=char.get("name", ""),
                    char_type=self._determine_char_type(char.get("charcType", 0)),
                    is_required=char.get("required", False),
                    is_collection=char.get("collection", False),
                    is_multiple=char.get("multiple", False),
                    max_length=char.get("maxCount") or char.get("maxLength"),
                    unit_name=char.get("unitName"),
                    is_popular=char.get("popular", False),
                    description=char.get("description"),
                    created_at=datetime.now()
                )
                db_session.add(wb_char)
                saved_count += 1

            db_session.commit()
            print(f"  ✅ Сохранено {saved_count} характеристик для subject_id={subject_id}")

    def _determine_char_type(self, charc_type: int) -> str:
        """Определяет тип характеристики по charcType из API"""
        type_map = {
            1: "string",
            2: "integer",
            3: "float",
            4: "size",
            5: "boolean",
            6: "list",
        }
        return type_map.get(charc_type, "string")


    def _determine_char_type(self, charc_type: int) -> str:
        """
        Определяет тип характеристики по charcType из API

        Типы по документации Wildberries:
        1 - строка
        2 - число
        3 - список/массив
        4 - единица измерения (размер)
        и т.д.
        """
        type_map = {
            1: "string",
            2: "integer",
            3: "list",
            4: "size",
        }
        return type_map.get(charc_type, "string")

    def save_product(self, data_api):
        try:
            with get_db_session() as db:
                for data in data_api:

                    extist = db.query(WbCard).filter(WbCard.nm_id == data.get('nmID', )).first()
                    sizes = data.get('sizes', [])
                    if sizes and isinstance(sizes, list):
                        first_size = sizes[0]
                        skus = first_size.get('skus')[0]

                    if extist:
                        extist.imt_id = data.get('imtID', )
                        extist.nm_uuid = data.get('nmUUID', )
                        extist.subject_id = data.get('subjectID', )
                        extist.subject_name = data.get('subjectName', )
                        extist.vendor_code = data.get('vendorCode', )
                        extist.brand = data.get('brand', )
                        extist.title = data.get('title', )
                        extist.need_kiz = data.get('needKiz', )
                        extist.photos = data.get('photos', )
                        extist.video = data.get('video', )
                        extist.wholesale = data.get('wholesale', )
                        extist.dimensions = data.get('dimensions', )
                        extist.characteristics = data.get('characteristics', )
                        extist.sizes = data.get('sizes', )
                        extist.tags = data.get('tags', )
                        extist.skus = skus
                        extist.id_ul = 1
                        extist.created_at = data.get('createdAt', )
                        extist.updated_at = data.get('updatedAt', )


                    else:
                        new_rec = WbCard(
                            nm_id=data.get('nmID', ),
                            imt_id=data.get('imtID', ),
                            nm_uuid=data.get('nmUUID', ),
                            subject_id=data.get('subjectID', ),
                            subject_name=data.get('subjectName', ),
                            vendor_code=data.get('vendorCode', ),
                            brand=data.get('brand', ),
                            title=data.get('title', ),
                            need_kiz=data.get('needKiz', ),
                            photos=data.get('photos', ),
                            video=data.get('video', ),
                            wholesale=data.get('wholesale', ),
                            dimensions=data.get('dimensions', ),
                            characteristics=data.get('characteristics', ),
                            sizes=data.get('sizes', ),
                            tags=data.get('tags', ),
                            skus=skus,
                            id_ul=1,
                            created_at=data.get('createdAt', ),
                            updated_at=data.get('updatedAt', )

                        )

                        db.add(new_rec)

                    db.commit()
        except Exception as e:
            print(e)
            db.rollback()

    def get_wharehouses_seller(self, url: str):

        response = requests.get(url, headers=self.get_headers())
        if response.status_code == 200:
            data = response.json()
        else:
            data = None
        return data

    @staticmethod
    def save_wharehouse(data_api: list[dict]):
        """
        Сохраняет или обновляет данные складов WB в таблице WbWarehouseSellers.
        """
        try:
            with get_db_session() as db:
                for data in data_api:
                    office_id = data.get("officeId")
                    if not office_id:
                        continue  # пропускаем некорректные записи

                    exist = db.query(WbWarehouseSellers).filter(
                        WbWarehouseSellers.office_id == office_id
                    ).first()

                    if exist:
                        # обновляем существующую запись
                        exist.id_wb_warehouse = data.get("id")
                        exist.name = data.get("name")
                        exist.cargoType = data.get("cargoType")
                        exist.deliveryType = bool(data.get('deliveryType')) if data.get('deliveryType') else False
                        exist.is_deleting = data.get("isDeleting")
                        exist.is_processing = data.get("isProcessing")
                        exist.updated_at = datetime.now()
                    else:
                        # создаем новую
                        new_warehouse = WbWarehouseSellers(
                            id_wb_warehouse=data.get("id"),
                            office_id=office_id,
                            name=data.get("name"),
                            cargoType=data.get("cargoType"),
                            deliveryType=bool(data.get('deliveryType')) if data.get('deliveryType') else False,
                            is_deleting=data.get("isDeleting"),
                            is_processing=data.get("isProcessing"),
                            created_at=datetime.now(),
                        )
                        db.add(new_warehouse)

                db.commit()
                print(f"✅ Складов обработано: {len(data_api)}")

        except Exception as e:
            print(f"❌ Ошибка при сохранении складов: {e}")

    def _get_all_skus(self) -> list[dict]:
        """Извлекает все SKU из JSON-поля sizes в таблице wb_cards."""
        skus = []
        with get_db_session() as db:
            cards = db.query(WbCard).all()
            for card in cards:
                if not card.sizes:
                    continue
                try:
                    for size_item in card.sizes:
                        if isinstance(size_item, dict):
                            size_skus = size_item.get("skus", [])
                            if isinstance(size_skus, list):
                                for sku in size_skus:
                                    if sku and isinstance(sku, str):
                                        skus.append(sku)
                except Exception as e:
                    print(f"⚠️ Ошибка при обработке карточки {card.id}: {e}")

        print(f"✅ Всего найдено SKU: {len(skus)}")
        return skus

    def get_stocks_by_skus(self, url: list[str]) -> dict:
        """
        Получает остатки товаров по их баркодам на указанном складе.
        Лимит — до 1000 SKU за один запрос.
        """

        headers = self.get_headers()
        skus = self._get_all_skus()
        if not skus:
            return {"status": "empty", "message": "Нет артикулов (SKU) для запроса"}

        # WB разрешает максимум 1000 sku за запрос — разбиваем при необходимости
        def chunk_list(lst, size=1000):
            for i in range(0, len(lst), size):
                yield lst[i:i + size]

        results = []
        for chunk in chunk_list(skus, 1000):
            payload = {"skus": chunk}
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                status = response.status_code

                if status == 200:
                    data = response.json()
                    results.extend(data.get("stocks", []))
                    print(f"✅ Получено {len(data.get('stocks', []))} остатков")
                elif status == 409:
                    print("⚠️ Код 409 — превышен лимит, считаем как 10 запросов. Пауза 2 секунды...")
                    time.sleep(2)
                else:
                    print(f"❌ Ошибка {status}: {response.text}")

                # Соблюдаем лимиты WB — не чаще 1 запроса/200 мс
                time.sleep(0.2)

            except requests.exceptions.RequestException as e:
                print(f"❌ Ошибка при запросе остатков: {e}")
                send_telegram_message(f"Ошибка при запросе остатков: {e}")

        return results

    @staticmethod
    def get_wharehouse_wb():
        with get_db_session() as db:
            wh = db.query(WbWarehouseSellers).all()
            if wh:
                office_id = [w.id_wb_warehouse for w in wh]
                return office_id
            else:
                return None

    @staticmethod
    def get_card_wb(barcode: str):

        with get_db_session() as db:
            row = (
                db.query(
                    WbCard.nm_id,
                    WbCard.vendor_code,
                    WbCard.title,

                )
                .filter(
                    WbCard.skus == barcode
                )
                .first()
            )

            if not row:
                return None

            # Конвертация в словарь: row._mapping — это правильный способ
            result = dict(row._mapping)

        return result

    @staticmethod
    def save_wb_stock_seller(wharehouse: int, data: dict, pcs: int, type_wh: str):
        """
        Сохраняет остатки WB в БД
        - Если запись за сегодня уже существует - обновляет
        - Если записи нет - создает новую
        """
        try:
            with get_db_session() as db:
                from sqlalchemy import and_, func

                today = datetime.now().date()
                nm_id = data['nm_id']
                vendor_code = data.get('vendor_code', '')

                # Ищем существующую запись за сегодня
                existing = db.query(WbStock).filter(
                    and_(
                        WbStock.nm_id_wb == nm_id,
                        WbStock.type_wharehouse == type_wh,
                        WbStock.wharehouse_seller_wb == wharehouse,
                        func.date(WbStock.updated_at) == today
                    )
                ).first()

                if existing:
                    # Обновляем существующую запись
                    existing.product_id = data['nm_id']
                    existing.artikul_wb = vendor_code
                    existing.pcs = pcs
                    existing.updated_at = datetime.now()
                    print(f"🔄 Обновлен остаток WB: nm_id={nm_id}, pcs={pcs}, type={type_wh}")
                else:
                    # Создаем новую запись
                    new_rec = WbStock(
                        product_id=data['nm_id'],
                        type_wharehouse=type_wh,
                        artikul_wb=vendor_code,
                        nm_id_wb=nm_id,
                        pcs=pcs,
                        wharehouse_seller_wb=wharehouse,
                        id_ul=Config.DEFAULT_UL_ID,
                        updated_at=datetime.now()
                    )
                    db.add(new_rec)
                    print(f"✅ Создан новый остаток WB: nm_id={nm_id}, pcs={pcs}, type={type_wh}")

                db.commit()
                return True

        except Exception as e:
            print(f"❌ Ошибка при сохранении остатка WB: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
            return False

    @staticmethod
    def save_wb_stock_fbo(wharehouse: int, data: dict, type_wh: str):
        with get_db_session() as db:
            for skus in data:
                pcs = 0
                for pcs_data in skus['warehouses']:
                    if pcs_data['warehouseName'] == 'Всего находится на складах':
                        pcs = int(pcs_data['quantity'])
                new_rec = WbStock(product_id=skus['vendorCode'],
                                        type_wharehouse=type_wh,
                                        artikul_wb=skus['vendorCode'],
                                        nm_id_wb=skus['nmId'],
                                        pcs=pcs,
                                        wharehouse_seller_wb=wharehouse,
                                        id_ul=Config.DEFAULT_UL_ID,
                                        updated_at=datetime.now()
                                        )
                db.add(new_rec)
        db.commit()



class Ozon:
    def __init__(self):
        self.client_id = Config.OZON_CLIENT_ID
        self.api_key = Config.OZON_API_KEY
        self.base_url = Config.BASE_URL_OZON

    def get_headers(self):
        """Получаем заголовки для Ozon API"""
        if self.client_id and self.api_key:
            return {
                "Client-Id": self.client_id,
                "Api-Key": self.api_key,
                "Content-Type": "application/json"
            }
        else:
            print("-----------Ozon tokens not found--------")
            return None

    def get_all_product_ids(self, limit: int = 1000) -> List[Dict]:
        """Получение списка всех product_id товаров из Ozon с пагинацией"""
        url = f"{self.base_url}/v3/product/list"
        headers = self.get_headers()

        if not headers:
            return []

        all_items = []
        last_id = ""
        page = 1

        while True:
            payload = {
                "filter": {
                    "visibility": "ALL"
                },
                "limit": limit,
                "last_id": last_id
            }

            print(f"Запрос страницы {page}, last_id: {last_id}")
            response = requests.post(url, headers=headers, json=payload)

            if response.status_code != 200:
                print(f"Ошибка Ozon: {response.status_code} - {response.text}")
                break

            data = response.json()

            if 'result' in data:
                items = data['result'].get('items', [])
                total = data['result'].get('total', 0)
                last_id = data['result'].get('last_id')
            else:
                items = data.get('items', [])
                total = data.get('total', 0)
                last_id = data.get('last_id')

            all_items.extend(items)
            print(f"Загружено ID товаров: {len(items)} (всего: {len(all_items)} из {total})")

            if not last_id or len(items) < limit:
                break

            page += 1
            time.sleep(0.3)

        print(f"✅ Всего загружено ID товаров: {len(all_items)}")
        return all_items

    def get_product_info_list(self, product_ids: List[int]) -> List[Dict]:
        """Получение информации о нескольких товарах сразу"""
        url = f"{self.base_url}/v3/product/info/list"
        headers = self.get_headers()

        chunk_size = 1000
        all_products = []
        total_chunks = (len(product_ids) + chunk_size - 1) // chunk_size

        for i in range(0, len(product_ids), chunk_size):
            chunk = product_ids[i:i + chunk_size]
            chunk_num = i // chunk_size + 1

            payload = {"product_id": chunk}

            print(f"Запрос информации для {len(chunk)} товаров (чанк {chunk_num}/{total_chunks})...")
            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                data = response.json()

                if 'result' in data:
                    items = data['result'].get('items', [])
                else:
                    items = data.get('items', [])

                all_products.extend(items)
                print(f"✅ Получена информация о {len(items)} товарах")
            else:
                print(f"❌ Ошибка: {response.status_code} - {response.text}")

            time.sleep(0.5)

        return all_products

    def _list_to_string(self, items: Optional[List], delimiter: str = ';') -> Optional[str]:
        """Преобразует список в строку с разделителем"""
        if not items or not isinstance(items, list):
            return None
        return delimiter.join(str(item) for item in items if item)

    def _safe_float(self, value, default=None):
        """Ограничиваем значение цены"""
        if value  > 99999999.99:
            value = 99999999.99

        """Безопасное преобразование в float"""
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _safe_int(self, value, default=None):
        """Безопасное преобразование в int"""
        if value is None or value == "":
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def _safe_str(self, value, default="fbs"):
        """Безопасное преобразование в строку"""
        if value is None:
            return default
        return str(value)

    def _parse_datetime(self, value):
        """Безопасное преобразование в datetime"""
        if not value:
            return None
        try:
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            return value
        except:
            return None

    def save_products(self, data_api: list[dict]):
        """Сохраняет товары Ozon в БД"""
        if not data_api:
            print("❌ Нет данных для сохранения")
            return None

        try:
            with get_db_session() as db:
                new_count = 0
                updated_count = 0
                error_count = 0

                for data in data_api:
                    try:
                        product_id = data.get('id')
                        if not product_id:
                            continue

                        exist = db.query(OzonCard).filter(
                            OzonCard.product_id == product_id
                        ).first()

                        # Подготовка данных
                        images_str = self._list_to_string(data.get('images'))
                        images360_str = self._list_to_string(data.get('images360'))
                        barcodes_str = self._list_to_string(data.get('barcodes'))

                        # Получаем SKU из sources если есть
                        sku = None
                        sources = data.get('sources', [])
                        if sources and isinstance(sources, list) and len(sources) > 0:
                            sku = sources[0].get('sku')

                        # Безопасно получаем primary_image
                        primary_image = None
                        primary_image_data = data.get('primary_image')
                        if primary_image_data:
                            if isinstance(primary_image_data, list) and len(primary_image_data) > 0:
                                primary_image = primary_image_data[0]
                            elif isinstance(primary_image_data, str):
                                primary_image = primary_image_data

                        # Получаем информацию об остатках
                        stocks_data = data.get('stocks', {})

                        # Получаем даты
                        created_at = self._parse_datetime(data.get('created_at')) or datetime.now()
                        updated_at = self._parse_datetime(data.get('updated_at'))

                        # Безопасно получаем color_image
                        color_image = None
                        color_image_data = data.get('color_image')
                        if color_image_data:
                            if isinstance(color_image_data, list) and len(color_image_data) > 0:
                                color_image = color_image_data[0]
                            elif isinstance(color_image_data, str):
                                color_image = color_image_data

                        product_data = {
                            'product_id': product_id,
                            'offer_id': self._safe_str(data.get('offer_id')),
                            'sku': sku,
                            'name': self._safe_str(data.get('name', 'Без названия'))[:500],
                            'description': self._safe_str(data.get('description')),
                            'description_category_id': self._safe_int(data.get('description_category_id')),
                            'type_id': self._safe_int(data.get('type_id')),
                            'price': self._safe_float(data.get('price')),
                            'old_price': self._safe_float(data.get('old_price')),
                            'min_price': self._safe_float(data.get('min_price')),
                            'currency_code': self._safe_str(data.get('currency_code')),
                            'vat': self._safe_str(data.get('vat')),
                            'barcodes': barcodes_str,
                            'images': images_str,
                            'primary_image': primary_image,
                            'images360': images360_str,
                            'color_image': color_image,
                            'volume_weight': self._safe_float(data.get('volume_weight')),
                            'is_kgt': bool(data.get('is_kgt', False)),
                            'is_prepayment_allowed': bool(data.get('is_prepayment_allowed', False)),
                            'is_archived': bool(data.get('is_archived', False)),
                            'is_autoarchived': bool(data.get('is_autoarchived', False)),
                            'is_discounted': bool(data.get('is_discounted', False)),
                            'has_discounted_fbo_item': bool(data.get('has_discounted_fbo_item', False)),
                            'discounted_fbo_stocks': int(data.get('discounted_fbo_stocks', 0)),
                            'visible': True,
                            'statuses': data.get('statuses'),
                            'visibility_details': data.get('visibility_details'),
                            'price_indexes': data.get('price_indexes'),
                            'stocks': stocks_data,
                            'availabilities': data.get('availabilities'),
                            'commissions': data.get('commissions'),
                            'promotions': data.get('promotions'),
                            'sources': sources,
                            'model_info': data.get('model_info'),
                            'errors': data.get('errors'),
                            'created_at': created_at,
                            'updated_at': updated_at,
                            'last_api_update': datetime.now(),
                            'id_ul': Config.DEFAULT_UL_ID
                        }

                        if exist:
                            # Обновляем существующую запись
                            for key, value in product_data.items():
                                if key not in ['id', 'product_id', 'created_at']:
                                    setattr(exist, key, value)
                            updated_count += 1
                        else:
                            # Создаем новую запись
                            new_rec = OzonCard(**product_data)
                            db.add(new_rec)
                            new_count += 1

                        # Периодический flush
                        if (new_count + updated_count) % 100 == 0:
                            db.flush()
                            print(f"💾 Промежуточно: новых {new_count}, обновлено {updated_count}")

                    except Exception as e:
                        print(f"❌ Ошибка при обработке товара {data.get('id', 'unknown')}: {e}")
                        import traceback
                        traceback.print_exc()  # Добавляем полный стек ошибки для отладки
                        error_count += 1
                        continue

                db.commit()
                print(f"✅ Ozon: новых {new_count}, обновлено {updated_count}, ошибок {error_count}")

                # Сохраняем также остатки отдельно
                self._save_stocks_from_products(data_api)

                return {
                    'new': new_count,
                    'updated': updated_count,
                    'errors': error_count,
                    'total': new_count + updated_count
                }

        except Exception as e:
            print(f"❌ Ошибка при сохранении товаров Ozon: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
            return None


    def _save_stocks_from_products(self, products_data: list[dict]):
        """
        Сохраняет остатки из данных товаров
        - Если запись за сегодня уже существует - обновляет
        - Если записи нет - создает новую
        """
        try:
            with get_db_session() as db:
                from sqlalchemy import func, and_

                today = datetime.now().date()
                # Начало и конец сегодняшнего дня
                today_start = datetime.combine(today, datetime.min.time())
                today_end = datetime.combine(today, datetime.max.time())

                created_count = 0
                updated_count = 0
                saved_count = 0

                for product in products_data:
                    product_id = product.get('id')
                    if not product_id:
                        continue

                    stocks_data = product.get('stocks', {})
                    stocks_list = stocks_data.get('stocks', []) if isinstance(stocks_data, dict) else []

                    offer_id = self._safe_str(product.get('offer_id'))

                    # Получаем SKU
                    sku = None
                    sources = product.get('sources', [])
                    if sources and isinstance(sources, list) and len(sources) > 0:
                        sku = sources[0].get('sku')

                    if stocks_list:
                        for stock_item in stocks_list:
                            # Получаем данные из stock_item
                            stock_sku = stock_item.get('sku', sku)
                            stock_source = self._safe_str(stock_item.get('source'))
                            stock_present = int(stock_item.get('present', 0))
                            stock_reserved = int(stock_item.get('reserved', 0))

                            # Ищем существующую запись за сегодня по уникальным полям
                            existing = db.query(OzonStockSeller).filter(
                                and_(
                                    OzonStockSeller.product_id == product_id,
                                    OzonStockSeller.offer_id == offer_id,
                                    OzonStockSeller.sku == stock_sku,
                                    OzonStockSeller.source == stock_source,
                                    func.date(OzonStockSeller.updated_at) == today
                                )
                            ).first()

                            if existing:
                                # Обновляем существующую запись
                                existing.present = stock_present
                                existing.reserved = stock_reserved
                                existing.updated_at = datetime.now()
                                updated_count += 1
                            else:
                                # Создаем новую запись
                                new_stock = OzonStockSeller(
                                    product_id=product_id,
                                    offer_id=offer_id,
                                    sku=stock_sku,
                                    present=stock_present,
                                    reserved=stock_reserved,
                                    source=stock_source,
                                    id_ul=Config.DEFAULT_UL_ID,
                                    updated_at=datetime.now()
                                )
                                db.add(new_stock)
                                created_count += 1
                            saved_count += 1
                    else:
                        # Если нет остатков, создаем/обновляем запись с нулевыми значениями
                        existing = db.query(OzonStockSeller).filter(
                            and_(
                                OzonStockSeller.product_id == product_id,
                                OzonStockSeller.offer_id == offer_id,
                                func.date(OzonStockSeller.updated_at) == today
                            )
                        ).first()

                        if existing:
                            existing.present = 0
                            existing.reserved = 0
                            existing.updated_at = datetime.now()
                            updated_count += 1
                        else:
                            new_stock = OzonStockSeller(
                                product_id=product_id,
                                offer_id=offer_id,
                                sku=sku,
                                present=0,
                                reserved=0,
                                source=None,
                                id_ul=Config.DEFAULT_UL_ID,
                                updated_at=datetime.now()
                            )
                            db.add(new_stock)
                            created_count += 1
                        saved_count += 1

                    # Периодический flush для оптимизации
                    if saved_count % 500 == 0:
                        db.flush()
                        print(f"💾 Промежуточно: создано {created_count}, обновлено {updated_count}")

                db.commit()
                print(f"✅ Остатки Ozon: создано {created_count}, обновлено {updated_count}, всего {saved_count} записей")
                return saved_count

        except Exception as e:
            print(f"❌ Ошибка при сохранении остатков: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
            return 0

