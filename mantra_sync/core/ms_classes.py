from settings import Config
import requests
from core.db.models import MSStock
import sys
from core.db.connection import get_db_session
from datetime import datetime

class MSApi:
    def __init__(self):
        self.base_url = Config.BASE_URL_MS
        self.headers = {
            "Authorization": f"Bearer {Config.API_TOKEN_MS}",
            "Content-Type": "application/json"
        }
        self.base_update = MSDataLoader()

    def print_offset_progress(self, counter):
        sys.stdout.write(f'\r📦 Загружено пакетов: {counter}')
        sys.stdout.flush()

    def get_data_ms(self, endpoint, filters=None, moment=None, limit=1000):
        all_remains = []
        offset = 0  # Начальное смещение
        page = 0

        while True:
            filter_list = []

            # Формируем список фильтров
            if filters and "filter" in filters:
                filter_list.append(filters["filter"])

            if moment:
                # Убедимся, что формат даты соответствует требуемому
                if isinstance(moment, datetime):
                    moment = moment.strftime('%Y-%m-%d %H:%M:%S')
                filter_list.append(f"moment={moment}")

            # Объединяем все фильтры в одну строку
            combined_filter = ";".join(filter_list)

            params = {
                "limit": limit,
                "offset": offset,
                "filter": combined_filter
            }
            # Выводим прогресс
            page += 1
            # self.print_offset_progress(page)

            # Отправка GET-запроса
            response = requests.get(self.base_url + endpoint, headers=self.headers, params=params)

            # Проверка ответа
            if response.status_code != 200:
                print(f"Ошибка: {response.status_code}")
                print(response.text)
                break

            # Обработка данных
            data = response.json()
            rows = data.get("rows", [])
            all_remains.extend(rows)  # Добавление полученных данных в общий список

            # Если данных меньше лимита, значит мы получили все записи
            if len(rows) < limit:
                break

            # Увеличиваем смещение для следующей порции данных
            offset += limit

        return all_remains

    def get_data_post_ms(self, endpoint, params):
        all_orders = []
        page = 0
        while True:
            response = requests.get(self.base_url + endpoint, headers=self.headers, params=params)

            if response.status_code == 200:
                data = response.json()

                # Добавляем заказы на текущей странице в общий список
                all_orders.extend(data['rows'])

                # Проверяем, есть ли еще данные для следующей страницы
                if len(data['rows']) < params['limit']:
                    break  # Выход из цикла, если больше данных нет
                else:
                    params['offset'] += params['limit']  # Переходим к следующей странице
                    # Выводим строку загрузки с текущими точками
                page += 1
                self.print_offset_progress(page)
            else:
                print(f"Ошибка при запросе данных: {response.status_code}")
                break

        self.base_update.salesreturn_load_data(all_orders)


class MSDataLoader:

    def stock_load_data(self, data, warehouse_id, warehouse_name, moment):
        if data:

            # Чистим остатки на такую же дату
            with get_db_session() as db:
                db.query(MSStock).filter(MSStock.warehouse_id == warehouse_id, MSStock.moment == moment).delete()
                db.commit()

                for st in data:
                    new_product = MSStock(
                        moment=moment,
                        product_id=st.get("meta", {}).get("href").split('/')[8].split('?')[0],
                        warehouse_id=warehouse_id,
                        warehouse_name=warehouse_name,
                        stock=st.get('stock'),
                        reserve=st.get('reserve'),
                        quantity=st.get('quantity'),
                        cost=st.get('price')
                    )
                    db.add(new_product)


    def parse_datetime(self, value):
        if value:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
        return None
