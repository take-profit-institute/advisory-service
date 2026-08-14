from advisory_service.infrastructure.stock_catalog.grpc_stock_catalog import (
    GrpcStockCatalogSynchronizer,
)
from advisory_service.transport.grpc.generated.candle.stock.v1 import stock_pb2


class FakeStockClient:
    async def search_stocks(self, page, size):
        assert page == 0
        assert size == 100
        return stock_pb2.SearchStocksResponse(
            stocks=[
                stock_pb2.Stock(
                    code="005930",
                    name="삼성전자",
                    market=stock_pb2.KOSPI,
                    sector="전기전자",
                )
            ],
            total_pages=1,
        )

    async def get_stock(self, stock_code):
        return stock_pb2.GetStockResponse(
            stock=stock_pb2.StockDetail(
                stock=stock_pb2.Stock(
                    code=stock_code,
                    name="삼성전자",
                    market=stock_pb2.KOSPI,
                    sector="전기전자",
                ),
                financials=stock_pb2.StockFinancials(
                    per="10.2", pbr="1.1", roe="12.5", fiscal_period="2026Q1"
                ),
                description="반도체 및 전자제품 기업",
            )
        )


class FakeCache:
    def __init__(self):
        self.stocks = []
        self.narratives = []

    async def upsert(self, stock, financials):
        self.stocks.append((stock, financials))

    async def upsert_narrative(self, stock_code, content, embedding):
        self.narratives.append((stock_code, content, embedding))


async def test_sync_uses_existing_stock_contract_and_stock_code():
    cache = FakeCache()

    async def embed_fn(text):
        return [0.1, 0.2]

    synchronizer = GrpcStockCatalogSynchronizer(
        grpc_client=FakeStockClient(),
        cache=cache,
        embed_fn=embed_fn,
    )

    assert await synchronizer.sync_all() == 1
    assert cache.stocks[0][0]["stock_code"] == "005930"
    assert cache.stocks[0][1]["per"] == "10.2"
    assert cache.narratives == [("005930", "반도체 및 전자제품 기업", [0.1, 0.2])]
