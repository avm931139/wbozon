import requests
import re
from typing import List, Dict, Optional, Tuple
from loguru import logger
from sqlalchemy import func
from core.db.connection import get_db_session
from core.db.models import ParserProduct


class ProductImagesValidator:
    """Класс для проверки и нормализации изображений товаров"""

    def __init__(self):
        self.session = requests.Session()
        self.session.timeout = 10
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def parse_images_field(self, images_string: str) -> List[str]:
        """
        Разбирает поле images из таблицы ParserProduct

        Формат: "{url1,url2,url3}" - фигурные скобки и запятые

        Args:
            images_string: строка с URL изображений в формате {url1,url2,url3}

        Returns:
            список URL
        """
        if not images_string or images_string == '{}':
            return []

        images_string = images_string.strip()

        # Убираем фигурные скобки в начале и конце
        if images_string.startswith('{') and images_string.endswith('}'):
            content = images_string[1:-1]
        else:
            content = images_string

        if not content:
            return []

        # Разделяем по запятой
        urls = content.split(',')
        # Чистим пробелы и фильтруем пустые
        urls = [url.strip() for url in urls if url.strip()]

        return urls

    def build_images_string(self, urls: List[str]) -> str:
        """
        Собирает список URL в строку с разделителем ";"

        Формат: {url1;url2;url3}

        Args:
            urls: список URL

        Returns:
            строка вида "{url1;url2;url3}"
        """
        if not urls:
            return "{}"
        return "{" + ";".join(urls) + "}"

    def check_url_availability(self, url: str) -> bool:
        """
        Проверяет доступность URL

        Args:
            url: URL для проверки

        Returns:
            True если URL доступен, False в противном случае
        """
        try:
            # Используем HEAD запрос для экономии трафика
            response = self.session.head(url, allow_redirects=True, timeout=10)
            return response.status_code == 200
        except requests.RequestException as e:
            logger.debug(f"URL недоступен {url[:80]}...: {e}")
            return False

    def validate_and_update_images(self,
                                   product_id_ms: Optional[str] = None,
                                   limit: Optional[int] = None,
                                   dry_run: bool = False,
                                   test_mode: bool = False,
                                   check_availability: bool = True) -> Dict:
        """
        Проверяет изображения товаров и обновляет поле images

        Args:
            product_id_ms: ID товара (если нужно обработать только один)
            limit: ограничение количества товаров (для теста)
            dry_run: если True, только проверка без сохранения в БД
            test_mode: если True, выводит подробную информацию для отладки
            check_availability: проверять ли доступность URL

        Returns:
            словарь со статистикой
        """
        mode_text = []
        if dry_run:
            mode_text.append("DRY RUN (без сохранения)")
        if test_mode:
            mode_text.append("TEST MODE (подробный вывод)")
        if limit:
            mode_text.append(f"LIMIT={limit}")

        logger.info("=" * 70)
        logger.info("ПРОВЕРКА И НОРМАЛИЗАЦИЯ ИЗОБРАЖЕНИЙ ТОВАРОВ")
        if mode_text:
            logger.info(f"Режим: {', '.join(mode_text)}")
        logger.info("=" * 70)

        with get_db_session() as session:
            # Получаем товары
            query = session.query(ParserProduct)

            if product_id_ms:
                query = query.filter(ParserProduct.id_ms == product_id_ms)
                logger.info(f"Фильтр по товару: {product_id_ms}")

            if limit:
                query = query.limit(limit)

            products = query.all()
            logger.info(f"Найдено товаров для обработки: {len(products)}")

            stats = {
                "total_products": len(products),
                "processed_products": 0,
                "total_urls": 0,
                "valid_urls": 0,
                "invalid_urls": 0,
                "updated_products": 0,
                "details": []
            }

            for product in products:
                logger.info(f"\n{'─' * 70}")
                logger.info(f"📦 Товар: {product.id_ms}")
                logger.info(f"   Артикул: {product.articul_site}")
                logger.info(f"   Название: {product.name_site[:60]}..." if len(
                    product.name_site) > 60 else f"   Название: {product.name_site}")

                # Текущая строка images
                current_raw = product.images
                logger.info(f"   📸 Исходная строка: {current_raw[:100]}..." if len(
                    current_raw) > 100 else f"   📸 Исходная строка: {current_raw}")

                # Парсим текущие URL
                current_urls = self.parse_images_field(current_raw)
                logger.info(f"   📸 Найдено URL: {len(current_urls)}")

                if not current_urls:
                    logger.warning(f"   ⚠️ Нет изображений для товара")
                    stats["details"].append({
                        "product_id_ms": product.id_ms,
                        "status": "no_images",
                        "total": 0,
                        "valid": 0,
                        "invalid": 0
                    })
                    continue

                if test_mode:
                    for idx, url in enumerate(current_urls, start=1):
                        logger.info(f"      [{idx}] {url}")

                # Проверяем каждый URL
                valid_urls = []
                invalid_urls = []

                for idx, url in enumerate(current_urls, start=1):
                    if test_mode:
                        logger.info(f"   [{idx}/{len(current_urls)}] Проверка: {url[:80]}...")

                    if check_availability:
                        is_valid = self.check_url_availability(url)
                    else:
                        is_valid = True  # Пропускаем проверку

                    if is_valid:
                        valid_urls.append(url)
                        if test_mode:
                            logger.info(f"      ✅ ДОСТУПЕН")
                    else:
                        invalid_urls.append(url)
                        logger.warning(f"      ❌ НЕ ДОСТУПЕН: {url[:80]}...")

                # Формируем новую строку в формате {url1;url2;url3}
                new_images_string = self.build_images_string(valid_urls)

                # Выводим информацию
                logger.info(f"   📊 Результат:")
                logger.info(f"      Всего: {len(current_urls)}")
                logger.info(f"      Доступно: {len(valid_urls)}")
                logger.info(f"      Недоступно: {len(invalid_urls)}")

                if valid_urls:
                    logger.info(f"      Новая строка: {new_images_string[:100]}..." if len(
                        new_images_string) > 100 else f"      Новая строка: {new_images_string}")
                else:
                    logger.warning(f"      ⚠️ Нет доступных изображений!")

                # Обновляем в БД (если не dry_run)
                if not dry_run:
                    if valid_urls:
                        try:
                            product.images = new_images_string
                            session.commit()
                            stats["updated_products"] += 1
                            logger.info(f"   ✅ ОБНОВЛЕНО в БД")
                        except Exception as e:
                            session.rollback()
                            logger.error(f"   ❌ Ошибка при обновлении: {e}")
                            stats["details"].append({
                                "product_id_ms": product.id_ms,
                                "status": f"update_error: {e}",
                                "total": len(current_urls),
                                "valid": len(valid_urls),
                                "invalid": len(invalid_urls)
                            })
                            continue
                    else:
                        logger.warning(f"   ⚠️ Нет доступных изображений, поле НЕ обновлено")
                else:
                    logger.info(f"   🔍 DRY RUN: изменение НЕ сохранено")

                stats["processed_products"] += 1
                stats["total_urls"] += len(current_urls)
                stats["valid_urls"] += len(valid_urls)
                stats["invalid_urls"] += len(invalid_urls)

                stats["details"].append({
                    "product_id_ms": product.id_ms,
                    "articul_site": product.articul_site,
                    "status": "success" if valid_urls else "no_valid_images",
                    "total": len(current_urls),
                    "valid": len(valid_urls),
                    "invalid": len(invalid_urls),
                    "old_string": current_raw[:200] if test_mode else None,
                    "new_string": new_images_string if test_mode else None
                })

            # Итоговая статистика
            logger.info(f"\n{'=' * 70}")
            logger.info("📊 ИТОГОВАЯ СТАТИСТИКА")
            logger.info(f"{'=' * 70}")
            logger.info(f"Обработано товаров: {stats['processed_products']}/{stats['total_products']}")
            logger.info(f"Обновлено товаров: {stats['updated_products']}")
            logger.info(f"Всего URL: {stats['total_urls']}")
            logger.info(f"Доступных URL: {stats['valid_urls']}")
            logger.info(f"Недоступных URL: {stats['invalid_urls']}")

            if stats['total_urls'] > 0:
                success_rate = (stats['valid_urls'] / stats['total_urls']) * 100
                logger.info(f"Процент доступных: {success_rate:.1f}%")

            logger.info(f"{'=' * 70}")

            if dry_run:
                logger.info("🔍 DRY RUN завершен. Изменения не были сохранены в БД.")
                logger.info("   Для сохранения изменений запустите с dry_run=False")

            return stats


# Упрощенные функции для вызова
def test_images_validation(limit: int = 5, check_availability: bool = True) -> Dict:
    """
    Тестовый запуск (с сохранением, но ограниченным количеством)

    Args:
        limit: количество товаров для проверки
        check_availability: проверять доступность URL
    """
    validator = ProductImagesValidator()
    return validator.validate_and_update_images(
        limit=limit,
        dry_run=False,
        test_mode=True,
        check_availability=check_availability
    )


def dry_run_images_validation(limit: Optional[int] = None, check_availability: bool = True) -> Dict:
    """
    Пробный запуск БЕЗ сохранения в БД

    Args:
        limit: ограничение количества товаров
        check_availability: проверять доступность URL
    """
    validator = ProductImagesValidator()
    return validator.validate_and_update_images(
        limit=limit,
        dry_run=True,
        test_mode=True,
        check_availability=check_availability
    )


def validate_all_images(check_availability: bool = True) -> Dict:
    """
    Полная проверка и обновление всех товаров

    Args:
        check_availability: проверять доступность URL
    """
    validator = ProductImagesValidator()
    return validator.validate_and_update_images(
        dry_run=False,
        test_mode=False,
        check_availability=check_availability
    )


def validate_single_product(product_id_ms: str, check_availability: bool = True) -> Dict:
    """
    Проверка конкретного товара

    Args:
        product_id_ms: ID товара
        check_availability: проверять доступность URL
    """
    validator = ProductImagesValidator()
    return validator.validate_and_update_images(
        product_id_ms=product_id_ms,
        dry_run=False,
        test_mode=True,
        check_availability=check_availability
    )


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("ВАРИАНТЫ ЗАПУСКА:")
    print("=" * 70)
    print("1. DRY RUN (только проверка, без сохранения):")
    print("   dry_run_images_validation(limit=5)")
    print("\n2. ТЕСТОВЫЙ запуск (с сохранением, 5 товаров):")
    print("   test_images_validation(limit=5)")
    print("\n3. Проверка конкретного товара:")
    print("   validate_single_product('182056')")
    print("\n4. Полная проверка всех товаров:")
    print("   validate_all_images()")
    print("=" * 70)

    # ЗАПУСК: DRY RUN (без сохранения)
    print("\n🔍 ЗАПУСК DRY RUN (только проверка, без сохранения)...")
    result = dry_run_images_validation(limit=15)

    print(f"\n📊 Результат: {result['processed_products']} товаров обработано")
    print(f"   Доступных URL: {result['valid_urls']} из {result['total_urls']}")