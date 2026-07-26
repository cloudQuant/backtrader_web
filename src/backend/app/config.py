"""
Configuration management - Load configuration from environment variables.
"""

import json
import os
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ai_provider_registry import get_default_provider_registry

_DEFAULT_SECRETS = frozenset(
    {
        "your-secret-key-change-in-production",
        "your-jwt-secret-change-in-production",
    }
)

_DEFAULT_PASSWORDS = frozenset({"admin123", "password", "12345678"})
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SQLITE_DATABASE_URL = (
    f"sqlite+aiosqlite:///{(_REPO_ROOT / 'data' / 'dev' / 'backtrader.db').as_posix()}"
)


def _coerce_bool(value: object) -> bool | None:
    """Coerce common boolean-like values from settings inputs or env vars."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return None


def _is_production(debug: object | None = None, *, debug_was_explicit: bool = False) -> bool:
    """Check if the application should apply production-only safeguards."""
    normalized_debug = _coerce_bool(debug)
    if debug_was_explicit and normalized_debug is not None:
        return not normalized_debug
    env_debug = _coerce_bool(os.environ.get("DEBUG"))
    if env_debug is not None:
        return not env_debug
    return False


def production_security_mode(settings: "Settings") -> bool:
    """Return whether production-only runtime security guards apply."""
    return _is_production(
        settings.DEBUG,
        debug_was_explicit="DEBUG" in settings.model_fields_set,
    )


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
    APP_NAME: str = "ai-for-investor"
    DEBUG: bool = Field(default=False, description="Debug mode (must remain False in production)")
    SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production",
        description="Secret key for encryption (CHANGE IN PRODUCTION)",
    )

    # Database settings
    DATABASE_TYPE: str = Field(
        default="sqlite", description="Database type: postgresql, mysql, mongodb, sqlite"
    )
    DATABASE_URL: str = Field(
        default=_DEFAULT_SQLITE_DATABASE_URL, description="Database connection URL"
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
    AKSHARE_SCHEDULER_MAX_CONCURRENT_TASKS: int = Field(
        default=1,
        ge=1,
        description="Maximum concurrent akshare scheduler-triggered tasks",
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
        default=60, description="JWT token expiration in minutes (default 1 hour)"
    )

    # Rate limiting (slowapi limit strings). E2E environments can raise these
    # quotas explicitly without weakening production brute-force protection.
    RATE_LIMIT_REGISTER: str = Field(
        default="5/hour", description="Rate limit for POST /auth/register (slowapi string)"
    )
    RATE_LIMIT_LOGIN: str = Field(
        default="10/minute", description="Rate limit for POST /auth/login (slowapi string)"
    )
    RATE_LIMIT_AUTH_ME: str = Field(
        default="60/minute", description="Rate limit for GET /auth/me (slowapi string)"
    )

    # Service settings
    # NOTE: defaults to 127.0.0.1 (loopback) for safety. Production / docker
    # deployments should override via HOST=0.0.0.0 in their env files.
    HOST: str = Field(
        default="127.0.0.1",
        description="Server host address (override to 0.0.0.0 in containers/production)",
    )
    PORT: int = Field(default=8000, description="Server port")
    AI_CHAT_ENABLED: bool = Field(
        default=False, description="Enable generated AI responses for knowledge-base chat"
    )
    AI_CHAT_BASE_URL: str = Field(
        default="", description="Base URL for an OpenAI-compatible chat completions endpoint"
    )
    AI_CHAT_API_KEY: str = Field(default="", description="API key for AI chat provider")
    AI_CHAT_MODEL: str = Field(default="", description="Model name for AI chat provider")
    AI_CHAT_TIMEOUT: float = Field(
        default=120.0, description="Timeout for AI chat provider requests in seconds"
    )
    AI_CHAT_TEMPERATURE: float = Field(
        default=0.2, description="Sampling temperature for AI chat provider requests"
    )
    AI_CHAT_MAX_TOKENS: int = Field(
        default=4096,
        ge=512,
        le=32768,
        description="Maximum tokens requested from the AI chat provider",
    )
    RAG_VECTOR_ENABLED: bool = Field(
        default=True,
        description="Enable local vector retrieval for knowledge-base chat",
    )
    RAG_EMBEDDING_MODEL: str = Field(
        default="BAAI/bge-small-zh-v1.5",
        description="Sentence Transformers model used for local RAG embeddings",
    )
    RAG_VECTOR_COLLECTION: str = Field(
        default="knowledge_base_documents_v3",
        description="Local Chroma collection name for knowledge-base document vectors",
    )
    RAG_VECTOR_UPSERT_BATCH_SIZE: int = Field(
        default=128,
        ge=16,
        le=512,
        description="Document vectors processed in one local Chroma upsert batch",
    )
    RAG_LLM_RERANK_TIMEOUT: float = Field(
        default=30.0,
        ge=5.0,
        le=120.0,
        description="Maximum seconds for the short knowledge-base rerank call",
    )
    AI_BUDGET_DAILY_USD: float | None = Field(
        default=None, description="Default daily AI cost budget in USD. None means unlimited"
    )
    AI_BUDGET_MODE: str = Field(default="soft", description="AI budget mode: soft or hard")
    AI_PROVIDERS: dict[str, dict[str, Any]] = Field(
        default_factory=get_default_provider_registry,
        description="AI provider registry keyed by provider name",
    )
    STRATEGY_SCORE_MODEL_VERSION: str = Field(
        default="v1", description="Model version for strategy score outputs"
    )
    STRATEGY_SCORE_WEIGHTS: dict[str, float] = Field(
        default_factory=lambda: {
            "profitability": 0.2,
            "risk_control": 0.2,
            "stability": 0.2,
            "overfitting_risk": 0.15,
            "executability": 0.15,
            "benchmark_comparison": 0.1,
        },
        description="Strategy score dimension weights",
    )

    # Graceful shutdown timeout (seconds)
    SHUTDOWN_TIMEOUT: int = Field(
        default=30,
        description="Graceful shutdown timeout in seconds (range 1-300)",
    )

    # Backtest subprocess timeout (seconds)
    BACKTEST_TIMEOUT: int = Field(default=300, description="Backtest subprocess timeout in seconds")
    AI_STRATEGY_SANDBOX_USE_DOCKER: bool = Field(
        default=True,
        description="Require Docker isolation for AI strategy draft validation in production",
    )
    AI_STRATEGY_SANDBOX_DOCKER_IMAGE: str = Field(
        default="backtrader-sandbox:latest",
        description="Docker image used for AI strategy draft validation",
    )

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

    # Logging format: "json" for structured JSON, "text" for plain text.
    # If unset, falls back to DEBUG-based default (DEBUG=true → colored text, DEBUG=false → JSON).
    LOG_FORMAT: str = Field(
        default="",
        description="Log output format: 'json' for structured JSON, 'text' for plain text, "
        "empty for auto-detection based on DEBUG flag",
    )

    # Log level override: when set, overrides the DEBUG-based default level.
    # Valid values: DEBUG, INFO, WARNING, ERROR, CRITICAL (case-insensitive).
    LOG_LEVEL: str = Field(
        default="",
        description="Explicit log level override. Empty = auto (DEBUG→DEBUG, prod→WARNING/INFO)",
    )

    # Log output directory
    LOG_DIR: str = Field(default="./logs", description="Log output directory path")

    # Log retention periods per category (days)
    LOG_RETENTION_APP_DAYS: int = Field(default=30, description="Application log retention in days")
    LOG_RETENTION_ERROR_DAYS: int = Field(default=90, description="Error log retention in days")
    LOG_RETENTION_AUDIT_DAYS: int = Field(default=365, description="Audit log retention in days")
    LOG_ROTATION_MAX_MB: int = Field(
        default=100,
        description="Maximum size in MB for each dated log file before rotation; 0 disables size cap",
    )

    # Audit settings
    AUDIT_RETENTION_DAYS: int = Field(
        default=90, description="Database audit record retention in days (7-365)"
    )
    AUDIT_CLEANUP_HOUR: int = Field(
        default=2, description="Hour of day to run audit cleanup (0-23)"
    )
    AUDIT_EVENT_MAX_SIZE_KB: int = Field(
        default=10, description="Maximum size of a single audit event_data in KB (1-100)"
    )

    # Airflow integration settings
    AIRFLOW_API_BASE_URL: str = Field(
        default="", description="Airflow REST API base URL (e.g. http://localhost:8080/api/v1)"
    )
    AIRFLOW_USERNAME: str = Field(default="admin", description="Airflow API username")
    AIRFLOW_PASSWORD: str = Field(default="", description="Airflow API password")
    ORCHESTRATION_BACKEND: str = Field(
        default="auto",
        description="Orchestration backend: airflow, apscheduler, auto (auto-detect)",
    )
    AIRFLOW_DAG_OUTPUT_DIR: str = Field(
        default="./dags", description="Directory for generated Airflow DAG files"
    )
    AIRFLOW_CALLBACK_BASE_URL: str = Field(
        default="http://localhost:8000",
        description="Base URL for Airflow task callbacks to ai-for-investor",
    )

    # SQL logging (independent of DEBUG to avoid too much noise)
    SQL_ECHO: bool = Field(default=False, description="Enable SQLAlchemy query logging")

    # Default admin account
    ADMIN_USERNAME: str = Field(default="admin", description="Default admin username")
    ADMIN_PASSWORD: str = Field(
        default="admin123", description="Default admin password (CHANGE IN PRODUCTION)"
    )
    ADMIN_EMAIL: str = Field(default="admin@example.com", description="Default admin email")

    SYNC_LOCAL_MYSQL_HOST: str = Field(
        default="127.0.0.1", description="Local MySQL host for data sync"
    )
    SYNC_LOCAL_MYSQL_PORT: int = Field(default=3306, description="Local MySQL port for data sync")
    SYNC_LOCAL_MYSQL_USER: str = Field(default="root", description="Local MySQL user for data sync")
    SYNC_LOCAL_MYSQL_PASSWORD: str = Field(
        default="", description="Local MySQL password for data sync"
    )

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
    IB_VERIFY_SSL: bool = Field(default=True, description="IB Web verify SSL")
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
    IB_WEB_VERIFY_SSL: bool = Field(default=True, description="IB Web verify SSL override")
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
    IB_PAPER_VERIFY_SSL: bool = Field(default=True, description="IB paper verify SSL")
    IB_PAPER_TIMEOUT: float = Field(default=0.0, description="IB paper request timeout in seconds")
    IB_PAPER_COOKIE_SOURCE: str = Field(default="", description="IB paper cookie source")
    IB_PAPER_COOKIE_BROWSER: str = Field(default="", description="IB paper cookie browser")
    IB_PAPER_COOKIE_PATH: str = Field(default="", description="IB paper cookie path")
    IB_LIVE_ACCOUNT_ID: str = Field(default="", description="IB live account ID")
    IB_LIVE_ASSET_TYPE: str = Field(default="", description="IB live asset type")
    IB_LIVE_BASE_URL: str = Field(default="", description="IB live base URL")
    IB_LIVE_ACCESS_TOKEN: str = Field(default="", description="IB live access token")
    IB_LIVE_VERIFY_SSL: bool = Field(default=True, description="IB live verify SSL")
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

    @model_validator(mode="after")
    def validate_runtime_security_guards(self) -> "Settings":
        """Validate production-only secret and admin-password guards."""
        if production_security_mode(self):
            cors_origins = {
                origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()
            }
            if "*" in cors_origins:
                raise ValueError(
                    "Wildcard CORS origin is not allowed in production when credentials are enabled. "
                    "Set CORS_ORIGINS to explicit http:// or https:// origins."
                )
            for field_name in ("SECRET_KEY", "JWT_SECRET_KEY"):
                if getattr(self, field_name) in _DEFAULT_SECRETS:
                    raise ValueError(
                        f"Default secret key detected (ENV: {field_name}). "
                        "Please set a secure random key via environment variable in production."
                    )
            if self.ADMIN_PASSWORD.lower() in _DEFAULT_PASSWORDS:
                raise ValueError(
                    "Default admin password detected. Set ADMIN_PASSWORD to a secure password in production."
                )
            for field_name in (
                "IB_VERIFY_SSL",
                "IB_WEB_VERIFY_SSL",
                "IB_PAPER_VERIFY_SSL",
                "IB_LIVE_VERIFY_SSL",
            ):
                if not getattr(self, field_name):
                    raise ValueError(
                        f"{field_name}=False is not allowed in production. "
                        "Install the gateway CA certificate and enable TLS verification."
                    )
            if not self.AI_STRATEGY_SANDBOX_USE_DOCKER:
                raise ValueError(
                    "AI_STRATEGY_SANDBOX_USE_DOCKER must be enabled in production. "
                    "AI-generated strategy code cannot run in the application process."
                )
        return self

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

    @field_validator("SHUTDOWN_TIMEOUT")
    @classmethod
    def validate_shutdown_timeout(cls, v: int) -> int:
        """Validate that shutdown timeout is in valid range (1-300)."""
        if not (1 <= v <= 300):
            import logging

            logging.getLogger(__name__).warning(
                "SHUTDOWN_TIMEOUT=%d is out of range (1-300), using default 30s", v
            )
            return 30
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

    @field_validator("AI_BUDGET_MODE")
    @classmethod
    def validate_ai_budget_mode(cls, v: str) -> str:
        normalized = str(v or "soft").strip().lower()
        supported_modes = {"soft", "hard"}
        if normalized not in supported_modes:
            raise ValueError(f"AI_BUDGET_MODE must be one of: {', '.join(sorted(supported_modes))}")
        return normalized

    @field_validator("AI_PROVIDERS", mode="before")
    @classmethod
    def validate_ai_providers(cls, v: object) -> dict[str, dict[str, Any]]:
        if isinstance(v, dict):
            return {str(key): dict(value) for key, value in v.items() if isinstance(value, dict)}
        if isinstance(v, str):
            text = v.strip()
            if not text:
                raise ValueError("AI_PROVIDERS cannot be empty")
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("AI_PROVIDERS must be valid JSON") from exc
            if not isinstance(data, dict):
                raise ValueError("AI_PROVIDERS must decode to an object")
            return {str(key): dict(value) for key, value in data.items() if isinstance(value, dict)}
        if v is None:
            raise ValueError("AI_PROVIDERS cannot be null")
        raise ValueError("AI_PROVIDERS must be a dict or JSON string")

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

    @field_validator("STRATEGY_SCORE_WEIGHTS", mode="before")
    @classmethod
    def validate_strategy_score_weights(cls, v: object) -> dict[str, float]:
        """Validate strategy score weights from dict or JSON string."""
        if isinstance(v, dict):
            return {str(key): float(value) for key, value in v.items()}
        if isinstance(v, str):
            text = v.strip()
            if not text:
                raise ValueError("STRATEGY_SCORE_WEIGHTS cannot be empty")
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("STRATEGY_SCORE_WEIGHTS must be valid JSON") from exc
            if not isinstance(data, dict):
                raise ValueError("STRATEGY_SCORE_WEIGHTS must decode to an object")
            return {str(key): float(value) for key, value in data.items()}
        if v is None:
            raise ValueError("STRATEGY_SCORE_WEIGHTS cannot be null")
        raise ValueError("STRATEGY_SCORE_WEIGHTS must be a dict or JSON string")


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
