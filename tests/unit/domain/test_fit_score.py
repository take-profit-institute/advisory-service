"""domain.services.fit_score 순수함수 단위테스트. DB/LLM 의존성 없음."""

import pytest

from advisory_service.domain.models.candidate import StockMetrics
from advisory_service.domain.services.fit_score import (
    compute_fit_score,
    score_profitability_fit,
    score_valuation_fit,
    score_volatility_fit,
)


def test_valuation_fit_penalizes_negative_earnings():
    metrics = StockMetrics(per=-5, pbr=1.5, roe=10, volatility_90d=15)
    assert score_valuation_fit(metrics) == 0.3


def test_profitability_fit_scales_with_roe():
    low_roe = StockMetrics(per=10, pbr=1, roe=5, volatility_90d=15)
    high_roe = StockMetrics(per=10, pbr=1, roe=20, volatility_90d=15)
    assert score_profitability_fit(low_roe) < score_profitability_fit(high_roe)
    assert score_profitability_fit(high_roe) == 1.0  # 15 이상은 만점 cap


@pytest.mark.parametrize(
    "risk_tolerance,volatility,expected_full_score",
    [
        ("conservative", 10, True),
        ("conservative", 25, False),
        ("aggressive", 25, True),
    ],
)
def test_volatility_fit_respects_risk_band(risk_tolerance, volatility, expected_full_score):
    metrics = StockMetrics(per=10, pbr=1, roe=10, volatility_90d=volatility)
    score = score_volatility_fit(metrics, risk_tolerance)
    assert (score == 1.0) == expected_full_score


def test_compute_fit_score_returns_breakdown_and_improvement_tags():
    metrics = StockMetrics(per=50, pbr=5, roe=2, volatility_90d=90)
    fit_score, breakdown, tags = compute_fit_score(metrics, "conservative")

    assert 0.0 <= fit_score <= 1.0
    assert set(breakdown.keys()) == {"valuation_fit", "profitability_fit", "volatility_fit"}
    assert "profitability_analysis" in tags  # roe=2 -> profitability_fit < 0.5
