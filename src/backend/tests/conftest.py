"""
Pytest 配置和 Fixtures

为所有测试提供共享的 fixtures 和配置。
使用 httpx.AsyncClient + ASGITransport 直接测试 FastAPI 应用。
每个测试使用独立的内存 SQLite 数据库（通过 StaticPool 共享连接）。
"""
import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

# 确保测试环境配置（在任何 app 导入之前）
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("SQL_ECHO", "false")

from app.db import database as db_module  # noqa: E402
from app.db.database import Base  # noqa: E402

# 覆盖数据库引擎和会话工厂：使用 StaticPool 让内存 SQLite 在整个测试期间共享一个连接
_test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)
_test_session_maker = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)

# 猴子补丁：让所有服务都使用测试数据库
db_module.engine = _test_engine
db_module.async_session_maker = _test_session_maker

# 同时补丁所有已导入 async_session_maker 的模块
from app.db import sql_repository as _sql_repo_module  # noqa: E402
_sql_repo_module.async_session_maker = _test_session_maker

from app.main import app  # noqa: E402


# ==================== 数据库 Fixtures ====================

@pytest.fixture(autouse=True)
async def setup_db():
    """每个测试前重建所有表，测试后清理"""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ==================== HTTP 客户端 Fixture ====================

@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """创建 httpx 异步测试客户端"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ==================== 认证 Helper ====================

async def register_and_login(
    client: AsyncClient,
    username: str = None,
    password: str = "Test12345678",
):
    """注册一个用户并返回 (user_data, auth_headers)"""
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
    """注册并登录一个测试用户，返回 (user_data, auth_headers)"""
    return await register_and_login(client)


@pytest_asyncio.fixture
async def auth_headers(auth_user) -> dict:
    """只返回认证头"""
    _, headers = auth_user
    return headers
