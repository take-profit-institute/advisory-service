"""
validate 노드: 스키마/품질 검증.

MVP 범위: narrative 최소 길이 체크 정도로 축소.
(정교한 환각 체크 등은 1차 고도화 대상)
"""

from advisory_service.application.advisory.state import AdvisoryState

MAX_RETRY = 2


async def validate_result(state: AdvisoryState) -> AdvisoryState:
    errors = []
    for rec in state["recommendations"]:
        if not rec.narrative or len(rec.narrative) < 10:
            errors.append(f"{rec.ticker}: narrative 생성 실패 또는 너무 짧음")

    passed = len(errors) == 0
    return {
        **state,
        "validation_passed": passed,
        "validation_errors": errors,
        "retry_count": state.get("retry_count", 0) + (0 if passed else 1),
    }


def route_after_validation(state: AdvisoryState) -> str:
    if state["validation_passed"]:
        return "end"
    if state["retry_count"] >= MAX_RETRY:
        return "end"  # 재시도 초과 -> 실패 상태로라도 종료 (무한루프 방지)
    return "retry"