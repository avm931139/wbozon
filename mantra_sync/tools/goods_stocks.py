from datetime import datetime
from sqlalchemy.orm import Session
from core.db.connection import get_db_session
from core.db.models import WbStock
from bot import send_telegram_message
from core.classes import Wb
from wb.endpoind_wb import base_url_mp_wb, get_stocks_mantra
from urllib.parse import urljoin
from core.classes import Wb
from wb.get_wharehouse_seller import get_wharehouse_seller


def notify(step: str, success: bool = True, error: Exception = None):
    """Отправка сообщения в Telegram и логирование в консоль."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if success:
        message = f"✅ [{timestamp}] {step} успешно выполнен"
    else:
        message = f"❌ [{timestamp}] {step} завершился с ошибкой: {error}"
    print(message)
    try:
        send_telegram_message(message)
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")


def get_wb_stocks():
    wb = Wb()
    with get_db_session() as db:  # type: Session

        # Загружаем остатки на складах продавца на ВБ
        url_base = urljoin(base_url_mp_wb, get_stocks_mantra)


        wh = wb.get_wharehouse_wb()
        for wharehouse in wh:
            url = urljoin(url_base, str(wharehouse))
            data_list = wb.get_stocks_by_skus(url)

            if data_list:
                try:
                    s = 0
                    for data in data_list:
                        sku = data['sku']
                        data_mantra = wb.get_card_wb(sku)
                        pcs = data['amount']
                        s += 1
                        wb.save_wb_stock_seller(wharehouse, data_mantra, pcs, 'fbs')

                    print(f'Загрузил остатки по складу в БД {wharehouse} товаров: {s}')

                    message = f'Загрузил остатки по складу в БД {wharehouse}: {s}'
                    notify(message, True)

                except Exception as e:
                    message = f'Не смог загрузить остатки по складу в БД {wharehouse}'
                    notify(message, False, e)

# get_wharehouse_seller()
# #
# #
# get_wb_stocks()
