from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    bot_token: str = Field(validation_alias="BOT_TOKEN")
    db_url: str = Field(validation_alias="DB_URL")
    super_admin_telegram_ids: list[int] = Field(
        default_factory=list,
        validation_alias="SUPER_ADMIN_TELEGRAM_IDS",
    )

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("db_url")
    @classmethod
    def validate_db_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DB_URL must start with 'postgresql+asyncpg://'.")
        return value

    @field_validator("super_admin_telegram_ids", mode="before")
    @classmethod
    def parse_super_admin_ids(cls, value: object) -> list[int]:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        if isinstance(value, int):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [int(item) for item in value]
        raise ValueError("SUPER_ADMIN_TELEGRAM_IDS must be a comma-separated list of integers.")

    def is_super_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.super_admin_telegram_ids

    @property
    def db_host(self) -> str | None:
        normalized_url = self.db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        return urlsplit(normalized_url).hostname

    @property
    def masked_db_url(self) -> str:
        normalized_url = self.db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        parsed = urlsplit(normalized_url)
        netloc = parsed.hostname or ""
        if parsed.port is not None:
            netloc = f"{netloc}:{parsed.port}"
        if parsed.username:
            netloc = f"{parsed.username}:***@{netloc}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
