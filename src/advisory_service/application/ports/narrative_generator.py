"""
LLM 기반 추천 사유(narrative) 생성 포트.

실제 구현은 infrastructure/llm/openai_narrative_generator.py 가 담당한다 (gpt-4o-mini).
narrative_generator는 score_breakdown에 없는 수치를 임의로 만들어내지 않는다는
제약을 프롬프트 레벨에서 지켜야 한다 (구현체 docstring 참고).
"""

from typing import Protocol

from advisory_service.domain.models.candidate import ScoredCandidate


class NarrativeGeneratorPort(Protocol):
    async def generate(self, candidate: ScoredCandidate) -> str:
        """score_breakdown을 근거로 2~3문장의 추천 사유를 생성한다."""
        ...
