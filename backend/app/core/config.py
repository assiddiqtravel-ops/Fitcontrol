"""Application configuration loaded from environment variables.

Secrets are ONLY sourced from the environment (see .env.example). Nothing
sensitive is hard-coded. See README for the full list of variables.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Environment ---
    environment: str = Field(default="development")  # development | production
    app_name: str = "FitControl"
    api_v1_prefix: str = "/api/v1"

    # --- Database ---
    # Async SQLAlchemy URL. For Postgres: postgresql+asyncpg://user:pass@host:5432/db
    database_url: str = Field(
        default="postgresql+asyncpg://fitcontrol:fitcontrol@localhost:5432/fitcontrol"
    )

    # --- Telegram ---
    # Bot token from BotFather. Used both to run the bot and to validate initData.
    telegram_bot_token: str = Field(default="")
    # Public URL where the Mini App is served (https). Bot opens this as a WebApp.
    webapp_url: str = Field(default="")
    # Max age (seconds) accepted for initData auth_date freshness.
    initdata_max_age_seconds: int = Field(default=86400)

    # --- Auth / security ---
    # DEV_AUTH_MODE lets the API accept an unsigned dev identity header. It is
    # OFF by default and HARD-BLOCKED when environment == production.
    dev_auth_mode: bool = Field(default=False)
    # Comma-separated list of allowed CORS origins. "*" only for local dev.
    cors_origins: str = Field(default="*")

    # --- Notifications / scheduler ---
    # Default IANA timezone used for daily summaries when a club has none set.
    default_timezone: str = Field(default="Asia/Tashkent")
    # Run the notification scheduler inside the API process (dev convenience).
    enable_scheduler: bool = Field(default=False)
    # Hour (0-23, club-local) at which the daily summary is sent.
    daily_summary_hour: int = Field(default=9)
    # Days-before-expiry threshold for "ending soon" reminders.
    expiry_reminder_days: int = Field(default=3)

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    def effective_dev_auth(self) -> bool:
        """DEV_AUTH_MODE is never honored in production."""
        return self.dev_auth_mode and not self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
