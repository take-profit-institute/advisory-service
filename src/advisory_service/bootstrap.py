"""
Composition Root — application이 정의한 포트(인터페이스)에
infrastructure의 실제 구현체를 주입(DI)하는 유일한 지점.

domain/application 계층은 이 파일의 존재를 모른다. 오직 이 파일만
infrastructure 구현체의 구체 타입을 알고 조립한다.
"""

import structlog
from openai import AsyncOpenAI

from advisory_service.application.advisory.graph import build_advisory_graph
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
from advisory_service.infrastructure.retrieval.hybrid_stock_search import HybridStockSearch
from advisory_service.infrastructure.stock_catalog.grpc_stock_catalog import (
    GrpcStockCatalogSynchronizer,
)

log = structlog.get_logger()


async def build_application(settings: Settings):
    pool = await create_pool(settings)
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    stock_cache = PostgresStockCache(pool)
    # TODO: 실제 Stock Service gRPC 클라이언트 연결 (조사 결과 확정 후)
    stock_catalog_synchronizer = GrpcStockCatalogSynchronizer(grpc_client=None, cache=stock_cache)

    async def embed_fn(text: str) -> list[float]:
        response = await openai_client.embeddings.create(
            model="text-embedding-3-small", input=text
        )
        return response.data[0].embedding

    stock_search = HybridStockSearch(pool, embed_fn)
    narrative_generator = OpenAINarrativeGenerator(openai_client)
    advisory_repository = PostgresAdvisoryRepository(pool)

    graph = build_advisory_graph(
        stock_search=stock_search,
        stock_metrics_reader=stock_cache,  # StockMetricsReader 구현: 로컬 캐시 조회
        narrative_generator=narrative_generator,
    )

    log.info("application_bootstrapped")
    return graph, advisory_repository, stock_catalog_synchronizer
