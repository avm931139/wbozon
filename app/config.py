import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be set in .env")

WB_API_KEY = os.getenv("WB_API_KEY")
WB_BASE_URL = os.getenv("WB_BASE_URL", "https://suppliers-api.wildberries.ru")
WB_CONTENT_BASE_URL = os.getenv("WB_CONTENT_BASE_URL", "https://content-api.wildberries.ru")
WB_MARKETPLACE_BASE_URL = os.getenv("WB_MARKETPLACE_BASE_URL", "https://marketplace-api.wildberries.ru")
WB_ANALYTICS_BASE_URL = os.getenv("WB_ANALYTICS_BASE_URL", "https://seller-analytics-api.wildberries.ru")
WB_STATISTICS_BASE_URL = os.getenv("WB_STATISTICS_BASE_URL", "https://statistics-api.wildberries.ru")
WB_SUPPLIES_BASE_URL = os.getenv("WB_SUPPLIES_BASE_URL", "https://supplies-api.wildberries.ru")
WB_FINANCE_BASE_URL = os.getenv("WB_FINANCE_BASE_URL", "https://finance-api.wildberries.ru")
WB_FEEDBACKS_BASE_URL = os.getenv("WB_FEEDBACKS_BASE_URL", "https://feedbacks-api.wildberries.ru")
WB_PROMOTION_BASE_URL = os.getenv("WB_PROMOTION_BASE_URL", "https://advert-api.wildberries.ru")
WB_PROMOTION_API_KEY = os.getenv("WB_PROMOTION_API_KEY") or WB_API_KEY
WB_QUESTION_RESPONSE_SLA_HOURS = int(os.getenv("WB_QUESTION_RESPONSE_SLA_HOURS", "24"))
WB_FEEDBACK_RESPONSE_SLA_HOURS = int(os.getenv("WB_FEEDBACK_RESPONSE_SLA_HOURS", "24"))
WB_TIMEOUT_SECONDS = int(os.getenv("WB_TIMEOUT_SECONDS", "30"))


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


WB_SYNC_INTERVAL_SECONDS = int(os.getenv("WB_SYNC_INTERVAL_SECONDS", "21600"))
WB_SYNC_RUN_ON_START = _env_bool("WB_SYNC_RUN_ON_START", True)
WB_SYNC_HISTORY_START = os.getenv("WB_SYNC_HISTORY_START", "2019-01-01")
WB_SYNC_PROMOTION_LOOKBACK_DAYS = int(os.getenv("WB_SYNC_PROMOTION_LOOKBACK_DAYS", "31"))
WB_SYNC_FBS_ORDER_OVERLAP_DAYS = int(os.getenv("WB_SYNC_FBS_ORDER_OVERLAP_DAYS", "2"))
WB_SYNC_FINANCE_OVERLAP_DAYS = int(os.getenv("WB_SYNC_FINANCE_OVERLAP_DAYS", "7"))
WB_LOG_DIR = os.getenv("WB_LOG_DIR", "logs/wb")
WB_LOG_LEVEL = os.getenv("WB_LOG_LEVEL", "INFO").upper()
WB_LOG_MAX_BYTES = int(os.getenv("WB_LOG_MAX_BYTES", "10485760"))
WB_LOG_BACKUP_COUNT = int(os.getenv("WB_LOG_BACKUP_COUNT", "10"))

# Telegram reporting is a separate read-only process over the synchronized DB.
WB_TG_BOT_TOKEN = os.getenv("WB_TG_BOT_TOKEN")
WB_TG_CHAT_ID = os.getenv("WB_TG_CHAT_ID")
WB_TG_TIMEZONE = os.getenv("WB_TG_TIMEZONE", "Europe/Moscow")
WB_TG_MORNING_TIME = os.getenv("WB_TG_MORNING_TIME", "09:00")
WB_TG_OPERATIONAL_INTERVAL_SECONDS = int(os.getenv("WB_TG_OPERATIONAL_INTERVAL_SECONDS", "10800"))
WB_TG_POLL_SECONDS = int(os.getenv("WB_TG_POLL_SECONDS", "30"))
WB_TG_REQUEST_TIMEOUT_SECONDS = int(os.getenv("WB_TG_REQUEST_TIMEOUT_SECONDS", "30"))
WB_TG_LOW_STOCK_THRESHOLD = int(os.getenv("WB_TG_LOW_STOCK_THRESHOLD", "5"))

# Ozon Seller API synchronization.
OZON_CLIENT_ID = os.getenv("OZON_CLIENT_ID")
OZON_API_KEY = os.getenv("OZON_API_KEY")
OZON_BASE_URL = os.getenv("OZON_BASE_URL", "https://api-seller.ozon.ru")
OZON_TIMEOUT_SECONDS = int(os.getenv("OZON_TIMEOUT_SECONDS", "30"))
OZON_SYNC_INTERVAL_SECONDS = int(os.getenv("OZON_SYNC_INTERVAL_SECONDS", "21600"))
OZON_SYNC_RUN_ON_START = _env_bool("OZON_SYNC_RUN_ON_START", True)
OZON_ORDER_LOOKBACK_DAYS = int(os.getenv("OZON_ORDER_LOOKBACK_DAYS", "30"))
OZON_HISTORY_FROM = os.getenv("OZON_HISTORY_FROM", "2026-01-01")
OZON_SYNC_OVERLAP_DAYS = int(os.getenv("OZON_SYNC_OVERLAP_DAYS", "3"))
OZON_TIMEZONE = os.getenv("OZON_TIMEZONE", "Europe/Moscow")
OZON_REQUIRED_TASKS = tuple(
    value.strip()
    for value in os.getenv("OZON_REQUIRED_TASKS", "").split(",")
    if value.strip()
)
OZON_PRODUCTS_MAX_AGE_SECONDS = int(os.getenv("OZON_PRODUCTS_MAX_AGE_SECONDS", "28800"))
OZON_ORDERS_MAX_AGE_SECONDS = int(os.getenv("OZON_ORDERS_MAX_AGE_SECONDS", "1800"))
OZON_SUPPLIES_MAX_AGE_SECONDS = int(os.getenv("OZON_SUPPLIES_MAX_AGE_SECONDS", "7200"))
OZON_COMMUNICATIONS_MAX_AGE_SECONDS = int(os.getenv("OZON_COMMUNICATIONS_MAX_AGE_SECONDS", "1800"))
OZON_DAILY_SALES_MAX_AGE_SECONDS = int(os.getenv("OZON_DAILY_SALES_MAX_AGE_SECONDS", "129600"))
OZON_FINANCES_MAX_AGE_SECONDS = int(os.getenv("OZON_FINANCES_MAX_AGE_SECONDS", "14400"))
OZON_ADS_MAX_AGE_SECONDS = int(os.getenv("OZON_ADS_MAX_AGE_SECONDS", "7200"))

# Ozon inventory is realtime; 00:00 Moscow is our daily business cutoff.
# Server timezone does not affect the snapshot schedule.
INVENTORY_SYNC_INTERVAL_SECONDS = int(os.getenv("INVENTORY_SYNC_INTERVAL_SECONDS", "3600"))
INVENTORY_SNAPSHOT_TIME = os.getenv("INVENTORY_SNAPSHOT_TIME", "00:00")
INVENTORY_SNAPSHOT_RETRY_SECONDS = int(os.getenv("INVENTORY_SNAPSHOT_RETRY_SECONDS", "300"))
INVENTORY_TIMEZONE = os.getenv("INVENTORY_TIMEZONE", "Europe/Moscow")
INVENTORY_SYNC_RUN_ON_START = _env_bool("INVENTORY_SYNC_RUN_ON_START", True)

# Ozon Performance API uses a separate OAuth client, not Seller API credentials.
OZON_PERFORMANCE_CLIENT_ID = os.getenv("OZON_PERFORMANCE_CLIENT_ID")
OZON_PERFORMANCE_CLIENT_SECRET = os.getenv("OZON_PERFORMANCE_CLIENT_SECRET")
OZON_PERFORMANCE_BASE_URL = os.getenv("OZON_PERFORMANCE_BASE_URL", "https://api-performance.ozon.ru")
