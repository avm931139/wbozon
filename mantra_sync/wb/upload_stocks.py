from core.classes import WBStockSender, Wb
from wb.endpoind_wb import base_url_mp_wb, update_stocks_mantra
from settings import Config
from urllib.parse import urljoin

def push_stock_wb():
    url = urljoin(base_url_mp_wb, update_stocks_mantra)
    wb = Wb()
    wh = wb.get_wharehouse_wb()
    for wharehouse in wh:
        wb_sender_stock = WBStockSender(Config.API_KEY_WB, url, wharehouse)
        wb_sender_stock.send_stocks()

