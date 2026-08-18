"""환경변수 기반 설정. pydantic-settings로 타입 검증까지 함께 수행한다."""

from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    openai_api_key: str
    # 기동 시 schema.sql 적용(멱등). 스키마를 외부에서 관리하는 환경이면 끈다.
    db_auto_migrate: bool = True
    stock_service_grpc_target: str = "stock-service:50051"
    stock_sync_page_size: int = 100
    stock_sync_concurrency: int = 5
    stock_sync_requests_per_second: float = 10.0
    stock_sync_enabled: bool = True
    stock_sync_run_on_startup: bool = False
    stock_sync_time: time = time(hour=23)
    stock_sync_timezone: str = "Asia/Seoul"
    stock_grpc_timeout_seconds: float = 5.0
    volatility_cache_ttl_seconds: int = 86_400
    # 변동성 캐시 워밍. 요청 경로에서 GetCandles를 타지 않게 하는 것이 목적이라
    # 기본값은 켜짐이다. stale 기준은 TTL의 절반이어야 다음 워밍 전에 캐시가
    # 만료되지 않는다.
    market_metrics_warm_enabled: bool = True
    market_metrics_warm_on_startup: bool = True
    market_metrics_warm_stale_after_seconds: int = 43_200
    market_metrics_warm_batch_size: int = 100
    # 워밍은 요청 경로가 아니라 배치다. GetCandles가 캔들이 없는 종목에 대해
    # 서버 쪽 백필을 유발해 첫 호출이 수십 초 걸리므로 timeout을 따로 크게 준다.
    market_metrics_warm_timeout_seconds: float = 30.0
    # 1회차에서 백필만 유발하고 timeout된 종목을 2회차에서 회수한다.
    market_metrics_warm_passes: int = 2
    grpc_port: int = 50051

    @field_validator("stock_sync_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {value}") from exc
        return value
