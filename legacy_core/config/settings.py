import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str | None = os.getenv("DB_URL")
    database_url_async: str | None = os.getenv("DATABASE_URL_ASYNC")
    api_key_wb: str | None = os.getenv("API_KEY_WB")
    api_key_ozon: str | None = os.getenv("OZON_API_KEY")


settings = Settings()
