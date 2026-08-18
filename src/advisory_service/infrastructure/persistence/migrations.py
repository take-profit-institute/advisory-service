"""
기동 시 스키마 적용.

Java 서비스는 Flyway가 하는 일이지만 이 서비스는 마이그레이션 도구를 두지 않는다.
대신 schema.sql 전체를 매 기동마다 재적용한다 — 그래서 schema.sql의 모든 DDL은
멱등(IF NOT EXISTS)이어야 한다.

전제: DSN의 role이 CREATE EXTENSION을 실행할 수 있어야 한다(pgvector는 trusted
extension이 아니라 superuser 필요). 로컬 compose와 lite 클러스터 모두 advisory
전용 postgres 인스턴스의 superuser로 접속하므로 충족된다. 공용 인스턴스에 얹는
구성으로 바뀌면 extension만 사전 생성해두고 db_auto_migrate를 꺼야 한다.
"""

from pathlib import Path

import asyncpg
import structlog

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

log = structlog.get_logger()


async def apply_schema(pool: asyncpg.Pool) -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    # PostgreSQL은 DDL도 트랜잭션이라, 중간에 실패하면 부분 적용 없이 전부 롤백된다.
    async with pool.acquire() as connection, connection.transaction():
        await connection.execute(sql)
    log.info("db_schema_applied", schema_path=str(SCHEMA_PATH))
