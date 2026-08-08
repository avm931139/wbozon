import pytest
from sqlalchemy import text

from app.db import engine


@pytest.mark.integration
def test_postgres_connection():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        assert result.scalar() == 1
