"""
application.ports.stock_catalog_synchronizer.StockCatalogSynchronizer 구현체 (부분 스텁).

Stock Service의 실제 gRPC 인터페이스(RPC 목록, 페이지네이션 방식,
candles 접근 방법)는 아직 조사 중이라 (GitHub Issue: "Stock Service gRPC
인터페이스 조사"), 이 파일은 조사 결과가 나오기 전까지 Protocol로
인터페이스만 정의해 나머지 레이어 개발이 막히지 않도록 한다.

CONVENTIONS.md 인터페이스 분리 원칙에 따라 조회(StockMetricsReader)는
PostgresStockCache가 별도로 담당하고, 이 클래스는 동기화(쓰기)만 담당한다.
"""

from typing import Protocol

from advisory_service.infrastructure.persistence.repositories.postgres_stock_cache import (
    PostgresStockCache,
)


class StockServiceGrpcClient(Protocol):
    """실제로는 protoc로 생성된 StockServiceStub. 인터페이스만 먼저 정의해 개발 병행."""

    async def list_stocks(
        self, page_token: str | None = None
    ) -> tuple[list[dict], str | None]:
        """(종목 목록, 다음 페이지 토큰) 반환. 토큰이 None이면 마지막 페이지."""
        ...

    async def get_financials(self, stock_id: int) -> dict | None:
        """PER/PBR/ROE/fiscal_period 등 최신 스냅샷. 데이터 없으면 None."""
        ...


class GrpcStockCatalogSynchronizer:
    def __init__(self, grpc_client: StockServiceGrpcClient, cache: PostgresStockCache):
        self._grpc_client = grpc_client
        self._cache = cache

    async def sync_all(self) -> int:
        """
        Stock Service 전체 종목을 페이지네이션하며 stocks_cache에 upsert.
        financials_fiscal_period가 없거나 오래된 경우에도 일단 적재하되,
        값 자체를 임의로 채우지 않고 synced_at으로 staleness를 추적한다.
        """
        synced_count = 0
        page_token: str | None = None

        while True:
            stocks, page_token = await self._grpc_client.list_stocks(page_token)
            for stock in stocks:
                financials = await self._grpc_client.get_financials(stock["stock_id"])
                await self._cache.upsert(stock, financials)
                synced_count += 1

            if page_token is None:
                break

        return synced_count
