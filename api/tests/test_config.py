import pytest
from pydantic import ValidationError

from core.config import Settings


def make_settings(**overrides) -> Settings:
    defaults = dict(
        google_client_id="client-id",
        google_client_secret="client-secret",
        session_secret="a-sufficiently-random-production-secret",
        token_encryption_key="a-sufficiently-random-encryption-key",
        anthropic_api_key="sk-ant-test",
        env="production",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_local_env_allows_all_defaults():
    settings = Settings(env="local")
    assert settings.session_secret == "dev-secret-change-me"
    assert settings.token_encryption_key == ""


def test_production_with_proper_secrets_succeeds():
    settings = make_settings()
    assert settings.env == "production"


def test_production_rejects_default_session_secret():
    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        make_settings(session_secret="dev-secret-change-me")


def test_production_rejects_short_session_secret():
    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        make_settings(session_secret="short")


def test_production_rejects_missing_token_encryption_key():
    with pytest.raises(ValidationError, match="TOKEN_ENCRYPTION_KEY"):
        make_settings(token_encryption_key="")


def test_production_rejects_missing_google_client_secret():
    with pytest.raises(ValidationError, match="GOOGLE_CLIENT_SECRET"):
        make_settings(google_client_secret="")


def test_production_rejects_missing_anthropic_api_key():
    with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY"):
        make_settings(anthropic_api_key="")
