"""캐시에 없는 변동성을 ChartService 일봉으로 보충하는 지표 조회 어댑터."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import grpc

from advisory_service.domain.models.candidate import StockMetrics
from advisory_service.infrastructure.persistence.repositories.postgres_stock_cache import (
    PostgresStockCache,
)
from advisory_service.infrastructure.stock_catalog.grpc_market_metrics import (
    GrpcMarketMetricsFetcher,
)


class GrpcBackedStockMetricsReader:
    def __init__(
        self,
        channel: grpc.aio.Channel,
        cache: PostgresStockCache,
        *,
        timeout_seconds: float = 5.0,
        requests_per_second: float = 10.0,
        concurrency: int = 5,
        volatility_cache_ttl_seconds: int = 86_400,
    ):
        # 요청 경로의 보충 호출은 MarketMetricsWarmer와 같은 fetcher를 쓴다.
        # 워밍이 정상 동작하면 여기는 사실상 타지 않는 fallback이다.
        self._fetcher = GrpcMarketMetricsFetcher(
            channel,
            timeout_seconds=timeout_seconds,
            requests_per_second=requests_per_second,
            concurrency=concurrency,
        )
        self._cache = cache
        self._volatility_cache_ttl = timedelta(
            seconds=max(volatility_cache_ttl_seconds, 0)
        )
        # 동일 프로세스에서 같은 종목의 cache miss가 겹쳐도 GetCandles는 한 번만 호출한다.
        self._refresh_locks: dict[str, asyncio.Lock] = {}

    async def get_metrics(self, stock_code: str) -> StockMetrics | None:
        return (await self.get_metrics_many([stock_code])).get(stock_code)

    async def get_metrics_many(
        self, stock_codes: Sequence[str]
    ) -> dict[str, StockMetrics]:
        unique_codes = list(dict.fromkeys(stock_codes))
        raw = await self._cache.get_metric_values_many(unique_codes)
        resolved = await asyncio.gather(
            *(self._build_metrics(code, raw.get(code)) for code in unique_codes)
        )
        return {code: metrics for code, metrics in resolved if metrics is not None}

    async def _build_metrics(
        self, stock_code: str, values: dict | None
    ) -> tuple[str, StockMetrics | None]:
        if values is None or any(values.get(key) is None for key in ("per", "pbr", "roe")):
            return stock_code, None

        cached = self._fresh_cached_metrics(values)
        if cached is not None:
            return stock_code, cached

        lock = self._refresh_locks.setdefault(stock_code, asyncio.Lock())
        async with lock:
            # 다른 요청이 lock을 기다리는 동안 갱신했을 수 있으므로 DB를 다시 확인한다.
            latest_values = (
                await self._cache.get_metric_values_many([stock_code])
            ).get(stock_code)
            if latest_values is None or any(
                latest_values.get(key) is None for key in ("per", "pbr", "roe")
            ):
                return stock_code, None

            cached = self._fresh_cached_metrics(latest_values)
            if cached is not None:
                return stock_code, cached

            market_metrics = await self._fetch_market_metrics(stock_code)
            if market_metrics is None:
                return stock_code, None
            volatility, latest_close = market_metrics
            await self._cache.update_market_metrics(stock_code, volatility, latest_close)

            return stock_code, self._to_metrics(
                latest_values,
                volatility=volatility,
                latest_close=latest_close,
            )

    def _fresh_cached_metrics(self, values: dict) -> StockMetrics | None:
        volatility = values.get("volatility_90d")
        calculated_at = values.get("volatility_calculated_at")
        if volatility is None or calculated_at is None:
            return None
        if calculated_at.tzinfo is None:
            calculated_at = calculated_at.replace(tzinfo=UTC)
        if datetime.now(UTC) - calculated_at > self._volatility_cache_ttl:
            return None
        return self._to_metrics(
            values,
            volatility=float(volatility),
            latest_close=values.get("latest_close"),
        )

    @staticmethod
    def _to_metrics(
        values: dict,
        *,
        volatility: float,
        latest_close,
    ) -> StockMetrics:
        return StockMetrics(
            per=float(values["per"]),
            pbr=float(values["pbr"]),
            roe=float(values["roe"]),
            volatility_90d=float(volatility),
            price_snapshot=(float(latest_close) if latest_close is not None else None),
        )

    async def _fetch_market_metrics(
        self, stock_code: str
    ) -> tuple[float, float] | None:
        return await self._fetcher.fetch(stock_code)
