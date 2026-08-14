"""
스코어링: 순수함수로 설계 (부작용 없음, 입력 -> 출력만 존재)

domain 계층이므로 DB, LLM, gRPC 등 어떤 외부 의존성도 import하지 않는다.
이 파일 하나만으로 단위테스트가 완결된다 (tests/unit/domain/test_fit_score.py).

지표 선택 근거 (Stock Service 실제 가용 데이터 기준):
- PER, PBR, ROE: stock_financials에 존재 (단, 정기 최신화는 안 되고 있어
  financials_fiscal_period로 staleness를 함께 응답에 노출하는 걸 권장)
- volatility_90d: Stock Service가 제공하지 않아 candles(일봉) 데이터로
  infrastructure 계층이 직접 계산해 domain에 StockMetrics로 전달
- dividend_yield, debt_ratio: Stock Service에 필드 자체가 없어서 제외.
  DART 연동 등 추후 지원되면 스코어링 축으로 추가 검토 (팀 협의 항목)
"""

from advisory_service.domain.models.candidate import StockMetrics

WEIGHTS = {
    "valuation_fit": 0.35,
    "profitability_fit": 0.30,
    "volatility_fit": 0.35,
}

_RISK_BANDS = {
    "conservative": (0, 15),
    "moderate": (10, 30),
    "aggressive": (20, 100),
}

_IMPROVEMENT_TOPIC_MAP = {
    "valuation_fit": "valuation_basics",
    "profitability_fit": "profitability_analysis",
    "volatility_fit": "volatility_risk",
}


def score_valuation_fit(metrics: StockMetrics) -> float:
    """PER/PBR 기반 밸류에이션 점수. 업종 평균 비교는 1차 고도화 대상(현재는 절대값 기준)."""
    if metrics.per <= 0 or metrics.pbr <= 0:
        return 0.3  # 적자 기업 등 -> 낮은 점수, 0은 아님(정보 부족일 수도 있으므로)
    per_score = max(0.0, min(1.0, 1.0 - (metrics.per - 10) / 30))
    pbr_score = max(0.0, min(1.0, 1.0 - (metrics.pbr - 1) / 3))
    return round((per_score + pbr_score) / 2, 5)


def score_profitability_fit(metrics: StockMetrics) -> float:
    """ROE 기반 수익성 점수. ROE 15% 이상이면 만점에 가깝게 선형 스케일링."""
    return max(0.0, min(1.0, metrics.roe / 15.0))


def score_volatility_fit(metrics: StockMetrics, risk_tolerance: str) -> float:
    """리스크 성향 대비 변동성 적합도"""
    low, high = _RISK_BANDS[risk_tolerance]
    v = metrics.volatility_90d
    if low <= v <= high:
        return 1.0
    distance = min(abs(v - low), abs(v - high))
    return max(0.0, 1.0 - distance / 20.0)


def compute_fit_score(
    metrics: StockMetrics, risk_tolerance: str
) -> tuple[float, dict[str, float], list[str]]:
    """
    최종 적합도 점수 + breakdown + improvement_tags 반환.
    가중치는 하드코딩 시작값 -> 이후 실측 데이터로 튜닝 대상 (팀 협의 후 자동화 검토).
    """
    breakdown = {
        "valuation_fit": score_valuation_fit(metrics),
        "profitability_fit": score_profitability_fit(metrics),
        "volatility_fit": score_volatility_fit(metrics, risk_tolerance),
    }

    fit_score = sum(breakdown[k] * WEIGHTS[k] for k in WEIGHTS)

    # 개선포인트: 0.5 미만인 항목을 태그 후보로 추출 (narrative 근거 + 선택적 응답 노출용)
    improvement_tags = [
        _IMPROVEMENT_TOPIC_MAP[k] for k, v in breakdown.items() if v < 0.5
    ]

    return round(fit_score, 5), breakdown, improvement_tags
