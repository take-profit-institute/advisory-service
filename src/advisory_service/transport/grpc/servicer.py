"""인증된 x-user-id를 사용하는 AdvisoryService gRPC transport."""

from uuid import UUID

import grpc

from advisory_service.application.advisory.use_case import GenerateAdvisoryUseCase
from advisory_service.domain.models.investor_profile import (
    InvestmentHorizon,
    InvestorProfile,
    RiskTolerance,
)
from advisory_service.transport.grpc.generated.advisory.v1 import (
    advisory_pb2,
    advisory_pb2_grpc,
)

USER_ID_METADATA_KEY = "x-user-id"


class AdvisoryServicer(advisory_pb2_grpc.AdvisoryServiceServicer):
    def __init__(self, use_case: GenerateAdvisoryUseCase):
        self._use_case = use_case

    async def GetRecommendations(self, request, context):
        user_id = await self._require_user_id(context)
        try:
            risk_tolerance = RiskTolerance(request.risk_tolerance)
            investment_horizon = (
                InvestmentHorizon(request.investment_horizon)
                if request.investment_horizon
                else None
            )
        except ValueError as exc:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
            raise AssertionError("context.abort must terminate the RPC") from exc

        profile = InvestorProfile(
            user_id=user_id,
            risk_tolerance=risk_tolerance,
            investment_horizon=investment_horizon,
            preferred_sectors=list(request.preferred_sectors),
            free_text_query=request.free_text_query,
        )
        result = await self._use_case.execute(profile)

        return advisory_pb2.GetRecommendationsResponse(
            recommendations=[
                advisory_pb2.Recommendation(
                    stock_code=item.stock_code,
                    name_kr=item.name_kr,
                    fit_score=item.fit_score,
                    narrative=item.narrative,
                    improvement_tags=item.improvement_tags,
                    price_snapshot=int(item.price_snapshot or 0),
                )
                for item in result.recommendations
            ],
            validation_status=result.validation_status.value,
            validation_errors=result.validation_errors,
            retry_count=result.retry_count,
        )

    @staticmethod
    async def _require_user_id(context) -> str:
        metadata = dict(context.invocation_metadata())
        user_id = metadata.get(USER_ID_METADATA_KEY)
        if not user_id:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "MISSING_ACTOR")
            raise AssertionError("context.abort must terminate the RPC")
        try:
            return str(UUID(user_id))
        except ValueError as exc:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "INVALID_ACTOR")
            raise AssertionError("context.abort must terminate the RPC") from exc
