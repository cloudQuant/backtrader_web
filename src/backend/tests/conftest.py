"""
Pytest Configuration and Fixtures.

Provides shared fixtures and configuration for all tests.
Uses httpx.AsyncClient + ASGITransport for direct FastAPI app testing.
Each test uses an independent in-memory SQLite database (shared connection via StaticPool).
"""

import asyncio
import importlib
import logging
import os
import tempfile
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Ensure test environment configuration (before any app imports)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("SQL_ECHO", "false")
os.environ.setdefault("ADMIN_PASSWORD", "TestAdmin@12345")
# Keep rate-limit assertions independent of a developer's permissive local
# `.env` values.  These are the documented security defaults exercised by the
# auth and header integration tests.
os.environ["RATE_LIMIT_REGISTER"] = "5/hour"
os.environ["RATE_LIMIT_LOGIN"] = "10/minute"
# Tests must never inherit a developer's configured AI endpoint or credentials.
# Individual provider tests patch their own settings explicitly.
os.environ["AI_CHAT_ENABLED"] = "false"
os.environ["AI_CHAT_BASE_URL"] = ""
os.environ["AI_CHAT_API_KEY"] = ""
os.environ["AI_CHAT_MODEL"] = ""
_TEST_LOG_DIR = Path(tempfile.mkdtemp(prefix="backtrader_web_pytest_logs_"))
os.environ["LOG_DIR"] = str(_TEST_LOG_DIR)

for noisy_logger in ("aiosqlite", "aiosqlite.core"):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

importlib.import_module("app.models")
db_module = importlib.import_module("app.db.database")
Base = db_module.Base
limiter = importlib.import_module("app.rate_limit").limiter

# Override database engine and session factory: use StaticPool to share one connection for in-memory SQLite during tests
_test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)
_test_session_maker = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)

# Monkey patch: make all services use test database
db_module.engine = _test_engine
db_module.async_session_maker = _test_session_maker

# Also patch modules that imported async_session_maker by value before the test override.
for module_name in [
    "app.db.session_provider",
    "app.db.sql_repository",
    "app.services.backtest.manager",
]:
    importlib.import_module(module_name).async_session_maker = _test_session_maker

app = importlib.import_module("app.main").app
_ai_log_module = importlib.import_module("app.services.ai_observability.logger")


# ==================== Database Fixtures ====================


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Ensure pytest-asyncio sees an explicit loop-scope default."""
    config.inicfg["asyncio_default_fixture_loop_scope"] = "function"


def pytest_sessionfinish(session, exitstatus):
    """Dispose the shared async engine so aiosqlite worker threads can exit."""
    for noisy_logger in ("aiosqlite", "aiosqlite.core"):
        logging.getLogger(noisy_logger).disabled = True
    asyncio.run(_test_engine.dispose())


@pytest.fixture(autouse=True)
def disable_live_gateway_restore(monkeypatch, tmp_path):
    live_trading_manager = importlib.import_module("app.services.live_trading_manager")
    instance_store = importlib.import_module("app.services.instance_store")
    data_dir = tmp_path / "backend_data"
    instances_file = data_dir / "live_trading_instances.json"
    manual_gateways_file = data_dir / "manual_gateways.json"
    monkeypatch.setattr(live_trading_manager, "_DATA_DIR", data_dir)
    monkeypatch.setattr(live_trading_manager, "_INSTANCES_FILE", instances_file)
    monkeypatch.setattr(live_trading_manager, "_MANUAL_GATEWAYS_FILE", manual_gateways_file)
    monkeypatch.setattr(instance_store, "_DATA_DIR", data_dir)
    monkeypatch.setattr(instance_store, "_INSTANCES_FILE", instances_file)
    monkeypatch.setattr(
        live_trading_manager.LiveTradingManager,
        "_start_restore_manual_gateways_background",
        lambda self: None,
    )
    monkeypatch.setattr(
        live_trading_manager.LiveTradingManager,
        "_start_restore_running_gateway_background",
        lambda self: None,
    )
    live_trading_manager._manager = None
    yield
    live_trading_manager._manager = None


@pytest.fixture(autouse=True)
def isolate_ai_provider_config(monkeypatch, tmp_path):
    """Keep provider-catalog tests independent of a developer's local overrides."""
    monkeypatch.setenv("AI_PROVIDER_CONFIG_PATH", str(tmp_path / "ai_provider_config.json"))


@pytest.fixture(autouse=True)
async def setup_db():
    """Rebuild all tables before each test, cleanup after."""
    limiter.reset()
    response_cache = importlib.import_module("app.utils.response_cache")
    response_cache._cache_backend = response_cache.MemoryCacheBackend()
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    sink = _ai_log_module._default_sink
    if sink is not None:
        try:
            await sink.shutdown()
        finally:
            _ai_log_module._default_sink = None
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    limiter.reset()
    response_cache._cache_backend = response_cache.MemoryCacheBackend()


# ==================== HTTP Client Fixture ====================


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create httpx async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ==================== Authentication Helper ====================


async def register_and_login(
    client: AsyncClient,
    username: str = None,
    password: str = "Test12345678",
):
    """Register a user and return (user_data, auth_headers)."""
    username = username or f"user_{uuid.uuid4().hex[:8]}"
    email = f"{username}@test.com"

    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": email,
            "password": password,
        },
    )
    assert reg.status_code == 200, f"Register failed: {reg.text}"

    login = await client.post(
        "/api/v1/auth/login",
        json={
            "username": username,
            "password": password,
        },
    )
    assert login.status_code == 200, f"Login failed: {login.text}"
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return {"username": username, "email": email, "password": password}, headers


@pytest_asyncio.fixture
async def auth_user(client: AsyncClient):
    """Register and login a test user, return (user_data, auth_headers)."""
    return await register_and_login(client)


@pytest_asyncio.fixture
async def auth_headers(auth_user) -> dict:
    """Return only authentication headers."""
    _, headers = auth_user
    return headers
