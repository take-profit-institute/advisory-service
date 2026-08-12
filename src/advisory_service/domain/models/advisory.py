"""최종 추천 결과 도메인 모델."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class AdvisoryRecommendation:
    user_id: int
    stock_id: int
    ticker: str
    name_kr: str
    rrf_score: float
    fit_score: float
    narrative: str
    improvement_tags: list[str] = field(default_factory=list)
    price_snapshot: float | None = None
    snapshot_at: datetime | None = None
    validation_status: str = "passed"  # 'passed' | 'retried' | 'failed'