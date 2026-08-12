"""
하이브리드 검색(벡터+키워드+RRF) 포트.

실제 구현은 infrastructure/retrieval/hybrid_stock_search.py 가 담당한다
(pgvector 코사인 유사도 + pg_trgm 트라이그램 + RRF 융합).
application 계층은 "검색 결과를 어떻게 얻는지" 모른 채 이 인터페이스만 호출한다.
"""

from typing import Protocol

from advisory_service.domain.models.candidate import RetrievedCandidate


class StockSearchPort(Protocol):
    async def hybrid_search(
        self, query_text: str, top_k: int = 20
    ) -> list[RetrievedCandidate]:
        """자연어 질의에 대해 벡터+키워드 하이브리드 검색을 수행하고 RRF로 융합된 결과를 반환한다."""
        ...