"""
stocks_cache 테이블 조회/upsert.

StockMetricsReader의 구현체(get_metrics, get_metrics_many)를 담당한다. 실제 Stock Service
동기화(sync_all)는 infrastructure/stock_catalog/grpc_stock_catalog.py 가 담당하고,
이 repository는 그 결과를 로컬에 upsert/조회하는 역할만 한다.
"""

from collections.abc import Sequence
from decimal import Decimal

import asyncpg

from advisory_service.domain.models.candidate import StockMetrics


class PostgresStockCache:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_metrics(self, stock_code: str) -> StockMetrics | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT per, pbr, roe, volatility_90d, latest_close
                FROM stocks_cache
                WHERE stock_code = $1
                """,
                stock_code,
            )
        return self._row_to_metrics(row)

    async def get_metrics_many(
        self, stock_codes: Sequence[str]
    ) -> dict[str, StockMetrics]:
        """
        여러 종목을 WHERE stock_code = ANY($1) 한 번의 쿼리로 조회한다.
        score_candidates가 후보 개수만큼 순차 조회(N+1)하지 않도록 한다.
        """
        if not stock_codes:
            return {}

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT stock_code, per, pbr, roe, volatility_90d, latest_close
                FROM stocks_cache
                WHERE stock_code = ANY($1::varchar[])
                """,
                list(stock_codes),
            )

        result: dict[str, StockMetrics] = {}
        for row in rows:
            metrics = self._row_to_metrics(row)
            if metrics is not None:
                result[row["stock_code"]] = metrics
        return result

    async def get_metric_values_many(self, stock_codes: Sequence[str]) -> dict[str, dict]:
        """변동성 보충 어댑터가 사용할 nullable 원본 지표를 반환한다."""
        if not stock_codes:
            return {}
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT stock_code, per, pbr, roe, volatility_90d, latest_close
                FROM stocks_cache
                WHERE stock_code = ANY($1::varchar[])
                """,
                list(stock_codes),
            )
        return {row["stock_code"]: dict(row) for row in rows}

    @staticmethod
    def _row_to_metrics(row) -> StockMetrics | None:
        """
        지표 중 하나라도 결측이면 None을 반환해 후보에서 제외되게 한다.

        특히 volatility_90d를 `or 0`으로 기본값 처리하면 "데이터 없음"이
        "변동성 0(매우 안정적)"으로 잘못 해석되어, 보수형 사용자에게
        검증되지 않은 종목이 안전한 것처럼 추천될 위험이 있다.
        MVP 정책: 결측치가 있는 종목은 후보에서 제외한다 (0으로 대체하지 않음).
        """
        if row is None:
            return None
        if row["per"] is None or row["pbr"] is None or row["roe"] is None:
            return None
        if row["volatility_90d"] is None:
            return None

        return StockMetrics(
            per=float(row["per"]),
            pbr=float(row["pbr"]),
            roe=float(row["roe"]),
            volatility_90d=float(row["volatility_90d"]),
            price_snapshot=(
                float(row["latest_close"]) if row.get("latest_close") is not None else None
            ),
        )

    async def upsert(self, stock: dict, financials: dict | None) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stocks_cache (
                    stock_code, name_kr, name_en, sector, market, market_cap,
                    per, pbr, roe, financials_fiscal_period, synced_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now())
                ON CONFLICT (stock_code) DO UPDATE SET
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
                stock["stock_code"], stock["name_kr"], stock.get("name_en"),
                stock.get("sector"), stock.get("market"), stock.get("market_cap"),
                self._decimal(financials.get("per")) if financials else None,
                self._decimal(financials.get("pbr")) if financials else None,
                self._decimal(financials.get("roe")) if financials else None,
                financials.get("fiscal_period") if financials else None,
            )

    async def update_market_metrics(
        self, stock_code: str, volatility_90d: float, latest_close: float
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE stocks_cache
                SET volatility_90d = $2,
                    volatility_calculated_at = now(),
                    latest_close = $3,
                    latest_close_at = now()
                WHERE stock_code = $1
                """,
                stock_code,
                Decimal(str(volatility_90d)),
                Decimal(str(latest_close)),
            )

    async def upsert_narrative(
        self,
        stock_code: str,
        content: str,
        embedding: list[float],
        source: str = "stock-service",
    ) -> None:
        vector_literal = "[" + ",".join(str(value) for value in embedding) + "]"
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stock_narratives (
                    stock_code, narrative_type, content, embedding, source
                )
                VALUES ($1, 'company_description', $2, $3::vector, $4)
                ON CONFLICT (stock_code, narrative_type, source) DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    created_at = now()
                """,
                stock_code,
                content,
                vector_literal,
                source,
            )

    @staticmethod
    def _decimal(value) -> Decimal | None:
        if value in (None, ""):
            return None
        return Decimal(str(value))
