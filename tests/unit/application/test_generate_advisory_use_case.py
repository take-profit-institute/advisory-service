"""
GenerateAdvisoryUseCase 단위테스트.

검증 대상:
1. 검증 통과 시에만 repository.save_many()가 호출되는지 (investor_profile도 함께 전달되는지)
2. validation_status가 개별 추천 객체가 아니라 실행 결과(AdvisoryResult)에
   올바르게 귀속되는지 (첫 시도 통과=PASSED, 재시도 후 통과=RETRIED,
   재시도 초과=FAILED)
3. 추천 후보가 0건이면 검증 실패로 처리되는지 (빈 결과가 PASSED로 새는 걸 방지)
"""

import pytest

from advisory_service.application.advisory.graph import build_advisory_graph
from advisory_service.application.advisory.use_case import GenerateAdvisoryUseCase
from advisory_service.domain.models.advisory import ValidationStatus
from advisory_service.domain.models.candidate import RetrievedCandidate, StockMetrics
from advisory_service.domain.models.investor_profile import (
    InvestorProfile,
    RiskTolerance,
)

_CANDIDATE = RetrievedCandidate(
    stock_code="005930", name_kr="삼성전자",
    narrative_content="...", vector_rank=1, keyword_rank=1, rrf_score=0.03,
)


class FakeStockSearch:
    def __init__(self, results=(_CANDIDATE,)):
        self._results = list(results)

    async def hybrid_search(self, query_text, top_k=20):
        return self._results


class FakeStockMetricsReader:
    async def get_metrics(self, stock_code):
        return StockMetrics(per=10, pbr=1, roe=12, volatility_90d=15)

    async def get_metrics_many(self, stock_codes):
        return {code: StockMetrics(per=10, pbr=1, roe=12, volatility_90d=15) for code in stock_codes}


class AlwaysValidNarrativeGenerator:
    async def generate(self, candidate):
        return "충분히 긴 테스트용 추천 사유 문장입니다."


class AlwaysInvalidNarrativeGenerator:
    async def generate(self, candidate):
        return ""  # validate_result가 실패 처리하도록 빈 문자열 반환


class FirstCallShortThenValidNarrativeGenerator:
    """첫 호출은 검증 실패(짧은 문장), 두 번째 호출부터는 통과 -> RETRIED 상태 재현용."""

    def __init__(self):
        self.call_count = 0

    async def generate(self, candidate):
        self.call_count += 1
        if self.call_count == 1:
            return "짧음"
        return "충분히 긴 테스트용 추천 사유 문장입니다."


class SpyAdvisoryRepository:
    def __init__(self):
        self.saved: list = []
        self.saved_profile = None
        self.save_many_call_count = 0

    async def save_many(self, recommendations, investor_profile):
        self.save_many_call_count += 1
        self.saved.extend(recommendations)
        self.saved_profile = investor_profile


def _build_profile() -> InvestorProfile:
    return InvestorProfile(
        user_id="11111111-1111-1111-1111-111111111111",
        risk_tolerance=RiskTolerance.MODERATE,
        free_text_query="저평가 우량주",
    )


@pytest.mark.asyncio
async def test_use_case_saves_only_on_pass_and_reports_passed_status():
    repository = SpyAdvisoryRepository()
    graph = build_advisory_graph(
        stock_search=FakeStockSearch(),
        stock_metrics_reader=FakeStockMetricsReader(),
        narrative_generator=AlwaysValidNarrativeGenerator(),
    )
    use_case = GenerateAdvisoryUseCase(graph=graph, advisory_repository=repository)

    profile = _build_profile()
    result = await use_case.execute(profile)

    assert result.validation_status == ValidationStatus.PASSED
    assert repository.save_many_call_count == 1
    assert len(repository.saved) == 1
    assert repository.saved_profile is profile  # 프로필도 함께 전달되는지 (FK upsert용)


@pytest.mark.asyncio
async def test_use_case_does_not_save_when_validation_fails_after_max_retry():
    repository = SpyAdvisoryRepository()
    graph = build_advisory_graph(
        stock_search=FakeStockSearch(),
        stock_metrics_reader=FakeStockMetricsReader(),
        narrative_generator=AlwaysInvalidNarrativeGenerator(),
    )
    use_case = GenerateAdvisoryUseCase(graph=graph, advisory_repository=repository)

    result = await use_case.execute(_build_profile())

    assert result.validation_status == ValidationStatus.FAILED
    assert result.retry_count >= 2  # MAX_RETRY(2) 소진
    assert repository.save_many_call_count == 0  # 실패 시 저장 안 함


@pytest.mark.asyncio
async def test_use_case_reports_retried_status_when_second_attempt_passes():
    repository = SpyAdvisoryRepository()
    narrative_generator = FirstCallShortThenValidNarrativeGenerator()
    graph = build_advisory_graph(
        stock_search=FakeStockSearch(),
        stock_metrics_reader=FakeStockMetricsReader(),
        narrative_generator=narrative_generator,
    )
    use_case = GenerateAdvisoryUseCase(graph=graph, advisory_repository=repository)

    result = await use_case.execute(_build_profile())

    assert result.validation_status == ValidationStatus.RETRIED
    assert result.retry_count == 1
    assert repository.save_many_call_count == 1  # 재시도 후 통과했으므로 저장은 됨


@pytest.mark.asyncio
async def test_use_case_fails_when_no_candidates_found():
    """검색 결과가 0건이면 narrative가 하나도 안 만들어지고, 빈 추천이 PASSED로 새면 안 된다."""
    repository = SpyAdvisoryRepository()
    graph = build_advisory_graph(
        stock_search=FakeStockSearch(results=[]),
        stock_metrics_reader=FakeStockMetricsReader(),
        narrative_generator=AlwaysValidNarrativeGenerator(),
    )
    use_case = GenerateAdvisoryUseCase(graph=graph, advisory_repository=repository)

    result = await use_case.execute(_build_profile())

    assert result.validation_status == ValidationStatus.FAILED
    assert "추천 가능한 종목이 없습니다." in result.validation_errors
    assert repository.save_many_call_count == 0
