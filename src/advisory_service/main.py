"""서비스 진입점."""

import asyncio

import structlog

from advisory_service.bootstrap import build_application
from advisory_service.config import Settings
from advisory_service.transport.grpc.server import serve
from advisory_service.transport.grpc.servicer import AdvisoryServicer


def _configure_logging() -> None:
    """
    CONVENTIONS.md 12장: 로그에는 traceId, userId 같은 추적 키를 구조화해 기록한다.
    JSON 렌더러로 구조화된 로그를 남겨, 추후 traceId/userId 등을
    bind_contextvars로 요청 단위로 주입할 수 있게 한다.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )


async def _amain() -> None:
    _configure_logging()
    settings = Settings()  # type: ignore[call-arg]  # values are loaded from environment
    use_case, stock_catalog_synchronizer = await build_application(settings)
    servicer = AdvisoryServicer(use_case)
    sync_task = None
    if settings.stock_sync_enabled:
        sync_task = asyncio.create_task(
            _run_stock_sync_loop(
                stock_catalog_synchronizer,
                settings.stock_sync_interval_seconds,
            )
        )
    try:
        await serve(servicer, port=settings.grpc_port)
    finally:
        if sync_task is not None:
            sync_task.cancel()
            await asyncio.gather(sync_task, return_exceptions=True)


async def _run_stock_sync_loop(synchronizer, interval_seconds: int) -> None:
    log = structlog.get_logger()
    while True:
        try:
            synced = await synchronizer.sync_all()
            log.info("stock_catalog_synchronized", synced_count=synced)
        except Exception:
            log.exception("stock_catalog_sync_failed")
        await asyncio.sleep(max(interval_seconds, 60))


def main() -> None:
    """
    pyproject.toml의 [project.scripts] 엔트리포인트가 참조하는 동기 함수.
    `advisory-service` 명령어 및 `python -m advisory_service.main` 양쪽에서
    동일하게 동작하도록, 실제 로직은 _amain()에 두고 asyncio.run()으로만 감싼다.
    (async 함수를 엔트리포인트에 직접 연결하면 coroutine이 await되지 않고
    아무 동작 없이 끝나는 버그가 있었음 — 반드시 sync wrapper를 거쳐야 한다.)
    """
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
