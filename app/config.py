from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Async Payment Processing Service"
    api_key: str = Field(default="change-me", alias="API_KEY")
    database_url: str = Field(
        default="postgresql+asyncpg://app:app@postgres:5432/payments",
        alias="DATABASE_URL",
    )
    rabbitmq_url: str = Field(
        default="amqp://guest:guest@rabbitmq:5672/",
        alias="RABBITMQ_URL",
    )
    outbox_poll_interval_seconds: float = Field(
        default=1.0,
        alias="OUTBOX_POLL_INTERVAL_SECONDS",
    )
    outbox_batch_size: int = Field(default=100, alias="OUTBOX_BATCH_SIZE")
    max_processing_attempts: int = Field(default=3, alias="MAX_PROCESSING_ATTEMPTS")
    retry_backoff_base_seconds: int = Field(
        default=1,
        alias="RETRY_BACKOFF_BASE_SECONDS",
    )
    payment_min_delay_seconds: int = Field(
        default=2,
        alias="PAYMENT_MIN_DELAY_SECONDS",
    )
    payment_max_delay_seconds: int = Field(
        default=5,
        alias="PAYMENT_MAX_DELAY_SECONDS",
    )
    webhook_timeout_seconds: float = Field(
        default=10.0,
        alias="WEBHOOK_TIMEOUT_SECONDS",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
