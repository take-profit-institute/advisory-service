"""
PostgresAdvisoryRepository 통합 테스트 (스텁).

실제 PostgreSQL(로컬 Docker Compose)에 연결해 저장/조회를 검증한다.
CI에서는 docker-compose 기반 테스트 DB가 필요 — CI 파이프라인 구성 후 활성화.
"""

import pytest

pytestmark = pytest.mark.skip(reason="로컬 PostgreSQL 연결 필요 — Docker Compose 환경에서 활성화 예정")


async def test_save_many_persists_recommendations():
    ...
