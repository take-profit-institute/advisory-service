"""gRPC 서버 부팅. main.py에서 호출된다."""

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

# from advisory_service.transport.grpc.generated import advisory_pb2_grpc

SERVICE_NAME = "candle.advisory.v1.AdvisoryService"


async def serve(servicer, port: int = 50051) -> None:
    server = grpc.aio.server()
    # advisory_pb2_grpc.add_AdvisoryServiceServicer_to_server(servicer, server)  # proto 확정 후 활성화

    # gRPC Health Checking Protocol 등록.
    # k8s(k3s) liveness/readiness probe가 이 프로토콜을 기대하는지는
    # Candle 인프라팀 확인 필요 (README "확인 필요 사항" 참고).
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    await health_servicer.set(SERVICE_NAME, health_pb2.HealthCheckResponse.SERVING)
    await health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # 전체 서버 상태

    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    await server.wait_for_termination()
