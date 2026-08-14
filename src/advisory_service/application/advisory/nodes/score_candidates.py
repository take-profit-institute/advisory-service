"""
score 노드: domain.services.fit_score 순수함수로 정량 스코어링을 수행한다.

순위 정책: RRF는 검색 후보를 추리는 데만 쓰이고, 최종 정렬은 fit_score만
사용한다. 검색 관련성이 낮아도 fit_score가 높으면 상위에 올 수 있다는
뜻이다. 즉 "검색은 후보 생성용, 최종 순위는 적합도 전용"이 현재 정책이다.
RRF와 fit_score를 함께 반영한 가중합(예: fit*0.7 + rrf*0.3)으로 바꾸는 건
가중치를 뒷받침할 실측 데이터가 쌓인 뒤 재검토한다.
"""

from advisory_service.application.advisory.state import AdvisoryState
from advisory_service.application.ports.stock_metrics_reader import StockMetricsReader
from advisory_service.domain.models.candidate import ScoredCandidate
from advisory_service.domain.services.fit_score import compute_fit_score

TOP_N_RECOMMEND = 5


async def score_candidates(
    state: AdvisoryState, stock_metrics_reader: StockMetricsReader
) -> AdvisoryState:
    profile = state["investor_profile"]
    risk_tolerance = profile.risk_tolerance.value
    candidates = state["retrieved_candidates"]

    # 후보마다 개별 조회(N+1)하지 않고 한 번에 일괄 조회한다.
    metrics_by_stock_code = await stock_metrics_reader.get_metrics_many(
        [c.stock_code for c in candidates]
    )

    scored: list[ScoredCandidate] = []
    for candidate in candidates:
        metrics = metrics_by_stock_code.get(candidate.stock_code)
        if metrics is None:
            # 지표 결측(get_metrics_many가 걸러냄) -> 후보에서 제외
            continue
        fit_score, breakdown, improvement_tags = compute_fit_score(metrics, risk_tolerance)
        scored.append(
            ScoredCandidate(
                stock_code=candidate.stock_code,
                name_kr=candidate.name_kr,
                rrf_score=candidate.rrf_score,
                fit_score=fit_score,
                price_snapshot=metrics.price_snapshot,
                score_breakdown=breakdown,
                improvement_tags=improvement_tags,
            )
        )

    scored.sort(key=lambda c: c.fit_score, reverse=True)
    return {**state, "scored_candidates": scored[:TOP_N_RECOMMEND]}
