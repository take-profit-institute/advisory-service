# syntax=docker/dockerfile:1

# ------------------------------------------------------------
# Stage 1: proto-builder — grpc_tools(dev 그룹)로 .proto를 컴파일한다.
# 런타임에는 불필요하므로 이 스테이지의 결과물(생성 코드)만 다음 단계로 넘긴다.
# ------------------------------------------------------------
FROM python:3.12.13-slim AS proto-builder
WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
# dev 그룹(grpcio-tools)까지 포함해 설치 — 여기서만 필요
RUN uv sync --frozen --no-install-project

COPY proto/ ./proto/
# 주의 1: `uv run python -m grpc_tools.protoc`를 쓰면 uv가 실행 전 프로젝트
# 자신을 editable로 재설치하려 시도하는데, 이 시점엔 아직 src/를 복사하지
# 않아 src/advisory_service/__init__.py가 없어 빌드가 실패한다.
# grpc_tools는 서드파티 의존성이라 프로젝트 설치 없이 venv python으로
# 바로 실행 가능하므로 `uv run`을 거치지 않는다.
#
# 주의 2: protoc는 __init__.py를 만들지 않고, 생성된 import도 proto_path
# 기준 절대 경로(from advisory.v1 import ...)라서 우리 패키지 트리에
# 그대로는 resolve되지 않는다. scripts/generate_grpc.sh와 동일한 후처리 필요.
RUN GEN_DIR=src/advisory_service/transport/grpc/generated && \
    mkdir -p "$GEN_DIR" && \
    .venv/bin/python -m grpc_tools.protoc \
      --proto_path=proto \
      --python_out="$GEN_DIR" \
      --pyi_out="$GEN_DIR" \
      --grpc_python_out="$GEN_DIR" \
      proto/advisory/v1/advisory.proto && \
    find "$GEN_DIR" -type d -exec sh -c 'test -f "$1/__init__.py" || touch "$1/__init__.py"' _ {} \; && \
    sed -i 's/^from advisory\.v1 import/from . import/' "$GEN_DIR/advisory/v1/advisory_pb2_grpc.py"

# ------------------------------------------------------------
# Stage 2: runtime-builder — 프로덕션 의존성만 설치 (dev 그룹 제외).
# pyproject.toml/uv.lock만 먼저 복사해 소스 변경 시에도 의존성 레이어는 캐시되게 한다.
# ------------------------------------------------------------
FROM python:3.12.13-slim AS runtime-builder
WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
COPY README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY --from=proto-builder /app/src/advisory_service/transport/grpc/generated \
     ./src/advisory_service/transport/grpc/generated
# 프로젝트 자체를 설치해야 [project.scripts]의 advisory-service 엔트리포인트가 .venv/bin에 생성됨
RUN uv sync --frozen --no-dev

# ------------------------------------------------------------
# Stage 3: 최종 런타임 이미지 — dev 의존성, uv, 소스 트리 없이 실행에 필요한 것만 포함
# ------------------------------------------------------------
FROM python:3.12.13-slim
WORKDIR /app

RUN groupadd --system advisory && useradd --system --gid advisory advisory
COPY --from=runtime-builder /app/.venv /app/.venv
COPY --from=runtime-builder /app/src /app/src
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

USER advisory
EXPOSE 50051

CMD ["advisory-service"]