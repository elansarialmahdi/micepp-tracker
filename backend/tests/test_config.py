import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_origins_are_parsed_from_comma_separated_value() -> None:
    settings = Settings(allowed_origins="https://one.example, https://two.example")
    assert settings.allowed_origins == ["https://one.example", "https://two.example"]


def test_origins_are_parsed_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://one.example,https://two.example")
    settings = Settings(_env_file=None)
    assert settings.allowed_origins == ["https://one.example", "https://two.example"]


def test_default_secret_is_rejected_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", app_secret_key="development-only-change-me")


def test_security_rate_limits_cannot_be_disabled_with_zero() -> None:
    with pytest.raises(ValidationError):
        Settings(scan_create_rate_limit=0)


def test_wildcard_cors_is_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="ALLOWED_ORIGINS"):
        Settings(
            app_env="production",
            app_secret_key="production-secret",
            jwt_algorithm="RS256",
            jwt_private_key="private-key",
            jwt_public_key="public-key",
            allowed_origins="*",
        )
