"""
Authentication API tests with improved assertions and parametrization.

This file demonstrates:
1. Using factories for test data generation
2. Descriptive assertion messages
3. Parametrized tests for validation
"""

import uuid

import pytest
from httpx import AsyncClient

from tests.factories import HTTP, UserFactory


class TestRegister:
    """Registration endpoint tests."""

    async def test_register_success(self, client: AsyncClient):
        """Test successful user registration."""
        user_data = UserFactory.create()
        resp = await client.post("/api/v1/auth/register", json=user_data)

        assert resp.status_code == HTTP.OK, f"Registration failed: {resp.text}"

        data = resp.json()
        assert data["username"] == user_data["username"], (
            f"Username mismatch: expected {user_data['username']}, got {data.get('username')}"
        )
        assert data["email"] == user_data["email"], (
            f"Email mismatch: expected {user_data['email']}, got {data.get('email')}"
        )
        assert "id" in data, "Response missing user ID"

    async def test_register_duplicate_username(self, client: AsyncClient):
        """Test duplicate username returns 400 error."""
        user_data = UserFactory.create()

        # First registration should succeed
        resp1 = await client.post("/api/v1/auth/register", json=user_data)
        assert resp1.status_code == HTTP.OK, "First registration should succeed"

        # Second with same username but different email should fail
        user_data["email"] = f"different_{uuid.uuid4().hex[:8]}@test.com"
        resp2 = await client.post("/api/v1/auth/register", json=user_data)

        assert resp2.status_code == HTTP.BAD_REQUEST, (
            f"Expected 400 for duplicate username, got {resp2.status_code}: {resp2.text}"
        )

    async def test_register_duplicate_email(self, client: AsyncClient):
        """Test duplicate email returns 400 error."""
        user1 = UserFactory.create()
        user2 = UserFactory.create(email=user1["email"])

        # First registration
        resp1 = await client.post("/api/v1/auth/register", json=user1)
        assert resp1.status_code == HTTP.OK, "First registration should succeed"

        # Second with same email
        resp2 = await client.post("/api/v1/auth/register", json=user2)

        assert resp2.status_code == HTTP.BAD_REQUEST, (
            f"Expected 400 for duplicate email, got {resp2.status_code}: {resp2.text}"
        )

    @pytest.mark.parametrize(
        "field,value,should_fail",
        [
            ("password", "123", True),  # Too short
            ("password", "nodigit", True),  # No digit (but might pass validation)
            ("email", "not-an-email", True),  # Invalid format
            ("username", "", True),  # Empty
            ("username", "a", True),  # Too short
        ],
    )
    async def test_register_validation_errors(self, client: AsyncClient, field, value, should_fail):
        """Test various validation errors return 422."""
        user_data = UserFactory.create(**{field: value})
        resp = await client.post("/api/v1/auth/register", json=user_data)

        if should_fail:
            assert resp.status_code == HTTP.UNPROCESSABLE_ENTITY, (
                f"Expected 422 for invalid {field}={value}, got {resp.status_code}: {resp.text}"
            )
        else:
            assert resp.status_code in (HTTP.OK, HTTP.BAD_REQUEST), (
                f"Unexpected status for {field}={value}: {resp.status_code}"
            )


class TestLogin:
    """Login endpoint tests."""

    async def test_login_success(self, client: AsyncClient):
        """Test successful login returns JWT token."""
        user_data = UserFactory.create()

        # Register first
        await client.post("/api/v1/auth/register", json=user_data)

        # Login
        resp = await client.post(
            "/api/v1/auth/login",
            json={
                "username": user_data["username"],
                "password": user_data["password"],
            },
        )

        assert resp.status_code == HTTP.OK, f"Login failed: {resp.text}"

        data = resp.json()
        assert "access_token" in data, "Response missing access_token"
        assert data["token_type"] == "bearer", (
            f"Expected token_type 'bearer', got {data.get('token_type')}"
        )
        assert "expires_in" in data, "Response missing expires_in"

    @pytest.mark.parametrize(
        "scenario,password_modifier,expected_status",
        [
            ("wrong password", lambda p: "wrongpassword", HTTP.UNAUTHORIZED),
            ("empty password", lambda p: "", HTTP.UNAUTHORIZED),
        ],
    )
    async def test_login_invalid_credentials(
        self, client: AsyncClient, scenario, password_modifier, expected_status
    ):
        """Test login with invalid credentials."""
        user_data = UserFactory.create()

        # Register first
        await client.post("/api/v1/auth/register", json=user_data)

        # Try login with invalid password
        resp = await client.post(
            "/api/v1/auth/login",
            json={
                "username": user_data["username"],
                "password": password_modifier(user_data["password"]),
            },
        )

        assert resp.status_code == expected_status, (
            f"Expected {expected_status} for {scenario}, got {resp.status_code}"
        )

    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login with non-existent user returns 401."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={
                "username": f"ghost_{uuid.uuid4().hex[:8]}",
                "password": "password123",
            },
        )

        assert resp.status_code == HTTP.UNAUTHORIZED, (
            f"Expected 401 for non-existent user, got {resp.status_code}"
        )


class TestMe:
    """Get current user info tests."""

    async def test_get_me_success(self, client: AsyncClient, auth_user):
        """Test getting current user info with valid token."""
        user_data, headers = auth_user
        resp = await client.get("/api/v1/auth/me", headers=headers)

        assert resp.status_code == HTTP.OK, f"Get /me failed: {resp.text}"

        data = resp.json()
        assert data["username"] == user_data["username"], (
            f"Username mismatch: expected {user_data['username']}, got {data.get('username')}"
        )
        assert data["email"] == user_data["email"], (
            f"Email mismatch: expected {user_data['email']}, got {data.get('email')}"
        )

    @pytest.mark.parametrize(
        "headers,expected_status,description",
        [
            ({}, HTTP.UNAUTHORIZED, "No token provided"),
            ({"Authorization": "Bearer invalid.token.here"}, HTTP.UNAUTHORIZED, "Invalid token"),
            ({"Authorization": "Bearer"}, HTTP.UNAUTHORIZED, "Malformed token header"),
        ],
    )
    async def test_get_me_authentication_required(
        self, client: AsyncClient, headers, expected_status, description
    ):
        """Test /me endpoint requires authentication."""
        resp = await client.get("/api/v1/auth/me", headers=headers)

        assert resp.status_code == expected_status, (
            f"Expected {expected_status} for '{description}', got {resp.status_code}"
        )


class TestChangePassword:
    """Change password tests."""

    async def test_change_password_success(self, client: AsyncClient):
        """Test successful password change."""
        user_data = UserFactory.create()

        # Register
        await client.post("/api/v1/auth/register", json=user_data)

        # Login
        login = await client.post(
            "/api/v1/auth/login",
            json={
                "username": user_data["username"],
                "password": user_data["password"],
            },
        )
        assert login.status_code == HTTP.OK, "Login failed"

        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # Change password
        new_password = "NewPass12345"
        resp = await client.put(
            "/api/v1/auth/change-password",
            headers=headers,
            json={
                "old_password": user_data["password"],
                "new_password": new_password,
            },
        )

        assert resp.status_code == HTTP.OK, f"Password change failed: {resp.text}"

        # Verify can login with new password
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={
                "username": user_data["username"],
                "password": new_password,
            },
        )
        assert login_resp.status_code == HTTP.OK, "Login with new password failed"

    @pytest.mark.parametrize(
        "old_password,new_password,expected_status,error_type",
        [
            ("WrongOldPass", "NewPass12345", HTTP.BAD_REQUEST, "wrong old password"),
            ("Test12345678", "short", HTTP.UNPROCESSABLE_ENTITY, "short new password"),
        ],
    )
    async def test_change_password_validation_errors(
        self,
        client: AsyncClient,
        auth_headers,
        old_password,
        new_password,
        expected_status,
        error_type,
    ):
        """Test password change validation errors."""
        resp = await client.put(
            "/api/v1/auth/change-password",
            headers=auth_headers,
            json={
                "old_password": old_password,
                "new_password": new_password,
            },
        )

        assert resp.status_code == expected_status, (
            f"Expected {expected_status} for {error_type}, got {resp.status_code}: {resp.text}"
        )
