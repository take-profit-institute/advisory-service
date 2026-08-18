"""
스키마 자동 적용 검증.

apply_schema는 매 기동마다 schema.sql 전체를 재실행하므로, 이미 스키마가 있는
DB에 다시 걸어도 실패하지 않아야 한다(멱등). 이게 깨지면 파드가 재시작
루프에 빠지기 때문에 통합 테스트로 고정한다.
"""

import pytest

from advisory_service.infrastructure.persistence.migrations import apply_schema

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "stocks_cache",
    "stock_narratives",
    "user_profiles",
    "recommendations",
}


async def test_apply_schema_is_idempotent(postgres_pool):
    # postgres_pool 픽스처가 이미 1회 적용한 상태 — 여기서 두 번 더 건다.
    await apply_schema(postgres_pool)
    await apply_schema(postgres_pool)

    rows = await postgres_pool.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    )
    assert EXPECTED_TABLES <= {row["tablename"] for row in rows}


async def test_apply_schema_creates_required_extensions(postgres_pool):
    rows = await postgres_pool.fetch("SELECT extname FROM pg_extension")
    assert {"vector", "pg_trgm"} <= {row["extname"] for row in rows}
