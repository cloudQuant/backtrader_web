"""
认证API测试
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    """测试用户注册"""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "password123"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "newuser"
    assert data["email"] == "newuser@example.com"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient):
    """测试重复用户名注册"""
    # 第一次注册
    await client.post(
        "/api/v1/auth/register",
        json={
            "username": "duplicateuser",
            "email": "dup1@example.com",
            "password": "password123"
        }
    )
    
    # 重复用户名注册
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "duplicateuser",
            "email": "dup2@example.com",
            "password": "password123"
        }
    )
    
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    """测试用户登录"""
    # 先注册
    await client.post(
        "/api/v1/auth/register",
        json={
            "username": "loginuser",
            "email": "login@example.com",
            "password": "password123"
        }
    )
    
    # 登录
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": "loginuser",
            "password": "password123"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """测试错误密码登录"""
    # 先注册
    await client.post(
        "/api/v1/auth/register",
        json={
            "username": "wrongpwuser",
            "email": "wrongpw@example.com",
            "password": "password123"
        }
    )
    
    # 错误密码登录
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": "wrongpwuser",
            "password": "wrongpassword"
        }
    )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, auth_headers: dict):
    """测试获取当前用户信息"""
    response = await client.get(
        "/api/v1/auth/me",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "username" in data
    assert "email" in data


@pytest.mark.asyncio
async def test_get_me_without_auth(client: AsyncClient):
    """测试未认证访问"""
    response = await client.get("/api/v1/auth/me")
    
    assert response.status_code == 403
