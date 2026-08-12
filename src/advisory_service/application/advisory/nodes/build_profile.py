"""profile 노드: 사용자 프로필을 정규화하고 검색 질의를 준비한다."""

from advisory_service.application.advisory.state import AdvisoryState

async def build_profile(state: AdvisoryState) -> AdvisoryState:
    profile = state["investor_profile"]
    # free_text_query가 비어있으면 risk_tolerance/preferred_sectors 기반으로
    # 템플릿 쿼리를 생성하는 로직을 이후 추가한다 (TODO).
    if not profile.free_text_query:
        pass
    return state
