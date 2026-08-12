"""domain.ports.advisory_repository.AdvisoryRepository의 PostgreSQL 구현체."""

import asyncpg

from advisory_service.domain.models.advisory import AdvisoryRecommendation


class PostgresAdvisoryRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def save(self, recommendation: AdvisoryRecommendation) -> None:
        await self.save_many([recommendation])

    async def save_many(self, recommendations: list[AdvisoryRecommendation]) -> None:
        if not recommendations:
            return
        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO recommendations (
                    user_id, stock_id, rrf_score, fit_score, narrative,
                    improvement_tags, price_snapshot, snapshot_at, validation_status
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                [
                    (
                        r.user_id, r.stock_id, r.rrf_score, r.fit_score, r.narrative,
                        r.improvement_tags, r.price_snapshot, r.snapshot_at,
                        r.validation_status,                        
                    )
                    for r in recommendations
                ],
            )