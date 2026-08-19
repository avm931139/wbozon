"""
Тестовый скрипт для извлечения всех значений цвета из таблицы wb_normalized_characteristic
Запуск: python test_colors.py
"""

import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db.connection import get_db_session
from core.db.models import WBNormalizedCharacteristic
from loguru import logger


def extract_all_colors():
    """Извлекает все значения цвета из таблицы"""

    # ID характеристики "Цвет" в WB
    COLOR_CHAR_ID = 14177449

    colors = set()
    raw_values = []  # Для отладки - сохраняем原始 значения

    with get_db_session() as session:
        # Ищем все характеристики с charc_id = 14177449 (цвет)
        color_chars = session.query(WBNormalizedCharacteristic).filter(
            WBNormalizedCharacteristic.charc_id == COLOR_CHAR_ID
        ).all()

        print(f"\n{'=' * 70}")
        print(f"Найдено записей с цветом: {len(color_chars)}")
        print(f"{'=' * 70}\n")

        for idx, char in enumerate(color_chars, 1):
            value = char.value
            raw_values.append(str(value))

            # Обрабатываем разные типы значений
            if isinstance(value, list):
                for v in value:
                    if v and str(v).strip():
                        cleaned = str(v).strip().lower()
                        colors.add(cleaned)
                        print(f"{idx:4}. [list]    {cleaned}")
            elif isinstance(value, str):
                # Если строка с запятыми
                if ',' in value:
                    for v in value.split(','):
                        if v and v.strip():
                            cleaned = v.strip().lower()
                            colors.add(cleaned)
                            print(f"{idx:4}. [str,comma] {cleaned}")
                else:
                    if value and value.strip():
                        cleaned = value.strip().lower()
                        colors.add(cleaned)
                        print(f"{idx:4}. [str]      {cleaned}")
            elif value:
                cleaned = str(value).strip().lower()
                colors.add(cleaned)
                print(f"{idx:4}. [other]    {cleaned}")
            else:
                print(f"{idx:4}. [empty]    ---")

    # Сортируем цвета
    sorted_colors = sorted(colors)

    print(f"\n{'=' * 70}")
    print(f"УНИКАЛЬНЫЕ ЦВЕТА (всего: {len(sorted_colors)})")
    print(f"{'=' * 70}\n")

    for i, color in enumerate(sorted_colors, 1):
        print(f"{i:3}. {color}")

    # Сохраняем в файл
    with open("colors_list.txt", "w", encoding="utf-8") as f:
        f.write("Список уникальных цветов из базы данных:\n\n")
        for color in sorted_colors:
            f.write(f"{color}\n")
        f.write(f"\nВсего: {len(sorted_colors)} цветов\n")

    # Сохраняем raw значения для анализа
    with open("colors_raw.txt", "w", encoding="utf-8") as f:
        f.write("Raw значения цветов из базы:\n\n")
        for val in raw_values:
            f.write(f"{val}\n")

    print(f"\n{'=' * 70}")
    print(f"✅ Список сохранен в файл: colors_list.txt")
    print(f"✅ Raw значения сохранены в: colors_raw.txt")
    print(f"{'=' * 70}")

    # Выводим в формате Python для копирования
    print("\n\n📋 Python список для копирования в код:")
    print("COLOR_MAPPING = {")
    for color in sorted_colors:
        # Пока оставляем как есть, позже заменим на правильные
        print(f'    "{color}": "{color}",  # TODO: проверить и заменить')
    print("}")

    return sorted_colors


if __name__ == "__main__":
    print("\n🔍 Извлечение цветов из базы данных...")
    colors = extract_all_colors()

    print("\n\n💡 Дальнейшие действия:")
    print("1. Посмотрите файл colors_list.txt")
    print("2. Отметьте, какие цвета нужно нормализовать")
    print("3. Пришлите мне список, и я составлю правильное соответствие")