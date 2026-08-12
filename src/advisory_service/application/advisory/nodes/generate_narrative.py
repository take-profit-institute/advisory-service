"""narrative 노드: NarrativeGeneratorPort로 추천 사유를 생성한다."""

from advisory_service.application.advisory.state import AdvisoryState
from advisory_service.application.ports.narrative_generator import NarrativeGeneratorPort
from advisory_service.domain.models.advisory import AdvisoryRecommendation

async def generate_narrative(
    state: AdvisoryState,
    narrative_generator: NarrativeGeneratorPort,
) -> AdvisoryState:
    profile = state["investor_profile"]
    recommendations = list[AdvisoryRecommendation] = []

    for candidate in state["scored_candidates"]:
        narrative_text = await narrative_generator.generate(candidate)
        recommendations.append(
            AdvisoryRecommendation(
                user_id=profile.user_id,
                stock_id=candidate.stock_id,
                ticker=candidate.ticker,
                name_kr=candidate.name_kr,
                rrf_score=candidate.rrf_score,
                fit_score=candidate.fit_score,
                narrative=narrative_text,
                improvement_tags=candidate.improvement_tags,
            )
        )

    return {**state, "recommendations": recommendations}