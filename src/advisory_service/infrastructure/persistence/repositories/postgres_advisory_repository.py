"""
application.ports.advisory_repository.AdvisoryRepository의 PostgreSQL 구현체.

이 repository는 GenerateAdvisoryUseCase가 검증(validate_result)을 통과한
추천 결과만 저장할 때 호출된다는 전제를 갖는다 — 즉 저장되는 모든 행은
validation_status='passed'다. 검증 실패/재시도초과 결과는 애초에
save_many()가 호출되지 않으므로 별도 상태값을 인자로 받지 않는다.

user_profiles upsert를 recommendations insert와 같은 트랜잭션에서 처리하는
이유는 advisory_repository.py 포트 docstring 참고 (FK 위반 방지).
"""

from collections.abc import Sequence
from decimal import Decimal

import asyncpg

from advisory_service.domain.models.advisory import AdvisoryRecommendation
from advisory_service.domain.models.investor_profile import InvestorProfile


class PostgresAdvisoryRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def save_many(
        self,
        recommendations: Sequence[AdvisoryRecommendation],
        investor_profile: InvestorProfile,
    ) -> None:
        if not recommendations:
            return

        async with self._pool.acquire() as conn, conn.transaction():
            await self._upsert_investor_profile(conn, investor_profile)
            await conn.executemany(
                """
                INSERT INTO recommendations (
                    user_id, stock_code, rrf_score, fit_score, narrative,
                    improvement_tags, price_snapshot, snapshot_at, validation_status
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'passed')
                """,
                [
                    (
                        r.user_id,
                        r.stock_code,
                        Decimal(str(r.rrf_score)),
                        Decimal(str(r.fit_score)),
                        r.narrative,
                        r.improvement_tags,
                        Decimal(str(r.price_snapshot)) if r.price_snapshot is not None else None,
                        r.snapshot_at,
                    )
                    for r in recommendations
                ],
            )

    @staticmethod
    async def _upsert_investor_profile(conn: asyncpg.Connection, profile: InvestorProfile) -> None:
        await conn.execute(
            """
            INSERT INTO user_profiles (
                user_id, risk_tolerance, investment_horizon,
                preferred_sectors, free_text_query, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, now())
            ON CONFLICT (user_id) DO UPDATE SET
                risk_tolerance = EXCLUDED.risk_tolerance,
                investment_horizon = EXCLUDED.investment_horizon,
                preferred_sectors = EXCLUDED.preferred_sectors,
                free_text_query = EXCLUDED.free_text_query,
                updated_at = now()
            """,
            profile.user_id,
            profile.risk_tolerance.value,
            profile.investment_horizon.value if profile.investment_horizon else None,
            profile.preferred_sectors,
            profile.free_text_query,
        )
