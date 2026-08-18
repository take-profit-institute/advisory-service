"""ChartService 일봉으로 시장 지표(변동성/최근 종가)를 계산하는 공용 클라이언트."""

import asyncio

import grpc

from advisory_service.domain.services.volatility import annualized_volatility
from advisory_service.infrastructure.stock_catalog.grpc_stock_catalog import (
    RequestRateLimiter,
)
from advisory_service.transport.grpc.generated.candle.stock.v1 import (
    chart_pb2,
    chart_pb2_grpc,
)

# 변동성 계산에 쓰는 일봉 개수. 90일 수익률을 얻으려면 종가가 91개 필요하다.
CANDLE_LIMIT = 91


class GrpcMarketMetricsFetcher:
    """
    GetCandles 호출 하나를 담당한다.

    요청 경로(GrpcBackedStockMetricsReader)와 워밍 배치(MarketMetricsWarmer)가
    같은 계산·같은 rate limit을 쓰도록 여기 한 곳에 모아둔다.
    """

    def __init__(
        self,
        channel: grpc.aio.Channel,
        *,
        timeout_seconds: float = 5.0,
        requests_per_second: float = 10.0,
        concurrency: int = 5,
    ):
        self._stub = chart_pb2_grpc.ChartServiceStub(channel)
        self._timeout_seconds = timeout_seconds
        self._limiter = RequestRateLimiter(requests_per_second)
        self._semaphore = asyncio.Semaphore(max(concurrency, 1))

    async def fetch(self, stock_code: str) -> tuple[float, float] | None:
        """(변동성, 최근 종가)를 반환한다. 계산에 필요한 일봉이 없으면 None."""
        async with self._semaphore:
            await self._limiter.wait()
            response = await self._stub.GetCandles(
                chart_pb2.GetCandlesRequest(
                    code=stock_code,
                    interval=chart_pb2.DAY_1,
                    limit=CANDLE_LIMIT,
                ),
                timeout=self._timeout_seconds,
            )
        closes = [candle.close for candle in response.candles if candle.closed]
        volatility = annualized_volatility(closes)
        if volatility is None or not closes:
            return None
        return volatility, float(closes[-1])
