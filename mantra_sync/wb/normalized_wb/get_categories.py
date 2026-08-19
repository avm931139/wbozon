from core.classes import Wb
from settings import Config
from wb.endpoind_wb import category_wb_endp
from urllib.parse import urljoin


def get_category_wb():
    """
    Загружает и сохраняет категории Wildberries

    Args:
        api_key: API ключ Wildberries
    """
    # Инициализация клиента
    wb = Wb()
    headers = wb.get_headers()

    # Формируем URL для получения списка предметов

    url = urljoin(Config.BASE_URL_WB_CONTENT, category_wb_endp)

    # Параметры запроса (можно получить все предметы)
    params = {
        "limit": 1000,  # Максимум 1000 за запрос
        "offset": 0
    }

    all_categories = []

    # Пагинация - получаем все категории
    while True:
        print(f"Загрузка категорий (offset={params['offset']})...")

        data = wb.get_all_categories(url,headers, params)

        if not data or not data.get("data"):
            break

        categories = data["data"]
        if not categories:
            break

        all_categories.extend(categories)

        # Если получили меньше, чем limit - это последняя страница
        if len(categories) < params["limit"]:
            break

        # Увеличиваем offset для следующей страницы
        params["offset"] += params["limit"]

    if all_categories:
        print(f"✅ Загружено {len(all_categories)} категорий")

        # Сохраняем в БД
        wb.save_categories_to_db(all_categories)

        # Выводим первые 5 для примера
        for cat in all_categories[:5]:
            print(f"  {cat.get('subjectID')}: {cat.get('subjectName')} (parent: {cat.get('parentID')})")

        return all_categories
    else:
        print("❌ Не удалось загрузить категории")
        return None


get_category_wb()