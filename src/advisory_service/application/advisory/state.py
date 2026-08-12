"""
LangGraph 상태 정의.

State는 데이터 컨테이너 역할만 하고, 실제 로직은 domain/services와
infrastructure 구현체(포트를 통해 주입됨)에 있다. 오케스트레이션(graph.py)과
비즈니스 로직을 분리하기 위함이다.
"""

from typing import TypedDict

from advisory_service.domain.models.advisory import AdvisoryRecommendation
from advisory_service.domain.models.candidate import RetrievedCandidate, ScoredCandidate
from advisory_service.domain.models.investor_profile import InvestorProfile

class AdvisoryState(TypedDict):
    # --- 입력 ---
    investor_profile: InvestorProfile

    # --- retrieve_candidates 노드 출력 ---
    retrieved_candidates: list[RetrievedCandidate]

    # --- score_candidates 노드 출력 ---
    scored_candidates: list[ScoredCandidate]

    # --- generate_narrative 노드 출력 ---
    recommendations: list[AdvisoryRecommendation]

    # -- validate_result 노드 출력 ---
    validation_passed: bool
    validation_errors: list[str]
    retry_count: int