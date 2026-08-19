"""
update_wb_nm_id.py
Обновление wb_nm_id и статуса в нормализованных товарах из карточек WB

ЛОГИКА (ПРАВИЛЬНЫЙ ПОРЯДОК):
1. Сначала ищем соответствие с карточкой WB (vendor_code товара СОДЕРЖИТ vendor_code карточки)
   - Если найдено -> заполняем wb_nm_id, ставим статус 'upload'
   - Если не найдено -> wb_nm_id = None, статус 'ready upload'

2. ПОСЛЕ этого проверяем габариты:
   - Если length, width, height, weight = 0 или None -> статус МЕНЯЕТСЯ на 'review'
   - nm_id при этом остается заполненным (если был найден)

ТО ЕСТЬ: review имеет приоритет над upload, но nm_id сохраняется
"""

from sqlalchemy import or_
from loguru import logger
from core.db.models import WBNormalizedProduct, WbCard
from core.db.connection import get_db_session


# ======================== НАСТРОЙКИ (меняй здесь) ========================
DRY_RUN = False          # True - только просмотр, False - реальное обновление
ONLY_EMPTY = True       # True - только товары без nm_id, False - все товары
# ========================================================================


def check_and_fix_dimensions(product) -> tuple:
    """
    Проверяет габариты товара

    Returns:
        (has_zero_dimensions, zero_fields_list)
    """
    zero_fields = []

    if product.length is None or product.length == 0:
        zero_fields.append('length')
    if product.width is None or product.width == 0:
        zero_fields.append('width')
    if product.height is None or product.height == 0:
        zero_fields.append('height')
    if product.weight is None or product.weight == 0:
        zero_fields.append('weight')

    return len(zero_fields) > 0, zero_fields


def find_matching_card(product_vendor, cards):
    """
    Ищет подходящую карточку несколькими способами

    Returns:
        WbCard or None
    """
    product_vendor_lower = product_vendor.lower().strip()

    # Сортируем карточки по длине артикула (от большего к меньшему)
    sorted_cards = sorted(cards, key=lambda x: len(x.vendor_code), reverse=True)

    for card in sorted_cards:
        card_vendor = card.vendor_code.lower().strip()

        # Способ 1: простое вхождение (самый надежный)
        if card_vendor in product_vendor_lower:
            return card

        # Способ 2: начало строки
        if product_vendor_lower.startswith(card_vendor):
            return card

    return None


def update_products_status_from_cards(dry_run: bool = False):
    """
    Обновляет статус товаров:
    1. Сначала находит WB карточки и заполняет nm_id
    2. Потом проверяет габариты и при необходимости меняет статус на 'review'
    """
    with get_db_session() as session:
        products = session.query(WBNormalizedProduct).all()

        print(f"\n📦 Всего товаров: {len(products)}")

        if not products:
            print("❌ Нет товаров для обработки!")
            return

        cards = session.query(WbCard).all()
        print(f"📇 Всего карточек WB: {len(cards)}")

        stats = {
            'matched': 0,
            'not_matched': 0,
            'zero_dimensions': 0,
            'both_upload_and_zero': 0  # товары у которых есть nm_id, но нулевые габариты
        }

        for product in products:
            product_vendor = product.vendor_code
            matched_card = None

            # ============ ЭТАП 1: Поиск карточки WB и заполнение nm_id ============
            for card in cards:
                card_vendor = card.vendor_code
                if product_vendor.startswith(card_vendor):
                    matched_card = card
                    break

            if matched_card:
                # Товар НАЙДЕН в WB - заполняем nm_id
                if not dry_run:
                    product.wb_nm_id = matched_card.nm_id
                    product.status = 'upload'
                    product.validation_errors = 'Товар выгружен на ВБ'

                stats['matched'] += 1
                logger.info(f"✅ НАЙДЕН: {product_vendor[:50]}... -> nm_id: {matched_card.nm_id}")
            else:
                # Товар НЕ НАЙДЕН в WB
                if not dry_run:
                    product.wb_nm_id = None
                    if product.status !="processing":
                        product.status = 'ready upload'
                    product.validation_errors = None

                stats['not_matched'] += 1
                logger.warning(f"❌ НЕ НАЙДЕН: {product_vendor[:50]}...")

            # ============ ЭТАП 2: Проверка габаритов (переопределяем статус если нужно) ============
            has_zero, zero_fields = check_and_fix_dimensions(product)

            if has_zero:
                # Если есть нулевые габариты - меняем статус на review
                # НО nm_id оставляем (если он был заполнен)
                if not dry_run:
                    product.status = 'review'
                    error_msg = f"Нулевые габариты: {', '.join(zero_fields)}"
                    product.validation_errors = error_msg

                stats['zero_dimensions'] += 1

                if matched_card:
                    stats['both_upload_and_zero'] += 1
                    logger.warning(f"⚠️ НУЛЕВЫЕ ГАБАРИТЫ у товара с nm_id={matched_card.nm_id}: {product_vendor[:50]}... -> {zero_fields}")
                else:
                    logger.warning(f"⚠️ НУЛЕВЫЕ ГАБАРИТЫ: {product_vendor[:50]}... -> {zero_fields}")

        if not dry_run:
            session.commit()
            print(f"\n💾 Изменения сохранены в БД")

        print(f"\n{'='*60}")
        print(f"📊 РЕЗУЛЬТАТ:")
        print(f"   Найдено в WB (status='upload'): {stats['matched']}")
        print(f"   Не найдено в WB (status='ready upload'): {stats['not_matched']}")
        print(f"   Нулевые габариты (status='review'): {stats['zero_dimensions']}")
        print(f"     - из них с nm_id: {stats['both_upload_and_zero']}")
        print(f"   Всего обработано: {len(products)}")
        print(f"{'='*60}\n")

        return stats


def update_only_empty_nm_ids(dry_run: bool = False):
    """
    Обновляет ТОЛЬКО товары у которых нет wb_nm_id
    Сначала заполняет nm_id, потом проверяет габариты
    """
    with get_db_session() as session:
        products = session.query(WBNormalizedProduct).filter(
            or_(
                WBNormalizedProduct.wb_nm_id == None,
                WBNormalizedProduct.wb_nm_id == 0
            )
        ).all()

        print(f"\n📦 Найдено товаров без nm_id: {len(products)}")

        if not products:
            print("✅ Все товары уже имеют nm_id!")
            return

        cards = session.query(WbCard).all()
        print(f"📇 Всего карточек WB: {len(cards)}")

        stats = {
            'updated': 0,
            'not_found': 0,
            'zero_dimensions': 0,
            'zero_with_nm_id': 0
        }

        for product in products:
            product_vendor = product.vendor_code

            # ============ ЭТАП 1: Поиск карточки и заполнение nm_id ============
            matched_card = None
            for card in cards:
                if card.vendor_code in product_vendor:
                    matched_card = card
                    break

            if matched_card:
                if not dry_run:
                    product.wb_nm_id = matched_card.nm_id
                    product.status = 'upload'
                    product.validation_errors = 'Товар выгружен на ВБ'

                stats['updated'] += 1
                logger.info(f"✅ {product_vendor[:50]} -> nm_id: {matched_card.nm_id}")
            else:
                if not dry_run:
                    product.wb_nm_id = None
                    product.status = 'ready upload'
                    product.validation_errors = None

                stats['not_found'] += 1
                logger.warning(f"❌ НЕ НАЙДЕН: {product_vendor[:50]}")

            # ============ ЭТАП 2: Проверка габаритов ============
            has_zero, zero_fields = check_and_fix_dimensions(product)

            if has_zero:
                if not dry_run:
                    product.status = 'review'
                    error_msg = f"Нулевые габариты: {', '.join(zero_fields)}"
                    product.validation_errors = error_msg

                stats['zero_dimensions'] += 1

                if matched_card:
                    stats['zero_with_nm_id'] += 1
                    logger.warning(f"⚠️ НУЛЕВЫЕ ГАБАРИТЫ у товара с nm_id={matched_card.nm_id}: {zero_fields}")
                else:
                    logger.warning(f"⚠️ НУЛЕВЫЕ ГАБАРИТЫ: {product_vendor[:50]} -> {zero_fields}")

        if not dry_run:
            session.commit()
            print(f"\n💾 Изменения сохранены в БД")

        print(f"\n{'='*50}")
        print(f"📊 РЕЗУЛЬТАТ:")
        print(f"   Обновлено nm_id (status='upload'): {stats['updated']}")
        print(f"   Не найдено (status='ready upload'): {stats['not_found']}")
        print(f"   Нулевые габариты (status='review'): {stats['zero_dimensions']}")
        print(f"     - из них с nm_id: {stats['zero_with_nm_id']}")
        print(f"   Всего обработано: {len(products)}")
        print(f"{'='*50}\n")

        return stats


def fix_dimensions_only(dry_run: bool = False):
    """
    Только проверка и установка статуса 'review' для товаров с нулевыми габаритами
    НЕ меняет nm_id, только статус
    """
    with get_db_session() as session:
        products = session.query(WBNormalizedProduct).all()

        print(f"\n📦 Всего товаров: {len(products)}")

        zero_count = 0
        zero_products = []

        for product in products:
            has_zero, zero_fields = check_and_fix_dimensions(product)

            if has_zero:
                zero_products.append({
                    'id': product.product_id_ms,
                    'vendor': product.vendor_code[:50],
                    'nm_id': product.wb_nm_id,
                    'zero_fields': zero_fields
                })

                if not dry_run:
                    product.status = 'review'
                    error_msg = f"Нулевые габариты: {', '.join(zero_fields)}"
                    product.validation_errors = error_msg

                zero_count += 1

        if not dry_run:
            session.commit()
            print(f"\n💾 Изменения сохранены в БД")

        print(f"\n{'='*50}")
        print(f"📊 РЕЗУЛЬТАТ ПРОВЕРКИ ГАБАРИТОВ:")
        print(f"   Товаров с нулевыми габаритами: {zero_count}")

        if zero_products[:5]:
            print(f"\n⚠️ Примеры:")
            for zp in zero_products[:5]:
                nm_id_info = f"nm_id={zp['nm_id']}" if zp['nm_id'] else "без nm_id"
                print(f"   - {zp['vendor']} ({nm_id_info}) -> нулевые: {zp['zero_fields']}")

        print(f"{'='*50}\n")

        return zero_count, zero_products


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("     ОБНОВЛЕНИЕ СТАТУСА ТОВАРОВ ПО КАРТОЧКАМ WB")
    print("=" * 60)

    print(f"\n🔧 НАСТРОЙКИ:")
    print(f"   Режим dry-run: {'ВКЛЮЧЕН (только просмотр)' if DRY_RUN else 'ВЫКЛЮЧЕН (реальное обновление)'}")
    print(f"   Режим only-empty: {'ВКЛЮЧЕН (только без nm_id)' if ONLY_EMPTY else 'ВЫКЛЮЧЕН (все товары)'}")

    print(f"\n📋 ЛОГИКА РАБОТЫ:")
    print(f"   1. Сначала ищем карточку WB и заполняем nm_id")
    print(f"   2. Затем проверяем габариты")
    print(f"   3. Если габариты нулевые -> статус 'review' (nm_id сохраняется)")

    if DRY_RUN:
        print("\n⚠️  РЕЖИМ ПРОСМОТРА - изменения НЕ будут сохранены")
    else:
        print("\n⚠️  РЕЖИМ ОБНОВЛЕНИЯ - изменения БУДУТ сохранены в БД")

        confirm = input("\n❓ Вы уверены? (y/n): ").strip().lower()
        if confirm != 'y':
            print("❌ Отменено")
            exit()

    if ONLY_EMPTY:
        update_only_empty_nm_ids(dry_run=DRY_RUN)
    else:
        update_products_status_from_cards(dry_run=DRY_RUN)

    print("\n✅ Готово!")