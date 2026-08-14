"""캐시에 없는 변동성을 ChartService 일봉으로 보충하는 지표 조회 어댑터."""

import asyncio
from collections.abc import Sequence

import grpc

from advisory_service.domain.models.candidate import StockMetrics
from advisory_service.domain.services.volatility import annualized_volatility
from advisory_service.infrastructure.persistence.repositories.postgres_stock_cache import (
    PostgresStockCache,
)
from advisory_service.infrastructure.stock_catalog.grpc_stock_catalog import (
    RequestRateLimiter,
)
from advisory_service.transport.grpc.generated.candle.stock.v1 import (
    chart_pb2,
    chart_pb2_grpc,
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
    ):
        self._stub = chart_pb2_grpc.ChartServiceStub(channel)
        self._cache = cache
        self._timeout_seconds = timeout_seconds
        self._limiter = RequestRateLimiter(requests_per_second)
        self._semaphore = asyncio.Semaphore(max(concurrency, 1))

    async def get_metrics(self, stock_code: str) -> StockMetrics | None:
        return (await self.get_metrics_many([stock_code])).get(stock_code)

    async def get_metrics_many(
        self, stock_codes: Sequence[str]
    ) -> dict[str, StockMetrics]:
        cached = await self._cache.get_metrics_many(stock_codes)
        missing = [code for code in stock_codes if code not in cached]
        if not missing:
            return cached

        raw = await self._cache.get_metric_values_many(missing)
        refreshed = await asyncio.gather(
            *(self._build_metrics(code, raw.get(code)) for code in missing)
        )
        cached.update(
            {code: metrics for code, metrics in refreshed if metrics is not None}
        )
        return cached

    async def _build_metrics(
        self, stock_code: str, values: dict | None
    ) -> tuple[str, StockMetrics | None]:
        if values is None or any(values.get(key) is None for key in ("per", "pbr", "roe")):
            return stock_code, None

        cached_volatility = values.get("volatility_90d")
        latest_close: float | None
        if cached_volatility is None:
            market_metrics = await self._fetch_market_metrics(stock_code)
            if market_metrics is None:
                return stock_code, None
            volatility, latest_close = market_metrics
            await self._cache.update_market_metrics(
                stock_code, volatility, latest_close
            )
        else:
            volatility = float(cached_volatility)
            raw_latest_close = values.get("latest_close")
            latest_close = (
                float(raw_latest_close) if raw_latest_close is not None else None
            )

        return stock_code, StockMetrics(
            per=float(values["per"]),
            pbr=float(values["pbr"]),
            roe=float(values["roe"]),
            volatility_90d=float(volatility),
            price_snapshot=(float(latest_close) if latest_close is not None else None),
        )

    async def _fetch_market_metrics(
        self, stock_code: str
    ) -> tuple[float, float] | None:
        async with self._semaphore:
            await self._limiter.wait()
            response = await self._stub.GetCandles(
                chart_pb2.GetCandlesRequest(
                    code=stock_code,
                    interval=chart_pb2.DAY_1,
                    limit=91,
                ),
                timeout=self._timeout_seconds,
            )
        closes = [candle.close for candle in response.candles if candle.closed]
        volatility = annualized_volatility(closes)
        if volatility is None or not closes:
            return None
        return volatility, float(closes[-1])
