from __future__ import annotations

from unittest.mock import patch

import pytest

from app.infrastructure.config.settings import Settings


def test_settings_defaults():
    with patch.dict("os.environ", {
        "APP_ENV": "development",
        "JWT_SECRET_KEY": "test-secret-key-that-is-at-least-32-characters-long",
        "DEBUG": "false",
    }, clear=False):
        settings = Settings(_env_file=None)
    assert settings.app_name == "IntentLock"
    assert settings.app_env == "development"
    assert settings.debug is False
    assert settings.cors_origins == ["http://localhost:3000"]


def test_settings_cors_origins_string_list():
    with patch.dict("os.environ", {
        "CORS_ORIGINS": '["https://a.com"]',
        "JWT_SECRET_KEY": "test-secret-key-that-is-at-least-32-characters-long",
    }, clear=False):
        settings = Settings(_env_file=None)
    assert settings.cors_origins == ["https://a.com"]


def test_settings_rejects_change_me_secret():
    with pytest.raises(ValueError, match="must be replaced"):
        Settings(
            jwt_secret_key="change-me-1234567890123456789012345678",
            _env_file=None,
        )


def test_settings_production_requires_jwt():
    with patch.dict(
        "os.environ",
        {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql://localhost/intentlock",
        },
        clear=True,
    ), pytest.raises(ValueError, match="JWT_SECRET_KEY must be configured explicitly"):
        Settings(_env_file=None)


def test_settings_production_requires_redis_url():
    with patch.dict("os.environ", {
        "APP_ENV": "production",
        "JWT_SECRET_KEY": "secure-key-1234567890123456789012345678",
        "DATABASE_URL": "postgresql://localhost/intentlock",
    }, clear=True), pytest.raises(ValueError, match="REDIS_URL must be configured"):
        Settings(_env_file=None)


def test_settings_production_requires_redis_enabled():
    with patch.dict("os.environ", {
        "APP_ENV": "production",
        "JWT_SECRET_KEY": "secure-key-1234567890123456789012345678",
        "DATABASE_URL": "postgresql://localhost/intentlock",
        "REDIS_URL": "redis://localhost:6379/0",
    }, clear=True), pytest.raises(ValueError, match="Redis replay protection cannot be disabled"):
        Settings(redis_enabled=False, _env_file=None)


def test_settings_production_requires_postgres():
    with patch.dict("os.environ", {
        "APP_ENV": "production",
        "JWT_SECRET_KEY": "secure-key-1234567890123456789012345678",
        "REDIS_URL": "redis://localhost:6379/0",
    }, clear=True), pytest.raises(ValueError, match="must use a PostgreSQL DATABASE_URL"):
        Settings(database_url="sqlite:///./test.db", _env_file=None)


def test_settings_parse_trusted_proxies():
    with patch.dict("os.environ", {
        "TRUSTED_PROXIES": '["10.0.0.1", "10.0.0.2"]',
        "JWT_SECRET_KEY": "test-secret-key-that-is-at-least-32-characters-long",
    }, clear=False):
        settings = Settings(_env_file=None)
    assert settings.trusted_proxies == ["10.0.0.1", "10.0.0.2"]


def test_settings_parse_role_actions():
    with patch.dict("os.environ", {
        "AUTHORIZATION_ROLE_ACTIONS": '{"admin": ["read", "write"]}',
        "JWT_SECRET_KEY": "test-secret-key-that-is-at-least-32-characters-long",
    }, clear=False):
        settings = Settings(_env_file=None)
    assert settings.authorization_role_actions == {"admin": ["read", "write"]}
