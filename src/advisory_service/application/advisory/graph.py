"""
LangGraph 오케스트레이션 조립.

노드 함수는 application/advisory/nodes/ 에 있고, 이 파일은 그것들을
State 흐름(build_profile -> retrieve -> score -> narrative -> validate)으로
엮기만 한다. 실제 포트 구현체(DB 커넥션, LLM 클라이언트 등)는
bootstrap.py에서 주입된다 (Composition Root).

주의: 노드를 `lambda s: some_async_fn(s, dep)` 형태로 감싸면 LangGraph가
`inspect.iscoroutinefunction`으로 비동기 여부를 판단하지 못해 coroutine을
await하지 않고 그대로 반환값 취급해버린다. functools.partial을 쓰면
원본 async 함수의 시그니처가 유지되어 이 문제가 발생하지 않는다.
"""

from functools import partial

from langgraph.graph import END, StateGraph

from advisory_service.application.advisory.nodes.build_profile import build_profile
from advisory_service.application.advisory.nodes.generate_narrative import (
    generate_narrative,
)
from advisory_service.application.advisory.nodes.retrieve_candidates import (
    retrieve_candidates,
)
from advisory_service.application.advisory.nodes.score_candidates import (
    score_candidates,
)
from advisory_service.application.advisory.nodes.validate_result import (
    route_after_validation,
    validate_result,
)
from advisory_service.application.advisory.state import AdvisoryState
from advisory_service.application.ports.narrative_generator import (
    NarrativeGeneratorPort,
)
from advisory_service.application.ports.stock_metrics_reader import StockMetricsReader
from advisory_service.application.ports.stock_search import StockSearchPort


def build_advisory_graph(
    stock_search: StockSearchPort,
    stock_metrics_reader: StockMetricsReader,
    narrative_generator: NarrativeGeneratorPort,
):
    graph = StateGraph(AdvisoryState)

    graph.add_node("build_profile", build_profile)
    graph.add_node("retrieve_candidates", partial(retrieve_candidates, stock_search=stock_search))
    graph.add_node(
        "score_candidates",
        partial(score_candidates, stock_metrics_reader=stock_metrics_reader),
    )
    graph.add_node(
        "generate_narrative",
        partial(generate_narrative, narrative_generator=narrative_generator),
    )
    graph.add_node("validate_result", validate_result)

    graph.set_entry_point("build_profile")
    graph.add_edge("build_profile", "retrieve_candidates")
    graph.add_edge("retrieve_candidates", "score_candidates")
    graph.add_edge("score_candidates", "generate_narrative")
    graph.add_edge("generate_narrative", "validate_result")

    graph.add_conditional_edges(
        "validate_result",
        route_after_validation,
        {"retry": "generate_narrative", "end": END},
    )

    return graph.compile()
