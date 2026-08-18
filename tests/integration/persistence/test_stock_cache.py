import asyncpg
import pytest

from advisory_service.infrastructure.persistence.repositories.postgres_stock_cache import (
    PostgresStockCache,
)

pytestmark = pytest.mark.integration


async def insert_stock(
    pool: asyncpg.Pool,
    stock_code: str,
    *,
    per=10,
    pbr=1,
    roe=12,
    volatility=15,
    volatility_age_hours=0,
) -> None:
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO stocks_cache (
                stock_code, name_kr, per, pbr, roe,
                volatility_90d, volatility_calculated_at, latest_close
            )
            VALUES (
                $1, $2, $3, $4, $5, $6,
                CASE WHEN $6::numeric IS NULL THEN NULL
                     ELSE now() - make_interval(hours => $7) END,
                70000
            )
            """,
            stock_code,
            f"테스트-{stock_code}",
            per,
            pbr,
            roe,
            volatility,
            volatility_age_hours,
        )


async def test_get_metrics_many_returns_complete_metrics(postgres_pool):
    await insert_stock(postgres_pool, "TEST001")
    repository = PostgresStockCache(postgres_pool)

    result = await repository.get_metrics_many(["TEST001"])

    assert result["TEST001"].per == 10
    assert result["TEST001"].volatility_90d == 15
    assert result["TEST001"].price_snapshot == 70_000


async def test_get_metrics_many_excludes_missing_financials(postgres_pool):
    await insert_stock(postgres_pool, "TEST002", per=None)
    repository = PostgresStockCache(postgres_pool)

    result = await repository.get_metrics_many(["TEST002"])

    assert "TEST002" not in result


async def test_raw_metrics_include_volatility_timestamp(postgres_pool):
    await insert_stock(postgres_pool, "TEST003")
    repository = PostgresStockCache(postgres_pool)

    result = await repository.get_metric_values_many(["TEST003"])

    assert result["TEST003"]["volatility_calculated_at"] is not None


async def test_stale_codes_include_missing_and_expired_volatility(postgres_pool):
    await insert_stock(postgres_pool, "FRESH01")
    await insert_stock(postgres_pool, "STALE01", volatility_age_hours=13)
    await insert_stock(postgres_pool, "EMPTY01", volatility=None)
    repository = PostgresStockCache(postgres_pool)

    result = await repository.list_stale_market_metric_codes(43_200)

    assert result == ["EMPTY01", "STALE01"]
