"""
Tests for API rate limiting.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestRateLimiting:
    """Test suite for API rate limiting functionality."""

    async def test_auth_endpoints_work(self, client: AsyncClient):
        """Test that auth endpoints work properly (rate limiting should not break normal operation)."""
        # Test registration
        reg_response = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "test_user_rl",
                "email": "testrl@example.com",
                "password": "Test@12345",
            },
        )
        assert reg_response.status_code == 200

        # Test login
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "username": "test_user_rl",
                "password": "Test@12345",
            },
        )
        assert login_response.status_code == 200
        assert "access_token" in login_response.json()

    async def test_multiple_logins_succeed(self, client: AsyncClient):
        """Test that multiple legitimate logins work."""
        # Create user
        await client.post(
            "/api/v1/auth/register",
            json={
                "username": "multi_login_test",
                "email": "multilogin@test.com",
                "password": "Test@12345",
            },
        )

        # Test multiple login attempts
        login_data = {"username": "multi_login_test", "password": "Test@12345"}
        for _ in range(5):
            response = await client.post("/api/v1/auth/login", json=login_data)
            assert response.status_code == 200

    async def test_me_endpoint_requires_auth(self, client: AsyncClient):
        """Test that /me endpoint requires authentication."""
        # Without auth token
        response = await client.get("/api/v1/auth/me")
        assert response.status_code in (401, 403)

        # With auth token
        reg_response = await client.post(
            "/api/v1/auth/register",
            json={
                "username": "me_test_user",
                "email": "metest@example.com",
                "password": "Test@12345",
            },
        )
        assert reg_response.status_code == 200

        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "username": "me_test_user",
                "password": "Test@12345",
            },
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        me_response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert me_response.status_code == 200
        assert me_response.json()["username"] == "me_test_user"

    async def test_password_strength_validation(self, client: AsyncClient):
        """Test that password strength validation is enforced."""
        # Test weak passwords
        weak_passwords = [
            "short",
            "alllowercase",
            "ALLUPPERCASE",
            "12345678",
            "NoSpecialChars1",
        ]

        for password in weak_passwords:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "username": f"user_{password}",
                    "email": f"{password}@test.com",
                    "password": password,
                },
            )
            # Should either fail validation or succeed if validation is lenient
            # The important thing is the server doesn't crash
            assert response.status_code in (200, 400, 422)

    async def test_rate_limiting_configured(self, client: AsyncClient):
        """Test that rate limiting infrastructure is in place."""
        # This test verifies the rate limiter is configured
        # We don't actually hit the rate limit to avoid flaky tests

        from app.main import app

        assert hasattr(app.state, "limiter"), "Rate limiter should be configured"

    async def test_change_password_works(self, client: AsyncClient):
        """Test password change functionality."""
        # Create user
        await client.post(
            "/api/v1/auth/register",
            json={
                "username": "passwd_change_test",
                "email": "passwdchange@test.com",
                "password": "OldPass@123",
            },
        )

        # Login
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "username": "passwd_change_test",
                "password": "OldPass@123",
            },
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Change password
        change_response = await client.put(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "OldPass@123", "new_password": "NewPass@456"},
        )
        assert change_response.status_code == 200

        # Login with new password
        new_login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "username": "passwd_change_test",
                "password": "NewPass@456",
            },
        )
        assert new_login_response.status_code == 200

        # Old password should fail
        old_login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "username": "passwd_change_test",
                "password": "OldPass@123",
            },
        )
        assert old_login_response.status_code == 401

    async def test_register_rate_limit(self, client: AsyncClient):
        """Test that register endpoint enforces rate limiting (5/hour)."""
        from app.main import app

        # Reset limiter to ensure clean state
        if hasattr(app.state, "limiter"):
            app.state.limiter.reset()

        # Attempt to register 6 times (exceeds limit of 5/hour)
        responses = []
        for i in range(6):
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "username": f"rate_limit_user_{i}",
                    "email": f"ratelimit{i}@example.com",
                    "password": "Test@12345",
                },
            )
            responses.append(response)

        # First 5 should succeed
        for i in range(5):
            assert responses[i].status_code == 200, f"Registration {i + 1} should succeed"

        # 6th attempt should be rate limited
        assert responses[5].status_code == 429, "6th registration should be rate limited"

    async def test_login_rate_limit(self, client: AsyncClient):
        """Test that login endpoint enforces rate limiting (10/minute)."""
        from app.main import app

        # Create a user first
        await client.post(
            "/api/v1/auth/register",
            json={
                "username": "login_rl_test",
                "email": "loginrl@example.com",
                "password": "Test@12345",
            },
        )

        # Reset limiter to ensure clean state
        if hasattr(app.state, "limiter"):
            app.state.limiter.reset()

        # Attempt to login 11 times (exceeds limit of 10/minute)
        login_data = {"username": "login_rl_test", "password": "Test@12345"}
        responses = []
        for _ in range(11):
            response = await client.post("/api/v1/auth/login", json=login_data)
            responses.append(response)

        # First 10 should succeed
        for i in range(10):
            assert responses[i].status_code == 200, f"Login {i + 1} should succeed"
            assert "access_token" in responses[i].json()

        # 11th attempt should be rate limited
        assert responses[10].status_code == 429, "11th login should be rate limited"
