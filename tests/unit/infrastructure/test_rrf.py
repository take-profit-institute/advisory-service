"""infrastructure.retrieval.hybrid_stock_search 의 RRF 융합 로직 단위테스트."""

from advisory_service.infrastructure.retrieval.hybrid_stock_search import (
    HybridStockSearch,
)


def test_rrf_favors_item_ranked_high_in_both_lists():
    vector_results = [
        {"stock_code": "A", "name_kr": "가", "content": "..."},
        {"stock_code": "B", "name_kr": "나", "content": "..."},
    ]
    keyword_results = [
        {"stock_code": "A", "name_kr": "가", "content": "..."},
        {"stock_code": "C", "name_kr": "다", "content": "..."},
    ]

    fused = HybridStockSearch._reciprocal_rank_fusion(vector_results, keyword_results)

    assert fused[0].stock_code == "A"  # 두 검색 모두에서 1위 -> 최상위
    assert {c.stock_code for c in fused} == {"A", "B", "C"}


def test_rrf_handles_item_in_only_one_list():
    vector_results = [{"stock_code": "A", "name_kr": "가", "content": "..."}]
    keyword_results = []

    fused = HybridStockSearch._reciprocal_rank_fusion(vector_results, keyword_results)

    assert len(fused) == 1
    assert fused[0].keyword_rank is None
    assert fused[0].vector_rank == 1
