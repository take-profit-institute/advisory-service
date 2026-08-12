"""score 노드: domain.services.fit_score 순수함수로 정량 스코어링을 수행한다."""

from advisory_service.application.advisory.state import AdvisoryState
from advisory_service.application.ports.stock_metrics_reader import StockMetricsReader
from advisory_service.domain.models.candidate import ScoredCandidate
from advisory_service.domain.services.fit_score import compute_fit_score

TOP_N_RECOMMEND = 5


async def score_candidates(
    state: AdvisoryState,
    stock_metrics_reader: StockMetricsReader,
) -> AdvisoryState:
    profile = state["investor_profile"]
    risk_tolerance = profile.risk_tolerance.value

    scored: list[ScoredCandidate] = []
    for candidate in state["retrieved_candidates"]:
        metrics = await stock_metrics_reader.get_metrics(candidate.stock_id)
        if metrics is None:
            continue
        fit_score, breakdown, improvement_tags = compute_fit_score(metrics, risk_tolerance)
        scored.append(
            ScoredCandidate(
                stock_id=candidate.stock_id,
                ticker=candidate.ticker,
                name_kr=candidate.name_kr,
                rrf_score=candidate.rrf_score,
                fit_score=fit_score,
                score_breakdown=breakdown,
                improvement_tags=improvement_tags,
            )
        )

    scored.sort(key=lambda c: c.fit_score, reverse=True)
    return {**state, "scored_candidates": scored[:TOP_N_RECOMMEND]}