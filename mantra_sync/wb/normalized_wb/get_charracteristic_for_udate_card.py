# Модуль для получения характеристик по категориям
from core.classes import Wb
from settings import Config
from wb.endpoind_wb import object_wb_endp
from urllib.parse import urljoin
import requests


def get_subject_characteristics(subject_id: int, locale: str = "ru"):
    """
    Получает характеристики для конкретного предмета (категории) Wildberries

    Args:
        subject_id: ID предмета (категории)
        locale: Язык (ru, en, zh)

    Returns:
        Список характеристик или None в случае ошибки

    Пример ответа:
    {
        "data": [
            {
                "charcID": 54337,
                "subjectName": "Кроссовки",
                "subjectID": 105,
                "name": "Размер",
                "required": false,
                "unitName": "см",
                "maxCount": 0,
                "popular": false,
                "charcType": 4
            }
        ],
        "error": false,
        "errorText": "",
        "additionalErrors": null
    }
    """
    endpoint = object_wb_endp  + str(subject_id)
    url = urljoin(Config.BASE_URL_WB_CONTENT, endpoint)
    wb = Wb()
    headers = wb.get_headers()
    params = {"locale": locale}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Проверяем наличие ошибки в ответе
        if data.get("error"):
            print(f"Ошибка API: {data.get('errorText')}")
            return None

        wb.save_characteristics_to_db(subject_id, data)

    except requests.exceptions.RequestException as e:
        print(f"Ошибка запроса к API: {e}")
        return None
    except ValueError as e:
        print(f"Ошибка парсинга JSON: {e}")
        return None

data = get_subject_characteristics(1158)
