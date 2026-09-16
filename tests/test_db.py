import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def _test_database_url() -> str:
    value = os.getenv("TEST_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    database = make_url(value).database or ""
    if "test" not in database.lower():
        pytest.fail("TEST_DATABASE_URL must point to a database whose name contains 'test'")
    return value


@pytest.mark.integration
def test_postgres_connection():
    engine = create_engine(_test_database_url(), future=True)
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        assert result.scalar() == 1
    engine.dispose()
