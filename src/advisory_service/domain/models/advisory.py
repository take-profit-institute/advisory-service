"""최종 추천 결과 도메인 모델."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


@dataclass(frozen=True)
class AdvisoryRecommendation:
    user_id: str
    stock_code: str
    name_kr: str
    rrf_score: float
    fit_score: float
    narrative: str
    improvement_tags: list[str] = field(default_factory=list)
    price_snapshot: float | None = None
    snapshot_at: datetime | None = None


class ValidationStatus(str, Enum):
    PASSED = "passed"
    RETRIED = "retried"
    FAILED = "failed"


@dataclass(frozen=True)
class AdvisoryResult:
    """
    그래프 실행 1회의 최종 결과.

    validation_status는 개별 AdvisoryRecommendation이 아니라 실행 단위에
    귀속되는 값이다. 검증은 추천 객체들이 이미 생성된 뒤에 수행되므로,
    개별 객체에 이 상태를 기본값("passed")으로 미리 박아두면 재시도
    한도를 넘겨 실패해도 값이 갱신되지 않는 문제가 있었다.
    """

    recommendations: list[AdvisoryRecommendation]
    validation_status: ValidationStatus
    validation_errors: list[str] = field(default_factory=list)
    retry_count: int = 0
