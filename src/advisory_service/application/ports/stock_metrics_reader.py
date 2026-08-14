"""
종목 정량 지표 조회 포트.

CONVENTIONS.md 4장 "인터페이스 분리" 원칙: 읽기와 쓰기 요구가 다르면 즉시 분리한다.
score_candidates 노드는 조회만 필요하므로, 동기화(쓰기) 책임과 분리된
이 인터페이스 하나만 주입받는다. 동기화는 StockCatalogSynchronizer 참고.

실제 구현은 infrastructure/persistence/repositories/postgres_stock_cache.py
(로컬 캐시 조회) 가 담당한다.
"""

from collections.abc import Sequence
from typing import Protocol

from advisory_service.domain.models.candidate import StockMetrics


class StockMetricsReader(Protocol):
    async def get_metrics(self, stock_code: str) -> StockMetrics | None:
        """종목의 정량 지표(PER/PBR/ROE/변동성)를 조회한다. 데이터 없으면 None."""
        ...

    async def get_metrics_many(
        self, stock_codes: Sequence[str]
    ) -> dict[str, StockMetrics]:
        """
        여러 종목의 정량 지표를 한 번에 조회한다.
        score_candidates가 후보마다 개별 조회(N+1)하지 않도록 배치 조회용으로 둔다.
        지표가 없거나 결측치가 있는 종목은 결과 dict에서 제외된다.
        """
        ...
