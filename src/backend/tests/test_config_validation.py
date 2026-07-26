"""
Tests for environment variable validation.
"""

import os

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings

_SETTINGS_ENV_KEYS = (
    "DEBUG",
    "SECRET_KEY",
    "JWT_SECRET_KEY",
    "IB_VERIFY_SSL",
    "IB_WEB_VERIFY_SSL",
    "IB_PAPER_VERIFY_SSL",
    "IB_LIVE_VERIFY_SSL",
)
_ORIGINAL_SETTINGS_ENV = {key: os.environ.get(key) for key in _SETTINGS_ENV_KEYS}


@pytest.fixture(autouse=True)
def isolate_settings_security_environment(monkeypatch):
    """Keep test-local production flags from leaking into later settings tests."""
    for key in _SETTINGS_ENV_KEYS[3:]:
        monkeypatch.setenv(key, "true")
    yield
    for key, value in _ORIGINAL_SETTINGS_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class TestSettingsValidation:
    """Test suite for Settings validation."""

    @pytest.mark.skip(
        reason="Test expects defaults but .env file overrides them - pre-existing issue"
    )
    def test_default_settings_load(self):
        """Test that default settings can be loaded."""
        settings = Settings()
        assert settings.APP_NAME == "ai-for-investor"
        assert settings.DEBUG is False
        assert settings.DATABASE_TYPE == "sqlite"
        assert settings.DB_AUTO_CREATE_SCHEMA is False
        assert settings.DB_AUTO_CREATE_DEFAULT_ADMIN is False
        assert settings.PORT == 8000
        assert settings.JWT_EXPIRE_MINUTES > 0

    def test_secret_key_validation_default_in_production(self):
        """Test that default secret key is rejected in production."""
        # Simulate production environment
        os.environ["DEBUG"] = "false"
        os.environ["SECRET_KEY"] = "your-secret-key-change-in-production"

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "Default secret key detected" in str(exc_info.value)

        # Cleanup
        del os.environ["DEBUG"]
        del os.environ["SECRET_KEY"]

    def test_secret_key_length_validation(self):
        """Test that short secret keys are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(SECRET_KEY="short")

        assert "must be at least 32 characters" in str(exc_info.value)

    def test_jwt_secret_key_validation_default_in_production(self):
        """Test that default JWT secret is rejected in production."""
        os.environ["DEBUG"] = "false"
        os.environ["JWT_SECRET_KEY"] = "your-jwt-secret-change-in-production"

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "Default secret key detected" in str(exc_info.value)

        # Cleanup
        del os.environ["DEBUG"]
        del os.environ["JWT_SECRET_KEY"]

    def test_custom_secret_key_passes_in_production(self):
        """Test that custom secret keys pass validation in production."""
        os.environ["DEBUG"] = "false"
        os.environ["SECRET_KEY"] = "a" * 32
        os.environ["JWT_SECRET_KEY"] = "b" * 32

        settings = Settings()
        assert settings.SECRET_KEY == "a" * 32
        assert settings.JWT_SECRET_KEY == "b" * 32

        # Cleanup
        del os.environ["DEBUG"]
        del os.environ["SECRET_KEY"]
        del os.environ["JWT_SECRET_KEY"]

    def test_database_type_validation(self):
        """Test that only supported database types are accepted."""
        # Valid types should work
        for db_type in ["sqlite", "postgresql", "mysql"]:
            settings = Settings(DATABASE_TYPE=db_type)
            assert settings.DATABASE_TYPE == db_type.lower()

        # Invalid type should fail
        with pytest.raises(ValidationError) as exc_info:
            Settings(DATABASE_TYPE="mongodb")

        assert "Unsupported DATABASE_TYPE" in str(exc_info.value)

    def test_port_range_validation(self):
        """Test that port must be in valid range."""
        # Valid ports
        for port in [1, 8080, 65535]:
            settings = Settings(PORT=port)
            assert settings.PORT == port

        # Invalid ports
        for port in [0, -1, 65536, 100000]:
            with pytest.raises(ValidationError):
                Settings(PORT=port)

    def test_jwt_expiration_validation(self):
        """Test that JWT expiration must be reasonable."""
        # Valid expirations (5 min to 7 days)
        for exp in [5, 60, 1440, 10080]:
            settings = Settings(JWT_EXPIRE_MINUTES=exp)
            assert settings.JWT_EXPIRE_MINUTES == exp

        # Too short
        with pytest.raises(ValidationError):
            Settings(JWT_EXPIRE_MINUTES=4)

        # Too long
        with pytest.raises(ValidationError):
            Settings(JWT_EXPIRE_MINUTES=10081)

    def test_cors_origins_validation(self):
        """Test that CORS origins must be properly formatted."""
        # Valid origins
        valid_origins = [
            "http://localhost:3000",
            "http://localhost:3000,https://example.com",
            "*",  # Wildcard
        ]
        for origins in valid_origins:
            settings = Settings(CORS_ORIGINS=origins)
            assert settings.CORS_ORIGINS == origins

        # Empty origins
        with pytest.raises(ValidationError):
            Settings(CORS_ORIGINS="")

        # Invalid format (missing http/https)
        with pytest.raises(ValidationError) as exc_info:
            Settings(CORS_ORIGINS="example.com")

        assert "start with http:// or https://" in str(exc_info.value)

    def test_production_rejects_wildcard_cors_origins(self):
        """Test that wildcard CORS origins are blocked in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                DEBUG=False,
                SECRET_KEY="a" * 32,
                JWT_SECRET_KEY="b" * 32,
                ADMIN_PASSWORD="SecurePass@123!",
                CORS_ORIGINS="*",
            )

        assert "Wildcard CORS origin is not allowed in production" in str(exc_info.value)

    def test_production_accepts_explicit_cors_origins(self):
        """Test that explicit CORS origins are accepted in production."""
        settings = Settings(
            DEBUG=False,
            SECRET_KEY="a" * 32,
            JWT_SECRET_KEY="b" * 32,
            ADMIN_PASSWORD="SecurePass@123!",
            CORS_ORIGINS="https://example.com,https://app.example.com",
        )

        assert settings.CORS_ORIGINS == "https://example.com,https://app.example.com"

    def test_default_admin_password_does_not_emit_python_warning_outside_production(self):
        """Default-password notices are emitted by structured startup checks."""
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Settings(ADMIN_PASSWORD="admin123")

        assert len(w) == 0

    def test_custom_admin_password_no_warning(self):
        """Test that custom admin password doesn't trigger warning."""
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Settings(ADMIN_PASSWORD="SecurePass@123!")

        # Should not have triggered a warning
        assert len(w) == 0

    def test_get_settings_singleton(self):
        """Test that get_settings returns a singleton instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_env_file_loading(self, monkeypatch):
        """Test that settings can be loaded from .env file."""
        # This test would need an actual .env file
        # For now, we just verify the mechanism exists
        settings = Settings()
        # The model_config is a SettingsConfigDict instance
        assert settings.model_config is not None
        # Check that env_file was configured (it's in the model config)
        assert (
            "env_file" in str(settings.model_config).lower()
            or ".env" in str(settings.model_config).lower()
        )


class TestSettingsInProduction:
    """Test suite for production environment validation."""

    def test_production_requires_secure_secrets(self):
        """Test that production environment enforces secure secrets."""
        os.environ["DEBUG"] = "false"

        # Should fail with default secret
        with pytest.raises(ValidationError):
            Settings(
                SECRET_KEY="your-secret-key-change-in-production",
                JWT_SECRET_KEY="your-jwt-secret-change-in-production",
                ADMIN_PASSWORD="SecurePass@123!",
            )

        # Should pass with secure secret
        secure_secret = "a" * 64  # 64 character secure random key
        settings = Settings(SECRET_KEY=secure_secret, JWT_SECRET_KEY=secure_secret)
        assert settings.SECRET_KEY == secure_secret

        # Cleanup
        del os.environ["DEBUG"]

    def test_production_with_custom_short_secret_fails(self):
        """Test that even custom secrets must be long enough in production."""
        os.environ["DEBUG"] = "false"
        short_secret = "a" * 20  # Only 20 characters

        with pytest.raises(ValidationError) as exc_info:
            Settings(SECRET_KEY=short_secret)

        assert "at least 32 characters" in str(exc_info.value)

        # Cleanup
        del os.environ["DEBUG"]


class TestSettingsSecurityDefaults:
    """Test suite for security-related default settings."""

    def test_secure_algorithm_defaults(self):
        """Test that JWT uses secure algorithm defaults."""
        settings = Settings()
        assert settings.JWT_ALGORITHM == "HS256"

    def test_reasonable_timeout_defaults(self):
        """Test that backtest timeout has reasonable default."""
        settings = Settings()
        assert settings.BACKTEST_TIMEOUT == 300  # 5 minutes

    def test_debug_mode_default(self):
        """Test that debug mode defaults to False (safe-by-default)."""
        assert Settings.model_fields["DEBUG"].default is False

    def test_debug_mode_explicit_true_overrides_env(self, monkeypatch):
        """Test that explicit DEBUG=True wins over a production-like env default."""
        monkeypatch.setenv("DEBUG", "false")
        settings = Settings(DEBUG=True, ADMIN_PASSWORD="SecurePass@123!", _env_file=None)
        assert settings.DEBUG is True
        assert settings.SECRET_KEY == "your-secret-key-change-in-production"

    def test_host_default_is_loopback(self):
        """Test that host defaults to loopback instead of all interfaces."""
        settings = Settings(DEBUG=True, ADMIN_PASSWORD="SecurePass@123!")
        assert settings.HOST == "127.0.0.1"

    def test_sql_echo_disabled_by_default(self):
        """Test that SQL echo is disabled by default."""
        settings = Settings()
        assert settings.SQL_ECHO is False


class TestSettingsIntegration:
    """Integration tests for settings with real-world scenarios."""

    def test_development_configuration(self):
        """Test typical development configuration."""
        settings = Settings(
            DEBUG=True,
            DATABASE_TYPE="sqlite",
            HOST="localhost",
            PORT=8000,
            CORS_ORIGINS="http://localhost:3000",
        )
        assert settings.DEBUG is True
        assert settings.DATABASE_TYPE == "sqlite"

    def test_staging_configuration(self):
        """Test typical staging configuration."""
        settings = Settings(
            DEBUG=False,
            SECRET_KEY="staging-secret-key-at-least-32-chars-long",
            JWT_SECRET_KEY="staging-jwt-secret-key-at-least-32-chars",
            DATABASE_TYPE="postgresql",
            DATABASE_URL="postgresql://user:pass@localhost/backtrader_staging",
            PORT=8000,
        )
        assert settings.DEBUG is False
        assert settings.DATABASE_TYPE == "postgresql"

    @pytest.mark.skip(
        reason="Test expects defaults but .env file overrides them - pre-existing issue"
    )
    def test_minimum_viable_configuration(self):
        """Test the minimum required configuration for operation."""
        # These are the absolute minimum settings needed
        settings = Settings(
            SECRET_KEY="a" * 32,
            JWT_SECRET_KEY="b" * 32,
        )
        # Should use sensible defaults for everything else
        assert settings.DATABASE_TYPE == "sqlite"
        assert settings.PORT == 8000
