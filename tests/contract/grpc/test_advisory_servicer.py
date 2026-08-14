import grpc
import pytest

from advisory_service.domain.models.advisory import (
    AdvisoryRecommendation,
    AdvisoryResult,
    ValidationStatus,
)
from advisory_service.transport.grpc.generated.advisory.v1 import (
    advisory_pb2,
    advisory_pb2_grpc,
)
from advisory_service.transport.grpc.server import create_server
from advisory_service.transport.grpc.servicer import AdvisoryServicer

USER_ID = "11111111-1111-1111-1111-111111111111"


class FakeUseCase:
    def __init__(self):
        self.profile = None

    async def execute(self, profile):
        self.profile = profile
        return AdvisoryResult(
            recommendations=[
                AdvisoryRecommendation(
                    user_id=profile.user_id,
                    stock_code="005930",
                    name_kr="삼성전자",
                    rrf_score=0.03,
                    fit_score=0.8,
                    narrative="충분히 긴 추천 사유입니다.",
                )
            ],
            validation_status=ValidationStatus.PASSED,
        )


class FakeContext:
    def __init__(self, metadata=()):
        self._metadata = metadata

    def invocation_metadata(self):
        return self._metadata

    async def abort(self, code, details):
        raise RpcAborted(code, details)


class RpcAborted(Exception):
    def __init__(self, code, details):
        self.code = code
        self.details = details


async def test_get_recommendations_uses_authenticated_user_and_maps_response():
    use_case = FakeUseCase()
    servicer = AdvisoryServicer(use_case)
    request = advisory_pb2.GetRecommendationsRequest(
        risk_tolerance=advisory_pb2.RISK_TOLERANCE_MODERATE,
        free_text_query="저평가 우량주",
    )

    response = await servicer.GetRecommendations(
        request,
        FakeContext((("x-user-id", USER_ID),)),
    )

    assert use_case.profile.user_id == USER_ID
    assert response.validation_status == advisory_pb2.VALIDATION_STATUS_PASSED
    assert response.recommendations[0].stock_code == "005930"


async def test_get_recommendations_rejects_missing_authenticated_user():
    servicer = AdvisoryServicer(FakeUseCase())

    with pytest.raises(RpcAborted) as exc_info:
        await servicer.GetRecommendations(
            advisory_pb2.GetRecommendationsRequest(
                risk_tolerance=advisory_pb2.RISK_TOLERANCE_MODERATE
            ),
            FakeContext(),
        )

    assert exc_info.value.code == grpc.StatusCode.UNAUTHENTICATED


async def test_get_recommendations_rejects_unspecified_risk_tolerance():
    servicer = AdvisoryServicer(FakeUseCase())

    with pytest.raises(RpcAborted) as exc_info:
        await servicer.GetRecommendations(
            advisory_pb2.GetRecommendationsRequest(),
            FakeContext((("x-user-id", USER_ID),)),
        )

    assert exc_info.value.code == grpc.StatusCode.INVALID_ARGUMENT


async def test_real_grpc_stub_maps_metadata_request_and_response():
    server, _, port = create_server(AdvisoryServicer(FakeUseCase()), port=0)
    await server.start()
    channel = grpc.aio.insecure_channel(f"localhost:{port}")
    stub = advisory_pb2_grpc.AdvisoryServiceStub(channel)
    try:
        response = await stub.GetRecommendations(
            advisory_pb2.GetRecommendationsRequest(
                risk_tolerance=advisory_pb2.RISK_TOLERANCE_MODERATE,
                investment_horizon=advisory_pb2.INVESTMENT_HORIZON_LONG,
                preferred_sectors=["반도체"],
            ),
            metadata=(("x-user-id", USER_ID),),
        )
    finally:
        await channel.close()
        await server.stop(0)

    assert response.validation_status == advisory_pb2.VALIDATION_STATUS_PASSED
    assert response.recommendations[0].stock_code == "005930"
