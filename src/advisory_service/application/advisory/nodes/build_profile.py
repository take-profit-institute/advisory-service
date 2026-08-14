"""profile 노드: 사용자 프로필을 정규화하고 검색 질의를 준비한다."""

from dataclasses import replace

from advisory_service.application.advisory.state import AdvisoryState
from advisory_service.domain.models.investor_profile import (
    InvestmentHorizon,
    RiskTolerance,
)

_RISK_QUERY = {
    RiskTolerance.CONSERVATIVE: "변동성이 낮고 안정적인",
    RiskTolerance.MODERATE: "수익성과 안정성이 균형 잡힌",
    RiskTolerance.AGGRESSIVE: "성장 가능성이 높은 적극적인",
}

_HORIZON_QUERY = {
    InvestmentHorizon.SHORT: "단기 투자",
    InvestmentHorizon.MID: "중기 투자",
    InvestmentHorizon.LONG: "장기 투자",
}


async def build_profile(state: AdvisoryState) -> AdvisoryState:
    profile = state["investor_profile"]
    query = profile.free_text_query.strip()
    if query:
        return {**state, "investor_profile": replace(profile, free_text_query=query)}

    parts = [_RISK_QUERY[profile.risk_tolerance]]
    if profile.investment_horizon is not None:
        parts.append(_HORIZON_QUERY[profile.investment_horizon])
    if profile.preferred_sectors:
        parts.append(" ".join(profile.preferred_sectors))
    parts.append("종목")

    return {
        **state,
        "investor_profile": replace(profile, free_text_query=" ".join(parts)),
    }
