base_url_mp_wb = 'https://marketplace-api.wildberries.ru'
prices_api_base_url_wb = 'https://discounts-prices-api.wildberries.ru'
content_api_base_url_wb = 'https://content-api.wildberries.ru'

base_url_seller_analytics = "https://seller-analytics-api.wildberries.ru"
warehouse_remains = "/api/v1/warehouse_remains"
status = "/api/v1/warehouse_remains/tasks"

download_report = "/api/v1/warehouse_remains/tasks"

analytics_sales_funnel = "/api/analytics/v3/sales-funnel/products"

cards_wb_endp = '/content/v2/get/cards/list' #— карточки товаров (через Content API).
update_cards_wb_endp = '/content/v2/cards/update' #— карточки товаров (через Content API).
update_foto_cards_wb_endp = '/content/v3/media/save' #— карточки товаров (через Content API).
category_wb_endp = 'content/v2/object/all' #—все категории товаров ВБ.

cards_upload_wb_endp = 'content/v2/cards/upload' #—загрузка товаров товаров ВБ.

object_wb_endp = '/content/v2/object/charcs/' #— характеристики товаров (через Content API).
wharehouses_sellers = '/api/v3/warehouses' #Получить список складов продавца base_url_mp_wb
update_stocks_mantra ='/api/v3/stocks/' #Обновить остатки товаров на складе мантра
get_stocks_mantra ='/api/v3/stocks/' #Получить остатки товаров на складах ВБ
get_price_wb_mantra ='/api/v2/list/goods/filter' #Метод возвращает информацию о товарах: цены, валюту,
                                                # общие скидки и скидки WB Клуба.
