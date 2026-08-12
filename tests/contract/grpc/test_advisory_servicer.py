"""
AdvisoryServicer gRPC 계약 테스트 (스텁).

proto/advisory/v1/advisory.proto 가 draft 상태라, 계약이 팀과 확정되고
scripts/generate_grpc.sh 로 코드 생성이 완료된 뒤 작성한다.
"""

import pytest

pytestmark = pytest.mark.skip(reason="proto 계약 확정 및 코드 생성 후 작성 예정")


async def test_get_recommendations_returns_valid_response():
    ...
