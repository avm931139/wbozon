import requests
from settings import Config
from core.db.models import MSProduct
from core.db.connection import get_db_session
from sqlalchemy import update
import sys
import logging
from typing import List, Dict, Optional, Set
from datetime import datetime
import gc

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ProductSyncService:
    """Сервис для синхронизации товаров с МойСклад"""

    def __init__(self, batch_size: int = 500):
        """
        Инициализация сервиса

        Args:
            batch_size: Размер пакета для записи в БД
        """
        self.api_token = Config.API_TOKEN_MS
        if not self.api_token:
            raise ValueError("API_TOKEN_MS не задан в настройках!")

        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        self.base_url = "https://api.moysklad.ru/api/remap/1.2/entity/product"
        self.limit = 100  # Максимальное количество товаров за запрос к API
        self.batch_size = batch_size  # Размер пакета для записи в БД

    def get_products_streaming(self) -> List[Dict]:
        """
        Потоковое получение товаров из API (пакетами)

        Yields:
            List[Dict]: Пакет товаров
        """
        offset = 0
        total_loaded = 0
        first_request = True
        total_products = 0

        logger.info("Начало потоковой загрузки товаров из МойСклад")

        while True:
            try:
                url = f"{self.base_url}?limit={self.limit}&offset={offset}&expand=productFolder,images,supplier,price,stock"
                response = requests.get(url, headers=self.headers, timeout=30)

                if response.status_code != 200:
                    logger.error(f"Ошибка API: {response.status_code} - {response.text}")
                    break

                data = response.json()
                products = data.get("rows", [])

                # Получаем общее количество при первом запросе
                if first_request:
                    total_products = data.get("meta", {}).get("size", 0)
                    logger.info(f"Всего товаров для загрузки: {total_products}")
                    first_request = False

                if not products:
                    print()  # Новая строка после прогресс-бара
                    logger.info(f"Загрузка из API завершена. Всего загружено: {total_loaded}")
                    break

                total_loaded += len(products)

                # Выводим прогресс
                if total_products:
                    percent = (total_loaded / total_products) * 100
                    print(f'\r📦 Загружено: {total_loaded}/{total_products} товаров ({percent:.1f}%)',
                          end='', flush=True)
                else:
                    print(f'\r📦 Загружено товаров: {total_loaded}', end='', flush=True)

                yield products

                offset += self.limit

            except requests.exceptions.RequestException as e:
                logger.error(f"Ошибка при запросе к API: {e}")
                break

    @staticmethod
    def extract_barcode(product: Dict) -> Optional[str]:
        """Извлечение штрихкода из данных товара"""
        try:
            barcodes = product.get("barcodes", [])
            if barcodes and isinstance(barcodes[0], dict):
                return barcodes[0].get('ean13')
            return None
        except (IndexError, KeyError, AttributeError):
            return None

    @staticmethod
    def extract_uuid_href(product: Dict) -> Optional[str]:
        """Извлечение UUID href из метаданных товара"""
        try:
            href = product.get("meta", {}).get("href", "")
            if href:
                return href.split('?')[0]
            return None
        except (AttributeError, KeyError):
            return None

    def create_product_from_api_data(self, product: Dict) -> MSProduct:
        """Создание объекта MSProduct из данных API"""
        product_folder = product.get("productFolder", {})

        return MSProduct(
            id_ms=product.get("id"),
            uuidHref=self.extract_uuid_href(product),
            type=product.get("meta", {}).get("type"),
            name=product.get("name"),
            code=product.get("code"),
            article=product.get("article"),
            externalCode=product.get("externalCode"),
            pathName=product.get("pathName"),
            product_folder_id=product_folder.get("id"),
            product_folder_name=product_folder.get("name"),
            barcodes=self.extract_barcode(product),
            attributes=product.get("attributes", []),
            deleted=False
        )

    def update_existing_product(self, db_product: MSProduct, api_product: Dict) -> None:
        """Обновление существующего товара в БД"""
        product_folder = api_product.get("productFolder", {})

        db_product.uuidHref = self.extract_uuid_href(api_product)
        db_product.type = api_product.get("meta", {}).get("type")
        db_product.name = api_product.get("name")
        db_product.code = api_product.get("code")
        db_product.article = api_product.get("article")
        db_product.externalCode = api_product.get("externalCode")
        db_product.pathName = api_product.get("pathName")
        db_product.product_folder_id = product_folder.get("id")
        db_product.product_folder_name = product_folder.get("name")
        db_product.barcodes = self.extract_barcode(api_product)
        db_product.attributes = api_product.get("attributes", [])
        db_product.deleted = False

    def process_batch(self, session, products_batch: List[Dict],
                      existing_products: Dict[str, MSProduct]) -> tuple:
        """
        Обработка пакета товаров

        Returns:
            tuple: (new_count, updated_count)
        """
        new_products = []
        updated_count = 0

        for api_product in products_batch:
            id_ms = api_product.get("id")
            if not id_ms:
                continue

            if id_ms in existing_products:
                # Обновление существующего товара
                self.update_existing_product(existing_products[id_ms], api_product)
                updated_count += 1
            else:
                # Добавление нового товара
                new_product = self.create_product_from_api_data(api_product)
                new_products.append(new_product)

        # Массовая вставка новых товаров
        if new_products:
            session.add_all(new_products)

        # Коммитим пакет
        session.commit()

        return len(new_products), updated_count

    def mark_deleted_products(self, session, api_ids: Set[str]) -> int:
        """
        Пометка удаленных товаров

        Returns:
            int: Количество помеченных товаров
        """
        deleted_count = session.query(MSProduct).filter(
            ~MSProduct.id_ms.in_(api_ids),
            MSProduct.deleted == False
        ).update(
            {MSProduct.deleted: True},
            synchronize_session=False
        )

        if deleted_count:
            session.commit()
            logger.info(f"Помечено как удаленные: {deleted_count} товаров")

        return deleted_count

    def load_products_to_db(self) -> None:
        """Загрузка и синхронизация товаров с базой данных (пакетная обработка)"""
        start_time = datetime.now()

        with get_db_session() as session:
            try:
                # Получаем существующие товары из БД (только ID и объекты)
                logger.info("Загрузка существующих товаров из БД...")
                existing_products = {
                    p.id_ms: p for p in session.query(MSProduct).all()
                }
                logger.info(f"Найдено товаров в БД: {len(existing_products)}")

                # Статистика
                total_new = 0
                total_updated = 0
                batch_number = 0
                api_ids = set()

                # Потоковая обработка товаров из API
                for products_batch in self.get_products_streaming():
                    batch_number += 1

                    # Сохраняем ID для поиска удаленных
                    for product in products_batch:
                        if product.get("id"):
                            api_ids.add(product.get("id"))

                    # Обрабатываем пакет
                    new_count, updated_count = self.process_batch(
                        session, products_batch, existing_products
                    )

                    total_new += new_count
                    total_updated += updated_count

                    # Логируем прогресс
                    logger.info(f"Пакет {batch_number}: +{new_count} новых, ~{updated_count} обновлений | "
                                f"Всего: +{total_new} новых, {total_updated} обновлений")

                    # Принудительная сборка мусора после каждого пакета
                    if batch_number % 10 == 0:
                        gc.collect()

                # Пометка удаленных товаров
                deleted_count = self.mark_deleted_products(session, api_ids)

                # Финальная статистика
                elapsed_time = (datetime.now() - start_time).total_seconds()
                logger.info("=" * 60)
                logger.info(f"Синхронизация завершена за {elapsed_time:.1f} сек")
                logger.info(f"📊 Статистика:")
                logger.info(f"   - Новых товаров: {total_new}")
                logger.info(f"   - Обновлено товаров: {total_updated}")
                logger.info(f"   - Удалено/помечено: {deleted_count}")
                logger.info(f"   - Всего в API: {len(api_ids)}")
                logger.info(f"   - Всего в БД: {len(existing_products) + total_new}")
                logger.info("=" * 60)

            except Exception as e:
                logger.error(f"Ошибка при синхронизации товаров: {e}", exc_info=True)
                session.rollback()
                raise


def main():
    """Основная функция для запуска синхронизации"""
    try:
        logger.info("=" * 60)
        logger.info("Запуск синхронизации товаров с МойСклад")
        logger.info("=" * 60)

        # Можно настроить размер пакета в зависимости от объема данных
        sync_service = ProductSyncService(batch_size=500)
        sync_service.load_products_to_db()

        logger.info("✅ Синхронизация успешно завершена")

    except ValueError as e:
        logger.error(f"❌ Ошибка конфигурации: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("⚠️ Синхронизация прервана пользователем")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()