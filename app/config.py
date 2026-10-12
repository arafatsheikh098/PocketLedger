"""Application settings.

All configuration comes from environment variables (or .env). Defaults are
baked in; production refuses to start with the default SECRET_KEY.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "change-me-please-change-me-please-change-me-please-1234567890"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    secret_key: str = DEFAULT_SECRET_KEY
    database_url: str = "sqlite:///./pocketledger.db"
    allow_registration: bool = False
    demo_mode: bool = False
    seed_on_start: bool = False
    user_timezone: str = "UTC"
    default_currency: str = "USD"
    max_upload_bytes: int = 5 * 1024 * 1024
    app_env: str = "development"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


def get_settings() -> Settings:
    return Settings()


def sqlite_file_path(database_url: str) -> Path:
    """Translate a sqlite:/// URL to a filesystem path."""
    if database_url.startswith("sqlite:///"):
        return Path(database_url[len("sqlite:///") :])
    if database_url.startswith("sqlite://"):
        return Path(database_url[len("sqlite://") :])
    raise ValueError(f"Only sqlite URLs are supported, got: {database_url}")
