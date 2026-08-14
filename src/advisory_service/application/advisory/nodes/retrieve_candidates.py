"""retrieve 노드: StockSearchPort를 통해 하이브리드 검색을 수행한다."""

from advisory_service.application.advisory.state import AdvisoryState
from advisory_service.application.ports.stock_search import StockSearchPort


async def retrieve_candidates(
    state: AdvisoryState, stock_search: StockSearchPort
) -> AdvisoryState:
    profile = state["investor_profile"]
    candidates = await stock_search.hybrid_search(profile.free_text_query, top_k=20)
    return {**state, "retrieved_candidates": candidates}
