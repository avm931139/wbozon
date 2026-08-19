import requests
from typing import List, Optional, Dict
from urllib.parse import urlparse
from loguru import logger
from sqlalchemy.orm import Session

from core.db.models import WBNormalizedProduct, WBNormalizedProductImage
from core.db.connection import get_db_session


class LuRuImageGenerator:
    """
    Класс для генерации и проверки изображений с домена lu.ru
    """

    def __init__(self, request_timeout: int = 10):
        self.request_timeout = request_timeout
        self.base_url = "https://img.lu.ru/add_photo/big"
        self.stats = {
            'products_processed': 0,
            'images_added': 0,
            'images_skipped': 0,
            'products_updated': 0
        }

    def _extract_path_from_url(self, url: str) -> Optional[str]:
        """
        Извлечь путь из URL формата //img.lu.ru/big/evoluce_sle1096-203-01.jpg
        или https://img.lu.ru/big/evoluce_sle1096-203-01.jpg

        Возвращает: "evoluce_sle1096-203-01.jpg"
        """
        if not url:
            return None

        # Убираем протокол, если есть
        clean_url = url.replace('http://', '').replace('https://', '')

        # Находим часть после /big/
        if '/big/' in clean_url:
            path = clean_url.split('/big/')[-1]
            return path

        return None

    def _is_image_accessible(self, url: str) -> bool:
        """
        Проверить, доступна ли ссылка на изображение
        """
        if not url:
            return False

        try:
            response = requests.head(
                url,
                timeout=self.request_timeout,
                allow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; LuRuImageGenerator/1.0)'}
            )

            if response.status_code == 405:  # HEAD не поддерживается
                response = requests.get(
                    url,
                    timeout=self.request_timeout,
                    stream=True,
                    allow_redirects=True
                )
                for _ in response.iter_content(chunk_size=100):
                    break
                response.close()

            return response.status_code == 200

        except Exception as e:
            logger.debug(f"Изображение недоступно {url[:100]}: {str(e)}")
            return False

    def _get_existing_images(self, session: Session, product_id_ms: str) -> List[str]:
        """
        Получить существующие изображения товара
        """
        image_record = session.query(WBNormalizedProductImage).filter(
            WBNormalizedProductImage.product_id_ms == product_id_ms
        ).first()

        if not image_record or not image_record.url:
            return []

        # Разбиваем строку на список URL
        existing_urls = [url.strip() for url in image_record.url.split(';') if url.strip()]
        return existing_urls

    def _update_product_images(self, session: Session, product_id_ms: str, new_urls: List[str]) -> bool:
        """
        Обновить изображения товара, добавив новые URL
        """
        # Получаем существующие изображения
        existing_urls = self._get_existing_images(session, product_id_ms)

        # Добавляем новые уникальные URL
        all_urls = existing_urls.copy()
        added_count = 0

        for url in new_urls:
            if url not in all_urls:
                all_urls.append(url)
                added_count += 1

        if added_count == 0:
            logger.debug(f"Для товара {product_id_ms} нет новых изображений для добавления")
            return False

        # Обновляем запись в БД
        image_record = session.query(WBNormalizedProductImage).filter(
            WBNormalizedProductImage.product_id_ms == product_id_ms
        ).first()

        if image_record:
            # Обновляем существующую запись
            new_images_string = ';'.join(all_urls)
            image_record.url = new_images_string
            image_record.position = len(all_urls)
            logger.info(f"Товар {product_id_ms}: добавлено {added_count} новых изображений. Всего: {len(all_urls)}")
        else:
            # Создаем новую запись
            new_images_string = ';'.join(all_urls)
            new_image_record = WBNormalizedProductImage(
                product_id_ms=product_id_ms,
                url=new_images_string,
                position=len(all_urls)
            )
            session.add(new_image_record)
            logger.info(f"Товар {product_id_ms}: создана запись с {len(all_urls)} изображениями")

        self.stats['images_added'] += added_count
        return True


    def add_luru_images_for_all_products(self, image_field_name: str = 'wb_images') -> Dict[str, int]:
        """
        Добавить изображения lu.ru для всех товаров, у которых есть ссылка на lu.ru

        :param image_field_name: название поля с изображениями (если нужно)
        """
        logger.info("Начинаем добавление изображений lu.ru для всех товаров")

        with get_db_session() as session:
            # Находим все товары, у которых есть изображения с lu.ru
            # Предполагаем, что ссылки хранятся в отдельной таблице или поле
            # Здесь нужно уточнить, где хранится исходная ссылка на lu.ru

            # Вариант: ищем в таблице WBNormalizedProductImage
            products_with_luru = session.query(WBNormalizedProductImage).filter(
                WBNormalizedProductImage.url.like('%img.lu.ru%')
            ).all()

            for img_record in products_with_luru:
                # Извлекаем первую ссылку (основное изображение)
                urls = img_record.url.split(';')
                for url in urls:
                    if 'img.lu.ru' in url:
                        # Добавляем дополнительные изображения
                        result = self.add_luru_images_for_product(img_record.product_id_ms, url)
                        logger.info(f"Результат для {img_record.product_id_ms}: {result}")
                        break  # берем только первую найденную ссылку lu.ru

        self.stats['products_processed'] = len(products_with_luru)
        logger.info(f"Завершено. Статистика: {self.stats}")
        return self.stats


    def _generate_image_urls(self, base_filename: str, max_images: int = 20) -> List[str]:
        """
        Генерировать URL для дополнительных изображений (2, 3, 4 и т.д.)

        Возвращает список URL до первого отсутствующего
        """
        urls = []

        # Разделяем имя файла и расширение
        if '.' in base_filename:
            name_parts = base_filename.rsplit('.', 1)
            name_without_ext = name_parts[0]
            ext = name_parts[1]
        else:
            name_without_ext = base_filename
            ext = 'jpg'

        # Генерируем последовательно от 2 до max_images
        for i in range(2, max_images + 1):
            numbered_filename = f"{name_without_ext}_{i}.{ext}"

            # Формируем путь с буквами для структуры папок
            first_letter = name_without_ext[0] if name_without_ext else ''
            second_letter = name_without_ext[1] if len(name_without_ext) > 1 else ''
            third_letter = name_without_ext[2] if len(name_without_ext) > 2 else ''

            if first_letter and second_letter and third_letter:
                folder_path = f"{first_letter}/{second_letter}/{third_letter}"
            else:
                folder_path = "unknown"

            url = f"{self.base_url}/{folder_path}/{numbered_filename}"
            urls.append(url)

        return urls

    def add_luru_images_for_product(self, product_id_ms: str, original_url: str) -> Dict[str, any]:
        """
        Добавить изображения lu.ru для конкретного товара.
        Останавливается при первом недоступном изображении.
        """
        with get_db_session() as session:
            # Проверяем существование товара
            product = session.query(WBNormalizedProduct).filter(
                WBNormalizedProduct.product_id_ms == product_id_ms
            ).first()

            if not product:
                return {'error': f'Товар {product_id_ms} не найден'}

            # Извлекаем базовое имя файла
            base_filename = self._extract_path_from_url(original_url)
            if not base_filename:
                return {'error': f'Не удалось извлечь путь из URL: {original_url}'}

            logger.info(f"Обрабатываем товар {product_id_ms}, базовый файл: {base_filename}")

            # Генерируем URL для дополнительных изображений
            generated_urls = self._generate_image_urls(base_filename)

            # Проверяем доступность последовательно, останавливаемся при первом недоступном
            valid_urls = []
            for i, url in enumerate(generated_urls, start=2):
                if self._is_image_accessible(url):
                    valid_urls.append(url)
                    logger.info(f"✅ Изображение {i} доступно: {url}")
                else:
                    logger.info(f"❌ Изображение {i} недоступно, останавливаем проверку (дальнейшие тоже будут недоступны)")
                    break  # Останавливаемся при первом недоступном

            # Обновляем изображения в БД
            if valid_urls:
                updated = self._update_product_images(session, product_id_ms, valid_urls)
                session.commit()

                if updated:
                    self.stats['products_updated'] += 1
                    return {
                        'success': True,
                        'product_id_ms': product_id_ms,
                        'images_added': len(valid_urls),
                        'last_successful_index': 1 + len(valid_urls),  # 1 - основное, + доп. изображения
                        'added_urls': valid_urls
                    }
                else:
                    return {
                        'success': False,
                        'product_id_ms': product_id_ms,
                        'message': 'Нет новых изображений для добавления'
                    }
            else:
                return {
                    'success': False,
                    'product_id_ms': product_id_ms,
                    'message': 'Нет доступных дополнительных изображений (уже с _2 нет)'
                }

# Функция для быстрого использования
def add_luru_images(product_id_ms: str, original_url: str) -> Dict[str, any]:
    """
    Добавить изображения lu.ru для одного товара
    """
    generator = LuRuImageGenerator()
    return generator.add_luru_images_for_product(product_id_ms, original_url)


# # Пример использования
# if __name__ == "__main__":
#
#     generator = LuRuImageGenerator()
#     stats = generator.add_luru_images_for_all_products()
#     print(f"Статистика: {stats}")