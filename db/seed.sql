-- Advisory Service 로컬 개발용 테스트 데이터.
-- 실제 종목 데이터가 아니며 운영 환경에서는 실행하지 않는다.
-- 여러 번 실행해도 같은 stock_code를 갱신하도록 구성했다.

INSERT INTO stocks_cache (
    stock_code,
    name_kr,
    name_en,
    sector,
    market,
    market_cap,
    per,
    pbr,
    roe,
    financials_fiscal_period,
    volatility_90d,
    volatility_calculated_at,
    latest_close,
    latest_close_at,
    synced_at
)
VALUES
    -- 모든 지표가 정상인 안정적인 종목: 보수형 사용자 점수 확인용
    (
        'TEST001', '테스트안정전자', 'Test Stable Electronics',
        '반도체', 'KOSPI', 500000000000,
        12.00, 1.20, 15.00, '2026Q2',
        10.000, now(), 70000.00, now(), now()
    ),
    -- PER와 ROE가 음수인 적자 종목: 가치평가 페널티 확인용
    (
        'TEST002', '테스트적자바이오', 'Test Loss Bio',
        '바이오', 'KOSDAQ', 50000000000,
        -5.00, 2.00, -3.00, '2026Q2',
        40.000, now(), 5000.00, now(), now()
    ),
    -- 재무지표가 없는 신규 종목: 추천 후보 제외 정책 확인용
    (
        'TEST003', '테스트신규상장', 'Test New Listing',
        '소프트웨어', 'KOSDAQ', 30000000000,
        NULL, NULL, NULL, NULL,
        20.000, now(), 12000.00, now(), now()
    ),
    -- 변동성이 매우 큰 종목: 보수형 사용자 변동성 페널티 확인용
    (
        'TEST004', '테스트고변동성', 'Test High Volatility',
        '이차전지', 'KOSDAQ', 80000000000,
        30.00, 4.00, 8.00, '2026Q2',
        90.000, now(), 18000.00, now(), now()
    ),
    -- 변동성 계산 전인 종목: 지표 보충 전 후보 제외 확인용
    (
        'TEST005', '테스트변동성미수집', 'Test Missing Volatility',
        '자동차', 'KOSPI', 120000000000,
        9.00, 0.90, 12.00, '2026Q2',
        NULL, NULL, 25000.00, now(), now()
    )
ON CONFLICT (stock_code) DO UPDATE SET
    name_kr = EXCLUDED.name_kr,
    name_en = EXCLUDED.name_en,
    sector = EXCLUDED.sector,
    market = EXCLUDED.market,
    market_cap = EXCLUDED.market_cap,
    per = EXCLUDED.per,
    pbr = EXCLUDED.pbr,
    roe = EXCLUDED.roe,
    financials_fiscal_period = EXCLUDED.financials_fiscal_period,
    volatility_90d = EXCLUDED.volatility_90d,
    volatility_calculated_at = EXCLUDED.volatility_calculated_at,
    latest_close = EXCLUDED.latest_close,
    latest_close_at = EXCLUDED.latest_close_at,
    synced_at = EXCLUDED.synced_at;
