import grpc
import pytest

from advisory_service.domain.models.advisory import (
    AdvisoryRecommendation,
    AdvisoryResult,
    ValidationStatus,
)
from advisory_service.transport.grpc.generated.advisory.v1 import advisory_pb2
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
        risk_tolerance="moderate",
        free_text_query="저평가 우량주",
    )

    response = await servicer.GetRecommendations(
        request,
        FakeContext((("x-user-id", USER_ID),)),
    )

    assert use_case.profile.user_id == USER_ID
    assert response.validation_status == "passed"
    assert response.recommendations[0].stock_code == "005930"


async def test_get_recommendations_rejects_missing_authenticated_user():
    servicer = AdvisoryServicer(FakeUseCase())

    with pytest.raises(RpcAborted) as exc_info:
        await servicer.GetRecommendations(
            advisory_pb2.GetRecommendationsRequest(risk_tolerance="moderate"),
            FakeContext(),
        )

    assert exc_info.value.code == grpc.StatusCode.UNAUTHENTICATED
