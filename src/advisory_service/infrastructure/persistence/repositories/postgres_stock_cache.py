"""
stocks_cache 테이블 조회/upsert.

StockMetricsReader의 구현체(get_metrics)를 담당한다. 실제 Stock Service
동기화(sync_all)는 infrastructure/stock_catalog/grpc_stock_catalog.py 가 담당하고,
이 repository는 그 결과를 로컬에 upsert/조회하는 역할만 한다.
"""

import asyncpg

from advisory_service.domain.models.candidate import StockMetrics


class PostgresStockCache:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_metrics(self, stock_id: int) -> StockMetrics | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT per, pbr, roe, volatility_90d
                FROM stocks_cache
                WHERE stock_id = $1
                """,
                stock_id,
            )
        if row is None or row["per"] is None:
            return None
        return StockMetrics(
            per=float(row["per"]),
            pbr=float(row["pbr"]),
            roe=float(row["roe"]),
            volatility_90d=float(row["volatility_90d"] or 0),
            )

    async def upsert(self, stock: dict, financials: dict | None) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stocks_cache (
                    stock_id, ticker, name_kr, name_en, sector, market, market_cap,
                    per, pbr, roe, financials_fiscal_period, synced_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, now())
                ON CONFLICT (stock_id) DO UPDATE SET
                    ticker = EXCLUDED.ticker,
                    name_kr = EXCLUDED.name_kr,
                    name_en = EXCLUDED.name_en,
                    sector = EXCLUDED.sector,
                    market = EXCLUDED.market,
                    market_cap = EXCLUDED.market_cap,
                    per = EXCLUDED.per,
                    pbr = EXCLUDED.pbr,
                    roe = EXCLUDED.roe,
                    financials_fiscal_period = EXCLUDED.financials_fiscal_period,
                    synced_at = now()
                """,
                stock["stock_id"], stock["ticker"], stock["name_kr"], stock.get("name_en"),
                stock.get("sector"), stock.get("market"), stock.get("market_cap"),
                financials.get("per") if financials else None,
                financials.get("pbr") if financials else None,
                financials.get("roe") if financials else None,
                financials.get("fiscal_period") if financials else None,
            )