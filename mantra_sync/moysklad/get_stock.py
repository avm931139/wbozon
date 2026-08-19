from core.db.models import MSStock, MsShops
from core.ms_classes import MSApi, MSDataLoader
from core.db.connection import get_db_session
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import logging

logger = logging.getLogger(__name__)

# Получаем склады

moment = datetime.now()

def get_stocks(whouse, moment):

    for wh in whouse:
        with get_db_session() as session:
            load = session.query(MSStock).filter(MSStock.warehouse_id == wh.wh_id_ms, MSStock.moment == moment).first()
            if not load:
                id_wh = wh.wh_id_ms
                name_wh = wh.name

                filters = {

                    "filter": f"store=https://api.moysklad.ru/api/remap/1.2/entity/store/{id_wh}"
                }

                # Вызов функции загрузки остатков
                ms_api = MSApi()
                endpoint = "report/stock/all"
                print(f'Загружаю остатки по {name_wh}')
                all_remains = ms_api.get_data_ms(endpoint, filters, moment)


                MSDataLoader().stock_load_data(all_remains, id_wh, name_wh, moment)
                print(f'\nЗагрузил и обновил в БД остатки по {name_wh}'
                      f'\nКоличество товаров: {len(all_remains)} \n')
            else:
                print(f'Остатки уже загружены на {moment}')

def job_stocs_ms():
    with get_db_session() as session:
        shops = session.query(MsShops).all()

        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)  # начало дня
        start_date_str = start_date.strftime('%Y-%m-%d %H:%M:%S')

        print(f'Получаю остатки на: {start_date}...')

        get_stocks(shops, start_date_str)


def get_stocks_for_date_range():
    """
    Получение остатков за период с 1 января 2025 по февраль 2026
    на 1-е число каждого месяца
    """
    with get_db_session() as session:
        shops = session.query(MsShops).all()

        # Начальная дата: 1 января 2025
        start_date = date(2026, 4, 1)
        # Конечная дата: февраль 2026
        end_date = date(2026, 2, 1)

        current_date = start_date
        dates_list = []

        # Формируем список дат (1-е число каждого месяца)
        while current_date <= end_date:
            dates_list.append(current_date)
            # Переходим на 1-е число следующего месяца
            current_date += relativedelta(months=1)

        logger.info(f"Всего дат для загрузки: {len(dates_list)}")
        logger.info(f"Период: с {dates_list[0]} по {dates_list[-1]}")

        # Получаем остатки для каждой даты
        for i, target_date in enumerate(dates_list, 1):
            # Преобразуем дату в строку с временем 00:00:00
            target_date_str = target_date.strftime('%Y-%m-%d %H:%M:%S')

            logger.info(f"[{i}/{len(dates_list)}] Получаю остатки на: {target_date_str}")

            # Получаем остатки для всех магазинов на указанную дату
            get_stocks(shops, target_date_str)

        logger.info("Загрузка остатков за все даты завершена")

job_stocs_ms()