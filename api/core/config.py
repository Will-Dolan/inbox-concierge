import os
from functools import lru_cache
from urllib.parse import urlparse, urlunparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres (async app runtime + sync alembic migrations)
    database_url: str = "postgresql+asyncpg://inbox:inbox@localhost:5432/inbox_concierge"
    database_url_sync: str = "postgresql+psycopg2://inbox:inbox@localhost:5432/inbox_concierge"

    @field_validator("database_url", mode="before")
    @classmethod
    def ensure_async_driver(cls, v: str) -> str:
        """Railway's Postgres plugin injects DATABASE_URL as
        'postgresql://...', which defaults SQLAlchemy to the sync
        psycopg2 driver. The async engine requires 'postgresql+asyncpg://',
        so rewrite the scheme when DATABASE_URL is provided by the
        environment, while leaving the local dev default untouched.
        """
        raw = os.environ.get("DATABASE_URL")
        if not raw:
            return v

        parsed = urlparse(raw)
        if parsed.scheme == "postgresql":
            parsed = parsed._replace(scheme="postgresql+asyncpg")
            return urlunparse(parsed)

        return raw

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    # Session cookie
    session_secret: str = "dev-secret-change-me"

    # Refresh-token encryption at rest (Fernet key material; falls back to
    # session_secret in dev if unset — set a dedicated key in production)
    token_encryption_key: str = ""

    # Anthropic
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"

    # App
    env: str = "local"
    frontend_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
