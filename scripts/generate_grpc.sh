#!/bin/bash
# proto/ 의 .proto 파일을 src/advisory_service/transport/grpc/generated/ 로 컴파일한다.
# 생성된 코드는 .gitignore 처리되어 있으므로, 빌드/CI/로컬 개발 시마다 이 스크립트를 실행해야 한다.
set -e

GEN_DIR=src/advisory_service/transport/grpc/generated

mkdir -p "$GEN_DIR"

uv run python -m grpc_tools.protoc \
  --proto_path=proto \
  --python_out="$GEN_DIR" \
  --pyi_out="$GEN_DIR" \
  --grpc_python_out="$GEN_DIR" \
  proto/advisory/v1/advisory.proto \
  proto/candle/common/v1/common.proto \
  proto/candle/stock/v1/stock.proto \
  proto/candle/stock/v1/chart.proto

# protoc는 __init__.py를 만들지 않으므로 패키지 인식을 위해 직접 생성한다.
find "$GEN_DIR" -type d -exec sh -c 'test -f "$1/__init__.py" || touch "$1/__init__.py"' _ {} \;

# grpc_tools가 생성하는 import는 proto_path 기준 절대 경로(from advisory.v1 import ...)라서,
# advisory_service 패키지 하위에 중첩된 이 구조에서는 그대로 resolve되지 않는다.
# 상대 import로 고쳐써야 우리 패키지 트리 안에서 정상 동작한다.
# (참고: https://github.com/grpc/grpc/issues/9575 — grpc_tools의 알려진 미해결 이슈)
sed -i.bak 's/^from advisory\.v1 import/from . import/' "$GEN_DIR/advisory/v1/advisory_pb2_grpc.py"
sed -i.bak 's/^from candle\.stock\.v1 import/from . import/' "$GEN_DIR/candle/stock/v1/stock_pb2_grpc.py"
sed -i.bak 's/^from candle\.stock\.v1 import/from . import/' "$GEN_DIR/candle/stock/v1/chart_pb2_grpc.py"
sed -i.bak 's/^from candle\.common\.v1 import/from ...common.v1 import/' "$GEN_DIR/candle/stock/v1/stock_pb2.py"
find "$GEN_DIR" -name '*.bak' -delete

echo "gRPC 코드 생성 완료: $GEN_DIR/"
