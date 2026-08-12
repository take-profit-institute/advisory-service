"""
AdvisoryServiceServicer 구현체 — gRPC 요청을 받아 application/advisory/graph.py를
실행하고, 결과를 proto 응답 메시지로 매핑한다.

proto/advisory/v1/advisory.proto 계약이 아직 draft 상태라, 아래 import는
scripts/generate_grpc.sh 실행 후 생성되는 transport/grpc/generated/ 모듈을
참조하도록 채워질 예정이다 (계약 확정 후 작업).
"""

# from advisory_service.transport.grpc.generated import advisory_pb2, advisory_pb2_grpc
from advisory_service.application.advisory.state import AdvisoryState
from advisory_service.domain.models.investor_profile import (
    InvestmentHorizon,
    InvestorProfile,
    RiskTolerance,
)


class AdvisoryServicer:
    """proto 확정 후 advisory_pb2_grpc.AdvisoryServiceServicer를 상속하도록 변경."""

    def __init__(self, graph):
        self._graph = graph  # application.advisory.graph.build_advisory_graph() 결과

    async def GetRecommendations(self, request, context):
        profile = InvestorProfile(
            user_id=request.user_id,
            risk_tolerance=RiskTolerance(request.risk_tolerance),
            investment_horizon=InvestmentHorizon(request.investment_horizon)
            if request.investment_horizon
            else None,
            preferred_sectors=list(request.preferred_sectors),
            free_text_query=request.free_text_query,
        )

        initial_state: AdvisoryState = {
            "investor_profile": profile,
            "retrieved_candidates": [],
            "scored_candidates": [],
            "recommendations": [],
            "validation_passed": False,
            "validation_errors": [],
            "retry_count": 0,
        }

        result_state = await self._graph.ainvoke(initial_state)

        # TODO: result_state["recommendations"] -> advisory_pb2.GetRecommendationsResponse 매핑
        # (proto 계약 확정 및 코드 생성 후 작성)
        return result_state["recommendations"]
