"""Integration tests for complete backtest workflow.

Tests the full lifecycle: submit -> status -> result -> delete
"""

import pytest
from httpx import AsyncClient

from tests.factories import HTTP, BacktestRequestFactory, UserFactory

pytestmark = pytest.mark.asyncio


class TestCompleteBacktestFlow:
    """Test complete backtest workflow from submission to deletion."""

    async def test_full_backtest_lifecycle(self, client: AsyncClient, auth_headers: dict):
        """Test complete backtest lifecycle: submit -> status -> result -> delete."""
        # Step 1: Submit backtest
        request_data = BacktestRequestFactory.create()
        submit_resp = await client.post(
            "/api/v1/backtests/run",
            json=request_data,
            headers=auth_headers,
        )
        assert submit_resp.status_code == HTTP.OK, f"Submit failed: {submit_resp.text}"
        submit_data = submit_resp.json()
        task_id = submit_data["task_id"]
        assert task_id, "Task ID should be returned"
        assert submit_data["status"] == "pending"

        # Step 2: Check status
        status_resp = await client.get(
            f"/api/v1/backtests/{task_id}/status",
            headers=auth_headers,
        )
        assert status_resp.status_code == HTTP.OK
        status_data = status_resp.json()
        assert status_data["task_id"] == task_id
        assert status_data["status"] in ["pending", "running", "completed"]

        # Step 3: List backtests (should include our task)
        list_resp = await client.get(
            "/api/v1/backtests/",
            headers=auth_headers,
        )
        assert list_resp.status_code == HTTP.OK
        list_data = list_resp.json()
        task_ids = [item["task_id"] for item in list_data.get("items", [])]
        assert task_id in task_ids, "Task should appear in list"

        # Step 4: Get result (may be pending/running/completed)
        result_resp = await client.get(
            f"/api/v1/backtests/{task_id}",
            headers=auth_headers,
        )
        # Result may not be ready immediately, but endpoint should work
        assert result_resp.status_code in [HTTP.OK, HTTP.NOT_FOUND]

        # Step 5: Delete backtest
        delete_resp = await client.delete(
            f"/api/v1/backtests/{task_id}",
            headers=auth_headers,
        )
        assert delete_resp.status_code == HTTP.OK, f"Delete failed: {delete_resp.text}"

        # Step 6: Verify deletion
        verify_resp = await client.get(
            f"/api/v1/backtests/{task_id}",
            headers=auth_headers,
        )
        assert verify_resp.status_code == HTTP.NOT_FOUND

    async def test_backtest_unauthorized_access(self, client: AsyncClient):
        """Test that unauthenticated requests are rejected."""
        request_data = BacktestRequestFactory.create()

        # No auth header
        resp = await client.post("/api/v1/backtests/run", json=request_data)
        assert resp.status_code == HTTP.UNAUTHORIZED

        # List without auth
        resp = await client.get("/api/v1/backtests/")
        assert resp.status_code == HTTP.UNAUTHORIZED

    async def test_backtest_cross_user_isolation(
        self, client: AsyncClient, auth_headers: dict, auth_headers_user2: dict
    ):
        """Test that users cannot access each other's backtests."""
        # User 1 creates a backtest
        request_data = BacktestRequestFactory.create()
        submit_resp = await client.post(
            "/api/v1/backtests/run",
            json=request_data,
            headers=auth_headers,
        )
        assert submit_resp.status_code == HTTP.OK
        task_id = submit_resp.json()["task_id"]

        # User 2 tries to access User 1's backtest
        result_resp = await client.get(
            f"/api/v1/backtests/{task_id}",
            headers=auth_headers_user2,
        )
        assert result_resp.status_code == HTTP.NOT_FOUND

        # User 2 tries to delete User 1's backtest
        delete_resp = await client.delete(
            f"/api/v1/backtests/{task_id}",
            headers=auth_headers_user2,
        )
        assert delete_resp.status_code == HTTP.NOT_FOUND


class TestStrategyCRUDFlow:
    """Test complete strategy CRUD workflow."""

    async def test_strategy_crud_lifecycle(self, client: AsyncClient, auth_headers: dict):
        """Test complete strategy lifecycle: create -> read -> update -> delete."""
        # Step 1: Create strategy
        create_data = {
            "name": "Test Strategy",
            "description": "Integration test strategy",
            "code": "# Test strategy code\nprint('hello')",
            "params": {},
            "category": "custom",
        }
        create_resp = await client.post(
            "/api/v1/strategy/",
            json=create_data,
            headers=auth_headers,
        )
        assert create_resp.status_code == HTTP.OK, f"Create failed: {create_resp.text}"
        strategy_id = create_resp.json()["id"]

        # Step 2: Read strategy
        read_resp = await client.get(
            f"/api/v1/strategy/{strategy_id}",
            headers=auth_headers,
        )
        assert read_resp.status_code == HTTP.OK
        assert read_resp.json()["name"] == "Test Strategy"

        # Step 3: Update strategy
        update_data = {"name": "Updated Strategy"}
        update_resp = await client.put(
            f"/api/v1/strategy/{strategy_id}",
            json=update_data,
            headers=auth_headers,
        )
        assert update_resp.status_code == HTTP.OK
        assert update_resp.json()["name"] == "Updated Strategy"

        # Step 4: List strategies (should include ours)
        list_resp = await client.get(
            "/api/v1/strategy/",
            headers=auth_headers,
        )
        assert list_resp.status_code == HTTP.OK
        ids = [s["id"] for s in list_resp.json().get("items", [])]
        assert strategy_id in ids

        # Step 5: Delete strategy
        delete_resp = await client.delete(
            f"/api/v1/strategy/{strategy_id}",
            headers=auth_headers,
        )
        assert delete_resp.status_code == HTTP.OK

        # Step 6: Verify deletion
        verify_resp = await client.get(
            f"/api/v1/strategy/{strategy_id}",
            headers=auth_headers,
        )
        assert verify_resp.status_code == HTTP.NOT_FOUND


class TestAuthFlow:
    """Test complete authentication workflow."""

    async def test_register_login_flow(self, client: AsyncClient):
        """Test complete auth flow: register -> login -> me -> logout."""
        # Step 1: Register new user
        user_data = UserFactory.create()
        register_resp = await client.post(
            "/api/v1/auth/register",
            json=user_data,
        )
        assert register_resp.status_code == HTTP.OK, f"Register failed: {register_resp.text}"

        # Step 2: Login (only username and password)
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={
                "username": user_data["username"],
                "password": user_data["password"],
            },
        )
        assert login_resp.status_code == HTTP.OK, f"Login failed: {login_resp.text}"
        token = login_resp.json()["access_token"]
        assert token

        # Step 3: Get current user info
        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == HTTP.OK
        assert me_resp.json()["username"] == user_data["username"]

    async def test_duplicate_registration(self, client: AsyncClient):
        """Test that duplicate registration fails gracefully."""
        user_data = UserFactory.create()

        # First registration should succeed
        resp1 = await client.post("/api/v1/auth/register", json=user_data)
        assert resp1.status_code == HTTP.OK

        # Second registration with same data should fail
        resp2 = await client.post("/api/v1/auth/register", json=user_data)
        assert resp2.status_code in [HTTP.BAD_REQUEST, HTTP.UNPROCESSABLE_ENTITY]


# Fixtures for these tests
@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict:
    """Create user and return auth headers."""
    user = UserFactory.create(username="testuser1", email="test1@example.com")
    await client.post("/api/v1/auth/register", json=user)
    # Login expects JSON body, not form data
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"username": user["username"], "password": user["password"]},
    )
    assert login_resp.status_code == HTTP.OK, f"Login failed: {login_resp.text}"
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def auth_headers_user2(client: AsyncClient) -> dict:
    """Create second user and return auth headers."""
    user = UserFactory.create(username="testuser2", email="test2@example.com")
    await client.post("/api/v1/auth/register", json=user)
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"username": user["username"], "password": user["password"]},
    )
    assert login_resp.status_code == HTTP.OK, f"Login failed: {login_resp.text}"
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
