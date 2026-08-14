"""
Composition Root — application이 정의한 포트(인터페이스)에
infrastructure의 실제 구현체를 주입(DI)하는 유일한 지점.

domain/application 계층은 이 파일의 존재를 모른다. 오직 이 파일만
infrastructure 구현체의 구체 타입을 알고 조립한다.
"""

import grpc
import structlog
from openai import AsyncOpenAI

from advisory_service.application.advisory.graph import build_advisory_graph
from advisory_service.application.advisory.use_case import GenerateAdvisoryUseCase
from advisory_service.config import Settings
from advisory_service.infrastructure.llm.openai_narrative_generator import (
    OpenAINarrativeGenerator,
)
from advisory_service.infrastructure.persistence.repositories.postgres_advisory_repository import (
    PostgresAdvisoryRepository,
)
from advisory_service.infrastructure.persistence.repositories.postgres_stock_cache import (
    PostgresStockCache,
)
from advisory_service.infrastructure.persistence.session import create_pool
from advisory_service.infrastructure.retrieval.hybrid_stock_search import (
    HybridStockSearch,
)
from advisory_service.infrastructure.stock_catalog.grpc_stock_catalog import (
    GrpcStockCatalogSynchronizer,
    StockServiceGrpcClient,
)
from advisory_service.infrastructure.stock_catalog.grpc_stock_metrics_reader import (
    GrpcBackedStockMetricsReader,
)

log = structlog.get_logger()


async def build_application(settings: Settings):
    pool = await create_pool(settings)
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    stock_channel = grpc.aio.insecure_channel(settings.stock_service_grpc_target)

    stock_cache = PostgresStockCache(pool)

    async def embed_fn(text: str) -> list[float]:
        response = await openai_client.embeddings.create(
            model="text-embedding-3-small", input=text
        )
        return response.data[0].embedding

    stock_client = StockServiceGrpcClient(
        stock_channel,
        timeout_seconds=settings.stock_grpc_timeout_seconds,
        requests_per_second=settings.stock_sync_requests_per_second,
    )
    stock_catalog_synchronizer = GrpcStockCatalogSynchronizer(
        grpc_client=stock_client,
        cache=stock_cache,
        embed_fn=embed_fn,
        page_size=settings.stock_sync_page_size,
        concurrency=settings.stock_sync_concurrency,
    )
    stock_metrics_reader = GrpcBackedStockMetricsReader(
        stock_channel,
        stock_cache,
        timeout_seconds=settings.stock_grpc_timeout_seconds,
        requests_per_second=settings.stock_sync_requests_per_second,
        concurrency=settings.stock_sync_concurrency,
    )

    stock_search = HybridStockSearch(pool, embed_fn)
    narrative_generator = OpenAINarrativeGenerator(openai_client)
    advisory_repository = PostgresAdvisoryRepository(pool)

    graph = build_advisory_graph(
        stock_search=stock_search,
        stock_metrics_reader=stock_metrics_reader,
        narrative_generator=narrative_generator,
    )

    use_case = GenerateAdvisoryUseCase(graph=graph, advisory_repository=advisory_repository)

    log.info("application_bootstrapped")
    return use_case, stock_catalog_synchronizer
