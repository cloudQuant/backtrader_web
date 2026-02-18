"""
Pytest Configuration and Fixtures.

Provides shared fixtures and configuration for all tests.
Uses httpx.AsyncClient + ASGITransport for direct FastAPI app testing.
Each test uses an independent in-memory SQLite database (shared connection via StaticPool).
"""
import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

# Ensure test environment configuration (before any app imports)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("SQL_ECHO", "false")

from app.db import database as db_module  # noqa: E402
from app.db.database import Base  # noqa: E402

# Override database engine and session factory: use StaticPool to share one connection for in-memory SQLite during tests
_test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)
_test_session_maker = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)

# Monkey patch: make all services use test database
db_module.engine = _test_engine
db_module.async_session_maker = _test_session_maker

# Also patch all modules that have already imported async_session_maker
from app.db import sql_repository as _sql_repo_module  # noqa: E402
_sql_repo_module.async_session_maker = _test_session_maker

from app.main import app  # noqa: E402


# ==================== Database Fixtures ====================

@pytest.fixture(autouse=True)
async def setup_db():
    """Rebuild all tables before each test, cleanup after."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


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

    reg = await client.post("/api/v1/auth/register", json={
        "username": username,
        "email": email,
        "password": password,
    })
    assert reg.status_code == 200, f"Register failed: {reg.text}"

    login = await client.post("/api/v1/auth/login", json={
        "username": username,
        "password": password,
    })
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
