import sys
from typing import List, Dict, Optional, Any, Tuple
from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload
from loguru import logger
import json

from core.db.models import (
    WBNormalizedProduct,
    WBNormalizedCharacteristic,
    WBSubject,
    WBCharacteristic,
    WBSubjectCharacteristic
)
from core.db.connection import get_db_session


class ManualCharacteristicUpdater:
    """
    Модуль ручного обновления характеристик товаров

    Работает в интерактивном режиме:
    1. Выбор категории (subject_name)
    2. Выбор характеристики (charc_name)
    3. Просмотр товаров с пустыми/нулевыми значениями
    4. Ввод нового значения
    5. Применение ко всем выбранным товарам
    """

    def __init__(self):
        self.session: Optional[Session] = None
        self.selected_subject: Optional[WBSubject] = None
        self.selected_characteristic: Optional[WBCharacteristic] = None

    def run(self):
        """Запуск интерактивного режима"""
        print("\n" + "=" * 60)
        print("     РУЧНОЕ ОБНОВЛЕНИЕ ХАРАКТЕРИСТИК ТОВАРОВ")
        print("=" * 60 + "\n")

        with get_db_session() as self.session:
            try:
                # Шаг 1: Выбор категории
                self._select_category()
                if not self.selected_subject:
                    return

                # Шаг 2: Выбор характеристики
                self._select_characteristic()
                if not self.selected_characteristic:
                    return

                # Шаг 3: Просмотр товаров с пустыми значениями
                products = self._get_products_with_empty_characteristic()
                if not products:
                    print("\n✅ Все товары в этой категории уже имеют данную характеристику!")
                    return

                self._display_products(products)

                # Шаг 4: Ввод нового значения
                new_value = self._input_new_value()
                if new_value is None:
                    return

                # Шаг 5: Подтверждение и обновление
                self._update_characteristics(products, new_value)

            except KeyboardInterrupt:
                print("\n\n❌ Операция прервана пользователем")
            except Exception as e:
                logger.error(f"Ошибка: {e}")
                print(f"\n❌ Ошибка: {e}")

    def _select_category(self):
        """Выбор категории товаров"""
        # Получаем все категории, у которых есть товары
        categories = self.session.query(WBSubject).join(
            WBNormalizedProduct,
            WBSubject.subject_id == WBNormalizedProduct.subject_id
        ).distinct().all()

        if not categories:
            print("❌ Нет категорий с товарами!")
            return

        print("📂 Доступные категории:\n")
        print(f"{'№':<4} {'ID':<8} {'Название категории':<40} {'Товаров':<10}")
        print("-" * 65)

        for idx, cat in enumerate(categories, 1):
            product_count = self.session.query(WBNormalizedProduct).filter(
                WBNormalizedProduct.subject_id == cat.subject_id
            ).count()
            print(f"{idx:<4} {cat.subject_id:<8} {cat.subject_name[:40]:<40} {product_count:<10}")

        print("\n" + "-" * 65)

        while True:
            try:
                choice = input("\nВыберите категорию (введите номер или 0 для выхода): ").strip()
                if choice == '0':
                    return

                idx = int(choice)
                if 1 <= idx <= len(categories):
                    self.selected_subject = categories[idx - 1]
                    print(f"\n✅ Выбрана категория: {self.selected_subject.subject_name}\n")
                    break
                else:
                    print("❌ Неверный номер. Попробуйте снова.")
            except ValueError:
                print("❌ Введите число!")

    def _select_characteristic(self):
        """Выбор характеристики для обновления"""
        # Получаем характеристики для выбранной категории
        characteristics = self.session.query(WBCharacteristic).filter(
            WBCharacteristic.subject_id == self.selected_subject.subject_id
        ).all()

        if not characteristics:
            print("❌ Для этой категории нет характеристик!")
            return

        print(f"📋 Характеристики категории '{self.selected_subject.subject_name}':\n")
        print(f"{'№':<4} {'ID':<8} {'Название':<35} {'Тип':<12} {'Обязат.':<8} {'Заполнено':<10}")
        print("-" * 85)

        for idx, char in enumerate(characteristics, 1):
            # Считаем сколько товаров имеют эту характеристику
            filled_count = self.session.query(WBNormalizedCharacteristic).join(
                WBNormalizedProduct
            ).filter(
                WBNormalizedProduct.subject_id == self.selected_subject.subject_id,
                WBNormalizedCharacteristic.charc_id == char.char_id,
                WBNormalizedCharacteristic.value.isnot(None),
                WBNormalizedCharacteristic.value != ''
            ).count()

            total_count = self.session.query(WBNormalizedProduct).filter(
                WBNormalizedProduct.subject_id == self.selected_subject.subject_id
            ).count()

            filled_info = f"{filled_count}/{total_count}"
            required_mark = "Да" if char.is_required else "Нет"

            print(f"{idx:<4} {char.char_id:<8} {char.char_name[:35]:<35} "
                  f"{char.char_type:<12} {required_mark:<8} {filled_info:<10}")

        print("-" * 85)

        while True:
            try:
                choice = input("\nВыберите характеристику (введите номер или 0 для выхода): ").strip()
                if choice == '0':
                    return

                idx = int(choice)
                if 1 <= idx <= len(characteristics):
                    self.selected_characteristic = characteristics[idx - 1]
                    print(f"\n✅ Выбрана характеристика: {self.selected_characteristic.char_name}\n")
                    break
                else:
                    print("❌ Неверный номер. Попробуйте снова.")
            except ValueError:
                print("❌ Введите число!")

    def _get_products_with_empty_characteristic(self) -> List[WBNormalizedProduct]:
        """
        Получить товары, у которых выбранная характеристика:
        - отсутствует в таблице WBNormalizedCharacteristic
        - или имеет пустое значение (NULL, '', '0', 'null')
        """
        # Подзапрос: товары, у которых уже есть эта характеристика с непустым значением
        products_with_char = self.session.query(
            WBNormalizedCharacteristic.product_id
        ).filter(
            WBNormalizedCharacteristic.charc_id == self.selected_characteristic.char_id,
            WBNormalizedCharacteristic.value.isnot(None),
            WBNormalizedCharacteristic.value != '',
            WBNormalizedCharacteristic.value != '0',
            WBNormalizedCharacteristic.value != 'null',
            WBNormalizedCharacteristic.value != '[]',
            WBNormalizedCharacteristic.value != '{}'
        ).subquery()

        # Товары категории, у которых НЕТ этой характеристики
        products = self.session.query(WBNormalizedProduct).filter(
            WBNormalizedProduct.subject_id == self.selected_subject.subject_id,
            ~WBNormalizedProduct.id.in_(products_with_char)
        ).all()

        return products

    def _display_products(self, products: List[WBNormalizedProduct]):
        """Отобразить список товаров с пустыми характеристиками"""
        print(
            f"\n📦 Товары с пустой характеристикой '{self.selected_characteristic.char_name}' ({len(products)} шт.):\n")
        print(f"{'№':<4} {'ID товара':<20} {'Артикул':<20} {'Название':<40}")
        print("-" * 90)

        for idx, product in enumerate(products[:20], 1):  # Показываем первые 20
            print(f"{idx:<4} {product.product_id_ms[:18]:<20} {product.vendor_code[:18]:<20} "
                  f"{product.wb_title[:38]:<40}")

        if len(products) > 20:
            print(f"\n... и еще {len(products) - 20} товаров")

        print("-" * 90)

    def _input_new_value(self) -> Optional[Any]:
        """
        Ввод нового значения с учетом типа характеристики
        """
        char = self.selected_characteristic
        print(f"\n✏️ Введите значение для характеристики '{char.char_name}'")
        print(f"   Тип: {char.char_type}")

        if char.unit_name:
            print(f"   Единица измерения: {char.unit_name}")
        if char.max_length:
            print(f"   Макс. длина: {char.max_length}")

        print(f"   Пример: {self._get_example_value(char.char_type)}")

        while True:
            value = input("\nЗначение (или 'cancel' для отмены): ").strip()

            if value.lower() == 'cancel':
                return None

            if not value:
                print("❌ Значение не может быть пустым!")
                continue

            # Валидация по типу
            # validated_value = self._validate_by_type(value, char)
            # if validated_value is not None:
            #     return validated_value
            return value
    def _get_example_value(self, char_type: str) -> str:
        """Пример значения для типа характеристики"""
        examples = {
            'string': 'LED',
            'number': '100',
            'float': '15.5',
            'boolean': 'true/false',
            'array': 'красный,синий,зеленый',
            'json': '{"key": "value"}'
        }
        return examples.get(char_type, 'текст')

    def _validate_by_type(self, value: str, char: WBCharacteristic) -> Optional[Any]:
        """
        Валидация значения по типу характеристики
        """
        try:
            if char.char_type in ('string', 'text'):
                if char.max_length and len(value) > char.max_length:
                    print(f"❌ Значение слишком длинное! Максимум {char.max_length} символов")
                    return None
                return value

            elif char.char_type in ('number', 'integer', 'float'):
                # Убираем пробелы и заменяем запятую на точку
                value = value.replace(' ', '').replace(',', '.')
                if char.char_type == 'float':
                    num = float(value)
                else:
                    num = int(float(value))
                return str(num)

            elif char.char_type == 'boolean':
                if value.lower() in ('true', '1', 'да', '+'):
                    return 'true'
                elif value.lower() in ('false', '0', 'нет', '-'):
                    return 'false'
                else:
                    print("❌ Введите true/false или да/нет")
                    return None

            elif char.char_type == 'array':
                # Разделяем по запятым
                items = [item.strip() for item in value.split(',')]
                return json.dumps(items, ensure_ascii=False)

            else:
                return value

        except ValueError:
            print(f"❌ Ошибка: '{value}' не является числом!")
            return None

    def _update_characteristics(self, products: List[WBNormalizedProduct], new_value: str):
        """
        Обновить характеристику для всех выбранных товаров
        """
        print(f"\n⚠️ Будет обновлено {len(products)} товаров")
        print(f"   Характеристика: {self.selected_characteristic.char_name}")
        print(f"   Новое значение: {new_value}")

        confirm = input("\nПодтверждаете обновление? (y/n): ").strip().lower()

        if confirm != 'y':
            print("❌ Операция отменена")
            return

        updated_count = 0
        created_count = 0

        for product in products:
            # Ищем существующую запись
            existing = self.session.query(WBNormalizedCharacteristic).filter(
                WBNormalizedCharacteristic.product_id == product.id,
                WBNormalizedCharacteristic.charc_id == self.selected_characteristic.char_id
            ).first()

            if existing:
                # Обновляем существующую
                existing.value = new_value
                existing.value_type = self.selected_characteristic.char_type
                updated_count += 1
            else:
                # Создаем новую
                new_char = WBNormalizedCharacteristic(
                    product_id=product.id,
                    charc_id=self.selected_characteristic.char_id,
                    charc_name=self.selected_characteristic.char_name,
                    value=new_value,
                    value_type=self.selected_characteristic.char_type
                )
                self.session.add(new_char)
                created_count += 1

        self.session.commit()

        print(f"\n✅ Операция завершена!")
        print(f"   Обновлено: {updated_count} записей")
        print(f"   Создано: {created_count} записей")
        print(f"   Всего: {updated_count + created_count} товаров обновлено")

    def get_statistics(self):
        """Показать статистику по заполнению характеристик"""
        print("\n" + "=" * 60)
        print("     СТАТИСТИКА ЗАПОЛНЕНИЯ ХАРАКТЕРИСТИК")
        print("=" * 60 + "\n")

        with get_db_session() as session:
            categories = session.query(WBSubject).all()

            for cat in categories:
                product_count = session.query(WBNormalizedProduct).filter(
                    WBNormalizedProduct.subject_id == cat.subject_id
                ).count()

                if product_count == 0:
                    continue

                print(f"\n📂 {cat.subject_name} (ID: {cat.subject_id}) - {product_count} товаров")
                print("-" * 50)

                characteristics = session.query(WBCharacteristic).filter(
                    WBCharacteristic.subject_id == cat.subject_id
                ).all()

                for char in characteristics:
                    filled_count = session.query(WBNormalizedCharacteristic).join(
                        WBNormalizedProduct
                    ).filter(
                        WBNormalizedProduct.subject_id == cat.subject_id,
                        WBNormalizedCharacteristic.charc_id == char.char_id,
                        WBNormalizedCharacteristic.value.isnot(None),
                        WBNormalizedCharacteristic.value != '',
                        WBNormalizedCharacteristic.value != '0'
                    ).count()

                    percent = (filled_count / product_count * 100) if product_count > 0 else 0
                    bar = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))

                    print(f"   {char.char_name:<30} {bar} {filled_count}/{product_count} ({percent:.1f}%)")


# Функции для быстрого запуска
def run_updater():
    """Запустить интерактивный режим обновления"""
    updater = ManualCharacteristicUpdater()
    updater.run()


def show_statistics():
    """Показать статистику заполнения"""
    updater = ManualCharacteristicUpdater()
    updater.get_statistics()


if __name__ == "__main__":
    # Запуск обновления
    run_updater()

    # Или показать статистику
    # show_statistics()