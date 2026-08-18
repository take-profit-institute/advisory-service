# Candle Advisory Service

Candle 사용자의 투자 성향과 질의를 바탕으로 종목을 검색하고, 적합도 점수와
추천 근거를 반환하는 Python gRPC 마이크로서비스다.

- Python 3.12
- uv
- gRPC (`grpc.aio`)
- LangGraph
- PostgreSQL 16 + pgvector + pg_trgm
- OpenAI `text-embedding-3-small` / `gpt-4o-mini`

## 아키텍처

헥사고날 아키텍처(포트-어댑터)를 사용한다.

```text
transport → application → domain
                ↑            ↑
         infrastructure ─────┘
```

- `domain`은 DB, gRPC, LLM과 같은 외부 기술을 참조하지 않는다.
- `application`은 유스케이스와 포트를 정의하고 LangGraph 실행을 조율한다.
- `infrastructure`는 application 포트의 PostgreSQL, OpenAI, Stock Service 구현체를 제공한다.
- `transport`는 외부 gRPC 요청을 application use case로 전달한다.
- `bootstrap.py`가 구체 구현체를 조립하는 Composition Root다.

`AdvisoryRepository`는 도메인 모델 자체의 계약이 아니라 유스케이스의 출력
포트이므로 `application/ports`에 둔다. 종목 조회와 전체 동기화도 소비자가
다르므로 각각 `StockMetricsReader`, `StockCatalogSynchronizer`로 분리한다.

## 디렉터리 구조

```text
advisory-service/
├── db/
│   └── seed.sql                           # 로컬 개발용 TEST001~TEST005
├── .github/
│   ├── workflows/aws-ci.yml               # 테스트 → ECR push → GitOps tag bump
│   └── actions/bump-tag/                  # candle-k8s-lite ApplicationSet 태그 갱신
├── proto/
│   ├── advisory/v1/advisory.proto         # 외부에 노출하는 AdvisoryService 계약
│   └── candle/                            # Stock/Common Service 계약
├── scripts/
│   └── generate_grpc.sh                   # protobuf Python 코드 생성
├── src/advisory_service/
│   ├── domain/
│   │   ├── models/                        # 투자자 프로필, 검색/추천 모델
│   │   └── services/                      # 적합도 점수, 변동성 순수함수
│   ├── application/
│   │   ├── ports/                         # 외부 의존성 인터페이스
│   │   └── advisory/
│   │       ├── nodes/                     # LangGraph 노드
│   │       ├── graph.py                   # 그래프 구성
│   │       ├── state.py                   # 그래프 상태
│   │       └── use_case.py                # GenerateAdvisoryUseCase
│   ├── infrastructure/
│   │   ├── llm/                           # OpenAI 추천 근거 생성
│   │   ├── persistence/                   # asyncpg pool, schema.sql, PostgreSQL repository
│   │   ├── retrieval/                     # vector + trgm + RRF 검색
│   │   └── stock_catalog/                 # Stock/Chart Service gRPC 연동
│   ├── transport/grpc/
│   │   ├── generated/                     # protoc 생성 코드(버전 관리 제외)
│   │   ├── server.py                      # gRPC/health 서버 시작
│   │   └── servicer.py                    # RPC 요청·응답 매핑
│   ├── bootstrap.py                       # 의존성 조립
│   ├── config.py                          # pydantic-settings 환경변수
│   └── main.py                            # 동기 CLI 진입점 + 비동기 실행
├── tests/
│   ├── unit/                              # domain/application/infrastructure 단위 테스트
│   ├── contract/grpc/                     # gRPC servicer 계약 테스트
│   └── integration/persistence/           # 실제 PostgreSQL repository 테스트
├── docker-compose.yml                     # 로컬 PostgreSQL + 애플리케이션
├── docker-compose.test.yml                # 격리된 통합 테스트 DB
├── Dockerfile
├── Makefile
├── pyproject.toml
└── uv.lock
```

## 추천 요청 흐름

```text
gRPC GetRecommendations
  → AdvisoryServicer
  → GenerateAdvisoryUseCase
  → build_profile
  → retrieve_candidates (pgvector + pg_trgm + RRF)
  → score_candidates (PER/PBR/ROE/90일 변동성)
  → generate_narrative (OpenAI)
  → validate_result (실패 시 최대 1회 재시도)
  → PostgreSQL 저장
  → gRPC 응답
```

내부 서비스 간 통신은 gRPC를 사용한다. 사용자 ID는 request body가 아니라 인증된
`x-user-id` metadata에서 읽고, 종목 식별자는 Stock Service의 `code`를 사용한다.
서버는 `candle.advisory.v1.AdvisoryService`와 전체 서버(`""`)에 대한 표준 gRPC
health status도 제공한다.

### AdvisoryService v1 계약

`proto/advisory/v1/advisory.proto`를 BFF 코드 생성의 기준 계약으로 사용한다.

```proto
rpc GetRecommendations(GetRecommendationsRequest)
    returns (GetRecommendationsResponse);
```

요청 시 UUID 형식의 `x-user-id` metadata가 필수다. `risk_tolerance`도 반드시
지정해야 하며 `investment_horizon`은 `UNSPECIFIED`를 허용한다.

```text
risk_tolerance:
  RISK_TOLERANCE_CONSERVATIVE
  RISK_TOLERANCE_MODERATE
  RISK_TOLERANCE_AGGRESSIVE

investment_horizon:
  INVESTMENT_HORIZON_UNSPECIFIED
  INVESTMENT_HORIZON_SHORT
  INVESTMENT_HORIZON_MID
  INVESTMENT_HORIZON_LONG
```

입력 제한은 다음과 같다.

- `preferred_sectors`: 최대 10개, 각 1~50자
- `free_text_query`: 최대 500자
- 빈 `free_text_query`: 투자 성향, 기간, 선호 업종으로 서버가 기본 검색어 생성

응답의 `validation_status`는 `PASSED`, `RETRIED`, `FAILED` enum이며 추천 결과는
최대 5개다. v1 계약을 변경할 때는 기존 필드 번호를 재사용하지 않는다.

## 종목 데이터와 로컬 캐시

종목 원본의 Source of Truth는 Stock Service다. advisory-service는
`SearchStocks`, `GetStock`, `GetCandles` RPC로 다음 데이터를 가져와 자체 검색과
스코어링에 필요한 로컬 스냅샷만 저장한다.

| 필드 | 처리 방식 |
|---|---|
| 종목코드, 종목명, 시장, 업종, 시가총액 | Stock Service에서 전체 동기화 |
| PER, PBR, ROE | `GetStock(code)`로 동기화하고 `financials_fiscal_period` 기록 |
| 90일 변동성 | 워밍 배치가 `GetCandles` 일봉으로 미리 계산하고 계산 시각 기록 |
| 배당수익률, 부채비율 | 현재 Stock Service 계약에 없어 MVP에서 제외 |

`stocks_cache`는 원본 마스터가 아니다. 추천 요청은 로컬 캐시만 읽는 것이
정상 경로이며, 변동성이 없는 후보를 요청 중에 `GetCandles`로 보충하는 경로는
워밍이 놓친 종목을 위한 fallback으로만 남겨둔다. 재무지표나 변동성이 결측인
종목은 값을 0으로 간주하지 않고 점수 계산 후보에서 제외한다.

**변동성 워밍이 필요한 이유**: 후보 20종목이 전부 cache miss면 요청 한 건이
`GetCandles`를 20회 호출한다. 10 RPS 제한까지 겹쳐 `STOCK_GRPC_TIMEOUT_SECONDS`
(5초)를 넘기고, 요청은 `DEPENDENCY_UNAVAILABLE`로 실패한다. 그래서
`MarketMetricsWarmer`가 기동 직후와 매일 카탈로그 동기화 직후에 변동성이 없거나
`MARKET_METRICS_WARM_STALE_AFTER_SECONDS`(기본 12시간)보다 오래된 종목을 일괄
갱신한다. stale 기준을 `VOLATILITY_CACHE_TTL_SECONDS`(24시간)의 절반으로 두는
이유는, 둘이 같으면 다음 워밍 직전에 캐시가 먼저 만료돼 요청이 다시 gRPC
보충 경로를 타기 때문이다. 종목 단위 실패는 배치를 중단시키지 않고
`market_metrics_warmed` 로그에 `refreshed`/`unavailable`/`failed`로 집계된다.

전체 종목을 약 4,000개로 가정하면 초기 동기화는 `SearchStocks(size=100)` 약
40회와 종목별 `GetStock` 약 4,000회다. 기본값은 동시성 5, 최대 10 RPS이며
네트워크 지연과 재시도를 포함해 약 7~10분을 예상한다. 운영 기본값은 매일
23:00 KST(`Asia/Seoul`)이며, 작업이 끝난 시점부터 24시간을 세지 않고 다음
달력 날짜의 23:00을 다시 계산하므로 실행 시각이 뒤로 밀리지 않는다.

## 데이터베이스

`src/advisory_service/infrastructure/persistence/schema.sql`은 다음 테이블을 생성한다.

- `stocks_cache`: 동기화한 종목·재무·변동성 스냅샷
- `stock_narratives`: 검색 문서와 1,536차원 임베딩
- `user_profiles`: 투자 성향과 질의
- `recommendations`: 추천 결과, 점수, 가격 스냅샷과 검증 상태

PostgreSQL에는 `vector`, `pg_trgm` 확장이 필요하다. 벡터 검색에는 HNSW,
종목명·종목코드·문서 키워드 검색에는 GIN trigram 인덱스를 사용한다. 두 검색
순위는 RRF(`k=60`)로 합친다.

스키마는 기동 시 `bootstrap.build_application`이 자동 적용한다(`DB_AUTO_MIGRATE=true`,
기본값). Flyway 같은 버전 테이블 없이 `schema.sql` 전체를 매번 재실행하는 방식이라
**모든 DDL이 멱등해야 한다** — 컬럼 추가는 `CREATE TABLE` 수정이 아니라
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`를 파일 끝에 덧붙여야 반영된다.
`CREATE EXTENSION`에는 superuser가 필요하므로 이 서비스는 공용 인스턴스가 아니라
전용 PostgreSQL(로컬 compose, lite의 `advisory-postgres`)에 접속한다. 스키마를
외부에서 관리하는 환경이면 `DB_AUTO_MIGRATE=false`로 끈다.

## 환경 설정

```bash
cp .env.example .env
```

주요 환경변수는 다음과 같다.

| 변수 | 설명 | 기본값/예시 |
|---|---|---|
| `DATABASE_URL` | PostgreSQL 연결 문자열 | Compose에서는 `postgresql://advisory:advisory@postgres:5432/advisory` |
| `OPENAI_API_KEY` | 임베딩 및 추천 근거 생성용 키 | 필수 |
| `DB_AUTO_MIGRATE` | 기동 시 `schema.sql` 적용 여부 | `true` |
| `STOCK_SERVICE_GRPC_TARGET` | Stock Service gRPC 주소 | `stock-service:50051` (lite 클러스터는 `stock-service:9090`) |
| `STOCK_SYNC_ENABLED` | 전체 종목 동기화 스케줄러 실행 여부 | `true` |
| `STOCK_SYNC_RUN_ON_STARTUP` | 서버 시작 직후 추가 동기화 여부 | `false` |
| `STOCK_SYNC_TIME` | 매일 전체 동기화 실행 시각 | `23:00` |
| `STOCK_SYNC_TIMEZONE` | 동기화 시각의 IANA timezone | `Asia/Seoul` |
| `STOCK_SYNC_PAGE_SIZE` | `SearchStocks` 페이지 크기 | `100` |
| `STOCK_SYNC_CONCURRENCY` | Stock Service 동시 요청 수 | `5` |
| `STOCK_SYNC_REQUESTS_PER_SECOND` | 초당 최대 요청 수 | `10` |
| `STOCK_GRPC_TIMEOUT_SECONDS` | Stock Service RPC timeout | `5` |
| `VOLATILITY_CACHE_TTL_SECONDS` | 계산된 변동성 재사용 시간 | `86400` |
| `MARKET_METRICS_WARM_ENABLED` | 변동성/종가 캐시 워밍 실행 여부 | `true` |
| `MARKET_METRICS_WARM_ON_STARTUP` | 기동 직후 워밍 여부 (동기화가 startup에 돌면 생략) | `true` |
| `MARKET_METRICS_WARM_STALE_AFTER_SECONDS` | 이 시간보다 오래된 변동성을 워밍 대상으로 판단 | `43200` |
| `MARKET_METRICS_WARM_BATCH_SIZE` | 워밍 배치 한 묶음의 종목 수 | `100` |
| `GRPC_PORT` | Advisory gRPC 포트 | `50051` |

로컬 Compose에서 Stock Service를 함께 실행하지 않는다면 다음처럼 설정한다.

```env
DATABASE_URL=postgresql://advisory:advisory@postgres:5432/advisory
STOCK_SYNC_ENABLED=false
```

최초 배포에서 23:00 이전에도 캐시를 즉시 채워야 하는 경우에만
`STOCK_SYNC_RUN_ON_STARTUP=true`를 일시적으로 사용한다. 기본값 `false`는 업무
시간 중 Pod 재시작이 전체 4,000종목 동기화를 다시 유발하지 않도록 한다.

`.env`는 비밀정보를 포함할 수 있으므로 커밋하지 않는다.

## 로컬 실행

### 사전 준비

```bash
uv python install 3.12.13
uv sync
cp .env.example .env
```

### Docker Compose 실행

`.env`의 `DATABASE_URL` 호스트를 `postgres`로 설정한 후 실행한다.

```bash
make compose-up
```

다른 터미널에서 상태를 확인한다.

```bash
docker compose ps
```

`postgres`와 `advisory-service`가 모두 `Up`이어야 한다.

로컬 개발용 경계 사례 5개를 입력하려면 다음 명령을 실행한다.

```bash
make seed
```

`db/seed.sql`은 정상, 적자, 재무지표 결측, 고변동성, 변동성 결측 종목을
`TEST001`~`TEST005`로 추가한다. `ON CONFLICT DO UPDATE`를 사용하므로 반복
실행해도 중복되지 않으며 운영 환경에서는 실행하지 않는다.

서비스와 DB 볼륨을 종료·삭제하려면 다음 명령을 사용한다.

```bash
make compose-down
```

현재 `compose-down`은 `docker compose down -v`를 실행하므로 로컬 DB 데이터도
함께 삭제한다.

### 호스트에서 애플리케이션 실행

PostgreSQL과 Stock Service에 호스트에서 접근 가능한 주소를 `.env`에 설정한 뒤:

```bash
make run
```

## gRPC 코드 생성

```bash
make grpc
```

`scripts/generate_grpc.sh`는 `proto/`의 계약으로부터 코드를 생성하고
`src/advisory_service/transport/grpc/generated/`에 배치한다. 생성 결과는 Git으로
관리하지 않으며 로컬 실행, 테스트 및 Docker 빌드 과정에서 다시 생성한다.

## 검사와 테스트

```bash
make lint               # Ruff: src와 tests 검사
make test               # gRPC 코드 생성 후 integration 제외 전체 테스트
make integration-test   # localhost:5434의 advisory_test DB로 통합 테스트
make integration-down   # 통합 테스트 DB와 임시 볼륨 정리
```

`make test`에는 unit과 gRPC contract 테스트가 포함된다. 통합 테스트는
`docker-compose.test.yml`의 별도 PostgreSQL을 사용한다. fixture는 DB 이름이
`_test`로 끝나지 않으면 스키마 초기화를 거부해 개발·운영 DB의 실수 삭제를 막는다.

## 배포 (CI/CD)

`main` 푸시 → GitHub Actions(`.github/workflows/aws-ci.yml`) → ECR → ArgoCD 순으로 흐른다.

```
push main ─ test(lint·unit·integration)
          └ image ─ OIDC assume(candle-lite-dev-ci-deploy)
                  ─ ECR push  candle/advisory-service:<커밋 SHA>
                  └ bump-tag  candle-k8s-lite/platform/applications/services-dev.yaml
                              └ ArgoCD auto-sync → lite 클러스터(k3s) 재배포
```

PR에서는 테스트만 돌고 이미지 빌드·배포는 하지 않는다.

| 항목 | 값 |
|---|---|
| ECR | `633597729239.dkr.ecr.ap-northeast-2.amazonaws.com/candle/advisory-service` |
| 이미지 태그 | 커밋 SHA (repo가 IMMUTABLE — 같은 SHA 재실행 시 빌드 생략 후 bump만) |
| 인증 | GitHub OIDC → `candle-lite-dev-ci-deploy` (이 repo만 assume 가능, 키 없음) |
| 배포 대상 | lite k3s 클러스터, namespace `candle` |

인프라 정의는 `infrastructure-lite/envs/dev/ci.tf`(ECR·IAM), 배포 매니페스트는
`candle-k8s-lite`(ApplicationSet + services chart)에 있다.

repo 설정 두 가지가 있어야 동작한다.

```bash
gh variable set CI_DEPLOY_ROLE_ARN --body arn:aws:iam::633597729239:role/candle-lite-dev-ci-deploy
gh secret set GITOPS_TOKEN   # candle-k8s-lite push 권한 PAT
```

클러스터에서 쓰는 값 중 `OPENAI_API_KEY`는 git에 두지 않고 Secret으로 직접 만든다.

```bash
kubectl -n candle create secret generic advisory-service-app --from-literal=OPENAI_API_KEY=...
```

## 주요 설계 결정

| 결정 | 이유 |
|---|---|
| 헥사고날 아키텍처 | 핵심 로직을 DB, LLM, gRPC에서 분리하고 어댑터 교체와 테스트를 쉽게 하기 위해 |
| 조회/동기화 포트 분리 | 스코어링 노드와 배치 루프처럼 실제 소비자가 서로 다르기 때문에 |
| LangGraph | 노드 간 공유 상태, 조건 분기, validate 후 재시도가 필요하기 때문에 |
| pgvector + pg_trgm | 종목명·코드 검색과 의미 검색을 기존 PostgreSQL 안에서 함께 처리하기 위해 |
| 결정론적 점수와 LLM 설명 분리 | 추천 점수는 재현 가능하게 계산하고 LLM은 설명 생성에만 사용하기 위해 |
| Python 3.12 + uv lock | 개발, CI, Docker의 Python·의존성 환경을 재현하기 위해 |

## MVP 범위

포함:

- Stock Service 종목·재무정보 동기화
- 후보 종목의 90일 변동성 계산 및 캐시
- pgvector + pg_trgm 하이브리드 검색과 RRF
- 밸류에이션, 수익성, 변동성 기반 적합도 점수
- LangGraph 추천 흐름과 검증 실패 시 1회 재시도
- OpenAI 기반 추천 근거 생성
- 추천 결과 및 추천 시점 가격 저장

현재 제외 또는 추후 협의:

- 업종 평균 대비 상대 밸류에이션
- RRF 및 스코어링 가중치 자동 튜닝
- 배당수익률·부채비율 기반 점수
- 학습 콘텐츠 연동 범위
- 피드백 기반 재학습과 추천 성과 리포트
- Candle 전체 Python 서비스 CI/CD 규칙
