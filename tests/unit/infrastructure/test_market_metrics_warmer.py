import grpc

from advisory_service.infrastructure.stock_catalog.market_metrics_warmer import (
    MarketMetricsWarmer,
)


class FakeCache:
    """워밍이 채운 종목은 다음 pass의 stale 목록에서 빠지는 실제 동작을 흉내낸다."""

    def __init__(self, stale_codes):
        self.stale_codes = list(stale_codes)
        self.stale_after_seconds = None
        self.updates = []
        self.stale_queries = 0

    async def list_stale_market_metric_codes(self, stale_after_seconds):
        self.stale_after_seconds = stale_after_seconds
        self.stale_queries += 1
        warmed = {code for code, _, _ in self.updates}
        return [code for code in self.stale_codes if code not in warmed]

    async def update_market_metrics(self, stock_code, volatility_90d, latest_close):
        self.updates.append((stock_code, volatility_90d, latest_close))


class FakeFetcher:
    def __init__(self, results):
        self.results = results
        self.requested = []

    async def fetch(self, stock_code):
        self.requested.append(stock_code)
        result = self.results[stock_code]
        if isinstance(result, list):
            result = result.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeRpcError(grpc.RpcError):
    def code(self):
        return grpc.StatusCode.DEADLINE_EXCEEDED


async def test_warms_every_stale_code_into_cache():
    cache = FakeCache(["005930", "000660"])
    fetcher = FakeFetcher({"005930": (18.5, 70_000.0), "000660": (25.0, 120_000.0)})

    result = await MarketMetricsWarmer(fetcher, cache).warm_all()

    assert cache.updates == [
        ("005930", 18.5, 70_000.0),
        ("000660", 25.0, 120_000.0),
    ]
    assert (result.targeted, result.refreshed) == (2, 2)
    assert (result.unavailable, result.failed) == (0, 0)
    # 실패가 없으면 2회차를 돌지 않는다.
    assert result.passes == 1


async def test_uses_configured_stale_threshold():
    cache = FakeCache([])

    await MarketMetricsWarmer(
        FakeFetcher({}), cache, stale_after_seconds=3_600
    ).warm_all()

    assert cache.stale_after_seconds == 3_600


async def test_single_failure_does_not_abort_remaining_codes():
    """종목 하나가 실패해도 나머지 워밍은 계속돼야 한다 — 배치 전체를 잃지 않는다."""
    cache = FakeCache(["A", "B", "C"])
    fetcher = FakeFetcher(
        {"A": FakeRpcError(), "B": (30.0, 5_000.0), "C": RuntimeError("boom")}
    )

    result = await MarketMetricsWarmer(fetcher, cache, passes=1).warm_all()

    assert fetcher.requested == ["A", "B", "C"]
    assert cache.updates == [("B", 30.0, 5_000.0)]
    assert (result.targeted, result.refreshed, result.failed) == (3, 1, 2)


async def test_counts_stocks_without_candles_as_unavailable():
    cache = FakeCache(["NEW"])
    fetcher = FakeFetcher({"NEW": None})

    result = await MarketMetricsWarmer(fetcher, cache).warm_all()

    assert cache.updates == []
    assert (result.refreshed, result.unavailable, result.failed) == (0, 1, 0)


async def test_processes_codes_in_batches():
    cache = FakeCache([str(index) for index in range(5)])
    fetcher = FakeFetcher({str(index): (10.0, 1_000.0) for index in range(5)})

    result = await MarketMetricsWarmer(fetcher, cache, batch_size=2).warm_all()

    assert result.refreshed == 5
    assert len(cache.updates) == 5


async def test_second_pass_recovers_codes_that_timed_out_first():
    """
    GetCandles는 캔들이 없는 종목에 백필을 먼저 수행한다. 1회차가 timeout으로
    실패해도 서버에는 데이터가 남아 2회차는 성공한다 — 그 회수를 검증한다.
    """
    cache = FakeCache(["A", "B"])
    fetcher = FakeFetcher(
        {
            "A": [FakeRpcError(), (20.0, 1_000.0)],
            "B": [(30.0, 2_000.0)],
        }
    )

    result = await MarketMetricsWarmer(fetcher, cache, passes=2).warm_all()

    # 1회차: A 실패 + B 성공, 2회차: A만 재시도해 성공
    assert fetcher.requested == ["A", "B", "A"]
    assert sorted(code for code, _, _ in cache.updates) == ["A", "B"]
    assert (result.targeted, result.refreshed, result.failed) == (2, 2, 0)
    assert result.passes == 2


async def test_stops_when_nothing_is_stale():
    cache = FakeCache([])

    result = await MarketMetricsWarmer(FakeFetcher({}), cache, passes=3).warm_all()

    assert (result.targeted, result.refreshed, result.passes) == (0, 0, 0)
    assert cache.stale_queries == 1
