# matra_sync/ozon/get_product.py
from core.classes import Ozon


def get_ozon_products():
    """
    Загружает товары с Ozon
    """
    print("=" * 60)
    print("🚀 НАЧАЛО ЗАГРУЗКИ ТОВАРОВ OZON")
    print("=" * 60)

    ozon = Ozon()

    # Получаем все ID товаров
    print("\n📋 Шаг 1: Получение списка ID товаров...")
    product_list = ozon.get_all_product_ids()

    if not product_list:
        print("❌ Не удалось получить список товаров")
        return None

    print(f"\n📊 Шаг 2: Получение детальной информации...")
    product_ids = [item['product_id'] for item in product_list]
    detailed_products = ozon.get_product_info_list(product_ids)

    if not detailed_products:
        print("❌ Не удалось получить детальную информацию")
        return None

    print(f"\n💾 Шаг 3: Сохранение в базу данных...")
    result = ozon.save_products(detailed_products)

    print("\n" + "=" * 60)
    print("✅ ЗАГРУЗКА ЗАВЕРШЕНА")
    print("=" * 60)

    return result
# get_ozon_products()
