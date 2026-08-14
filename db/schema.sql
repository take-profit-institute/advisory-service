-- ============================================================
-- Candle Advisory Service - DB Schema (MVP)
-- PostgreSQL + pgvector(벡터) + pg_trgm(키워드)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ------------------------------------------------------------
-- 1. 종목 캐시 테이블 (원본 마스터 아님!)
--
--    종목 데이터의 Source of Truth는 Stock Service.
--    (services/stock-service, stocks / stock_financials / candles 테이블)
--    이 테이블은 advisory-service가 gRPC로 동기화해온 로컬 스냅샷.
--
--    이 테이블은 학습콘텐츠 서비스나 다른 어떤 서비스도 아닌,
--    advisory-service 자신의 하이브리드 검색(pg_trgm 인덱스)과
--    스코어링 계산을 위해 필요해서 만드는 테이블이다.
--
--    로컬 캐시가 필요한 이유:
--    - pg_trgm 인덱스는 PostgreSQL 내부 컬럼에만 걸 수 있음
--    - 매 요청마다 Stock Service에 gRPC 호출하는 대신 로컬 조인으로 처리
--    (Redis/TimescaleDB 대신 같은 PostgreSQL 인스턴스에 두는 이유는
--     README의 "캐싱 전략" 섹션 참고)
--
--    컬럼은 Stock Service 조사 결과에 맞춰 확정한 것:
--      - PER/PBR/ROE : stock_financials에 존재하나 정기 동기화가
--        안 되고 있어 최신값이 아닐 수 있음 -> fiscal_period로 추적
--      - dividend_yield, debt_ratio : Stock Service에 필드 자체가 없음
--        -> 제공 여부를 Stock Service팀에 확인 후 추가하거나 영구 제외
--      - volatility_90d : Stock Service가 직접 제공하지 않음.
--        candles(일봉) 원본 데이터를 받아 advisory-service가 직접 계산
-- ------------------------------------------------------------
CREATE TABLE stocks_cache (
    stock_code                    VARCHAR(20) PRIMARY KEY,     -- Stock Service gRPC의 code
    name_kr                        VARCHAR(100) NOT NULL,      -- 종목명 (한글)
    name_en                        VARCHAR(100),
    sector                          VARCHAR(50),
    market                           VARCHAR(20),               -- KOSPI / KOSDAQ 등
    market_cap                       BIGINT,

    -- 재무 지표 (Stock Service의 stock_financials 스냅샷)
    per                                NUMERIC(8,2),
    pbr                                NUMERIC(8,2),
    roe                                NUMERIC(6,2),
    financials_fiscal_period            VARCHAR(10),  -- 예: '2025Q3' — 재무수치 기준 분기
                                                        -- (최신이 아닐 수 있음을 판단하는 근거)

    -- 변동성 (advisory-service가 candles 원본 데이터로 직접 계산한 값)
    volatility_90d                        NUMERIC(6,3),
    volatility_calculated_at               TIMESTAMPTZ,  -- 변동성 계산 시점 (재계산 주기 판단용)
    latest_close                            NUMERIC(12,2),
    latest_close_at                         TIMESTAMPTZ,

    synced_at                               TIMESTAMPTZ NOT NULL DEFAULT now()  -- 마지막 동기화 시각
);

CREATE INDEX idx_stocks_cache_name_trgm ON stocks_cache USING GIN (name_kr gin_trgm_ops);
CREATE INDEX idx_stocks_cache_code_trgm ON stocks_cache USING GIN (stock_code gin_trgm_ops);

-- ------------------------------------------------------------
-- 2. 종목 내러티브 문서 (비정형 데이터: 벡터 검색이 강한 영역)
-- ------------------------------------------------------------
CREATE TABLE stock_narratives (
    narrative_id    BIGSERIAL PRIMARY KEY,
    stock_code      VARCHAR(20) NOT NULL REFERENCES stocks_cache(stock_code) ON DELETE CASCADE,
    narrative_type  VARCHAR(30) NOT NULL,
    content         TEXT NOT NULL,
    embedding       VECTOR(1536) NOT NULL,  -- text-embedding-3-small 기준 1536차원
    source          VARCHAR(50),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_stock_narratives_source
    ON stock_narratives (stock_code, narrative_type, source);

CREATE INDEX idx_narratives_embedding ON stock_narratives
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_narratives_content_trgm ON stock_narratives USING GIN (content gin_trgm_ops);

-- ------------------------------------------------------------
-- 3. 사용자 투자 성향 프로필
-- ------------------------------------------------------------
CREATE TABLE user_profiles (
    user_id             VARCHAR(64) PRIMARY KEY,
    risk_tolerance       VARCHAR(20) NOT NULL,
    investment_horizon    VARCHAR(20),
    preferred_sectors     TEXT[],
    free_text_query       TEXT,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- 4. 추천 결과 (LangGraph 실행 결과 저장 + 재현/검증용)
--
--    price_snapshot / snapshot_at: 나중에 "승률"(추천 이후 실제
--    성과) 리포팅을 만들 수 있게, 추천 시점의 가격 지표를 미리
--    기록해두는 필드. 승률 계산 로직 자체는 지금 만들지 않음.
-- ------------------------------------------------------------
CREATE TABLE recommendations (
    recommendation_id  BIGSERIAL PRIMARY KEY,
    user_id             VARCHAR(64) NOT NULL REFERENCES user_profiles(user_id),
    stock_code          VARCHAR(20) NOT NULL REFERENCES stocks_cache(stock_code),
    rrf_score            NUMERIC(8,5),
    fit_score             NUMERIC(8,5),
    narrative              TEXT,
    improvement_tags       TEXT[],
    price_snapshot          NUMERIC(12,2),
    snapshot_at              TIMESTAMPTZ,
    validation_status         VARCHAR(20),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);
