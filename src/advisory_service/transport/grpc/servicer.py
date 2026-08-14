"""인증된 x-user-id를 사용하는 AdvisoryService gRPC transport."""

from uuid import UUID

import grpc
import structlog

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
MAX_QUERY_LENGTH = 500
MAX_PREFERRED_SECTORS = 10
MAX_SECTOR_LENGTH = 50

_RISK_TOLERANCE_BY_PROTO = {
    advisory_pb2.RISK_TOLERANCE_CONSERVATIVE: RiskTolerance.CONSERVATIVE,
    advisory_pb2.RISK_TOLERANCE_MODERATE: RiskTolerance.MODERATE,
    advisory_pb2.RISK_TOLERANCE_AGGRESSIVE: RiskTolerance.AGGRESSIVE,
}

_INVESTMENT_HORIZON_BY_PROTO = {
    advisory_pb2.INVESTMENT_HORIZON_SHORT: InvestmentHorizon.SHORT,
    advisory_pb2.INVESTMENT_HORIZON_MID: InvestmentHorizon.MID,
    advisory_pb2.INVESTMENT_HORIZON_LONG: InvestmentHorizon.LONG,
}

_VALIDATION_STATUS_TO_PROTO = {
    "passed": advisory_pb2.VALIDATION_STATUS_PASSED,
    "retried": advisory_pb2.VALIDATION_STATUS_RETRIED,
    "failed": advisory_pb2.VALIDATION_STATUS_FAILED,
}

log = structlog.get_logger()


class AdvisoryServicer(advisory_pb2_grpc.AdvisoryServiceServicer):
    def __init__(self, use_case: GenerateAdvisoryUseCase):
        self._use_case = use_case

    async def GetRecommendations(self, request, context):
        user_id = await self._require_user_id(context)
        risk_tolerance = _RISK_TOLERANCE_BY_PROTO.get(request.risk_tolerance)
        if risk_tolerance is None:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "risk_tolerance must be specified",
            )
            raise AssertionError("context.abort must terminate the RPC")

        investment_horizon = _INVESTMENT_HORIZON_BY_PROTO.get(
            request.investment_horizon
        )
        if (
            request.investment_horizon
            != advisory_pb2.INVESTMENT_HORIZON_UNSPECIFIED
            and investment_horizon is None
        ):
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "investment_horizon is invalid",
            )
            raise AssertionError("context.abort must terminate the RPC")

        preferred_sectors = [sector.strip() for sector in request.preferred_sectors]
        if len(preferred_sectors) > MAX_PREFERRED_SECTORS:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"preferred_sectors must contain at most {MAX_PREFERRED_SECTORS} values",
            )
            raise AssertionError("context.abort must terminate the RPC")
        if any(not sector or len(sector) > MAX_SECTOR_LENGTH for sector in preferred_sectors):
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"each preferred sector must be 1 to {MAX_SECTOR_LENGTH} characters",
            )
            raise AssertionError("context.abort must terminate the RPC")

        free_text_query = request.free_text_query.strip()
        if len(free_text_query) > MAX_QUERY_LENGTH:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"free_text_query must be at most {MAX_QUERY_LENGTH} characters",
            )
            raise AssertionError("context.abort must terminate the RPC")

        profile = InvestorProfile(
            user_id=user_id,
            risk_tolerance=risk_tolerance,
            investment_horizon=investment_horizon,
            preferred_sectors=preferred_sectors,
            free_text_query=free_text_query,
        )
        try:
            result = await self._use_case.execute(profile)
        except TimeoutError:
            log.exception("advisory_request_timed_out", user_id=user_id)
            await context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, "ADVISORY_TIMEOUT")
            raise AssertionError("context.abort must terminate the RPC")
        except grpc.RpcError:
            log.exception("advisory_dependency_unavailable", user_id=user_id)
            await context.abort(grpc.StatusCode.UNAVAILABLE, "DEPENDENCY_UNAVAILABLE")
            raise AssertionError("context.abort must terminate the RPC")
        except Exception:
            log.exception("advisory_request_failed", user_id=user_id)
            await context.abort(grpc.StatusCode.INTERNAL, "ADVISORY_FAILED")
            raise AssertionError("context.abort must terminate the RPC")

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
            validation_status=_VALIDATION_STATUS_TO_PROTO[result.validation_status.value],
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
