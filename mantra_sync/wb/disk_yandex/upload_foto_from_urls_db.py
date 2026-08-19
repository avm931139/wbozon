"""
Модуль для загрузки изображений товаров из БД на Яндекс.Диск
С возможностью указания базовой папки на диске
"""

import os
import requests
from typing import List, Dict, Optional, Tuple
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
from loguru import logger

# Импортируем ваш контекстный менеджер
from core.db.connection import get_db_session
from settings import Config
from core.db.models import WBNormalizedProductImage
Base = declarative_base()


# ============================================
# 1. МОДЕЛЬ БД (только нужные колонки)
# ============================================


# ============================================
# 2. КЛАСС ДЛЯ РАБОТЫ С ЯНДЕКС ДИСКОМ
# ============================================

class YandexDiskUploader:
    """Класс для загрузки файлов на Яндекс.Диск"""

    def __init__(self, token: str, base_folder: str = "/"):
        """
        Args:
            token: OAuth токен Яндекс.Диска
            base_folder: базовая папка на диске (по умолчанию корень "/")
                         Примеры: "/product_photos", "/catalog/images", "/"
        """
        self.token = token
        self.base_folder = base_folder.rstrip('/')  # убираем слеш в конце
        self.base_url = "https://cloud-api.yandex.net/v1/disk"
        self.headers = {
            "Authorization": f"OAuth {token}",
            "Content-Type": "application/json"
        }

        # Создаем базовую папку, если она не корневая
        if self.base_folder and self.base_folder != "/":
            self._ensure_base_folder()

    def _ensure_base_folder(self) -> bool:
        """Создает базовую папку, если она не существует"""
        logger.info(f"Проверка/создание базовой папки: {self.base_folder}")
        return self.create_folder(self.base_folder)

    def _get_full_path(self, product_id: str) -> str:
        """
        Формирует полный путь к папке товара на Яндекс.Диске

        Args:
            product_id: ID товара (например, "290970")

        Returns:
            полный путь: "/product_photos/290970" или "/290970" (если base_folder="/")
        """
        # Убираем начальные слеши
        base = self.base_folder.lstrip('/')
        folder = product_id.lstrip('/')

        if base:
            return f"/{base}/{folder}"
        else:
            return f"/{folder}"

    def create_folder(self, folder_path: str) -> bool:
        """Создание папки на Яндекс.Диске"""
        folder_path = folder_path.lstrip('/')
        url = f"{self.base_url}/resources"
        params = {"path": folder_path}

        try:
            response = requests.put(url, headers=self.headers, params=params)

            if response.status_code == 201:
                logger.debug(f"Папка '{folder_path}' создана")
                return True
            elif response.status_code == 409:
                logger.debug(f"Папка '{folder_path}' уже существует")
                return True
            else:
                logger.error(f"Ошибка создания папки: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Ошибка сети при создании папки: {e}")
            return False

    def get_upload_url(self, disk_path: str, overwrite: bool = True) -> Optional[str]:
        """Получение URL для загрузки файла"""
        url = f"{self.base_url}/resources/upload"
        params = {
            "path": disk_path,
            "overwrite": str(overwrite).lower()
        }

        try:
            response = requests.get(url, headers=self.headers, params=params)
            if response.status_code == 200:
                return response.json().get("href")
            else:
                logger.error(f"Ошибка получения URL для загрузки: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении URL загрузки: {e}")
            return None

    def download_and_upload(self, file_url: str, disk_path: str) -> bool:
        """Скачивает файл по URL и загружает на Яндекс.Диск"""
        try:
            # Скачиваем файл
            logger.debug(f"Скачивание файла: {file_url[:100]}...")
            response = requests.get(file_url, timeout=30, stream=True)

            if response.status_code != 200:
                logger.error(f"Не удалось скачать файл: HTTP {response.status_code}")
                return False

            # Получаем URL для загрузки на диск
            upload_url = self.get_upload_url(disk_path)
            if not upload_url:
                return False

            # Загружаем на диск
            upload_response = requests.put(upload_url, data=response.content)

            if upload_response.status_code == 201:
                logger.debug(f"Файл успешно загружен: {disk_path}")
                return True
            else:
                logger.error(f"Ошибка загрузки на диск: {upload_response.status_code}")
                return False

        except requests.Timeout:
            logger.error(f"Таймаут при загрузке: {file_url[:100]}")
            return False
        except Exception as e:
            logger.error(f"Ошибка при загрузке файла: {e}")
            return False

    def upload_photos(self, product_id: str, photo_urls: List[str]) -> Tuple[int, List[str], str]:
        """
        Загружает фотографии в папку товара

        Args:
            product_id: ID товара (используется как имя папки)
            photo_urls: список ссылок на фото

        Returns:
            (количество успешно загруженных, список ошибок, полный путь на диске)
        """
        # Формируем полный путь к папке товара (динамически)
        folder_full_path = self._get_full_path(product_id)

        logger.info(f"Целевая папка на Яндекс.Диске: {folder_full_path}")

        # Создаем папку товара
        if not self.create_folder(folder_full_path):
            return 0, ["Не удалось создать папку товара"], folder_full_path

        errors = []
        success_count = 0

        for index, url in enumerate(photo_urls, start=1):
            if not url or not url.strip():
                error_msg = f"Ссылка {index}: пустая"
                errors.append(error_msg)
                logger.warning(error_msg)
                continue

            # Определяем расширение файла
            ext = self._get_file_extension(url)

            # Формируем имя файла: product_id_1.jpg
            filename = f"{product_id}_{index}{ext}"
            disk_path = f"{folder_full_path}/{filename}"

            logger.info(f"Загрузка {filename} ({index}/{len(photo_urls)})")

            # Загружаем
            if self.download_and_upload(url.strip(), disk_path):
                success_count += 1
                logger.info(f"  ✓ {filename} загружен")
            else:
                error_msg = f"Ссылка {index}: не удалось загрузить {url[:80]}..."
                errors.append(error_msg)
                logger.error(f"  ✗ {filename} - ошибка")

        return success_count, errors, folder_full_path

    @staticmethod
    def _get_file_extension(url: str) -> str:
        """Извлекает расширение файла из URL"""
        # Убираем параметры запроса (всё после ?)
        url_without_params = url.split('?')[0]

        # Извлекаем расширение
        ext = os.path.splitext(url_without_params)[1]

        # Если расширение не найдено, пробуем по MIME типу (по умолчанию jpg)
        if not ext:
            ext = '.jpg'

        # Приводим к нижнему регистру
        return ext.lower()


# ============================================
# 3. ОСНОВНАЯ ФУНКЦИЯ ЗАГРУЗКИ ИЗ БД
# ============================================

class ProductImageUploader:
    """Класс для загрузки изображений товаров из БД на Яндекс.Диск"""

    def __init__(self, yandex_token: str, base_folder: str = "/"):
        """
        Args:
            yandex_token: OAuth токен Яндекс.Диска
            base_folder: базовая папка на Яндекс.Диске (например, "/product_photos")
                         Если не указана, папки создаются в корне
        """
        self.yandex_uploader = YandexDiskUploader(yandex_token, base_folder)
        self.base_folder = base_folder

    def get_images_to_upload(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Получает записи, которые нужно загрузить

        Args:
            limit: ограничение количества записей (для тестирования)
        """
        with get_db_session() as session:
            query = session.query(WBNormalizedProductImage)

            # Можно загружать только те, которые еще не загружены
            # query = query.filter(WBNormalizedProductImage.uploaded_to_yadisk == False)

            if limit:
                query = query.limit(limit)

            products = query.all()

            # Экспортируем данные в словари
            products_data = []
            for product in products:
                products_data.append({
                    "id": product.id,
                    "product_id_ms": product.product_id_ms,
                    "url": product.url,
                    "position": product.position,
                })

            return products_data

    def parse_urls(self, url_string: str) -> List[str]:
        """Разбирает строку с URL, разделенными точкой с запятой"""
        if not url_string:
            return []

        # Разделяем по ; и чистим пробелы
        urls = [url.strip() for url in url_string.split(';') if url.strip()]
        return urls

    # def update_product_status(self, product_id: int, uploaded_to_yadisk: bool,
    #                           files_count: int, upload_error: Optional[str] = None):
    #     """
    #     Обновляет статус загрузки в БД
    #
    #     Args:
    #         product_id: ID записи в БД
    #         uploaded_to_yadisk: успешно ли загружены все фото
    #         files_count: количество загруженных файлов
    #         upload_error: текст ошибки (если есть)
    #     """
    #     with get_db_session() as session:
    #         product = session.query(WBNormalizedProductImage).filter_by(id=product_id).first()
    #         if product:
    #             product.uploaded_to_yadisk = uploaded_to_yadisk
    #             product.uploaded_at = datetime.now()
    #             product.files_count = files_count
    #             product.upload_error = upload_error
    #             session.commit()
    #             logger.debug(f"Обновлен статус для product_id={product.product_id_ms}: uploaded={uploaded_to_yadisk}")
    #         else:
    #             logger.error(f"Не найден продукт с id={product_id}")

    def upload_all_products(self, limit: Optional[int] = None) -> Dict:
        """
        Загружает изображения для всех товаров в таблице

        Args:
            limit: ограничение количества записей (для тестирования)

        Returns:
            словарь со статистикой загрузки
        """
        # Получаем данные из БД
        products_data = self.get_images_to_upload(limit)

        if not products_data:
            logger.info("Нет записей для загрузки")
            return {"total": 0, "success": 0, "failed": 0, "details": []}

        logger.info(f"{'=' * 60}")
        logger.info(f"НАЧАЛО ЗАГРУЗКИ ИЗОБРАЖЕНИЙ")
        logger.info(f"Базовая папка на Яндекс.Диске: {self.base_folder if self.base_folder else '/'}")
        logger.info(f"Всего товаров для обработки: {len(products_data)}")
        logger.info(f"{'=' * 60}")

        results = []
        total_success = 0
        total_failed_products = 0

        for product in products_data:
            logger.info(f"\n📦 Товар: {product['product_id_ms']} (ID записи={product['id']})")

            # Разбираем ссылки
            urls = self.parse_urls(product['url'])

            if not urls:
                logger.warning(f"  Нет ссылок для загрузки")
                # Обновляем статус в БД
                # self.update_product_status(
                #     product_id=product['id'],
                #     uploaded_to_yadisk=False,
                #     files_count=0,
                #     upload_error="Нет ссылок для загрузки"
                # )
                total_failed_products += 1
                results.append({
                    "product_id": product['product_id_ms'],
                    "success": False,
                    "files_uploaded": 0,
                    "total_files": 0,
                    "yandex_path": None,
                    "error": "Нет ссылок"
                })
                continue

            logger.info(f"  Найдено ссылок: {len(urls)}")
            logger.info(f"  Пример ссылки: {urls[0][:80]}...")

            # Загружаем фотографии (путь формируется динамически)
            uploaded_count, errors, yandex_path = self.yandex_uploader.upload_photos(
                product['product_id_ms'],
                urls
            )

            # Обновляем статус в БД (без сохранения пути)
            error_message = "; ".join(errors) if errors else None
            is_success = (uploaded_count == len(urls))

            # self.update_product_status(
            #     product_id=product['id'],
            #     uploaded_to_yadisk=is_success,
            #     files_count=uploaded_count,
            #     upload_error=error_message
            # )

            # Статистика
            if is_success:
                logger.info(f"  ✅ Успешно загружено: {uploaded_count}/{len(urls)}")
                logger.info(f"  📁 Путь на диске: {yandex_path}")
                total_success += 1
            else:
                logger.warning(f"  ⚠ Частично загружено: {uploaded_count}/{len(urls)}")
                logger.warning(f"  📁 Путь на диске: {yandex_path}")
                total_failed_products += 1

            results.append({
                "product_id": product['product_id_ms'],
                "success": is_success,
                "files_uploaded": uploaded_count,
                "total_files": len(urls),
                "yandex_path": yandex_path,
                "error": error_message
            })

        # Итоговая статистика
        logger.info(f"\n{'=' * 60}")
        logger.info(f"ЗАГРУЗКА ЗАВЕРШЕНА")
        logger.info(f"Всего товаров: {len(products_data)}")
        logger.info(f"Полностью успешно: {total_success}")
        logger.info(f"С ошибками: {total_failed_products}")
        logger.info(f"{'=' * 60}")

        return {
            "total": len(products_data),
            "success": total_success,
            "failed": total_failed_products,
            "base_folder": self.base_folder,
            "details": results
        }

    def reset_upload_status(self, product_id_ms: Optional[str] = None):
        """
        Сбрасывает статус загрузки (если нужно перезагрузить)

        Args:
            product_id_ms: если указан, сбрасывает только для одного товара
        """
        with get_db_session() as session:
            if product_id_ms:
                product = session.query(WBNormalizedProductImage).filter_by(product_id_ms=product_id_ms).first()
                if product:
                    product.uploaded_to_yadisk = False
                    product.upload_error = None
                    product.uploaded_at = None
                    product.files_count = 0
                    logger.info(f"Сброшен статус для {product_id_ms}")
                else:
                    logger.warning(f"Товар {product_id_ms} не найден")
            else:
                session.query(WBNormalizedProductImage).update({
                    "uploaded_to_yadisk": False,
                    "upload_error": None,
                    "uploaded_at": None,
                    "files_count": 0
                })
                logger.info(f"Сброшен статус для всех товаров")

            session.commit()


# ============================================
# 4. ПРИМЕР ИСПОЛЬЗОВАНИЯ
# ============================================

def main():
    # НАСТРОЙКИ
    YANDEX_TOKEN = Config.OAUTH_TOKEN_YA_DISK

    # ВАРИАНТЫ БАЗОВОЙ ПАПКИ:

    # 1. Папки создаются прямо в корне: /290970/, /290971/ и т.д.
    BASE_FOLDER = "ВБ люстры фото/Люстры Россия"

    # 2. Папки создаются внутри указанной папки: /product_images/290970/
    # BASE_FOLDER = "/product_images"

    # 3. Вложенные папки: /catalog/2024/products/290970/
    # BASE_FOLDER = "/catalog/2024/products"

    # СОЗДАЕМ ЗАГРУЗЧИК
    uploader = ProductImageUploader(YANDEX_TOKEN, base_folder=BASE_FOLDER)

    # Загружаем все товары
    result = uploader.upload_all_products()

    # Или только первые 5 для теста
    # result = uploader.upload_all_products(limit=5)

    # Выводим результат
    logger.info(f"\nИтоговый результат: {result}")

    return result


if __name__ == "__main__":
    main()