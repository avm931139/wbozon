from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from contextlib import contextmanager, asynccontextmanager
from loguru import logger
from settings import Config

# ----------------- Синхронный движок -----------------
engine = create_engine(
    Config.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=5,      # меньше, чем по умолчанию, достаточно для cron
    max_overflow=5
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db_session():
    """Синхронный контекстный менеджер для работы с БД"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception(f"Ошибка синхронной сессии БД {e}")
        raise
    finally:
        db.close()

# ----------------- Асинхронный движок -----------------
async_engine = create_async_engine(
    Config.DATABASE_URL_ASYNC,
    echo=False,
    future=True
)

AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)

@asynccontextmanager
async def get_async_db_session():
    """Асинхронный контекстный менеджер для работы с БД"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.exception(f"Ошибка асинхронной сессии БД: {e}")
            raise
