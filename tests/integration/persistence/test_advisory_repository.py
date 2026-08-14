from datetime import UTC, datetime

import asyncpg
import pytest

from advisory_service.domain.models.advisory import AdvisoryRecommendation
from advisory_service.domain.models.investor_profile import (
    InvestmentHorizon,
    InvestorProfile,
    RiskTolerance,
)
from advisory_service.infrastructure.persistence.repositories.postgres_advisory_repository import (
    PostgresAdvisoryRepository,
)

pytestmark = pytest.mark.integration

USER_ID = "11111111-1111-1111-1111-111111111111"


def profile() -> InvestorProfile:
    return InvestorProfile(
        user_id=USER_ID,
        risk_tolerance=RiskTolerance.MODERATE,
        investment_horizon=InvestmentHorizon.LONG,
        preferred_sectors=["반도체"],
        free_text_query="안정적인 반도체 종목",
    )


def recommendation(stock_code: str = "005930") -> AdvisoryRecommendation:
    return AdvisoryRecommendation(
        user_id=USER_ID,
        stock_code=stock_code,
        name_kr="삼성전자",
        rrf_score=0.03125,
        fit_score=0.82,
        narrative="실제 PostgreSQL 저장을 검증하기 위한 충분히 긴 추천 사유입니다.",
        improvement_tags=["volatility_risk"],
        price_snapshot=81_000,
        snapshot_at=datetime.now(UTC),
    )


async def seed_stock(pool: asyncpg.Pool, stock_code: str = "005930") -> None:
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO stocks_cache (stock_code, name_kr)
            VALUES ($1, '삼성전자')
            """,
            stock_code,
        )


async def test_save_many_upserts_profile_and_persists_recommendation(postgres_pool):
    await seed_stock(postgres_pool)
    repository = PostgresAdvisoryRepository(postgres_pool)

    await repository.save_many([recommendation()], profile())

    async with postgres_pool.acquire() as connection:
        saved_profile = await connection.fetchrow(
            "SELECT * FROM user_profiles WHERE user_id = $1", USER_ID
        )
        saved_recommendation = await connection.fetchrow(
            "SELECT * FROM recommendations WHERE user_id = $1", USER_ID
        )

    assert saved_profile["risk_tolerance"] == "moderate"
    assert saved_profile["preferred_sectors"] == ["반도체"]
    assert saved_recommendation["stock_code"] == "005930"
    assert float(saved_recommendation["fit_score"]) == 0.82
    assert saved_recommendation["validation_status"] == "passed"


async def test_save_many_rolls_back_profile_and_rows_when_stock_fk_fails(postgres_pool):
    repository = PostgresAdvisoryRepository(postgres_pool)

    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await repository.save_many([recommendation("999999")], profile())

    async with postgres_pool.acquire() as connection:
        profile_count = await connection.fetchval(
            "SELECT count(*) FROM user_profiles WHERE user_id = $1", USER_ID
        )
        recommendation_count = await connection.fetchval(
            "SELECT count(*) FROM recommendations WHERE user_id = $1", USER_ID
        )

    assert profile_count == 0
    assert recommendation_count == 0
