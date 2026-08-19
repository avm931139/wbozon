from ozon.get_ozon_data.get_product import Ozon

a = Ozon()
data_api = a.get_all_products()
a.save_products(data_api)
a.save_stocks(data_api)