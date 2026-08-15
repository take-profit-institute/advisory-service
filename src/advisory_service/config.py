"""환경변수 기반 설정. pydantic-settings로 타입 검증까지 함께 수행한다."""

from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    openai_api_key: str
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
    grpc_port: int = 50051

    @field_validator("stock_sync_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {value}") from exc
        return value
