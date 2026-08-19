import pandas as pd
from collections import defaultdict

from core.db.connection import get_db_session
from core.db.models import (
    WBNormalizedProduct,
    WBNormalizedCharacteristic,
    ParserProduct
)


def format_images(raw: str) -> str:
    """Преобразует {url1,url2} → url1; url2"""
    if not raw:
        return ""

    raw = raw.strip("{}")
    parts = [x.strip() for x in raw.split(",") if x.strip()]
    return "; ".join(parts)


def export_to_excel(file_path: str = "wb_export.xlsx"):
    with get_db_session() as db:

        # 1. Загружаем товары
        products = db.query(WBNormalizedProduct).all()

        if not products:
            print("❌ Нет товаров")
            return

        product_ids = [p.id for p in products]
        product_ms_ids = [p.product_id_ms for p in products]

        # 2. Загружаем характеристики
        chars = db.query(WBNormalizedCharacteristic).filter(
            WBNormalizedCharacteristic.product_id.in_(product_ids)
        ).all()

        # 3. Загружаем parser_product (для изображений)
        parser_products = db.query(ParserProduct).filter(
            ParserProduct.id_ms.in_(product_ms_ids)
        ).all()

        parser_map = {p.id_ms: p for p in parser_products}

        # 4. Группируем характеристики
        char_map = defaultdict(lambda: defaultdict(list))
        all_char_names = set()

        for c in chars:
            char_map[c.product_id][c.charc_name].append(c.value)
            all_char_names.add(c.charc_name)

        all_char_names = sorted(all_char_names)

        # 5. Формируем строки
        rows = []

        for p in products:
            parser = parser_map.get(p.product_id_ms)

            row = {
                "Артикул": p.vendor_code,
                "Наименование": p.wb_title,
                "Описание": p.wb_description,
                "Бренд": p.wb_brand,
                "Категория": p.subject_name,
                "Длина": p.length,
                "Ширина": p.width,
                "Высота": p.height,
                "Вес": p.weight,
                "Изображения": format_images(parser.images if parser else "")
            }

            # характеристики
            product_chars = char_map.get(p.id, {})

            for name in all_char_names:
                values = product_chars.get(name, [])
                row[name] = ", ".join(values) if values else ""

            rows.append(row)

        # 6. DataFrame
        df = pd.DataFrame(rows)

        # 7. Сохраняем
        df.to_excel(file_path, index=False)

        print(f"✅ Файл сохранен: {file_path}")


if __name__ == "__main__":
    export_to_excel()