from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from legacy_core.config.settings import settings


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=5,
    max_overflow=5,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

async_engine = create_async_engine(
    settings.database_url_async,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(bind=async_engine, expire_on_commit=False)


def get_session():
    """Получение синхронной сессии."""
    with SessionLocal() as session:
        yield session


async def get_async_session():
    """Получение асинхронной сессии."""
    async with AsyncSessionLocal() as session:
        yield session
