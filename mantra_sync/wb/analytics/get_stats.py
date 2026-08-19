import requests
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from settings import Config  # предпологается что Config.api_wb у вас есть
from wb.endpoind_wb import  base_url_seller_analytics, analytics_sales_funnel
from urllib.parse import urljoin


class WildberriesAnalyticsAPI:
    """Класс для работы с API аналитики Wildberries"""

    BASE_URL = base_url_seller_analytics

    def __init__(self, api_key: str):
        """
        Инициализация API клиента

        Args:
            api_key: API ключ Wildberries
        """
        self.api_key = api_key
        self.headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        }

    def get_sales_funnel_products(
            self,
            start_date: str,
            end_date: str,
            nm_ids: Optional[List[int]] = None,
            brand_names: Optional[List[str]] = None,
            subject_ids: Optional[List[int]] = None,
            tag_ids: Optional[List[int]] = None,
            past_start_date: Optional[str] = None,
            past_end_date: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
            skip_deleted_nm: bool = False,
            order_by_field: str = "openCard",
            order_by_mode: str = "desc"
    ) -> Dict[str, Any]:
        """
        Получение статистики карточек товаров за период
        Endpoint: /api/analytics/v3/sales-funnel/products

        Args:
            start_date: Начало периода (YYYY-MM-DD)
            end_date: Конец периода (YYYY-MM-DD)
            nm_ids: Список артикулов WB
            brand_names: Список брендов
            subject_ids: Список ID предметов
            tag_ids: Список ID ярлыков
            past_start_date: Начало прошлого периода для сравнения
            past_end_date: Конец прошлого периода для сравнения
            limit: Количество карточек (max 1000)
            offset: Смещение для пагинации
            skip_deleted_nm: Скрыть удаленные товары
            order_by_field: Поле для сортировки (openCard, cartCount, orderCount и т.д.)
            order_by_mode: Направление (asc/desc)

        Returns:
            Dict с данными ответа от API
        """
        endpoint = self.BASE_URL + analytics_sales_funnel
        # Формируем тело запроса
        payload = {
            "selectedPeriod": {
                "start": start_date,
                "end": end_date
            },
            "skipDeletedNm": skip_deleted_nm,
            "orderBy": {
                "field": order_by_field,
                "mode": order_by_mode
            },
            "limit": min(limit, 1000),
            "offset": offset
        }

        # Добавляем опциональные фильтры
        if nm_ids:
            payload["nmIds"] = nm_ids
        if brand_names:
            payload["brandNames"] = brand_names
        if subject_ids:
            payload["subjectIds"] = subject_ids
        if tag_ids:
            payload["tagIds"] = tag_ids

        # Добавляем прошлый период для сравнения
        if past_start_date and past_end_date:
            payload["pastPeriod"] = {
                "start": past_start_date,
                "end": past_end_date
            }
        else:
            # Если не указан прошлый период, используем аналогичный период неделю назад
            past_start = datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=8)
            past_end = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=8)
            payload["pastPeriod"] = {
                "start": past_start.strftime("%Y-%m-%d"),
                "end": past_end.strftime("%Y-%m-%d")
            }

        print(f"🔍 Отправляем запрос к API WB...")
        print(f"📅 Период: {start_date} - {end_date}")
        print(f"📊 Лимит: {limit}, Смещение: {offset}")

        try:
            response = requests.post(
                endpoint,
                headers=self.headers,
                json=payload,
                timeout=30
            )

            # Проверяем статус ответа
            if response.status_code == 200:
                print(f"✅ Успешно получены данные")
                return response.json()
            elif response.status_code == 401:
                raise Exception("❌ Ошибка авторизации: проверьте API ключ")
            elif response.status_code == 403:
                raise Exception("❌ Доступ запрещен: недостаточно прав")
            elif response.status_code == 429:
                raise Exception("❌ Слишком много запросов: превышен лимит")
            else:
                raise Exception(f"❌ Ошибка API: {response.status_code} - {response.text}")

        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка при запросе к API: {e}")
            raise

    def get_all_products_paginated(
            self,
            start_date: str,
            end_date: str,
            **filters
    ) -> List[Dict[str, Any]]:
        """
        Получение всех товаров с пагинацией

        Args:
            start_date: Начало периода
            end_date: Конец периода
            **filters: Остальные фильтры (nm_ids, brand_names, subject_ids и т.д.)

        Returns:
            List всех товаров
        """
        all_products = []
        offset = 0
        limit = 1000  # Максимальный лимит за раз

        while True:
            response = self.get_sales_funnel_products(
                start_date=start_date,
                end_date=end_date,
                offset=offset,
                limit=limit,
                **filters
            )

            products = response.get("data", {}).get("products", [])

            if not products:
                break

            all_products.extend(products)
            print(f"📦 Получено {len(products)} товаров. Всего: {len(all_products)}")

            if len(products) < limit:
                break

            offset += limit

        return all_products



def analytics_api():
    """Тестирование API запроса"""

    # Инициализируем API с ключом из конфига
    api = WildberriesAnalyticsAPI(api_key=Config.API_KEY_WB)

    # Получаем даты: сегодня и неделю назад
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)

    # Пример 1: Получить все товары за сегодня
    print("\n" + "=" * 60)
    print("📊 ТЕСТ 1: Получение всех товаров за сегодня")
    print("=" * 60)

    try:
        response = api.get_sales_funnel_products(
            start_date=week_ago.strftime("%Y-%m-%d"),
            end_date=today.strftime("%Y-%m-%d"),
            limit=30000  # Для теста берем 10 товаров
        )

        print(f"\n📋 Ответ API:")
        print(json.dumps(response, indent=2, ensure_ascii=False)[:2000])  # Выводим первые 2000 символов

        # Анализируем структуру
        if "data" in response and "products" in response["data"]:
            products = response["data"]["products"]
            print(f"\n✅ Найдено товаров: {len(products)}")

            if products:
                first_product = products[0]
                print(f"\n📦 Структура первого товара:")
                print(f"  - nmId: {first_product.get('product', {}).get('nmId')}")
                print(f"  - Название: {first_product.get('product', {}).get('title')}")
                print(f"  - Бренд: {first_product.get('product', {}).get('brandName')}")
                print(f"  - Категория: {first_product.get('product', {}).get('subjectName')}")

                # Статистика
                stats = first_product.get("statistic", {})
                selected = stats.get("selected", {})
                print(f"\n📈 Статистика за период:")
                print(f"  - Переходы: {selected.get('openCount')}")
                print(f"  - Корзина: {selected.get('cartCount')}")
                print(f"  - Заказы: {selected.get('orderCount')}")
                print(f"  - Выкупы: {selected.get('buyoutCount')}")
                print(f"  - Конверсия в корзину: {selected.get('conversions', {}).get('addToCartPercent')}%")
                print(f"  - Конверсия в заказ: {selected.get('conversions', {}).get('cartToOrderPercent')}%")

                # Динамика
                comparison = stats.get("comparison", {})
                if comparison:
                    print(f"\n🔄 Динамика:")
                    print(f"  - Переходы: {comparison.get('openCountDynamic')}%")
                    print(f"  - Заказы: {comparison.get('orderCountDynamic')}%")

                for first in products:
                    print(f"\n📦 Структура первого товара:")
                    print(f"  - nmId: {first.get('product', {}).get('nmId')}")
                    print(f"  - Название: {first.get('product', {}).get('title')}")
                    print(f"  - Бренд: {first.get('product', {}).get('brandName')}")
                    print(f"  - Категория: {first.get('product', {}).get('subjectName')}")
                    print(f"  - Категория: {first.get('statistic', {}).get('subjectName')}")

    except Exception as e:
        print(f"❌ Ошибка: {e}")

    # Пример 2: Фильтрация по предметам (категориям)
    print("\n" + "=" * 60)
    print("📊 ТЕСТ 2: Фильтрация по категориям")
    print("=" * 60)

    # try:
    #     # Пример subject_id для категории "Люстры" - нужно уточнить реальный ID
    #     # Для теста используем пустой фильтр, но вы можете подставить свой subject_id
    #     response = api.get_sales_funnel_products(
    #         start_date=today.strftime("%Y-%m-%d"),
    #         end_date=today.strftime("%Y-%m-%d"),
    #         subject_ids=[105],  # Пример ID (кроссовки из документации)
    #         limit=5
    #     )
    #
    #     if response.get("data", {}).get("products"):
    #         print(f"✅ Найдено товаров в категории: {len(response['data']['products'])}")
    #     else:
    #         print("ℹ️ Товаров в указанной категории не найдено")
    #
    # except Exception as e:
    #     print(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    analytics_api()