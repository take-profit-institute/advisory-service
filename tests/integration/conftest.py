import os
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio

TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"


@pytest_asyncio.fixture
async def postgres_pool() -> asyncpg.Pool:
    database_url = os.getenv(TEST_DATABASE_URL_ENV)
    if not database_url:
        pytest.skip(
            f"{TEST_DATABASE_URL_ENV} is not set; use `make integration-test`"
        )

    connection = await asyncpg.connect(database_url)
    try:
        database_name = await connection.fetchval("SELECT current_database()")
        if not str(database_name).endswith("_test"):
            pytest.fail(
                "Integration tests refuse to reset a database whose name does not "
                "end with '_test'"
            )

        await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        schema_path = Path(__file__).parents[2] / "db" / "schema.sql"
        await connection.execute(schema_path.read_text(encoding="utf-8"))
    finally:
        await connection.close()

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
    try:
        yield pool
    finally:
        await pool.close()
