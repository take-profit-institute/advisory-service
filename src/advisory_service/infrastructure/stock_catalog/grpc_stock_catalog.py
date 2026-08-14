"""기존 candle.stock.v1 gRPC 계약을 사용하는 종목 동기화 어댑터."""

import asyncio
import time
from collections.abc import Awaitable, Callable

import grpc

from advisory_service.infrastructure.persistence.repositories.postgres_stock_cache import (
    PostgresStockCache,
)
from advisory_service.transport.grpc.generated.candle.stock.v1 import (
    stock_pb2,
    stock_pb2_grpc,
)


class RequestRateLimiter:
    """여러 coroutine의 요청 시작 시점을 일정 간격으로 제한한다."""

    def __init__(self, requests_per_second: float):
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self._interval = 1.0 / requests_per_second
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_allowed - now)
            if delay:
                await asyncio.sleep(delay)
            self._next_allowed = max(now, self._next_allowed) + self._interval


class StockServiceGrpcClient:
    def __init__(
        self,
        channel: grpc.aio.Channel,
        *,
        timeout_seconds: float = 5.0,
        requests_per_second: float = 10.0,
    ):
        self._stub = stock_pb2_grpc.StockServiceStub(channel)
        self._timeout_seconds = timeout_seconds
        self._limiter = RequestRateLimiter(requests_per_second)

    async def search_stocks(self, page: int, size: int) -> stock_pb2.SearchStocksResponse:
        await self._limiter.wait()
        return await self._stub.SearchStocks(
            stock_pb2.SearchStocksRequest(
                status=stock_pb2.LISTED,
                sort=stock_pb2.CODE_ASC,
                page=page,
                size=size,
            ),
            timeout=self._timeout_seconds,
        )

    async def get_stock(self, stock_code: str) -> stock_pb2.GetStockResponse:
        await self._limiter.wait()
        return await self._stub.GetStock(
            stock_pb2.GetStockRequest(code=stock_code, allow_fallback=False),
            timeout=self._timeout_seconds,
        )


class GrpcStockCatalogSynchronizer:
    """전체 상장 종목을 페이지 조회해 제한된 동시성으로 로컬 캐시에 동기화한다."""

    def __init__(
        self,
        grpc_client: StockServiceGrpcClient,
        cache: PostgresStockCache,
        embed_fn: Callable[[str], Awaitable[list[float]]],
        *,
        page_size: int = 100,
        concurrency: int = 5,
    ):
        self._grpc_client = grpc_client
        self._cache = cache
        self._embed_fn = embed_fn
        self._page_size = min(max(page_size, 1), 100)
        self._semaphore = asyncio.Semaphore(max(concurrency, 1))

    async def sync_all(self) -> int:
        synced_count = 0
        page = 0

        while True:
            response = await self._grpc_client.search_stocks(page, self._page_size)
            if not response.stocks:
                break

            await asyncio.gather(*(self._sync_stock(stock) for stock in response.stocks))
            synced_count += len(response.stocks)
            page += 1
            if page >= response.total_pages:
                break

        return synced_count

    async def _sync_stock(self, listed_stock: stock_pb2.Stock) -> None:
        async with self._semaphore:
            response = await self._grpc_client.get_stock(listed_stock.code)
            detail = response.stock
            stock = detail.stock if detail.HasField("stock") else listed_stock
            financials = self._financials(detail)
            stock_data = {
                "stock_code": stock.code,
                "name_kr": stock.name,
                "sector": stock.sector or None,
                "market": stock_pb2.MarketType.Name(stock.market),
                "market_cap": stock.market_cap or None,
            }
            await self._cache.upsert(stock_data, financials)

            content = detail.description.strip() or self._fallback_narrative(stock_data, financials)
            embedding = await self._embed_fn(content)
            await self._cache.upsert_narrative(stock.code, content, embedding)

    @staticmethod
    def _financials(detail: stock_pb2.StockDetail) -> dict | None:
        if not detail.HasField("financials"):
            return None
        financials = detail.financials
        return {
            "per": financials.per or None,
            "pbr": financials.pbr or None,
            "roe": financials.roe or None,
            "fiscal_period": financials.fiscal_period or None,
        }

    @staticmethod
    def _fallback_narrative(stock: dict, financials: dict | None) -> str:
        metrics = financials or {}
        return (
            f"{stock['name_kr']}({stock['stock_code']})는 "
            f"{stock.get('market') or '국내'} 시장의 {stock.get('sector') or '미분류'} 종목이다. "
            f"PER {metrics.get('per') or '미제공'}, PBR {metrics.get('pbr') or '미제공'}, "
            f"ROE {metrics.get('roe') or '미제공'} 기준으로 분석한다."
        )
