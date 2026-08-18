"""stocks_cache의 변동성/종가를 배치로 미리 채워두는 워머."""

import asyncio
from dataclasses import dataclass

import grpc
import structlog

from advisory_service.infrastructure.persistence.repositories.postgres_stock_cache import (
    PostgresStockCache,
)
from advisory_service.infrastructure.stock_catalog.grpc_market_metrics import (
    GrpcMarketMetricsFetcher,
)

log = structlog.get_logger()


@dataclass(frozen=True)
class WarmResult:
    targeted: int
    refreshed: int
    unavailable: int
    failed: int
    passes: int


class MarketMetricsWarmer:
    """
    변동성은 요청 시점에 GetCandles로 보충하기엔 너무 느리다.

    후보 20종목이 전부 cache miss면 종목당 1회씩 gRPC를 타는데, rate limit까지
    걸려 있어 요청 deadline(5초)을 넘긴다. 실제로 그 상태에서 추천 요청이
    DEPENDENCY_UNAVAILABLE로 실패했다. 그래서 카탈로그 동기화와 같은 배치
    시점에 미리 계산해 캐시에 적재하고, 요청 경로는 DB만 읽게 한다.

    종목 단위 실패는 배치를 중단시키지 않는다 — 일부 종목의 일봉이 없다고
    나머지 수천 종목의 워밍을 포기할 이유가 없다.

    여러 pass를 도는 이유: Stock Service의 GetCandles는 일봉이 없는 종목에
    대해 외부 시세 백필을 먼저 수행한다. 그래서 첫 호출은 timeout으로 실패해도
    서버에는 캔들이 적재되고, 다음 pass의 같은 종목 호출은 로컬 조회라 즉시
    응답한다. 1회차는 백필 트리거, 2회차는 회수인 셈이다.
    """

    def __init__(
        self,
        fetcher: GrpcMarketMetricsFetcher,
        cache: PostgresStockCache,
        *,
        stale_after_seconds: int = 43_200,
        batch_size: int = 100,
        passes: int = 2,
    ):
        self._fetcher = fetcher
        self._cache = cache
        self._stale_after_seconds = max(stale_after_seconds, 0)
        self._batch_size = max(batch_size, 1)
        self._passes = max(passes, 1)

    async def warm_all(self) -> WarmResult:
        targeted = 0
        refreshed_total = 0
        unavailable = failed = 0
        completed_passes = 0

        for pass_number in range(1, self._passes + 1):
            codes = await self._cache.list_stale_market_metric_codes(
                self._stale_after_seconds
            )
            if pass_number == 1:
                targeted = len(codes)
            if not codes:
                break

            completed_passes = pass_number
            # refreshed는 회차별로 누적한다 — 이미 채운 종목은 다음 회차의
            # stale 목록에 다시 나오지 않으므로 중복 계산되지 않는다.
            # 반면 unavailable/failed는 재시도 대상이라 마지막 회차 값만 남긴다.
            refreshed = unavailable = failed = 0
            for start in range(0, len(codes), self._batch_size):
                batch = codes[start : start + self._batch_size]
                outcomes = await asyncio.gather(
                    *(self._warm_one(code) for code in batch)
                )
                refreshed += outcomes.count("refreshed")
                unavailable += outcomes.count("unavailable")
                failed += outcomes.count("failed")

            refreshed_total += refreshed
            log.info(
                "market_metrics_warm_pass_completed",
                pass_number=pass_number,
                targeted=len(codes),
                refreshed=refreshed,
                unavailable=unavailable,
                failed=failed,
            )
            if failed == 0:
                break

        return WarmResult(
            targeted=targeted,
            refreshed=refreshed_total,
            unavailable=unavailable,
            failed=failed,
            passes=completed_passes,
        )

    async def _warm_one(self, stock_code: str) -> str:
        try:
            market_metrics = await self._fetcher.fetch(stock_code)
        except grpc.RpcError as error:
            log.warning(
                "market_metrics_warm_rpc_failed",
                stock_code=stock_code,
                status=error.code().name if error.code() else None,
            )
            return "failed"
        except Exception:
            log.exception("market_metrics_warm_failed", stock_code=stock_code)
            return "failed"

        if market_metrics is None:
            # 일봉이 없거나 부족해 변동성을 계산할 수 없는 종목(신규 상장 등).
            return "unavailable"

        volatility, latest_close = market_metrics
        await self._cache.update_market_metrics(stock_code, volatility, latest_close)
        return "refreshed"
