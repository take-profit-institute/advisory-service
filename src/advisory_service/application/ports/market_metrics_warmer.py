"""
변동성/종가 캐시 워밍(쓰기) 포트.

StockCatalogSynchronizer와 마찬가지로 요청 경로가 아니라 배치/스케줄러
진입점에서만 사용된다. score_candidates가 읽는 값을 미리 채워두는 책임이라,
조회 포트(StockMetricsReader)와는 소비자도 인터페이스도 다르다.

실제 구현은 infrastructure/stock_catalog/market_metrics_warmer.py 가 담당한다.
"""

from typing import Protocol


class MarketMetricsWarmer(Protocol):
    async def warm_all(self):
        """변동성이 없거나 오래된 종목을 일괄 갱신한다. 반환값: 집계 결과."""
        ...
