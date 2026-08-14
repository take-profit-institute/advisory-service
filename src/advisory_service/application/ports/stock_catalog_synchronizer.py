"""
Stock Service 동기화(쓰기) 포트.

CONVENTIONS.md 4장 원칙에 따라 StockMetricsReader(조회)와 분리했다.
이 포트는 score_candidates 노드가 아니라 별도의 배치/스케줄러 진입점에서만
사용되며, 소비자가 다르므로 인터페이스도 다르게 유지한다.

실제 구현은 infrastructure/stock_catalog/grpc_stock_catalog.py 가 담당하며,
기존 candle.stock.v1의 SearchStocks/GetStock 계약을 그대로 사용한다.
"""

from typing import Protocol


class StockCatalogSynchronizer(Protocol):
    async def sync_all(self) -> int:
        """Stock Service 전체 종목을 로컬 캐시(stocks_cache)로 동기화한다. 반환값: 동기화 건수."""
        ...
