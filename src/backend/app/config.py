"""
Configuration management - Load configuration from environment variables.
"""

import os
import warnings

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SECRETS = frozenset({
    "your-secret-key-change-in-production",
    "your-jwt-secret-change-in-production",
})

_DEFAULT_PASSWORDS = frozenset({"admin123", "password", "12345678"})


def _is_production() -> bool:
    """Check if the application is running in production mode."""
    return os.environ.get("DEBUG", "true").lower() in ("false", "0", "no")


class Settings(BaseSettings):
    """Application settings.

    Attributes:
        APP_NAME: Application name.
        DEBUG: Debug mode flag.
        SECRET_KEY: Secret key for encryption.
        DATABASE_TYPE: Database type (postgresql, mysql, mongodb, sqlite).
        DATABASE_URL: Database connection URL.
        DOCUMENT_DB_TYPE: Optional document database type.
        DOCUMENT_DB_URL: Optional document database URL.
        TIMESERIES_DB_TYPE: Optional timeseries database type.
        TIMESERIES_DB_URL: Optional timeseries database URL.
        REDIS_URL: Optional Redis cache URL.
        JWT_SECRET_KEY: JWT secret key.
        JWT_ALGORITHM: JWT encryption algorithm.
        JWT_EXPIRE_MINUTES: JWT token expiration time in minutes.
        HOST: Server host address.
        PORT: Server port.
        BACKTEST_TIMEOUT: Backtest subprocess timeout in seconds.
        CORS_ORIGINS: Comma-separated list of allowed CORS origins.
        SQL_ECHO: Whether to echo SQL statements.
        ADMIN_USERNAME: Default admin username.
        ADMIN_PASSWORD: Default admin password.
        ADMIN_EMAIL: Default admin email.
    """

    # App settings
    APP_NAME: str = "backtrader_web"
    DEBUG: bool = Field(default=True, description="Debug mode (should be False in production)")
    SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production",
        description="Secret key for encryption (CHANGE IN PRODUCTION)",
    )

    # Database settings
    DATABASE_TYPE: str = Field(
        default="sqlite", description="Database type: postgresql, mysql, mongodb, sqlite"
    )
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./backtrader.db", description="Database connection URL"
    )
    DB_AUTO_CREATE_SCHEMA: bool = Field(default=False)
    DB_AUTO_CREATE_DEFAULT_ADMIN: bool = Field(default=False)

    # Optional: Document database
    DOCUMENT_DB_TYPE: str | None = Field(default=None, description="Document database type")
    DOCUMENT_DB_URL: str | None = Field(default=None, description="Document database URL")

    # Optional: Timeseries database
    TIMESERIES_DB_TYPE: str | None = Field(default=None, description="Timeseries database type")
    TIMESERIES_DB_URL: str | None = Field(default=None, description="Timeseries database URL")

    # Optional: Redis cache
    REDIS_URL: str | None = Field(default=None, description="Redis cache URL")

    # JWT settings
    JWT_SECRET_KEY: str = Field(
        default="your-jwt-secret-change-in-production",
        description="JWT secret key (CHANGE IN PRODUCTION)",
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT encryption algorithm")
    JWT_EXPIRE_MINUTES: int = Field(
        default=10080, description="JWT token expiration in minutes (default 7 days)"
    )

    # Service settings
    # NOTE: HOST="0.0.0.0" binds to all interfaces for development convenience.
    # In production, set HOST to specific IP or use firewall rules to restrict access.
    HOST: str = Field(default="0.0.0.0", description="Server host address (use specific IP in production)")
    PORT: int = Field(default=8000, description="Server port")

    # Backtest subprocess timeout (seconds)
    BACKTEST_TIMEOUT: int = Field(default=300, description="Backtest subprocess timeout in seconds")

    # Monitoring check intervals (seconds)
    MONITORING_SYSTEM_INTERVAL: int = Field(
        default=300, description="System alert check interval in seconds"
    )
    MONITORING_ACCOUNT_INTERVAL: int = Field(
        default=30, description="Account/Position alert check interval in seconds"
    )
    MONITORING_STRATEGY_INTERVAL: int = Field(
        default=60, description="Strategy alert check interval in seconds"
    )
    MONITORING_DEFAULT_INTERVAL: int = Field(
        default=60, description="Default alert check interval in seconds"
    )

    # CORS allowed origins (comma-separated)
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000", description="Comma-separated list of allowed CORS origins"
    )

    # SQL logging (independent of DEBUG to avoid too much noise)
    SQL_ECHO: bool = Field(default=False, description="Enable SQLAlchemy query logging")

    # Default admin account
    ADMIN_USERNAME: str = Field(default="admin", description="Default admin username")
    ADMIN_PASSWORD: str = Field(
        default="admin123", description="Default admin password (CHANGE IN PRODUCTION)"
    )
    ADMIN_EMAIL: str = Field(default="admin@example.com", description="Default admin email")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("SECRET_KEY", "JWT_SECRET_KEY")
    @classmethod
    def validate_secrets_not_default(cls, v: str, info) -> str:
        """Validate that secret keys are not default values in production."""
        if _is_production() and v in _DEFAULT_SECRETS:
            raise ValueError(
                f"Default secret key detected (ENV: {info.field_name}). "
                "Please set a secure random key via environment variable in production."
            )
        return v

    @field_validator("SECRET_KEY", "JWT_SECRET_KEY")
    @classmethod
    def validate_secrets_length(cls, v: str, info) -> str:
        """Validate that secret keys have sufficient length."""
        min_length = 32
        if len(v) < min_length:
            raise ValueError(
                f"{info.field_name} must be at least {min_length} characters long "
                f"for security. Current length: {len(v)}"
            )
        return v

    @field_validator("ADMIN_PASSWORD")
    @classmethod
    def validate_admin_password_not_default(cls, v: str) -> str:
        """Validate that admin password is not the default."""
        if v.lower() in _DEFAULT_PASSWORDS:
            if _is_production():
                raise ValueError(
                    "Default admin password detected. Set ADMIN_PASSWORD to a secure password in production."
                )
            warnings.warn(
                "Insecure default admin password detected. Change ADMIN_PASSWORD before shared or production use.",
                stacklevel=2,
            )
        return v

    @field_validator("DATABASE_TYPE")
    @classmethod
    def validate_database_type(cls, v: str) -> str:
        """Validate that database type is supported."""
        supported_databases = {"sqlite", "postgresql", "mysql"}
        if v.lower() not in supported_databases:
            raise ValueError(
                f"Unsupported DATABASE_TYPE: {v}. Supported types: {', '.join(supported_databases)}"
            )
        return v.lower()

    @field_validator("PORT")
    @classmethod
    def validate_port_range(cls, v: int) -> int:
        """Validate that port is in valid range."""
        if not (1 <= v <= 65535):
            raise ValueError(f"PORT must be between 1 and 65535, got: {v}")
        return v

    @field_validator("JWT_EXPIRE_MINUTES")
    @classmethod
    def validate_jwt_expiration(cls, v: int) -> int:
        """Validate that JWT expiration is reasonable."""
        if not (5 <= v <= 10080):  # 5 minutes to 7 days
            raise ValueError(
                f"JWT_EXPIRE_MINUTES must be between 5 and 10080 (5 min to 7 days), got: {v}"
            )
        return v

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, v: str) -> str:
        """Validate that CORS origins are properly formatted."""
        if not v:
            raise ValueError("CORS_ORIGINS cannot be empty")

        origins = [o.strip() for o in v.split(",") if o.strip()]
        for origin in origins:
            if origin == "*":
                continue  # Wildcard is acceptable
            if not origin.startswith(("http://", "https://")):
                raise ValueError(
                    f"Invalid CORS origin: '{origin}'. Origins must start with http:// or https://"
                )

        return v


# Use simple cache to avoid lru_cache issues in pydantic-settings v2
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get the configuration singleton.

    Returns:
        The Settings instance.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
