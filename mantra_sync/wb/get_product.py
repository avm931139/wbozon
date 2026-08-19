#matra_sync/wb/get_product_wb
from core.classes import Wb
from settings import Config
from wb.endpoind_wb import cards_wb_endp
from urllib.parse import urljoin


def get_product_wb():
    url = urljoin(Config.BASE_URL_WB_CONTENT, cards_wb_endp)
    wb = Wb()
    headers = wb.get_headers()
    data_api = wb.get_all_cards(url, headers)

    if data_api:
        wb.save_product(data_api)

# get_product_wb()

