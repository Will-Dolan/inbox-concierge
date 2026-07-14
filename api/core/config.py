import os
from functools import lru_cache
from urllib.parse import urlparse, urlunparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SESSION_SECRET = "dev-secret-change-me"
MIN_SESSION_SECRET_LENGTH = 16


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
    google_redirect_uri: str = "${{RAILWAY_PUBLIC_DOMAIN}}/auth/google/callback"

    # Session cookie
    session_secret: str = DEFAULT_SESSION_SECRET

    # Refresh-token encryption at rest (Fernet key material; falls back to
    # session_secret in dev if unset — a dedicated key is required in
    # production, enforced below)
    token_encryption_key: str = ""

    # Anthropic
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"

    # App
    env: str = "local"
    frontend_origin: str = "http://localhost:5173"

    @model_validator(mode="after")
    def guard_against_weak_production_secrets(self) -> "Settings":
        """Fail fast rather than silently running a production deploy with
        insecure defaults. `session_secret` signs session JWTs (core/session.py)
        and, absent a dedicated `token_encryption_key`, also derives the Fernet
        key that encrypts Gmail refresh tokens at rest (core/crypto.py) — so a
        weak/default secret compromises both session integrity and token
        confidentiality. Local dev (env="local") is intentionally exempt.
        """
        if self.env == "local":
            return self

        if self.session_secret == DEFAULT_SESSION_SECRET:
            raise ValueError(
                "SESSION_SECRET is still set to the insecure default "
                "'dev-secret-change-me'. Set a unique, random SESSION_SECRET "
                "before running with ENV != local."
            )
        if len(self.session_secret) < MIN_SESSION_SECRET_LENGTH:
            raise ValueError(
                f"SESSION_SECRET is only {len(self.session_secret)} characters. "
                f"Set SESSION_SECRET to a random value of at least "
                f"{MIN_SESSION_SECRET_LENGTH} characters before running with "
                "ENV != local."
            )
        if not self.token_encryption_key:
            raise ValueError(
                "TOKEN_ENCRYPTION_KEY is unset. Falling back to reusing "
                "SESSION_SECRET for refresh-token encryption is only allowed "
                "in local dev — set a dedicated TOKEN_ENCRYPTION_KEY before "
                "running with ENV != local."
            )
        if not self.google_client_secret:
            raise ValueError(
                "GOOGLE_CLIENT_SECRET is unset. Set it before running with "
                "ENV != local — Google OAuth cannot function without it."
            )
        if not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is unset. Set it before running with "
                "ENV != local — classification/agent features cannot "
                "function without it."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
