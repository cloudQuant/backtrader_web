"""
Configuration management - Load configuration from environment variables.
"""
import os
from typing import Optional
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
    DEBUG: bool = True
    SECRET_KEY: str = "your-secret-key-change-in-production"

    # Database settings
    DATABASE_TYPE: str = "sqlite"  # postgresql, mysql, mongodb, sqlite
    DATABASE_URL: str = "sqlite+aiosqlite:///./backtrader.db"

    # Optional: Document database
    DOCUMENT_DB_TYPE: Optional[str] = None
    DOCUMENT_DB_URL: Optional[str] = None

    # Optional: Timeseries database
    TIMESERIES_DB_TYPE: Optional[str] = None
    TIMESERIES_DB_URL: Optional[str] = None

    # Optional: Redis cache
    REDIS_URL: Optional[str] = None

    # JWT settings
    JWT_SECRET_KEY: str = "your-jwt-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Service settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Backtest subprocess timeout (seconds)
    BACKTEST_TIMEOUT: int = 300

    # CORS allowed origins (comma-separated)
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # SQL logging (independent of DEBUG to avoid too much noise)
    SQL_ECHO: bool = False

    # Default admin account
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    ADMIN_EMAIL: str = "admin@example.com"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Use simple cache to avoid lru_cache issues in pydantic-settings v2
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the configuration singleton.

    Returns:
        The Settings instance.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
