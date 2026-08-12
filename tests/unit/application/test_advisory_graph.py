"""
application.advisory.graph 통합 단위테스트.

포트(StockSearchPort, StockMetricsReader, NarrativeGeneratorPort)를 전부
간단한 in-memory fake로 대체해, 실제 DB/LLM 없이 오케스트레이션 흐름을 검증한다.
"""

import pytest

from advisory_service.application.advisory.graph import build_advisory_graph
from advisory_service.domain.models.candidate import RetrievedCandidate, StockMetrics
from advisory_service.domain.models.investor_profile import (
    InvestorProfile,
    RiskTolerance,
)


class FakeStockSearch:
    async def hybrid_search(self, query_text, top_k=20):
        return [
            RetrievedCandidate(
                stock_id=1, ticker="005930", name_kr="삼성전자",
                narrative_content="...", vector_rank=1, keyword_rank=1, rrf_score=0.03,
            )
        ]


class FakeStockMetricsReader:
    async def get_metrics(self, stock_id):
        return StockMetrics(per=10, pbr=1, roe=12, volatility_90d=15)


class FakeNarrativeGenerator:
    async def generate(self, candidate):
        return "테스트용 추천 사유 문장입니다."


@pytest.mark.asyncio
async def test_advisory_graph_end_to_end_with_fakes():
    graph = build_advisory_graph(
        stock_search=FakeStockSearch(),
        stock_metrics_reader=FakeStockMetricsReader(),
        narrative_generator=FakeNarrativeGenerator(),
    )

    initial_state = {
        "investor_profile": InvestorProfile(
            user_id=1, risk_tolerance=RiskTolerance.MODERATE, free_text_query="저평가 우량주"
        ),
        "retrieved_candidates": [],
        "scored_candidates": [],
        "recommendations": [],
        "validation_passed": False,
        "validation_errors": [],
        "retry_count": 0,
    }

    result = await graph.ainvoke(initial_state)

    assert result["validation_passed"] is True
    assert len(result["recommendations"]) == 1
    assert result["recommendations"][0].ticker == "005930"
