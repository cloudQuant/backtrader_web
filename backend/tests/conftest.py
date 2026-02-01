"""
Pytest配置和测试fixtures
"""
import pytest
import asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.database import engine, Base, async_session_maker


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    """初始化测试数据库"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """创建测试客户端"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session():
    """创建数据库会话"""
    async with async_session_maker() as session:
        yield session


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict:
    """创建认证头"""
    # 注册测试用户
    await client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpassword123"
        }
    )
    
    # 登录获取token
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": "testuser",
            "password": "testpassword123"
        }
    )
    
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
