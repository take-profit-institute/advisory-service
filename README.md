# Candle Advisory Service

Candle 프로젝트 — 사용자 투자성향 기반 종목 추천 마이크로서비스.
헥사고날 아키텍처(포트-어댑터)로 구성되어 있다.

## 디렉토리 구조

```
src/advisory_service/
├── domain/            # 핵심 비즈니스 로직. 어떤 외부 프레임워크/DB/LLM도 모른다.
│   ├── models/         # InvestorProfile, ScoredCandidate, AdvisoryRecommendation 등
│   ├── ports/           # domain이 필요로 하는 인터페이스 (예: AdvisoryRepository)
│   └── services/         # fit_score.py — 순수함수 스코어링
├── application/        # 유스케이스 오케스트레이션 (LangGraph)
│   ├── ports/            # StockSearchPort, StockCatalogPort, NarrativeGeneratorPort
│   └── advisory/          # state.py, nodes/, graph.py
├── infrastructure/      # 포트의 실제 구현체 (외부 세계와 맞닿는 부분)
│   ├── persistence/       # asyncpg, PostgreSQL repository
│   ├── retrieval/          # pgvector + pg_trgm 하이브리드 검색 + RRF
│   ├── llm/                 # OpenAI(gpt-4o-mini) narrative 생성
│   └── stock_catalog/        # Stock Service gRPC 클라이언트 (조사 결과 대기 중)
├── transport/           # 외부에 노출하는 인터페이스 (gRPC 서버)
├── bootstrap.py          # Composition Root — 포트에 구현체를 주입하는 유일한 지점
├── config.py              # pydantic-settings 환경변수
└── main.py                 # 진입점
```

## 의존성 방향

```
transport → application → domain
                ↑              ↑
         infrastructure ───────┘
```

domain은 아무것도 참조하지 않는다. application은 domain과 자신의 ports만 참조한다.
infrastructure가 application/domain의 ports를 구현한다. transport와 bootstrap이
맨 바깥에서 이 모든 걸 조립한다.

## 종목 데이터 소유권 — Stock Service가 Source of Truth

advisory-service는 종목 원본 데이터를 소유하지 않는다. Stock Service
(`services/stock-service`)가 `stocks` / `stock_financials` / `candles`로
종목 마스터·재무정보·일봉 데이터를 관리하고, advisory-service는 gRPC로
이를 읽어와 `stocks_cache`(로컬 스냅샷)에 동기화해서 쓴다.

`stocks_cache`는 advisory-service 자신의 필요(pg_trgm 인덱스, 스코어링
계산)를 위해 만드는 테이블이지, 학습콘텐츠 서비스나 다른 서비스를 위한
것이 아니다.

### 실제 가용 필드 (Stock Service 조사 결과 반영)

| 필드 | 상태 |
|---|---|
| 종목코드/명/시장/업종/시총 | Stock Service가 배치로 정기 동기화. 안정적 |
| PER / PBR / ROE | `stock_financials`에 존재하나 **정기 동기화 로직 미구현** → 최신값이 아닐 수 있음. `financials_fiscal_period`로 staleness 추적 |
| 배당수익률 / 부채비율 | **필드 자체가 없음.** DART Open API 연동 필요 여부를 Stock Service팀과 협의 (1차 고도화 후보) |
| 변동성(volatility_90d) | Stock Service 미제공. `candles`(일봉) 원본을 받아 **advisory-service가 직접 계산** (연율화된 일별 로그수익률 표준편차) |

## gRPC — Candle 내부 통신 컨벤션

내부 서비스 간 통신은 gRPC, REST는 웹앱-BFF 구간에서만 사용하는 것이 Candle
컨벤션이다. `proto/advisory/v1/advisory.proto`는 초안(draft) 상태이며, 필드는
팀장/BFF 담당자와 협의 후 확정한다.

```bash
make grpc   # proto -> src/advisory_service/transport/grpc/generated/ 코드 생성
```

## 로컬 개발

```bash
uv sync                  # 의존성 설치 (Python 3.12.13)
cp .env.example .env      # 환경변수 채우기
make compose-up            # PostgreSQL(pgvector) + advisory-service 기동
make test                   # 단위테스트 (domain/application/infrastructure는 즉시 실행 가능)
```

## 설계 결정 근거

| 결정 | 이유 |
|---|---|
| 헥사고날 아키텍처 | domain(순수 스코어링 로직)을 DB/LLM/gRPC로부터 분리해 테스트 용이성 확보. 포트만 바뀌면 어댑터(구현체) 교체가 자유로움 |
| LangGraph (LangChain 아님) | validate → retry 사이클, 조건 분기, 노드 간 공유 State가 필요한 구조 |
| pgvector + pg_trgm | Candle이 이미 PostgreSQL 기반 → 별도 벡터DB/Redis/TimescaleDB 없이 하이브리드 검색 구현 가능 |
| 키워드=trgm, 의미=vector 이원화 | 한국어 형태소 분석 없이도 종목명/코드는 trgm이 정확, 의미 기반 질의는 vector가 강함 |
| score_breakdown + improvement_tags | fit_score 숫자 하나로는 "왜"를 설명 못함 → narrative 프롬프트 근거. improvement_tags는 규칙 기반 계산(LLM 아님)이라 결정론적 |
| 임베딩: text-embedding-3-small / LLM: gpt-4o-mini | 개발 예산(약 $4) 대비 충분히 여유로운 비용 구조 |
| Python 3.12.13 | grpcio/asyncpg 등 핵심 의존성이 안정적으로 지원하는 검증된 버전 |

## MVP 스코프

**포함**: Stock Service 동기화, 하이브리드 검색+RRF(k=60 고정), 순수함수 스코어링
(밸류에이션/수익성/변동성 3축), LangGraph 기본 플로우 + 1회 재시도 밸리데이션,
승률 리포팅용 `price_snapshot` 필드만 우선 기록.

**제외 (우선순위)**

| 순위 | 항목 | 사유 |
|---|---|---|
| 1 | 업종 평균 대비 상대 밸류에이션 | 기존 sector 데이터로 바로 구현 가능 |
| 2 | RRF/스코어링 가중치 자동 튜닝 | 평가 라벨(정답 데이터) 부재로 아직 무의미 |
| 3 | 학습콘텐츠 연동 확장 | 담당자 서비스 소관 |
| 4 | 피드백 기반 재학습, 승률 리포팅 | 시간이 흘러야 검증 가능해 물리적으로 불가 |

## 다음 단계

**혼자 진행 가능**: domain/application/infrastructure(DB, LLM) 구현, 단위테스트,
candles 기반 변동성 계산 로직.

**팀/타 서비스 협의 필요**: proto 계약 확정, Stock Service gRPC 인터페이스·
재무지표 최신화 여부, 학습콘텐츠 담당자와 improvement_tags 노출 협의, Candle
전체 Python 서비스 컨벤션(CI/CD 등).