"""사용자 투자성향 도메인 모델. 외부 프레임워크/DB/LLM에 의존하지 않는다."""

from dataclasses import dataclass, field
from enum import Enum


class RiskTolerance(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class InvestmentHorizon(str, Enum):
    SHORT = "short"
    MID = "mid"
    LONG = "long"


@dataclass(frozen=True)
class InvestorProfile:
    user_id: int
    risk_tolerance: RiskTolerance
    investment_horizon: InvestmentHorizon | None = None
    preferred_sectors: list[str] = field(default_factory=list)
    free_text_query: str = ""
