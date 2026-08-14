"""gRPC 서버 부팅. main.py에서 호출된다."""

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from advisory_service.transport.grpc.generated.advisory.v1 import advisory_pb2_grpc

SERVICE_NAME = "candle.advisory.v1.AdvisoryService"
GRACEFUL_SHUTDOWN_SECONDS = 5


def create_server(servicer, port: int = 50051):
    server = grpc.aio.server()
    advisory_pb2_grpc.add_AdvisoryServiceServicer_to_server(servicer, server)

    # gRPC Health Checking Protocol 등록.
    # k8s(k3s) liveness/readiness probe가 이 프로토콜을 기대하는지는
    # Candle 인프라팀 확인 필요 (README "확인 필요 사항" 참고).
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set(SERVICE_NAME, health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # 전체 서버 상태

    bound_port = server.add_insecure_port(f"[::]:{port}")
    return server, health_servicer, bound_port


async def serve(servicer, port: int = 50051, shutdown_event=None) -> None:
    server, health_servicer, _ = create_server(servicer, port)
    await server.start()
    try:
        if shutdown_event is None:
            await server.wait_for_termination()
        else:
            await shutdown_event.wait()
    finally:
        health_servicer.set(SERVICE_NAME, health_pb2.HealthCheckResponse.NOT_SERVING)
        health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
        await server.stop(GRACEFUL_SHUTDOWN_SECONDS)
