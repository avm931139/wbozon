"""
Переписанный и объединённый модуль для работы с Wildberries и Мантра.
Содержит улучшенные классы и функции:
- WbClient: работа с API Wildberries (cards, stocks, warehouses)
- WBStockSender: отправка остатков на ВБ с учётом лимитов и логированием
- MantraClient: загрузка и парсинг XML от поставщика
- Скриптовые функции: update_cards_wb, upload_mantra, build_wb_upload_table, push_wb_stocks

Общие улучшения:
- Явная обработка ошибок и retries
- Централизованный логгер вместо print
- Меньше телеграм-спама: батч-уведомления
- Исправлены сигнатуры и проблемы с аргументами
- Безопасные транзакции при записи в БД
- Типизация

Примечание: код ожидает, что Config, модели SQLAlchemy и send_telegram_message
определены в вашем проекте так же, как раньше.
"""

from __future__ import annotations
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Iterable
from datetime import datetime
from urllib.parse import urljoin
from functools import wraps

from core.db.connection import get_db_session
from core.db.models import (
    WbCard, WbWarehouseSellers, WbStockSeller, WBStockLog,
    MantraProducts, MantraProductParam, MantraStocks
)
from settings import Config
from bot import send_telegram_message
import xml.etree.ElementTree as ET

# Настройка логгера
logger = logging.getLogger("wb_mantra")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(fmt)
logger.addHandler(handler)

# Небольшая утилита для retry
def retry(exceptions, tries=3, delay=2, backoff=2):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            _tries, _delay = tries, delay
            while _tries > 1:
                try:
                    return f(*args, **kwargs)
                except exceptions as e:
                    logger.warning(f"Retryable error in {f.__name__}: {e}. Retrying in {_delay}s...")
                    time.sleep(_delay)
                    _tries -= 1
                    _delay *= backoff
            return f(*args, **kwargs)
        return wrapper
    return deco


class WbClient:
    """Клиент для работы с Wildberries Content/Stocks API"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.API_KEY_WB
        if not self.api_key:
            logger.error("WB API key is not configured in Config.API_KEY_WB_AG")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": self.api_key, "Content-Type": "application/json"}

    @retry((requests.RequestException,), tries=3)
    def get_all_cards(self, url: str, with_photo: int = -1, limit: int = 100) -> List[Dict[str, Any]]:
        all_cards: List[Dict[str, Any]] = []
        cursor = {"limit": limit}

        while True:
            payload = {"settings": {"cursor": cursor, "filter": {"withPhoto": with_photo}}}
            r = requests.post(url, headers=self._headers(), json=payload, timeout=30)
            r.raise_for_status()
            data = r.json()
            cards = data.get("cards") or []
            all_cards.extend(cards)

            # лог
            total = data.get("cursor", {}).get("total")
            logger.info(f"Загружено карточек за запрос: {len(cards)}{f' / {total}' if total else ''}")

            # конец пагинации
            if len(cards) < limit:
                break

            cursor_data = data.get("cursor", {})
            updated_at = cursor_data.get("updatedAt")
            nm_id = cursor_data.get("nmID")
            if not (updated_at and nm_id):
                break

            cursor = {"limit": limit, "updatedAt": updated_at, "nmID": nm_id}
            time.sleep(0.2)

        return all_cards

    def save_products_bulk(self, cards: Iterable[Dict[str, Any]]):
        """Сохранение/обновление карточек в БД — батчами. Без коммитов на каждую запись."""
        if not cards:
            logger.info("Нет карточек для сохранения")
            return

        with get_db_session() as db:
            for data in cards:
                nm_id = data.get("nmID")
                if not nm_id:
                    continue

                # безопасное получение skus
                skus = None
                try:
                    sizes = data.get("sizes") or []
                    if isinstance(sizes, list) and sizes:
                        first = sizes[0]
                        skus_list = first.get("skus") if isinstance(first, dict) else None
                        if isinstance(skus_list, list) and skus_list:
                            skus = skus_list[0]
                except Exception:
                    skus = None

                obj = db.query(WbCard).filter(WbCard.nm_id == nm_id).one_or_none()
                now = datetime.now()
                if obj:
                    # обновляем только те поля, которые есть
                    obj.imt_id = data.get('imtID')
                    obj.nm_uuid = data.get('nmUUID')
                    obj.subject_id = data.get('subjectID')
                    obj.subject_name = data.get('subjectName')
                    obj.vendor_code = data.get('vendorCode')
                    obj.brand = data.get('brand')
                    obj.title = data.get('title')
                    obj.need_kiz = data.get('needKiz')
                    obj.photos = data.get('photos')
                    obj.video = data.get('video')
                    obj.wholesale = data.get('wholesale')
                    obj.dimensions = data.get('dimensions')
                    obj.characteristics = data.get('characteristics')
                    obj.sizes = data.get('sizes')
                    obj.tags = data.get('tags')
                    obj.skus = skus
                    obj.updated_at = now
                else:
                    new = WbCard(
                        nm_id=nm_id,
                        imt_id=data.get('imtID'),
                        nm_uuid=data.get('nmUUID'),
                        subject_id=data.get('subjectID'),
                        subject_name=data.get('subjectName'),
                        vendor_code=data.get('vendorCode'),
                        brand=data.get('brand'),
                        title=data.get('title'),
                        need_kiz=data.get('needKiz'),
                        photos=data.get('photos'),
                        video=data.get('video'),
                        wholesale=data.get('wholesale'),
                        dimensions=data.get('dimensions'),
                        characteristics=data.get('characteristics'),
                        sizes=data.get('sizes'),
                        tags=data.get('tags'),
                        skus=skus,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(new)
            db.commit()
        logger.info("Сохранение карточек завершено")

    def get_warehouses(self) -> List[int]:
        with get_db_session() as db:
            wh = db.query(WbWarehouseSellers).all()
            return [w.id_wb_warehouse for w in wh if w.id_wb_warehouse]

    @retry((requests.RequestException,), tries=3)
    def get_stocks_by_skus(self, url: str, skus: List[str]) -> List[Dict[str, Any]]:
        """Запрашивает остатки у ВБ по списку sku (батч до 1000). Возвращает список словарей."""
        results: List[Dict[str, Any]] = []
        if not skus:
            return results

        def chunk(lst, n=1000):
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        for chunk_skus in chunk(skus, 1000):
            payload = {"skus": chunk_skus}
            r = requests.post(url, headers=self._headers(), json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                stocks = data.get('stocks') or []
                results.extend(stocks)
                logger.info(f"Получено {len(stocks)} остатков от WB")
            elif r.status_code == 409:
                logger.warning("WB вернул 409 — превышение лимита, пауза 2 сек")
                time.sleep(2)
            else:
                logger.error(f"Ошибка {r.status_code} при запросе остатков: {r.text}")

            time.sleep(0.2)

        return results

    def get_mantra_stock_by_barcode(self, barcode: str) -> Optional[Dict[str, Any]]:
        """Проверяет таблицы Mantra/MantraStocks по штрихкоду. Возвращает словарь или None."""
        with get_db_session() as db:
            row = (
                db.query(
                    WbCard.nm_id,
                    WbCard.vendor_code,
                    MantraStocks.product_id,
                    MantraStocks.pcs
                )
                .join(WbCard, WbCard.vendor_code == MantraStocks.articul)
                .filter(WbCard.skus == barcode)
                .first()
            )
            if not row:
                return None
            return dict(row._mapping)

    def save_wb_stock_seller_bulk(self, warehouse: int, records: List[Dict[str, Any]]):
        """Сохраняем остатки для конкретного склада. records = [{sku, artikul, nm_id, pcs}]"""
        if not records:
            return
        with get_db_session() as db:
            # удаляем старые записи по этому складу и вставляем новые в рамках транзакции
            db.query(WbStockSeller).filter(WbStockSeller.wharehouse_seller_wb == warehouse).delete()
            for r in records:
                new = WbStockSeller(
                    product_id=r.get('product_id'),
                    barcode_wb=r.get('sku'),
                    artikul_wb=r.get('artikul'),
                    nm_id_wb=r.get('nm_id'),
                    pcs=r.get('pcs') or 0,
                    wharehouse_seller_wb=warehouse,
                    updated_at=datetime.now()
                )
                db.add(new)
            db.commit()
        logger.info(f"Сохранено {len(records)} остатков для склада {warehouse}")


class WBStockSender:
    """Отправляет остатки на WB с учётом лимитов и логов в таблицу WBStockLog."""

    def __init__(self, api_key: Optional[str], base_url: str, warehouse_id: int):
        self.api_key = api_key or Config.API_KEY_WB
        self.base_url = base_url.rstrip('/')
        self.warehouse_id = warehouse_id
        self.requests_timestamps: List[float] = []

    def _headers(self):
        return {"Authorization": self.api_key, "Content-Type": "application/json"}

    def _get_all_stocks_from_db(self) -> List[Dict[str, Any]]:
        with get_db_session() as db:
            stocks = db.query(WbStockSeller).filter(WbStockSeller.wharehouse_seller_wb == self.warehouse_id).all()
            return [{"sku": s.barcode_wb, "amount": int(s.pcs or 0)} for s in stocks if s.barcode_wb]

    def _chunk(self, data: List[Any], size: int = 1000):
        for i in range(0, len(data), size):
            yield data[i:i + size]

    def _respect_rate(self):
        now = time.time()
        # очищаем старые отметки
        self.requests_timestamps = [t for t in self.requests_timestamps if now - t < 60]
        if len(self.requests_timestamps) >= 300:
            wait = 60 - (now - self.requests_timestamps[0])
            logger.info(f"Лимит 300/мин достигнут, ждём {wait:.1f}s")
            time.sleep(max(wait, 1))
        if len(self.requests_timestamps) % 20 == 0 and len(self.requests_timestamps) != 0:
            time.sleep(2)
        time.sleep(0.2)
        self.requests_timestamps.append(time.time())

    def _log_attempt(self, chunk: List[Dict[str, Any]], status: str, error: Optional[str] = None):
        ts = datetime.now()
        with get_db_session() as db:
            for item in chunk:
                log = WBStockLog(sku=item.get('sku'), amount=item.get('amount'), status=status, error=error, updated_at=ts)
                db.add(log)
            db.commit()
        # Посылаем одно суммарное сообщение в Telegram при ошибке или успехе
        if error:
            send_telegram_message(f"Ошибка отправки {len(chunk)} остатков: {error}")
        else:
            logger.info(f"Успешно отправлен пакет из {len(chunk)} позиций")

    @retry((requests.RequestException,), tries=3)
    def send_stocks(self):
        data = self._get_all_stocks_from_db()
        if not data:
            send_telegram_message("Нет данных для отправки на WB")
            return

        url = f"{self.base_url}/{self.warehouse_id}"
        total = len(data)
        sent = 0

        for chunk in self._chunk(data, 1000):
            self._respect_rate()
            payload = {"stocks": chunk}
            try:
                r = requests.put(url, headers=self._headers(), json=payload, timeout=30)
                if r.status_code == 204:
                    sent += len(chunk)
                    self._log_attempt(chunk, status='success')
                else:
                    err = f"Код {r.status_code}: {r.text}"
                    logger.error(err)
                    self._log_attempt(chunk, status='fail', error=err)
            except requests.RequestException as e:
                logger.exception("Ошибка при отправке пакета в WB")
                self._log_attempt(chunk, status='fail', error=str(e))

        send_telegram_message(f"Отправка завершена: {sent}/{total} для склада {self.warehouse_id}")


class MantraClient:
    """Клиент для загрузки/парсинга XML от поставщика (Мантра)"""

    @staticmethod
    @retry((requests.RequestException,), tries=3)
    def fetch_xml(url: str) -> str:
        r = requests.get(url, timeout=30)
        r.encoding = 'windows-1251'
        r.raise_for_status()
        return r.text

    @staticmethod
    def parse_offers(xml_text: str) -> List[Dict[str, Any]]:
        root = ET.fromstring(xml_text)
        offers = []
        for offer in root.findall('.//offer'):
            params = {}
            for p in offer.findall('param'):
                name = p.attrib.get('name')
                params[name] = p.text
            try:
                offers.append({
                    'id': int(offer.attrib.get('id')) if offer.attrib.get('id') else None,
                    'name': offer.findtext('name'),
                    'vendor': offer.findtext('vendor'),
                    'price': float(offer.findtext('price') or 0),
                    'currency': offer.findtext('currencyId'),
                    'category_id': int(offer.findtext('categoryId') or 0),
                    'description': offer.findtext('description'),
                    'url': offer.findtext('url'),
                    'picture': offer.findtext('picture'),
                    'params': params
                })
            except Exception as e:
                logger.warning(f"Не удалось распарсить оффер: {e}")
        return offers

    @staticmethod
    def save_offers(offers: List[Dict[str, Any]]):
        if not offers:
            logger.info("Нет офферов для сохранения")
            return

        start = datetime.now()
        with get_db_session() as db:
            offer_ids = [o['id'] for o in offers if o.get('id')]

            existing_products = {p.id: p for p in db.query(MantraProducts).filter(MantraProducts.id.in_(offer_ids)).all()} if offer_ids else {}
            existing_params = db.query(MantraProductParam).filter(MantraProductParam.product_id.in_(offer_ids)).all() if offer_ids else []
            existing_stocks = {s.product_id: s for s in db.query(MantraStocks).filter(MantraStocks.product_id.in_(offer_ids)).all()} if offer_ids else {}

            params_map = {}
            for p in existing_params:
                params_map.setdefault(p.product_id, {})[p.name] = p

            new_products = []
            new_params = []
            new_stocks = []

            for offer in offers:
                oid = offer.get('id')
                if not oid:
                    continue

                prod = existing_products.get(oid)
                now = datetime.now()
                if prod:
                    prod.name = offer.get('name')
                    prod.vendor = offer.get('vendor')
                    prod.price = offer.get('price')
                    prod.currency = offer.get('currency')
                    prod.category_id = offer.get('category_id')
                    prod.description = offer.get('description')
                    prod.url = offer.get('url')
                    prod.picture = offer.get('picture')
                    prod.updated_at = now
                else:
                    prod = MantraProducts(
                        id=oid,
                        name=offer.get('name'),
                        vendor=offer.get('vendor'),
                        price=offer.get('price'),
                        currency=offer.get('currency'),
                        category_id=offer.get('category_id'),
                        description=offer.get('description'),
                        url=offer.get('url'),
                        picture=offer.get('picture'),
                        created_at=now,
                        updated_at=now,
                    )
                    new_products.append(prod)
                    existing_products[oid] = prod

                pcs = 0
                articul_value = None
                for k, v in (offer.get('params') or {}).items():
                    ent = params_map.get(oid, {}).get(k)
                    if ent:
                        ent.value = v
                    else:
                        p = MantraProductParam(product_id=oid, name=k, value=v)
                        new_params.append(p)
                        params_map.setdefault(oid, {})[k] = p

                    if k and k.lower() == 'остаток на складе':
                        try:
                            pcs = int(v)
                        except Exception:
                            pcs = 0
                    if k and k.lower() == 'артикул':
                        articul_value = v

                stock = existing_stocks.get(oid)
                if stock:
                    stock.pcs = pcs
                    if articul_value:
                        stock.articul = articul_value
                    stock.updated_at = now
                else:
                    s = MantraStocks(product_id=oid, pcs=pcs, articul=articul_value, updated_at=now)
                    new_stocks.append(s)
                    existing_stocks[oid] = s

            if new_products:
                db.add_all(new_products)
            if new_params:
                db.add_all(new_params)
            if new_stocks:
                db.add_all(new_stocks)

            db.commit()
        logger.info(f"Сохранение офферов завершено за {datetime.now() - start}")


# -------------------------- Скриптовые обёртки --------------------------

def notify(step: str, success: bool = True, error: Optional[Exception] = None, to_telegram: bool = True):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if success:
        msg = f"✅ [{ts}] {step} выполнен"
        logger.info(msg)
    else:
        msg = f"❌ [{ts}] {step} завершился с ошибкой: {error}"
        logger.error(msg)

    if to_telegram:
        try:
            send_telegram_message(msg)
        except Exception as e:
            logger.warning(f"Не удалось отправить Telegram уведомление: {e}")


def update_cards_wb():
    """Загрузить карточки с WB и сохранить в БД"""
    client = WbClient()
    url = urljoin(Config.BASE_URL_WB_CONTENT, getattr(Config, 'CARDS_WB_ENDP', '/content/v2/get/cards/list'))
    try:
        cards = client.get_all_cards(url)
        client.save_products_bulk(cards)
        notify('Обновление карточек WB')
    except Exception as e:
        notify('Обновление карточек WB', success=False, error=e)


def upload_mantra():
    try:
        xml = MantraClient.fetch_xml(Config.URL_MANTRA_XML)
        offers = MantraClient.parse_offers(xml)
        if not offers:
            notify('Парсинг Мантра - нет офферов', success=False)
            return
        MantraClient.save_offers(offers)
        notify('Загрузка офферов Мантра')
    except Exception as e:
        notify('Загрузка офферов Мантра', success=False, error=e)


def build_wb_upload_table(base_url_for_stocks: str):
    """Собирает таблицу WbStockSeller для загрузки на ВБ: берет остатки из WB и сопоставляет со складом Мантра"""
    client = WbClient()
    warehouses = client.get_warehouses()
    if not warehouses:
        notify('Получение складов WB', success=False, error=Exception('Список складов пуст'))
        return

    # получаем все skus из базы (WbCard.skus)
    with get_db_session() as db:
        cards = db.query(WbCard).all()
        skus = [c.skus for c in cards if c.skus]

    # формируем URL для запроса остатков у WB
    url = base_url_for_stocks

    for wh in warehouses:
        try:
            results = client.get_stocks_by_skus(urljoin(url, str(wh)), skus)
            # сопоставляем с Мантрой и формируем bulk
            save_records = []
            for d in results:
                sku = d.get('sku')
                if not sku:
                    continue
                mantra_row = client.get_mantra_stock_by_barcode(sku)
                if not mantra_row:
                    continue
                pcs = int(mantra_row.get('pcs') or 0)
                pcs_to_send = 0 if pcs < 5 else pcs
                save_records.append({
                    'sku': sku,
                    'product_id': mantra_row.get('product_id'),
                    'artikul': mantra_row.get('vendor_code'),
                    'nm_id': mantra_row.get('nm_id'),
                    'pcs': pcs_to_send
                })
            client.save_wb_stock_seller_bulk(wh, save_records)
            notify(f'Подготовка остатков для склада {wh}')
        except Exception as e:
            notify(f'Ошибка при подготовке остатков для склада {wh}', success=False, error=e)


def push_wb_stocks(base_url_update: str):
    client = WbClient()
    warehouses = client.get_warehouses()
    if not warehouses:
        notify('Получение складов WB (push)', success=False, error=Exception('Список складов пуст'))
        return

    for wh in warehouses:
        try:
            sender = WBStockSender(Config.API_KEY_WB, base_url_update, wh)
            sender.send_stocks()
            notify(f'Отправка остатков на склад {wh}')
        except Exception as e:
            notify(f'Отправка остатков на склад {wh}', success=False, error=e)

# Конец файла
