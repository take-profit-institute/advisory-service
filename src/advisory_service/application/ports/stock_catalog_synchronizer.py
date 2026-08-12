"""
Stock Service 동기화(쓰기) 포트.

컨벤션 원칙에 따라 StockMetricsReader(조회)와 분리했다.
이 포트는 score_candidates 노드가 아니라 별도의 배치/스케줄러 진입점에서만
사용되며, 소비자가 다르므로 인터페이스도 다르게 유지한다.

실제 구현은 infrastructure/stock_catalog/grpc_stock_catalog.py 가 담당한다.
Stock Service의 실제 gRPC 인터페이스(RPC 목록, 페이지네이션 등)는 아직
조사 중이며, 이 포트의 구현체는 해당 조사 결과가 나온 뒤 완성 가능하다.
"""

from typing import Protocol


class StockCatalogSynchronizerPort(Protocol):
    async def sync_all(self) -> int:
        """Stock Service 전체 종목을 로컬 캐시(stocks_cache)로 동기화한다. 반환값: 동기화 건수."""
        ...