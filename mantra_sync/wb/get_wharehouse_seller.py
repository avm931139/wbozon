from core.classes import Wb
from settings import Config
from wb.endpoind_wb import base_url_mp_wb, wharehouses_sellers
from urllib.parse import urljoin

def get_wharehouse_seller():
    url = urljoin(base_url_mp_wb, wharehouses_sellers)
    wb = Wb()
    data_api = wb.get_wharehouses_seller(url)

    if data_api:
        wb.save_wharehouse(data_api)

get_wharehouse_seller()