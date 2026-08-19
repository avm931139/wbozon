from core.db.models import WbCard, ParserProduct, WBNormalizedProduct
from core.db.connection import get_db_session
from sqlalchemy import text
from datetime import datetime

# Константа для dry-run режима
DRY_RUN = False  # True - только показать что будет сделано, False - реально обновить/создать


def sync_normalized_products_from_wb_cards():
    """
    Находит все соответствия между WbCard и ParserProduct и синхронизирует с wb_normalized_product

    Логика:
    1. Если запись с таким product_id_ms уже существует - обновляем
    2. Если нет - создаем новую
    3. Статус устанавливаем: "synced_with_wb" - карточка сопоставлена с ВБ

    DRY_RUN = True  - только вывод информации, без изменений в БД
    DRY_RUN = False - реальное обновление/создание записей
    """

    with get_db_session() as session:
        # Получаем все соответствия одним запросом
        query = text("""
            WITH parsed_vendor AS (
                SELECT 
                    wc.nm_id as wb_nm_id,
                    wc.imt_id as wb_imt_id,
                    wc.vendor_code as wb_vendor_code,
                    wc.title as wb_title,
                    wc.description as wb_description,
                    wc.brand as wb_brand,
                    wc.subject_id as subject_id,
                    wc.subject_name as subject_name,
                    wc.dimensions as dimensions,
                    wc.updated_at as uploaded_at,
                    SPLIT_PART(SPLIT_PART(wc.vendor_code, ' ', 1), '*', 1) as id_ms_part,
                    SPLIT_PART(SPLIT_PART(wc.vendor_code, ' ', 1), '*', 2) as code_ms_part
                FROM wb_cards wc
                WHERE wc.vendor_code IS NOT NULL 
                  AND wc.vendor_code != ''
                  AND wc.vendor_code LIKE '%*%'
            ),
            matched_products AS (
                SELECT 
                    pv.wb_nm_id,
                    pv.wb_imt_id,
                    pv.wb_vendor_code,
                    pv.wb_title,
                    pv.wb_description,
                    pv.wb_brand,
                    pv.subject_id,
                    pv.subject_name,
                    pv.dimensions,
                    pv.uploaded_at,
                    pp.id_ms as product_id_ms,
                    pp.code_ms as product_code_ms,
                    pp.name_site as product_name,
                    pp.brand as product_brand,
                    pp.description as product_description
                FROM parsed_vendor pv
                INNER JOIN parser_product pp ON (
                    (CASE 
                        WHEN position('-' IN pp.id_ms) > 0 
                        THEN SUBSTRING(pp.id_ms FROM 1 FOR position('-' IN pp.id_ms) - 1)
                        ELSE pp.id_ms 
                    END) = pv.id_ms_part
                    AND
                    (CASE 
                        WHEN LENGTH(pp.code_ms) > 4 
                        THEN SUBSTRING(pp.code_ms FROM 5)
                        ELSE pp.code_ms 
                    END) = pv.code_ms_part
                )
            )
            SELECT * FROM matched_products
        """)

        matches = session.execute(query).fetchall()

        print(f"\n{'=' * 80}")
        print(f"DRY-RUN режим: {'ВКЛЮЧЕН (только просмотр)' if DRY_RUN else 'ВЫКЛЮЧЕН (будут изменения)'}")
        print(f"{'=' * 80}")
        print(f"Найдено соответствий: {len(matches)}")

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for match in matches:
            # Извлекаем габариты из JSON поля dimensions
            dimensions = match.dimensions or {}
            length = dimensions.get('length', 0) if isinstance(dimensions, dict) else 0
            width = dimensions.get('width', 0) if isinstance(dimensions, dict) else 0
            height = dimensions.get('height', 0) if isinstance(dimensions, dict) else 0
            weight = dimensions.get('weightBrutto', 0.0) if isinstance(dimensions, dict) else 0.0

            # Проверяем, существует ли уже запись
            existing = session.query(WBNormalizedProduct).filter(
                WBNormalizedProduct.product_id_ms == match.product_id_ms
            ).first()

            if existing:
                # Обновляем существующую запись
                action = "ОБНОВЛЕНИЕ"
                if not DRY_RUN:
                    existing.vendor_code = match.wb_vendor_code
                    existing.wb_title = match.wb_title[:60] if match.wb_title else ''
                    existing.wb_description = match.wb_description or match.product_description
                    existing.wb_brand = match.wb_brand or match.product_brand
                    existing.subject_id = match.subject_id
                    existing.subject_name = match.subject_name
                    existing.length = length
                    existing.width = width
                    existing.height = height
                    existing.weight = weight
                    existing.wb_nm_id = match.wb_nm_id
                    existing.wb_imt_id = match.wb_imt_id
                    existing.status = "synced_with_wb"  # Статус: карточка сопоставлена с ВБ
                    existing.uploaded_at = match.uploaded_at
                    existing.updated_at = datetime.now()
                updated_count += 1
            else:
                # Создаем новую запись
                action = "СОЗДАНИЕ"
                if not DRY_RUN:
                    new_product = WBNormalizedProduct(
                        product_id_ms=match.product_id_ms,
                        vendor_code=match.wb_vendor_code,
                        wb_title=match.wb_title[:60] if match.wb_title else '',
                        wb_description=match.wb_description or match.product_description,
                        wb_brand=match.wb_brand or match.product_brand,
                        subject_id=match.subject_id,
                        subject_name=match.subject_name,
                        length=length,
                        width=width,
                        height=height,
                        weight=weight,
                        wb_nm_id=match.wb_nm_id,
                        wb_imt_id=match.wb_imt_id,
                        status="synced_with_wb",  # Статус: карточка сопоставлена с ВБ
                        uploaded_at=match.uploaded_at,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    session.add(new_product)
                created_count += 1

            # Выводим информацию
            print(f"\n{action}:")
            print(f"  product_id_ms: {match.product_id_ms}")
            print(f"  wb_nm_id: {match.wb_nm_id}")
            print(f"  vendor_code: {match.wb_vendor_code}")
            print(f"  wb_title: {match.wb_title[:50] if match.wb_title else 'N/A'}...")
            print(f"  status: synced_with_wb (карточка сопоставлена с ВБ)")
            print(f"  габариты: {length}x{width}x{height} см, {weight} кг")

        # Применяем изменения только если не dry-run
        if not DRY_RUN:
            session.commit()
            print(f"\n{'=' * 80}")
            print(f"ИЗМЕНЕНИЯ ПРИМЕНЕНЫ К БАЗЕ ДАННЫХ")
            print(f"{'=' * 80}")
        else:
            print(f"\n{'=' * 80}")
            print(f"DRY-RUN: ИЗМЕНЕНИЯ НЕ ПРИМЕНЕНЫ (откат)")
            print(f"Установите DRY_RUN = False для реального обновления")
            print(f"{'=' * 80}")

        print(f"\nСтатистика:")
        print(f"  Создано записей: {created_count}")
        print(f"  Обновлено записей: {updated_count}")
        print(f"  Всего обработано: {len(matches)}")

        return {
            'total': len(matches),
            'created': created_count,
            'updated': updated_count,
            'dry_run': DRY_RUN
        }


def print_current_normalized_products():
    """Выводит текущие записи из wb_normalized_product со статусом synced_with_wb"""
    with get_db_session() as session:
        products = session.query(WBNormalizedProduct).filter(
            WBNormalizedProduct.status == "synced_with_wb"
        ).all()

        print(f"\n{'=' * 80}")
        print(f"Текущие записи в wb_normalized_product со статусом 'synced_with_wb':")
        print(f"{'=' * 80}")
        print(f"Всего записей: {len(products)}")

        for p in products:
            print(f"\n  product_id_ms: {p.product_id_ms}")
            print(f"  wb_nm_id: {p.wb_nm_id}")
            print(f"  vendor_code: {p.vendor_code}")
            print(f"  wb_title: {p.wb_title[:50] if p.wb_title else 'N/A'}...")
            print(f"  status: {p.status}")
            print(f"  uploaded_at: {p.uploaded_at}")
        print(f"{'=' * 80}")


# Использование:
if __name__ == "__main__":
    # Сначала показываем текущие записи
    print_current_normalized_products()

    # Синхронизируем (в зависимости от DRY_RUN)
    result = sync_normalized_products_from_wb_cards()

    # Если dry-run, показываем пример команды для реального запуска
    if DRY_RUN:
        print("\n💡 Для реальной синхронизации:")
        print("   1. Откройте файл и установите DRY_RUN = False")
        print("   2. Запустите скрипт снова")