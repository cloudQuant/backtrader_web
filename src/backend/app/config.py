"""
Configuration management - Load configuration from environment variables.
"""

import os

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    HOST: str = Field(default="0.0.0.0", description="Server host address")
    PORT: int = Field(default=8000, description="Server port")

    # Backtest subprocess timeout (seconds)
    BACKTEST_TIMEOUT: int = Field(default=300, description="Backtest subprocess timeout in seconds")

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
        """Validate that secret keys are not default values in production.

        Args:
            v: The secret key value.
            info: Field validation info.

        Returns:
            The validated secret key.

        Raises:
            ValueError: If default secret is used in production environment.
        """
        # Check if running in production (DEBUG=False)
        debug_value = os.environ.get("DEBUG", "true").lower()
        is_production = debug_value in ("false", "0", "no")

        default_secrets = {
            "your-secret-key-change-in-production",
            "your-jwt-secret-change-in-production",
        }

        if is_production and v in default_secrets:
            raise ValueError(
                f"Default secret key detected (ENV: {info.field_name}). "
                "Please set a secure random key via environment variable in production."
            )

        return v

    @field_validator("SECRET_KEY", "JWT_SECRET_KEY")
    @classmethod
    def validate_secrets_length(cls, v: str, info) -> str:
        """Validate that secret keys have sufficient length.

        Args:
            v: The secret key value.
            info: Field validation info.

        Returns:
            The validated secret key.

        Raises:
            ValueError: If secret key is too short.
        """
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
        """Validate that admin password is not the default.

        Args:
            v: The admin password value.

        Returns:
            The validated password.

        Raises:
            ValueError: If default password is used.
        """
        default_passwords = {"admin123", "password", "12345678"}
        if v.lower() in default_passwords:
            debug_value = os.environ.get("DEBUG", "true").lower()
            is_production = debug_value in ("false", "0", "no")
            if is_production:
                raise ValueError(
                    "Default admin password detected. Set ADMIN_PASSWORD to a secure password in production."
                )
        return v

    @field_validator("DATABASE_TYPE")
    @classmethod
    def validate_database_type(cls, v: str) -> str:
        """Validate that database type is supported.

        Args:
            v: The database type value.

        Returns:
            The validated database type.

        Raises:
            ValueError: If database type is not supported.
        """
        supported_databases = {"sqlite", "postgresql", "mysql"}
        if v.lower() not in supported_databases:
            raise ValueError(
                f"Unsupported DATABASE_TYPE: {v}. Supported types: {', '.join(supported_databases)}"
            )
        return v.lower()

    @field_validator("PORT")
    @classmethod
    def validate_port_range(cls, v: int) -> int:
        """Validate that port is in valid range.

        Args:
            v: The port value.

        Returns:
            The validated port.

        Raises:
            ValueError: If port is out of valid range.
        """
        if not (1 <= v <= 65535):
            raise ValueError(f"PORT must be between 1 and 65535, got: {v}")
        return v

    @field_validator("JWT_EXPIRE_MINUTES")
    @classmethod
    def validate_jwt_expiration(cls, v: int) -> int:
        """Validate that JWT expiration is reasonable.

        Args:
            v: The expiration minutes value.

        Returns:
            The validated expiration.

        Raises:
            ValueError: If expiration is too short or too long.
        """
        if not (5 <= v <= 10080):  # 5 minutes to 7 days
            raise ValueError(
                f"JWT_EXPIRE_MINUTES must be between 5 and 10080 (5 min to 7 days), got: {v}"
            )
        return v

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, v: str) -> str:
        """Validate that CORS origins are properly formatted.

        Args:
            v: The CORS origins string.

        Returns:
            The validated CORS origins.

        Raises:
            ValueError: If CORS origins contain invalid entries.
        """
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
