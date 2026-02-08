"""
认证 API 测试
"""
import uuid
import pytest
from httpx import AsyncClient


class TestRegister:
    """注册接口测试"""

    async def test_register_success(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "password123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "newuser"
        assert data["email"] == "newuser@example.com"
        assert "id" in data

    async def test_register_duplicate_username(self, client: AsyncClient):
        payload = {"username": "dupuser", "email": "dup1@test.com", "password": "password123"}
        await client.post("/api/v1/auth/register", json=payload)
        payload["email"] = "dup2@test.com"
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 400

    async def test_register_duplicate_email(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "username": "user_a", "email": "same@test.com", "password": "password123",
        })
        resp = await client.post("/api/v1/auth/register", json={
            "username": "user_b", "email": "same@test.com", "password": "password123",
        })
        assert resp.status_code == 400

    async def test_register_short_password(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "username": "shortpw", "email": "short@test.com", "password": "123",
        })
        assert resp.status_code == 422  # validation error

    async def test_register_invalid_email(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "username": "bademail", "email": "not-an-email", "password": "password123",
        })
        assert resp.status_code == 422


class TestLogin:
    """登录接口测试"""

    async def test_login_success(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "username": "loginuser", "email": "login@test.com", "password": "password123",
        })
        resp = await client.post("/api/v1/auth/login", json={
            "username": "loginuser", "password": "password123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data

    async def test_login_wrong_password(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "username": "wrongpw", "email": "wrongpw@test.com", "password": "password123",
        })
        resp = await client.post("/api/v1/auth/login", json={
            "username": "wrongpw", "password": "badpassword",
        })
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "username": "ghost", "password": "password123",
        })
        assert resp.status_code == 401


class TestMe:
    """获取当前用户信息测试"""

    async def test_get_me_success(self, client: AsyncClient, auth_user):
        user_data, headers = auth_user
        resp = await client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == user_data["username"]
        assert data["email"] == user_data["email"]

    async def test_get_me_no_token(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 403

    async def test_get_me_invalid_token(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me", headers={
            "Authorization": "Bearer invalid.token.here",
        })
        assert resp.status_code == 401


class TestChangePassword:
    """修改密码测试"""

    async def test_change_password_success(self, client: AsyncClient):
        username = f"chgpw_{uuid.uuid4().hex[:6]}"
        await client.post("/api/v1/auth/register", json={
            "username": username, "email": f"{username}@test.com", "password": "OldPass12345",
        })
        login = await client.post("/api/v1/auth/login", json={
            "username": username, "password": "OldPass12345",
        })
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        resp = await client.put("/api/v1/auth/change-password", headers=headers, json={
            "old_password": "OldPass12345",
            "new_password": "NewPass12345",
        })
        assert resp.status_code == 200
        # 验证用新密码能登录
        login_resp = await client.post("/api/v1/auth/login", json={
            "username": username,
            "password": "NewPass12345",
        })
        assert login_resp.status_code == 200

    async def test_change_password_wrong_old(self, client: AsyncClient, auth_headers):
        resp = await client.put("/api/v1/auth/change-password", headers=auth_headers, json={
            "old_password": "WrongOldPass",
            "new_password": "NewPass12345",
        })
        assert resp.status_code == 400

    async def test_change_password_short_new(self, client: AsyncClient, auth_headers):
        resp = await client.put("/api/v1/auth/change-password", headers=auth_headers, json={
            "old_password": "Test12345678",
            "new_password": "short",
        })
        assert resp.status_code == 422
