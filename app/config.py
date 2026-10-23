"""
Application configuration loaded from environment variables.

Uses Pydantic Settings for type-safe env parsing with validation.
All secrets come from env vars (Render dashboard in production, .env locally).
"""

import sys
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration — every value comes from an env var or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Supabase ---
    supabase_url: str = "https://demo-project.supabase.co"
    supabase_anon_key: str = "demo-anon-key"
    supabase_service_role_key: str = "demo-service-role-key"

    @field_validator("supabase_url", mode="before")
    @classmethod
    def clean_supabase_url(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip().rstrip("/")
            if v.endswith("/rest/v1"):
                v = v[:-8]
        return v

    # --- Gemini AI ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"

    # --- Meta Messenger Platform ---
    meta_app_secret: str = ""
    meta_page_access_token: str = ""
    meta_verify_token: str = ""
    facebook_page_id: str = ""

    # --- Telegram Reports ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # --- Internal API Security ---
    internal_api_token: str = ""

    # --- Application ---
    # Defaults to production so a missing APP_ENV never enables the dev login
    # bypass or the API docs; set APP_ENV=development in your local .env.
    app_env: str = "production"
    # Public URL of this app; used to build links in password-reset / email-change emails.
    # Must also be listed in Supabase → Auth → URL Configuration → Redirect URLs.
    app_base_url: str = "http://localhost:8080"

    @field_validator("app_base_url", mode="before")
    @classmethod
    def clean_app_base_url(cls, v: str) -> str:
        return v.strip().rstrip("/") if isinstance(v, str) else v

    # --- Human-like replies ---
    # typing_on + a short pause before each reply; always off under pytest
    enable_typing_delay: bool = True

    @field_validator("enable_typing_delay", mode="after")
    @classmethod
    def disable_typing_delay_in_tests(cls, v: bool) -> bool:
        return v and "pytest" not in sys.modules

    # --- Store (single-store bootstrap) ---
    default_store_id: str = "00000000-0000-0000-0000-000000000001"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings singleton.

    Returns the same Settings instance for the lifetime of the process.
    In tests, override via FastAPI dependency injection.
    """
    return Settings()
