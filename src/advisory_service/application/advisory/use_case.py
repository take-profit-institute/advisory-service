"""
GenerateAdvisoryUseCase — transport와 LangGraph 사이의 경계.

servicer가 그래프를 직접 호출하지 않고 이 use case만 호출하게 하면,
transport 계층이 LangGraph라는 구체적인 오케스트레이션 도구에 결합되지 않는다.
(추후 그래프 구현을 교체하거나 배치/CLI 등 다른 진입점에서도 재사용 가능)

흐름:
    graph.ainvoke()
        -> 최종 State로부터 ValidationStatus 판정
        -> 통과(첫 시도 또는 재시도 후)한 경우에만 repository.save_many()
        -> AdvisoryResult 반환
"""

from advisory_service.application.advisory.state import AdvisoryState
from advisory_service.application.ports.advisory_repository import AdvisoryRepository
from advisory_service.domain.models.advisory import AdvisoryResult, ValidationStatus
from advisory_service.domain.models.investor_profile import InvestorProfile


class GenerateAdvisoryUseCase:
    def __init__(self, graph, advisory_repository: AdvisoryRepository):
        self._graph = graph  # application.advisory.graph.build_advisory_graph() 결과
        self._advisory_repository = advisory_repository

    async def execute(self, investor_profile: InvestorProfile) -> AdvisoryResult:
        initial_state: AdvisoryState = {
            "investor_profile": investor_profile,
            "retrieved_candidates": [],
            "scored_candidates": [],
            "recommendations": [],
            "validation_passed": False,
            "validation_errors": [],
            "retry_count": 0,
        }

        final_state = await self._graph.ainvoke(initial_state)
        result = self._build_result(final_state)

        # 검증을 통과한 결과만 저장한다 (실패/재시도초과 결과는 저장하지 않음).
        # validation_status를 개별 추천 객체가 아니라 이 실행 단위 결과에만
        # 두는 이유는 domain/models/advisory.py의 AdvisoryResult 참고.
        if result.validation_status in (ValidationStatus.PASSED, ValidationStatus.RETRIED):
            await self._advisory_repository.save_many(result.recommendations, investor_profile)

        return result

    @staticmethod
    def _build_result(final_state: AdvisoryState) -> AdvisoryResult:
        if final_state["validation_passed"]:
            status = (
                ValidationStatus.RETRIED
                if final_state["retry_count"] > 0
                else ValidationStatus.PASSED
            )
        else:
            status = ValidationStatus.FAILED

        return AdvisoryResult(
            recommendations=final_state["recommendations"],
            validation_status=status,
            validation_errors=final_state["validation_errors"],
            retry_count=final_state["retry_count"],
        )
