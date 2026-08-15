"""서비스 진입점."""

import asyncio
import signal
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

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
    application = await build_application(settings)
    servicer = AdvisoryServicer(application.use_case)
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_number, shutdown_event.set)
        except NotImplementedError:  # pragma: no cover - Windows fallback
            pass

    sync_task = None
    if settings.stock_sync_enabled:
        sync_task = asyncio.create_task(
            _run_stock_sync_loop(
                application.stock_catalog_synchronizer,
                sync_time=settings.stock_sync_time,
                timezone=ZoneInfo(settings.stock_sync_timezone),
                run_on_startup=settings.stock_sync_run_on_startup,
            )
        )
    try:
        await serve(
            servicer,
            port=settings.grpc_port,
            shutdown_event=shutdown_event,
        )
    finally:
        if sync_task is not None:
            sync_task.cancel()
            await asyncio.gather(sync_task, return_exceptions=True)
        await application.close()


def _next_sync_at(now: datetime, sync_time: time, timezone: ZoneInfo) -> datetime:
    local_now = now.astimezone(timezone)
    next_run = datetime.combine(local_now.date(), sync_time, tzinfo=timezone)
    if next_run < local_now:
        next_run += timedelta(days=1)
    return next_run


async def _sync_stock_catalog(synchronizer) -> None:
    log = structlog.get_logger()
    try:
        synced = await synchronizer.sync_all()
        log.info("stock_catalog_synchronized", synced_count=synced)
    except Exception:
        log.exception("stock_catalog_sync_failed")


async def _run_stock_sync_loop(
    synchronizer,
    *,
    sync_time: time,
    timezone: ZoneInfo,
    run_on_startup: bool = False,
) -> None:
    log = structlog.get_logger()
    if run_on_startup:
        await _sync_stock_catalog(synchronizer)

    while True:
        now = datetime.now(UTC)
        next_run = _next_sync_at(now, sync_time, timezone)
        delay_seconds = max((next_run - now).total_seconds(), 0)
        log.info(
            "stock_catalog_sync_scheduled",
            scheduled_at=next_run.isoformat(),
            delay_seconds=round(delay_seconds),
        )
        await asyncio.sleep(delay_seconds)
        await _sync_stock_catalog(synchronizer)


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
