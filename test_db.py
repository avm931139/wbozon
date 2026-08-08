import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise RuntimeError("DATABASE_URL не найден в .env")

engine = create_engine(database_url)

with engine.connect() as connection:
    result = connection.execute(text("SELECT version()"))
    print(result.scalar())