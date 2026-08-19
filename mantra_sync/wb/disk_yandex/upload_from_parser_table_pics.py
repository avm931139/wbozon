"""
Модуль для загрузки изображений товаров из БД (ParserProduct) на Яндекс.Диск
С возможностью указания базовой папки на диске и конвертации SVG в JPEG
"""

import os
import io
import re
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from loguru import logger
from PIL import Image

# Импортируем ваш контекстный менеджер и модели
from core.db.connection import get_db_session
from settings import Config
from core.db.models import ParserProduct, WBNormalizedProductImage


# ============================================
# 1. КЛАСС ДЛЯ РАБОТЫ С ЯНДЕКС ДИСКОМ
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

    def _get_full_path(self, product_id_ms: str) -> str:
        """
        Формирует полный путь к папке товара на Яндекс.Диске

        Args:
            product_id_ms: ID товара из МойСклад (например, "290970")

        Returns:
            полный путь: "/product_photos/290970" или "/290970" (если base_folder="/")
        """
        # Убираем начальные слеши
        base = self.base_folder.lstrip('/')
        folder = product_id_ms.lstrip('/')

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

    def _is_svg(self, content: bytes) -> bool:
        """Проверяет, является ли содержимое SVG"""
        content_stripped = content.strip()
        return content_stripped.startswith(b'<?xml') or content_stripped.startswith(b'<svg')

    def _convert_svg_to_jpeg(self, svg_content: bytes) -> Optional[bytes]:
        """
        Конвертирует SVG в JPEG с помощью cairosvg

        Returns:
            JPEG в виде bytes или None при ошибке
        """
        try:
            import cairosvg
            png_data = cairosvg.svg2png(bytestring=svg_content)

            # Конвертируем PNG в JPEG
            img = Image.open(io.BytesIO(png_data))

            # Создаем белый фон для JPEG (так как JPEG не поддерживает прозрачность)
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Сохраняем в JPEG
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=85)
            return output.getvalue()

        except ImportError:
            logger.error("Для конвертации SVG требуется установить cairosvg: pip install cairosvg")
            return None
        except Exception as e:
            logger.error(f"Ошибка конвертации SVG в JPEG: {e}")
            return None



    def _generate_filename(self, url: str, index: int, product_id_ms: str) -> str:
        """
        Генерирует имя файла на основе URL или product_id_ms

        Приоритет:
        1. Если в URL есть UUID - берем последнюю часть UUID
        2. Иначе используем формат {product_id_ms}_{index}

        Args:
            url: URL изображения
            index: порядковый номер
            product_id_ms: ID товара

        Returns:
            Имя файла с расширением
        """
        # Пытаемся извлечь последнюю часть UUID
        short_uuid = product_id_ms.split('-')[4]

        if short_uuid:
            base_name = str(index) + '_' + short_uuid
        else:
            base_name = f"{index}_{product_id_ms}"

        return base_name

    def download_and_upload(self, file_url: str, disk_path: str, convert_svg: bool = True) -> bool:
        """
        Скачивает файл по URL и загружает на Яндекс.Диск.
        Поддерживает конвертацию SVG в JPEG.

        Args:
            file_url: URL файла
            disk_path: путь на Яндекс.Диске
            convert_svg: конвертировать ли SVG в JPEG

        Returns:
            True при успехе, False при ошибке
        """
        try:
            # Скачиваем файл
            logger.debug(f"Скачивание файла: {file_url[:100]}...")
            response = requests.get(file_url, timeout=30)

            if response.status_code != 200:
                logger.error(f"Не удалось скачать файл: HTTP {response.status_code}")
                return False

            file_content = response.content

            # Проверяем и конвертируем SVG
            is_svg = self._is_svg(file_content)
            if is_svg and convert_svg:
                logger.debug(f"Обнаружен SVG, конвертируем в JPEG: {file_url}")
                file_content = self._convert_svg_to_jpeg(file_content)
                if file_content is None:
                    logger.error(f"Не удалось сконвертировать SVG: {file_url}")
                    return False
                # Меняем расширение в пути на .jpg
                disk_path = disk_path.rsplit('.', 1)[0] + '.jpg'

            # Получаем URL для загрузки на диск
            upload_url = self.get_upload_url(disk_path)
            if not upload_url:
                return False

            # Загружаем на диск
            upload_response = requests.put(upload_url, data=file_content)

            if upload_response.status_code == 201:
                logger.debug(f"Файл успешно загружен: {disk_path}")
                return True
            else:
                logger.error(f"Ошибка загрузки на диск: {upload_response.status_code} - {upload_response.text}")
                return False

        except requests.Timeout:
            logger.error(f"Таймаут при загрузке: {file_url[:100]}")
            return False
        except Exception as e:
            logger.error(f"Ошибка при загрузке файла: {e}")
            return False

    def upload_photos(self, product_id_ms: str, photo_urls: List[str]) -> Tuple[int, List[str], str]:
        """
        Загружает фотографии в папку товара

        Args:
            product_id_ms: ID товара из МойСклад (используется как имя папки)
            photo_urls: список ссылок на фото

        Returns:
            (количество успешно загруженных, список ошибок, полный путь на диске)
        """
        # Формируем полный путь к папке товара
        folder_full_path = self._get_full_path(product_id_ms)

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

            url = url.strip()

            # Определяем расширение файла
            ext = self._get_file_extension(url)

            # Для SVG файлов всегда используем .jpg после конвертации
            if ext.lower() == '.svg':
                ext = '.jpg'

            # Генерируем имя файла (из UUID или из product_id_ms + индекс)
            base_name = self._generate_filename(url, index, product_id_ms)
            filename = f"{base_name}{ext}"
            disk_path = f"{folder_full_path}/{filename}"

            logger.info(f"Загрузка {filename} ({index}/{len(photo_urls)})")

            # Загружаем
            if self.download_and_upload(url, disk_path, convert_svg=True):
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

        # Убираем якорь (всё после #)
        url_without_params = url_without_params.split('#')[0]

        # Извлекаем расширение
        ext = os.path.splitext(url_without_params)[1]

        # Если расширение не найдено, пробуем по MIME типу (по умолчанию jpg)
        if not ext:
            ext = '.jpg'

        # Приводим к нижнему регистру
        return ext.lower()


# ============================================
# 2. ОСНОВНАЯ ФУНКЦИЯ ЗАГРУЗКИ ИЗ БД
# ============================================

class ProductImageUploader:
    """Класс для загрузки изображений товаров из ParserProduct на Яндекс.Диск"""

    def __init__(self, yandex_token: str, base_folder: str = "/"):
        """
        Args:
            yandex_token: OAuth токен Яндекс.Диска
            base_folder: базовая папка на Яндекс.Диске (например, "/product_photos")
                         Если не указана, папки создаются в корне
        """
        self.yandex_uploader = YandexDiskUploader(yandex_token, base_folder)
        self.base_folder = base_folder

    def parse_images_field(self, images_string: str) -> List[str]:
        """
        Разбирает поле images из таблицы ParserProduct

        Поддерживаемые форматы:
        1. "url1;url2;url3;"
        2. "{url1,url2,url3}" - формат с фигурными скобками и запятыми
        3. "url1,url2,url3" - просто запятые

        Args:
            images_string: строка с URL изображений

        Returns:
            список URL
        """
        if not images_string:
            return []

        images_string = images_string.strip()

        # Формат с фигурными скобками: {url1,url2,url3}
        if images_string.startswith('{') and images_string.endswith('}'):
            # Убираем фигурные скобки
            content = images_string[1:-1]
            # Разделяем по запятой
            urls = content.split(',')
            # Чистим пробелы
            urls = [url.strip() for url in urls if url.strip()]
            return urls

        # Формат с точкой с запятой
        elif ';' in images_string:
            # Удаляем завершающую точку с запятой если есть
            clean_string = images_string.rstrip(';')
            # Разделяем по точке с запятой
            urls = clean_string.split(';')
            # Чистим пробелы
            urls = [url.strip() for url in urls if url.strip()]
            return urls

        # Формат с запятой
        elif ',' in images_string:
            urls = images_string.split(',')
            urls = [url.strip() for url in urls if url.strip()]
            return urls

        # Одиночный URL
        else:
            return [images_string]

    def get_products_data_to_upload(self, limit: Optional[int] = None,
                                     product_id_ms: Optional[str] = None) -> List[Dict]:
        """
        Получает данные товаров для загрузки из таблицы ParserProduct
        Возвращает список словарей, а не ORM объектов, чтобы избежать DetachedInstanceError

        Args:
            limit: ограничение количества записей (для тестирования)
            product_id_ms: если указан, загружает только один товар

        Returns:
            Список словарей с данными товаров
        """
        with get_db_session() as session:
            query = session.query(ParserProduct)

            if product_id_ms:
                query = query.filter(ParserProduct.id_ms == product_id_ms)

            if limit:
                query = query.limit(limit)

            products = query.all()

            # Преобразуем ORM объекты в словари ДО закрытия сессии
            products_data = []
            for product in products:
                products_data.append({
                    "id_ms": product.id_ms,
                    "articul_site": product.articul_site,
                    "name_site": product.name_site,
                    "groupe_site": product.groupe_site,
                    "url": product.url,
                    "images": product.images,
                    "description": product.description,
                    "brand": product.brand,
                    "prices": product.prices,
                })

            logger.info(f"Найдено товаров для обработки: {len(products_data)}")
            return products_data

    def update_normalized_images(self, product_id_ms: str, urls: List[str],
                                  uploaded_count: int, errors: List[str],
                                  yandex_path: str):
        """
        Обновляет/создает записи в WBNormalizedProductImage

        Args:
            product_id_ms: ID товара из МойСклад
            urls: список оригинальных URL изображений
            uploaded_count: количество успешно загруженных файлов
            errors: список ошибок
            yandex_path: путь на Яндекс.Диске
        """
        with get_db_session() as session:
            # Удаляем старые записи для этого товара
            session.query(WBNormalizedProductImage).filter_by(
                product_id_ms=product_id_ms
            ).delete()

            # Создаем новые записи для каждого URL
            for index, url in enumerate(urls, start=1):
                # Проверяем, какие поля есть в модели WBNormalizedProductImage
                # Убираем поле uploaded_to_yadisk, если его нет
                normalized_image = WBNormalizedProductImage(
                    product_id_ms=product_id_ms,
                    url=url,
                    position=index,
                    # uploaded_to_yadisk=(index <= uploaded_count),  # Закомментировано, если поля нет
                    # uploaded_at=datetime.now() if index <= uploaded_count else None,  # Если поля нет
                    # files_count=uploaded_count,  # Если поля нет
                    # upload_error="; ".join(errors) if errors else None,  # Если поля нет
                    # yandex_path=f"{yandex_path}/{product_id_ms}_{index}.jpg"  # Если поля нет
                )
                session.add(normalized_image)

            session.commit()
            logger.debug(f"Обновлены нормализованные изображения для {product_id_ms}")

    def upload_all_products(self, limit: Optional[int] = None,
                           product_id_ms: Optional[str] = None,
                           update_normalized: bool = False) -> Dict:
        """
        Загружает изображения для всех товаров в таблице ParserProduct

        Args:
            limit: ограничение количества записей (для тестирования)
            product_id_ms: загрузить только конкретный товар
            update_normalized: обновлять ли таблицу WBNormalizedProductImage (по умолчанию False)

        Returns:
            словарь со статистикой загрузки
        """
        # Получаем данные товаров в виде словарей (не ORM объектов!)
        products_data = self.get_products_data_to_upload(limit, product_id_ms)

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

        for product_data in products_data:
            logger.info(f"\n📦 Товар: {product_data['id_ms']} (арт: {product_data['articul_site']})")
            logger.info(f"   Название: {product_data['name_site'][:50] if product_data['name_site'] else 'N/A'}...")

            # Разбираем ссылки из поля images
            urls = self.parse_images_field(product_data['images'])

            if not urls:
                logger.warning(f"  Нет ссылок для загрузки в поле images")
                total_failed_products += 1
                results.append({
                    "product_id_ms": product_data['id_ms'],
                    "articul": product_data['articul_site'],
                    "success": False,
                    "files_uploaded": 0,
                    "total_files": 0,
                    "yandex_path": None,
                    "error": "Нет ссылок в поле images"
                })
                continue

            logger.info(f"  Найдено ссылок: {len(urls)}")
            for i, url in enumerate(urls[:3]):  # Показываем первые 3 ссылки для примера
                logger.info(f"    Ссылка {i+1}: {url[:80]}...")
            if len(urls) > 3:
                logger.info(f"    ... и еще {len(urls) - 3} ссылок")

            # Загружаем фотографии
            uploaded_count, errors, yandex_path = self.yandex_uploader.upload_photos(
                product_data['id_ms'],
                urls
            )

            # Обновляем связанную таблицу WBNormalizedProductImage (опционально, по умолчанию выключено)
            if update_normalized:
                self.update_normalized_images(
                    product_data['id_ms'],
                    urls,
                    uploaded_count,
                    errors,
                    yandex_path
                )

            # Статистика
            is_success = (uploaded_count == len(urls))

            if is_success:
                logger.info(f"  ✅ Успешно загружено: {uploaded_count}/{len(urls)}")
                logger.info(f"  📁 Путь на диске: {yandex_path}")
                total_success += 1
            else:
                logger.warning(f"  ⚠ Частично загружено: {uploaded_count}/{len(urls)}")
                logger.warning(f"  📁 Путь на диске: {yandex_path}")
                total_failed_products += 1

            results.append({
                "product_id_ms": product_data['id_ms'],
                "articul": product_data['articul_site'],
                "success": is_success,
                "files_uploaded": uploaded_count,
                "total_files": len(urls),
                "yandex_path": yandex_path,
                "error": "; ".join(errors) if errors else None
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


# ============================================
# 3. ПРИМЕР ИСПОЛЬЗОВАНИЯ
# ============================================

def main():
    # НАСТРОЙКИ
    YANDEX_TOKEN = Config.OAUTH_TOKEN_YA_DISK

    # ВАРИАНТЫ БАЗОВОЙ ПАПКИ:
    BASE_FOLDER = "ВБ люстры фото/Люстры Россия"

    # СОЗДАЕМ ЗАГРУЗЧИК
    uploader = ProductImageUploader(YANDEX_TOKEN, base_folder=BASE_FOLDER)

    # Варианты запуска:

    # 1. Загружаем первые 5 товаров для теста (без обновления нормализованных изображений)
    # result = uploader.upload_all_products(limit=5, update_normalized=False)

    # 2. Загружаем все товары
    result = uploader.upload_all_products()

    # 3. Только конкретный товар по id_ms
    # result = uploader.upload_all_products(product_id_ms="290970")

    # Выводим результат
    logger.info(f"\nИтоговый результат: {result}")

    return result


if __name__ == "__main__":
    main()