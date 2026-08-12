"""검색·스코어링 과정에서 다뤄지는 후보 종목 도메인 모델."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RetrievedCandidate:
    """하이브리드 검색(벡터+키워드) 결과 한 건."""

    stock_id: int
    ticker: str
    name_kr: str
    narrative_content: str
    vector_rank: int | None
    keyword_rank: int | None
    rrf_score: float


@dataclass(frozen=True)
class StockMetrics:
    """스코어링 계산에 필요한 종목 정량 지표."""

    per: float
    pbr: float
    roe: float
    volatility_90d: float


@dataclass(frozen=True)
class ScoredCandidate:
    """스코어링 완료 후보. score_breakdown은 narrative 생성 근거로 재사용된다."""

    stock_id: int
    ticker: str
    name_kr: str
    rrf_score: float
    fit_score: float
    score_breakdown: dict[str, float] = field(default_factory=dict)
    improvement_tags: list[str] = field(default_factory=list)
