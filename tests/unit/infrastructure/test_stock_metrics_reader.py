import asyncio
from datetime import UTC, datetime, timedelta

import grpc

from advisory_service.infrastructure.stock_catalog.grpc_stock_metrics_reader import (
    GrpcBackedStockMetricsReader,
)


class FakeCache:
    def __init__(self, values):
        self.values = values
        self.update_count = 0

    async def get_metric_values_many(self, stock_codes):
        return {
            code: dict(self.values[code])
            for code in stock_codes
            if code in self.values
        }

    async def update_market_metrics(self, stock_code, volatility_90d, latest_close):
        self.update_count += 1
        self.values[stock_code].update(
            volatility_90d=volatility_90d,
            volatility_calculated_at=datetime.now(UTC),
            latest_close=latest_close,
        )


def metrics_values(*, volatility=15.0, calculated_at=None):
    return {
        "per": 10,
        "pbr": 1,
        "roe": 12,
        "volatility_90d": volatility,
        "volatility_calculated_at": calculated_at,
        "latest_close": 70_000,
    }


async def build_reader(cache):
    channel = grpc.aio.insecure_channel("localhost:1")
    reader = GrpcBackedStockMetricsReader(channel, cache)
    return reader, channel


async def test_uses_volatility_cached_within_24_hours():
    cache = FakeCache(
        {"005930": metrics_values(calculated_at=datetime.now(UTC) - timedelta(hours=23))}
    )
    reader, channel = await build_reader(cache)

    async def unexpected_fetch(stock_code):
        raise AssertionError("fresh cache must not call GetCandles")

    reader._fetch_market_metrics = unexpected_fetch
    try:
        result = await reader.get_metrics("005930")
    finally:
        await channel.close()

    assert result is not None
    assert result.volatility_90d == 15.0


async def test_refreshes_volatility_older_than_24_hours():
    cache = FakeCache(
        {"005930": metrics_values(calculated_at=datetime.now(UTC) - timedelta(hours=25))}
    )
    reader, channel = await build_reader(cache)

    async def fetch(stock_code):
        return 22.0, 71_000.0

    reader._fetch_market_metrics = fetch
    try:
        result = await reader.get_metrics("005930")
    finally:
        await channel.close()

    assert result is not None
    assert result.volatility_90d == 22.0
    assert cache.update_count == 1


async def test_concurrent_cache_misses_share_one_refresh():
    cache = FakeCache({"005930": metrics_values(volatility=None, calculated_at=None)})
    reader, channel = await build_reader(cache)
    fetch_count = 0

    async def fetch(stock_code):
        nonlocal fetch_count
        fetch_count += 1
        await asyncio.sleep(0.01)
        return 18.0, 72_000.0

    reader._fetch_market_metrics = fetch
    try:
        first, second = await asyncio.gather(
            reader.get_metrics("005930"),
            reader.get_metrics("005930"),
        )
    finally:
        await channel.close()

    assert first == second
    assert fetch_count == 1
    assert cache.update_count == 1
