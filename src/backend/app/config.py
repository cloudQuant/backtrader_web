"""
Configuration management - Load configuration from environment variables.
"""

import os
import warnings
from pathlib import Path

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
    AKSHARE_DATA_DATABASE_URL: str = Field(
        default="", description="Akshare data warehouse database connection URL"
    )
    LEGACY_SQLITE_DATABASE_URL: str = Field(
        default="", description="Legacy SQLite database connection URL used during migration"
    )
    LEGACY_AKSHARE_DATABASE_URL: str = Field(
        default="", description="Legacy akshare_web database connection URL used during migration"
    )
    AKSHARE_SCHEDULER_TIMEZONE: str = Field(
        default="Asia/Shanghai", description="Scheduler timezone for akshare tasks"
    )
    AKSHARE_SCRIPT_ROOT: str = Field(
        default="app/data_fetch/scripts", description="Root directory for akshare scripts"
    )
    AKSHARE_INTERFACE_BOOTSTRAP_MODE: str = Field(
        default="manual", description="Akshare interface bootstrap mode: manual or refresh"
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
    HTTP_PROXY: str = Field(default="", description="HTTP proxy URL")
    HTTPS_PROXY: str = Field(default="", description="HTTPS proxy URL")
    SOCKS_PROXY: str = Field(default="", description="SOCKS proxy URL")
    PROXY_HOST: str = Field(default="", description="Proxy host with optional scheme")
    NO_PROXY: str = Field(default="", description="No proxy hosts")

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

    SYNC_LOCAL_MYSQL_HOST: str = Field(default="127.0.0.1", description="Local MySQL host for data sync")
    SYNC_LOCAL_MYSQL_PORT: int = Field(default=3306, description="Local MySQL port for data sync")
    SYNC_LOCAL_MYSQL_USER: str = Field(default="root", description="Local MySQL user for data sync")
    SYNC_LOCAL_MYSQL_PASSWORD: str = Field(default="", description="Local MySQL password for data sync")

    # CTP credentials (read from .env for form pre-fill)
    CTP_BROKER_ID: str = Field(default="", description="CTP broker ID")
    CTP_USER_ID: str = Field(default="", description="CTP user/investor ID")
    CTP_INVESTOR_ID: str = Field(default="", description="CTP investor ID")
    CTP_PASSWORD: str = Field(default="", description="CTP password")
    CTP_APP_ID: str = Field(default="simnow_client_test", description="CTP app ID")
    CTP_AUTH_CODE: str = Field(default="0000000000000000", description="CTP auth code")

    # MT5 credentials
    MT5_LOGIN: str = Field(default="", description="MT5 login")
    MT5_PASSWORD: str = Field(default="", description="MT5 password")
    MT5_SERVER: str = Field(default="", description="MT5 server name")
    MT5_WS_URI: str = Field(default="", description="MT5 WebSocket URI")
    MT5_DEMO_LOGIN: str = Field(default="", description="MT5 demo login")
    MT5_DEMO_PASSWORD: str = Field(default="", description="MT5 demo password")
    MT5_DEMO_SERVER: str = Field(default="", description="MT5 demo server name")
    MT5_DEMO_WS_URI: str = Field(default="", description="MT5 demo WebSocket URI")
    MT5_LIVE_LOGIN: str = Field(default="", description="MT5 live login")
    MT5_LIVE_PASSWORD: str = Field(default="", description="MT5 live password")
    MT5_LIVE_SERVER: str = Field(default="", description="MT5 live server name")
    MT5_LIVE_WS_URI: str = Field(default="", description="MT5 live WebSocket URI")
    MT5_SYMBOL_SUFFIX: str = Field(default="", description="MT5 symbol suffix")
    MT5_TIMEOUT: float = Field(default=60.0, description="MT5 request timeout in seconds")

    # IB Web credentials
    IB_ACCOUNT_ID: str = Field(default="", description="IB account ID")
    IB_ASSET_TYPE: str = Field(default="STK", description="IB asset type")
    IB_BASE_URL: str = Field(default="https://localhost:5000", description="IB Web base URL")
    IB_ACCESS_TOKEN: str = Field(default="", description="IB access token")
    IB_VERIFY_SSL: bool = Field(default=False, description="IB Web verify SSL")
    IB_TIMEOUT: float = Field(default=10.0, description="IB Web request timeout in seconds")
    IB_COOKIE_SOURCE: str = Field(default="", description="IB Web cookie source")
    IB_COOKIE_BROWSER: str = Field(default="chrome", description="IB Web cookie browser")
    IB_COOKIE_PATH: str = Field(default="/sso", description="IB Web cookie path")
    IB_USERNAME: str = Field(default="", description="IB Web username")
    IB_PASSWORD: str = Field(default="", description="IB Web password")
    IB_LOGIN_BROWSER: str = Field(default="chrome", description="IB Web login browser")
    IB_LOGIN_HEADLESS: bool = Field(default=False, description="IB Web login headless")
    IB_LOGIN_TIMEOUT: int = Field(default=180, description="IB Web login timeout in seconds")
    IB_COOKIE_OUTPUT: str = Field(default="", description="IB Web cookie output path")
    IB_WEB_ACCOUNT_ID: str = Field(default="", description="IB Web account ID")
    IB_WEB_ASSET_TYPE: str = Field(default="", description="IB Web asset type")
    IB_WEB_BASE_URL: str = Field(default="", description="IB Web base URL override")
    IB_WEB_ACCESS_TOKEN: str = Field(default="", description="IB Web access token override")
    IB_WEB_VERIFY_SSL: bool = Field(default=False, description="IB Web verify SSL override")
    IB_WEB_TIMEOUT: float = Field(default=0.0, description="IB Web request timeout override")
    IB_WEB_COOKIE_SOURCE: str = Field(default="", description="IB Web cookie source override")
    IB_WEB_COOKIE_BROWSER: str = Field(default="", description="IB Web cookie browser override")
    IB_WEB_COOKIE_PATH: str = Field(default="", description="IB Web cookie path override")
    IB_WEB_USERNAME: str = Field(default="", description="IB Web username override")
    IB_WEB_PASSWORD: str = Field(default="", description="IB Web password override")
    IB_WEB_LOGIN_MODE: str = Field(default="", description="IB Web login mode override")
    IB_WEB_LOGIN_BROWSER: str = Field(default="", description="IB Web login browser override")
    IB_WEB_LOGIN_HEADLESS: bool = Field(default=False, description="IB Web login headless override")
    IB_WEB_LOGIN_TIMEOUT: int = Field(default=0, description="IB Web login timeout override")
    IB_WEB_COOKIE_OUTPUT: str = Field(default="", description="IB Web cookie output override")
    IB_PAPER_ACCOUNT_ID: str = Field(default="", description="IB paper account ID")
    IB_PAPER_ASSET_TYPE: str = Field(default="", description="IB paper asset type")
    IB_PAPER_BASE_URL: str = Field(default="", description="IB paper base URL")
    IB_PAPER_ACCESS_TOKEN: str = Field(default="", description="IB paper access token")
    IB_PAPER_VERIFY_SSL: bool = Field(default=False, description="IB paper verify SSL")
    IB_PAPER_TIMEOUT: float = Field(default=0.0, description="IB paper request timeout in seconds")
    IB_PAPER_COOKIE_SOURCE: str = Field(default="", description="IB paper cookie source")
    IB_PAPER_COOKIE_BROWSER: str = Field(default="", description="IB paper cookie browser")
    IB_PAPER_COOKIE_PATH: str = Field(default="", description="IB paper cookie path")
    IB_LIVE_ACCOUNT_ID: str = Field(default="", description="IB live account ID")
    IB_LIVE_ASSET_TYPE: str = Field(default="", description="IB live asset type")
    IB_LIVE_BASE_URL: str = Field(default="", description="IB live base URL")
    IB_LIVE_ACCESS_TOKEN: str = Field(default="", description="IB live access token")
    IB_LIVE_VERIFY_SSL: bool = Field(default=False, description="IB live verify SSL")
    IB_LIVE_TIMEOUT: float = Field(default=0.0, description="IB live request timeout in seconds")
    IB_LIVE_COOKIE_SOURCE: str = Field(default="", description="IB live cookie source")
    IB_LIVE_COOKIE_BROWSER: str = Field(default="", description="IB live cookie browser")
    IB_LIVE_COOKIE_PATH: str = Field(default="", description="IB live cookie path")

    # Binance credentials
    BINANCE_ACCOUNT_ID: str = Field(default="", description="Binance account identifier")
    BINANCE_ASSET_TYPE: str = Field(default="SWAP", description="Binance asset type")
    BINANCE_API_KEY: str = Field(default="", description="Binance API key")
    BINANCE_SECRET_KEY: str = Field(default="", description="Binance secret key")
    BINANCE_TESTNET: bool = Field(default=False, description="Binance testnet flag")
    BINANCE_BASE_URL: str = Field(default="", description="Binance REST base URL")

    # OKX credentials
    OKX_ACCOUNT_ID: str = Field(default="", description="OKX account identifier")
    OKX_ASSET_TYPE: str = Field(default="SWAP", description="OKX asset type")
    OKX_API_KEY: str = Field(default="", description="OKX API key")
    OKX_SECRET_KEY: str = Field(default="", description="OKX secret key")
    OKX_PASSPHRASE: str = Field(default="", description="OKX passphrase")
    OKX_TESTNET: bool = Field(default=False, description="OKX testnet flag")
    OKX_BASE_URL: str = Field(default="", description="OKX REST base URL")

    model_config = SettingsConfigDict(
        env_file=(
            ".env",
            str(Path(__file__).resolve().parents[3] / ".env"),
        ),
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

    @field_validator("AKSHARE_INTERFACE_BOOTSTRAP_MODE")
    @classmethod
    def validate_akshare_interface_bootstrap_mode(cls, v: str) -> str:
        """Validate akshare interface bootstrap mode."""
        normalized = v.strip().lower()
        supported_modes = {"manual", "refresh"}
        if normalized not in supported_modes:
            raise ValueError(
                "AKSHARE_INTERFACE_BOOTSTRAP_MODE must be one of: "
                f"{', '.join(sorted(supported_modes))}"
            )
        return normalized

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
