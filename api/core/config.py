from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres (async app runtime + sync alembic migrations)
    database_url: str = "postgresql+asyncpg://inbox:inbox@localhost:5432/inbox_concierge"
    database_url_sync: str = "postgresql+psycopg2://inbox:inbox@localhost:5432/inbox_concierge"

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
