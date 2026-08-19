#matra_sync/settings
import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем конфигурации из .env файла
dotenv_path ="/mantra/xml_sync/.env"
load_dotenv(dotenv_path=dotenv_path)




class Config:
    # База данных
    DATABASE_URL = os.getenv('DB_URL')
    DATABASE_URL_ASYNC = os.getenv('DATABASE_URL_ASYNC')

    # Wildberries
    BASE_URL_WB_CONTENT = os.getenv('BASE_URL_WB_CONTENT')
    API_KEY_WB = os.getenv('API_KEY_WB')
    API_KEY_WB_RO_ALL = os.getenv('API_KEY_WB_RO_ALL')
    API_KEY_WB_CONTENT = os.getenv('API_KEY_WB_CONTENT')

    # Ozon
    BASE_URL_OZON = os.getenv('BASE_URL_OZON')
    OZON_CLIENT_ID = os.getenv('OZON_CLIENT_ID')
    OZON_API_KEY = os.getenv('OZON_API_KEY')

    # Mantra
    URL_MANTRA_XML = os.getenv('URL_MANTRA_XML')

    # Telegram
    BOT_MANTRA_API_KEY = os.getenv('BOT_MANTRA_API_KEY')
    GROUP_MANTRA_ID = os.getenv('GROUP_MANTRA_ID')

    # Moysklad
    BASE_URL_MS = os.getenv('BASE_URL_MS')
    API_TOKEN_MS = os.getenv('API_TOKEN_MS')

    # GPTTUNNEL
    API_TOKEN_GPT_TUN = os.getenv('API_TOKEN_GPT_TUN')

    # YA disk token
    OAUTH_TOKEN_YA_DISK = os.getenv('OAUTH_TOKEN_YA_DISK')

    # ID организации (по умолчанию 1)
    DEFAULT_UL_ID = 1

    #
    TOKEN_MAX=os.getenv('TOKEN_MAX')
    MAX_ORDER_WB = os.getenv('ORDER_WB')



