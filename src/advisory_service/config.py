"""환경변수 기반 설정. pydantic-settings로 타입 검증까지 함께 수행한다."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    openai_api_key: str
    stock_service_grpc_target: str = "stock-service:50051"
    grpc_port: int = 50051
