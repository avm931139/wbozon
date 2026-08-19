from core.db.models import (
    WbCard, WBNormalizedProduct, WBNormalizedCharacteristic,
    WBCharacteristic, WBSubject
)
from core.db.connection import get_db_session
from sqlalchemy import and_
from datetime import datetime
import json

# Константа для dry-run режима
DRY_RUN = False  # True - только показать, False - реально сохранить


def sync_normalized_characteristics_from_wb_cards():
    """
    Заполняет WBNormalizedCharacteristic из данных wb_cards.characteristics

    Ожидаемый формат characteristics:
    [
        {"id": 9623, "name": "Гарантийный срок", "value": ["12 месяцев"]},
        {"id": 355430, "name": "Максимальная потребляемая мощность (Вт)", "value": 320},
        ...
    ]
    """
    with get_db_session() as session:
        # Получаем все WbCard у которых есть characteristics
        wb_cards = session.query(WbCard).filter(
            WbCard.characteristics.isnot(None)
        ).all()

        print(f"\n{'=' * 80}")
        print(f"DRY-RUN режим: {'ВКЛЮЧЕН (только просмотр)' if DRY_RUN else 'ВЫКЛЮЧЕН (будут изменения)'}")
        print(f"{'=' * 80}")
        print(f"Найдено WbCard с характеристиками: {len(wb_cards)}")

        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0
        not_found_chars = set()

        for wb_card in wb_cards:
            # Находим соответствующий нормализованный продукт
            normalized_product = session.query(WBNormalizedProduct).filter(
                WBNormalizedProduct.wb_nm_id == wb_card.nm_id
            ).first()

            if not normalized_product:
                print(f"\n⚠️ ПРОПУЩЕН: Не найден WBNormalizedProduct для wb_nm_id={wb_card.nm_id}")
                skipped_count += 1
                continue

            # Парсим JSON характеристики
            characteristics_data = wb_card.characteristics
            if isinstance(characteristics_data, str):
                try:
                    characteristics_data = json.loads(characteristics_data)
                except json.JSONDecodeError as e:
                    print(f"\n❌ ОШИБКА: Не удалось распарсить JSON для nm_id={wb_card.nm_id}: {e}")
                    error_count += 1
                    continue

            if not isinstance(characteristics_data, list):
                print(f"\n⚠️ ПРОПУЩЕН: Характеристики не в формате list для nm_id={wb_card.nm_id}")
                skipped_count += 1
                continue

            print(f"\n📦 Обработка товара: nm_id={wb_card.nm_id}, subject_id={wb_card.subject_id}")
            print(f"   Найдено характеристик в JSON: {len(characteristics_data)}")

            # Для каждой характеристики из JSON
            for char_item in characteristics_data:
                if not isinstance(char_item, dict):
                    continue

                char_id = char_item.get('id')
                char_name = char_item.get('name')
                char_value = char_item.get('value')

                if not char_name or char_value is None:
                    continue

                # Преобразуем значение в строку
                if isinstance(char_value, list):
                    value_str = ', '.join(str(v) for v in char_value)
                else:
                    value_str = str(char_value)

                # Ищем соответствие в WBCharacteristic по subject_id и char_name
                wb_char = session.query(WBCharacteristic).filter(
                    and_(
                        WBCharacteristic.subject_id == wb_card.subject_id,
                        WBCharacteristic.char_name == char_name
                    )
                ).first()

                # Если не нашли по имени, пробуем найти по char_id
                if not wb_char and char_id:
                    wb_char = session.query(WBCharacteristic).filter(
                        and_(
                            WBCharacteristic.subject_id == wb_card.subject_id,
                            WBCharacteristic.char_id == char_id
                        )
                    ).first()

                if not wb_char:
                    not_found_chars.add(f"subject_id={wb_card.subject_id}: {char_name} (id={char_id})")
                    continue

                # Проверяем, существует ли уже такая характеристика
                existing = session.query(WBNormalizedCharacteristic).filter(
                    and_(
                        WBNormalizedCharacteristic.product_id_ms == normalized_product.product_id_ms,
                        WBNormalizedCharacteristic.charc_id == wb_char.char_id
                    )
                ).first()

                if existing:
                    print(f"   🔄 Обновление: {char_name} = {value_str[:50]}")
                    if not DRY_RUN:
                        existing.value = value_str
                        existing.value_type = wb_char.char_type
                        existing.updated_at = datetime.now()
                    updated_count += 1
                else:
                    print(f"   ✅ Добавление: {char_name} = {value_str[:50]}")
                    if not DRY_RUN:
                        new_char = WBNormalizedCharacteristic(
                            product_id=normalized_product.id,
                            product_id_ms=normalized_product.product_id_ms,
                            charc_id=wb_char.char_id,
                            charc_name=wb_char.char_name,
                            value=value_str,
                            value_type=wb_char.char_type,
                            created_at=datetime.now()
                        )
                        session.add(new_char)
                    created_count += 1

            print(f"   Итого обработано характеристик для товара: {len(characteristics_data)}")

        # Применяем изменения
        if not DRY_RUN:
            session.commit()
            print(f"\n{'=' * 80}")
            print(f"✅ ИЗМЕНЕНИЯ ПРИМЕНЕНЫ К БАЗЕ ДАННЫХ")
            print(f"{'=' * 80}")
        else:
            print(f"\n{'=' * 80}")
            print(f"⚠️ DRY-RUN: ИЗМЕНЕНИЯ НЕ ПРИМЕНЕНЫ")
            print(f"Установите DRY_RUN = False для реального сохранения")
            print(f"{'=' * 80}")

        print(f"\n📊 Статистика:")
        print(f"  Всего обработано WbCard: {len(wb_cards)}")
        print(f"  Добавлено характеристик: {created_count}")
        print(f"  Обновлено характеристик: {updated_count}")
        print(f"  Пропущено (нет normalized_product): {skipped_count}")
        print(f"  Ошибок: {error_count}")

        if not_found_chars:
            print(f"\n❌ Характеристики, не найденные в WBCharacteristic:")
            for char in sorted(not_found_chars):
                print(f"  - {char}")

        return {
            'total_cards': len(wb_cards),
            'created': created_count,
            'updated': updated_count,
            'skipped': skipped_count,
            'errors': error_count,
            'not_found': list(not_found_chars),
            'dry_run': DRY_RUN
        }


def get_characteristics_from_wb_card(nm_id: int):
    """
    Получить и отобразить характеристики конкретной карточки WB
    """
    with get_db_session() as session:
        wb_card = session.query(WbCard).filter(WbCard.nm_id == nm_id).first()

        if not wb_card:
            print(f"Карточка с nm_id={nm_id} не найдена")
            return None

        print(f"\n{'=' * 80}")
        print(f"Характеристики карточки nm_id={nm_id}")
        print(f"{'=' * 80}")
        print(f"Название: {wb_card.title}")
        print(f"Категория: {wb_card.subject_name} (id={wb_card.subject_id})")

        characteristics_data = wb_card.characteristics
        if isinstance(characteristics_data, str):
            characteristics_data = json.loads(characteristics_data)

        if isinstance(characteristics_data, list):
            print(f"\nХарактеристики ({len(characteristics_data)} шт.):")
            for char in characteristics_data:
                print(f"  [{char.get('id')}] {char.get('name')}: {char.get('value')}")
        else:
            print(f"\nХарактеристики в неожиданном формате: {type(characteristics_data)}")
            print(characteristics_data)

        return wb_card


def add_missing_wb_characteristics():
    """
    Добавляет недостающие характеристики в WBCharacteristic
    (на основе не найденных при синхронизации)
    """
    with get_db_session() as session:
        # Получаем все характеристики из wb_cards
        wb_cards = session.query(WbCard).filter(
            WbCard.characteristics.isnot(None)
        ).all()

        missing_map = {}  # {subject_id: {char_name: char_id}}

        for wb_card in wb_cards:
            characteristics_data = wb_card.characteristics
            if isinstance(characteristics_data, str):
                try:
                    characteristics_data = json.loads(characteristics_data)
                except:
                    continue

            if not isinstance(characteristics_data, list):
                continue

            for char_item in characteristics_data:
                char_id = char_item.get('id')
                char_name = char_item.get('name')

                if not char_name:
                    continue

                # Проверяем существование
                wb_char = session.query(WBCharacteristic).filter(
                    and_(
                        WBCharacteristic.subject_id == wb_card.subject_id,
                        WBCharacteristic.char_name == char_name
                    )
                ).first()

                if not wb_char:
                    key = wb_card.subject_id
                    if key not in missing_map:
                        missing_map[key] = {}
                    missing_map[key][char_name] = char_id

        # Выводим недостающие
        print(f"\n{'=' * 80}")
        print("Недостающие характеристики для добавления в WBCharacteristic:")
        print(f"{'=' * 80}")

        for subject_id, chars in missing_map.items():
            print(f"\nsubject_id={subject_id}:")
            for char_name, char_id in chars.items():
                print(f"  - char_id={char_id}, char_name='{char_name}'")
                print(f"    char_type='string', is_required=False, is_collection=False")

        if not DRY_RUN and missing_map:
            # Добавляем недостающие (нужно реализовать по необходимости)
            print("\n⚠️ Автоматическое добавление не реализовано, нужно добавить вручную через админку")

        return missing_map


# Использование:
if __name__ == "__main__":
    # 1. Посмотреть характеристики конкретной карточки
    # get_characteristics_from_wb_card(12345678)

    # 2. Проверить недостающие характеристики
    # add_missing_wb_characteristics()

    # 3. Синхронизировать характеристики
    result = sync_normalized_characteristics_from_wb_cards()