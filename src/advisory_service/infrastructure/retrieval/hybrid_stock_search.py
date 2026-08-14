"""
application.ports.stock_search.StockSearchPort의 구현체.

하이브리드 검색: pgvector(의미 기반) + pg_trgm(키워드/종목명/코드) + RRF 융합

설계 근거:
- "삼성전자", "005930" 같은 정확한 종목명/코드 질의 -> 키워드(trgm) 검색이 강함
- "저평가된 안정적인 회사" 같은 의미 기반 질의 -> 벡터 검색이 강함
- 두 방식을 각각 실행한 뒤 RRF(Reciprocal Rank Fusion)로 순위를 합침
  -> 별도 학습이나 가중치 튜닝 없이도 두 검색 방식의 장점을 결합 가능

RRF 공식: score(d) = sum( 1 / (k + rank_i(d)) ) for each ranking i
k=60은 정보검색 분야의 관례적 기본값 (실측 튜닝은 1차 고도화 대상).
"""

import asyncpg

from advisory_service.domain.models.candidate import RetrievedCandidate

RRF_K = 60


class HybridStockSearch:
    def __init__(self, pool: asyncpg.Pool, embed_fn):
        self._pool = pool
        self._embed_fn = embed_fn  # 텍스트 -> 임베딩 벡터 (text-embedding-3-small)

    async def hybrid_search(
        self, query_text: str, top_k: int = 20
    ) -> list[RetrievedCandidate]:
        query_embedding = await self._embed_fn(query_text)
        async with self._pool.acquire() as conn:
            vector_results = await self._vector_search(conn, query_embedding, top_k)
            keyword_results = await self._keyword_search(conn, query_text, top_k)
        # 벡터/키워드 검색 결과를 합치면 최대 2*top_k개가 나올 수 있으므로,
        # 포트가 약속한 top_k 의미를 지키기 위해 RRF 융합 이후 다시 자른다.
        fused = self._reciprocal_rank_fusion(vector_results, keyword_results)
        return fused[:top_k]

    async def _vector_search(
        self, conn: asyncpg.Connection, query_embedding: list[float], top_k: int
    ) -> list[dict]:
        vector_literal = "[" + ",".join(str(value) for value in query_embedding) + "]"
        rows = await conn.fetch(
            """
            SELECT s.stock_code, s.name_kr, n.content,
                   1 - (n.embedding <=> $1::vector) AS similarity
            FROM stock_narratives n
            JOIN stocks_cache s ON s.stock_code = n.stock_code
            ORDER BY n.embedding <=> $1::vector
            LIMIT $2
            """,
            vector_literal,
            top_k,
        )
        return [dict(r) for r in rows]

    async def _keyword_search(
        self, conn: asyncpg.Connection, query_text: str, top_k: int
    ) -> list[dict]:
        rows = await conn.fetch(
            """
            SELECT s.stock_code, s.name_kr, n.content,
                   GREATEST(
                       similarity(s.name_kr, $1),
                       similarity(s.stock_code, $1),
                       similarity(n.content, $1)
                   ) AS similarity
            FROM stocks_cache s
            JOIN stock_narratives n ON n.stock_code = s.stock_code
            WHERE s.name_kr % $1 OR s.stock_code % $1 OR n.content % $1
            ORDER BY similarity DESC
            LIMIT $2
            """,
            query_text,
            top_k,
        )
        return [dict(r) for r in rows]

    @staticmethod
    def _reciprocal_rank_fusion(
        vector_results: list[dict], keyword_results: list[dict], k: int = RRF_K
    ) -> list[RetrievedCandidate]:
        """순수 계산 로직. 단위테스트는 tests/unit/infrastructure/test_rrf.py 참고."""
        scores: dict[str, dict] = {}

        for rank, doc in enumerate(vector_results, start=1):
            sid = doc["stock_code"]
            scores.setdefault(
                sid, {"doc": doc, "vector_rank": None, "keyword_rank": None, "rrf": 0.0}
            )
            scores[sid]["vector_rank"] = rank
            scores[sid]["rrf"] += 1 / (k + rank)

        for rank, doc in enumerate(keyword_results, start=1):
            sid = doc["stock_code"]
            scores.setdefault(
                sid, {"doc": doc, "vector_rank": None, "keyword_rank": None, "rrf": 0.0}
            )
            scores[sid]["keyword_rank"] = rank
            scores[sid]["rrf"] += 1 / (k + rank)

        fused = sorted(scores.values(), key=lambda x: x["rrf"], reverse=True)

        return [
            RetrievedCandidate(
                stock_code=item["doc"]["stock_code"],
                name_kr=item["doc"]["name_kr"],
                narrative_content=item["doc"]["content"],
                vector_rank=item["vector_rank"],
                keyword_rank=item["keyword_rank"],
                rrf_score=item["rrf"],
            )
            for item in fused
        ]
