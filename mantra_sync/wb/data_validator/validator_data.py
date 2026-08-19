import requests
from typing import List, Dict, Any, Set, Optional, Tuple
from urllib.parse import urlparse
from sqlalchemy import and_, func
from sqlalchemy.orm import Session
from loguru import logger
import json
from datetime import datetime
from wb.data_validator.luru_correct_img_urls import add_luru_images, LuRuImageGenerator

from core.db.models import WBNormalizedProduct, WBNormalizedProductImage, ParserProduct
from core.db.connection import get_db_session


class ProductDataValidator:
    """
    Класс для проверки и очистки нормализованных данных о товарах. После него нужно запустить luru_correct_img_urls.py

    Задачи:
    1. Найти нулевые размеры в товаре и установить статус 'review'
    2. Проверить ссылки на изображения на доступность, удалить битые
    3. Найти и удалить дубликаты ссылок на изображения
    4. Обновить position (количество валидных изображений)

    Формат хранения изображений: строка с разделителем ";"
    Пример: "url1;url2;url3"
    """

    def __init__(self, request_timeout: int = 10, batch_size: int = 100):
        """
        :param request_timeout: таймаут для проверки ссылок (секунды)
        :param batch_size: размер пакета для обработки товаров
        """
        self.request_timeout = request_timeout
        self.batch_size = batch_size
        self.stats = {
            'products_checked': 0,
            'products_with_zero_sizes': 0,
            'images_checked': 0,
            'broken_images_deleted': 0,
            'duplicate_images_removed': 0,
            'products_updated': 0
        }

    def run_full_validation(self) -> Dict[str, int]:
        """
        Запустить полную проверку всех товаров и изображений
        """
        logger.info("Начинаем полную валидацию товаров и изображений")

        self.update_image() #Обновляем товары записей которых нет в изодбражениях

        with get_db_session() as session:
            self._check_zero_sizes(session)
            self._clean_images(session)

        logger.info(f"Валидация завершена. Статистика: {self.stats}")
        return self.stats

    def _check_zero_sizes(self, session: Session) -> None:
        """
        Проверить товары с нулевыми размерами и установить статус 'review'
        """
        logger.info("Проверяем товары с нулевыми размерами")

        # Находим товары с нулевыми размерами
        zero_size_products = session.query(WBNormalizedProduct).filter(
            and_(
                WBNormalizedProduct.status != 'uploaded',  # не трогаем уже загруженные
                (
                        (WBNormalizedProduct.length == 0) |
                        (WBNormalizedProduct.width == 0) |
                        (WBNormalizedProduct.height == 0) |
                        (WBNormalizedProduct.weight == 0.0)
                )
            )
        ).all()

        for product in zero_size_products:
            zero_fields = []

            if product.length == 0:
                zero_fields.append('length')
            if product.width == 0:
                zero_fields.append('width')
            if product.height == 0:
                zero_fields.append('height')
            if product.weight == 0.0:
                zero_fields.append('weight')

            # Формируем ошибку валидации
            error_msg = f"Нулевые размеры: {', '.join(zero_fields)}"

            existing_errors = {}
            if product.validation_errors:
                try:
                    existing_errors = json.loads(product.validation_errors)
                except:
                    existing_errors = {}

            existing_errors['zero_sizes'] = zero_fields
            product.validation_errors = json.dumps(existing_errors, ensure_ascii=False)
            product.status = 'review'

            self.stats['products_with_zero_sizes'] += 1
            logger.warning(
                f"Товар {product.product_id_ms} (vendor_code: {product.vendor_code}) - {error_msg}, статус изменен на 'review'")

        session.commit()
        self.stats['products_checked'] = len(zero_size_products)
        logger.info(f"Проверено товаров с нулевыми размерами: {self.stats['products_checked']}")

    def _clean_images(self, session: Session) -> None:
        """
        Проверить изображения на доступность и удалить битые ссылки
        Затем удалить дубликаты и обновить position
        """
        logger.info("Начинаем очистку изображений")

        # Получаем все товары, у которых есть изображения
        products = session.query(WBNormalizedProduct).filter(
            WBNormalizedProductImage.product_id_ms == WBNormalizedProduct.product_id_ms
        ).all()

        # Альтернативный запрос: получаем все товары, у которых поле images не пустое
        # Но так как изображения в отдельной таблице, используем первый вариант

        product_ids = session.query(WBNormalizedProductImage.product_id_ms).distinct().all()
        product_ids = [p[0] for p in product_ids]

        for product_id in product_ids:
            self._process_product_images(session, product_id)

        logger.info(f"Обработано товаров с изображениями: {len(product_ids)}")

    def _process_product_images(self, session: Session, product_id_ms: str) -> None:
        """
        Обработать изображения для одного товара:
        - получить строку с URL, разделенных ;
        - разбить на список
        - проверить доступность ссылок
        - удалить битые и дубликаты
        - обновить запись в таблице WBNormalizedProductImage
        """
        # Получаем запись с изображениями для этого товара
        image_record = session.query(WBNormalizedProductImage).filter(
            WBNormalizedProductImage.product_id_ms == product_id_ms
        ).first()

        if not image_record or not image_record.url:
            logger.debug(f"Нет изображений для товара {product_id_ms}")
            return

        # Разбиваем строку на список URL
        original_urls = [url.strip() for url in image_record.url.split(';') if url.strip()]

        if not original_urls:
            logger.debug(f"Пустая строка изображений для товара {product_id_ms}")
            return

        self.stats['images_checked'] += len(original_urls)
        logger.debug(f"Товар {product_id_ms}: найдено {len(original_urls)} изображений")

        # Шаг 1: проверяем доступность ссылок
        valid_urls = []
        for url in original_urls:
            if self._is_image_accessible(url):
                valid_urls.append(url)
            else:
                logger.warning(f"Удаляем битую ссылку для товара {product_id_ms}: {url[:100]}...")
                self.stats['broken_images_deleted'] += 1

        # Шаг 2: удаляем дубликаты ссылок (сохраняя порядок)
        seen_urls: Set[str] = set()
        unique_valid_urls = []
        for url in valid_urls:
            if url not in seen_urls:
                seen_urls.add(url)
                unique_valid_urls.append(url)
            else:
                logger.warning(f"Удаляем дубликат ссылки для товара {product_id_ms}: {url[:100]}...")
                self.stats['duplicate_images_removed'] += 1

        # Шаг 3: обновляем запись в БД
        new_images_string = ';'.join(unique_valid_urls)
        images_count = len(unique_valid_urls)

        # Обновляем поля
        image_record.url = new_images_string
        image_record.position = images_count

        # Шаг 4: обновляем статус товара, если изображений нет
        if images_count == 0:
            product = session.query(WBNormalizedProduct).filter(
                WBNormalizedProduct.product_id_ms == product_id_ms
            ).first()

            if product and product.status != 'uploaded':
                product.status = 'review'
                existing_errors = {}
                if product.validation_errors:
                    try:
                        existing_errors = json.loads(product.validation_errors)
                    except:
                        pass
                existing_errors['no_images'] = "Отсутствуют валидные изображения"
                product.validation_errors = json.dumps(existing_errors, ensure_ascii=False)
                logger.warning(f"Товар {product_id_ms} не имеет валидных изображений, статус изменен на 'review'")

        session.commit()
        self.stats['products_updated'] += 1

        if images_count > 0:
            logger.info(
                f"Товар {product_id_ms}: после очистки осталось {images_count} валидных изображений (было {len(original_urls)})")
        else:
            logger.warning(f"Товар {product_id_ms}: все {len(original_urls)} изображений удалены")

    def _is_image_accessible(self, url: str) -> bool:
        """
        Проверить, доступна ли ссылка на изображение

        Возвращает True, если URL доступен и возвращает HTTP 200 OK
        """
        if not url or not url.startswith(('http://', 'https://')):
            return False

        try:
            # Используем HEAD запрос для экономии трафика
            response = requests.head(
                url,
                timeout=self.request_timeout,
                allow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; ProductValidator/1.0)'}
            )

            # Если HEAD не поддерживается (405), пробуем GET с stream=True
            if response.status_code == 405:
                response = requests.get(
                    url,
                    timeout=self.request_timeout,
                    stream=True,
                    allow_redirects=True,
                    headers={'User-Agent': 'Mozilla/5.0 (compatible; ProductValidator/1.0)'}
                )
                # Считываем только первые 100 байт, чтобы не качать все изображение
                for _ in response.iter_content(chunk_size=100):
                    break
                response.close()

            return response.status_code == 200

        except requests.exceptions.Timeout:
            logger.debug(f"Timeout при проверке ссылки: {url[:100]}...")
            return False
        except requests.exceptions.ConnectionError:
            logger.debug(f"ConnectionError при проверке ссылки: {url[:100]}...")
            return False
        except Exception as e:
            logger.debug(f"Ошибка при проверке ссылки {url[:100]}...: {str(e)}")
            return False

    def check_single_product(self, product_id_ms: str) -> Dict[str, Any]:
        """
        Проверить один товар по его ID
        """
        with get_db_session() as session:
            product = session.query(WBNormalizedProduct).filter(
                WBNormalizedProduct.product_id_ms == product_id_ms
            ).first()

            if not product:
                return {'error': f'Товар {product_id_ms} не найден'}

            # Проверяем размеры
            zero_fields = []
            if product.length == 0:
                zero_fields.append('length')
            if product.width == 0:
                zero_fields.append('width')
            if product.height == 0:
                zero_fields.append('height')
            if product.weight == 0.0:
                zero_fields.append('weight')

            # Обрабатываем изображения
            self._process_product_images(session, product_id_ms)

            session.refresh(product)

            # Получаем актуальную строку с изображениями
            image_record = session.query(WBNormalizedProductImage).filter(
                WBNormalizedProductImage.product_id_ms == product_id_ms
            ).first()

            images_count = image_record.position if image_record else 0

            return {
                'product_id_ms': product_id_ms,
                'status': product.status,
                'zero_sizes': zero_fields,
                'validation_errors': product.validation_errors,
                'images_count': images_count,
                'images_string': image_record.url[:200] + '...' if image_record and len(image_record.url) > 200 else (
                    image_record.url if image_record else '')
            }

    def get_products_without_images(self) -> List[str]:
        """
        Получить список товаров, у которых нет валидных изображений:
        - нет записи в таблице wb_normalized_product_image
        - или запись есть, но url пустой (NULL или пустая строка)
        - или после очистки images_count == 0
        """
        with get_db_session() as session:
            # Вариант 1: через LEFT JOIN и проверку на NULL/пустоту
            products_without_images = session.query(WBNormalizedProduct.product_id_ms).outerjoin(
                WBNormalizedProductImage,
                WBNormalizedProduct.product_id_ms == WBNormalizedProductImage.product_id_ms
            ).filter(
                (WBNormalizedProductImage.id == None) |  # нет записи
                (WBNormalizedProductImage.url == None) |  # url = NULL
                (WBNormalizedProductImage.url == '') |  # url = пустая строка
                (WBNormalizedProductImage.position == 0)  # position = 0 (нет изображений)
            ).all()

            return [p[0] for p in products_without_images]

    def update_image(self):

        products_without_img = self.get_products_without_images()

        with get_db_session() as session:

            for sku_without_img in products_without_img:

                parser_product = session.query(ParserProduct).filter(ParserProduct.id_ms ==sku_without_img).first()

                str_img = parser_product.images.replace('{', '').replace('}', '')

                str_img = str_img.replace(',', ';')

                new_img = WBNormalizedProductImage(product_id_ms=sku_without_img,
                                                   url=str_img
                                                   )
                session.add(new_img)

                self.stats['products_checked'] += 1



# Функция для запуска валидации
def run_validation() -> Dict[str, int]:
    """Запустить валидацию всех товаров"""
    validator = ProductDataValidator(request_timeout=10, batch_size=100)
    return validator.run_full_validation()


# Функция для запуска валидации с кастомными настройками
def run_validation_custom(
        request_timeout: int = 15,
        batch_size: int = 50
) -> Dict[str, int]:
    """Запустить валидацию с кастомными параметрами"""
    validator = ProductDataValidator(
        request_timeout=request_timeout,
        batch_size=batch_size
    )
    return validator.run_full_validation()


if __name__ == "__main__":
    # Пример запуска
    print("\n📊 ЗАПУСК ВАЛИДАЦИИ")
    stats = run_validation()
    print(f"✅ Статистика валидации: {stats}")

    print("\n" + "🖼️ " + "=" * 57)
    print(" ОБРАБОТКА ИЗОБРАЖЕНИЙ LU.RU ".center(60, "="))
    print("=" * 60 + "\n")

    generator = LuRuImageGenerator()
    stats_luru = generator.add_luru_images_for_all_products()
    print(f"✅ Статистика LU.RU: {stats_luru}")