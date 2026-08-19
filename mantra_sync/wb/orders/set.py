import os
from settings import Config




class SetOrder:
    WB_API_URL = "https://marketplace-api.wildberries.ru/api/v3/orders/new"
    WB_API_KEY = Config.API_KEY_WB_RO_ALL
    TG_GROUP = Config.GROUP_MANTRA_ID
    REQUEST_TIMEOUT = 30
    SLEEP_INTERVAL = 15  # секунд

    # при 429 делаем паузу дольше
    RATE_LIMIT_SLEEP = 60