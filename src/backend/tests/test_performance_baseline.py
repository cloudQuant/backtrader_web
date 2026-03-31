"""
Performance baseline tests for critical API endpoints.

These tests establish performance baselines and detect regressions.
Run with: pytest -m performance -v
"""

import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def perf_client():
    """Create async client for performance tests using test app."""
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def performance_thresholds():
    """Define performance thresholds in seconds.

    Note: Test environment thresholds are more relaxed than production.
    Production thresholds should be stricter.
    """
    return {
        "health": 0.05,  # 50ms (test env)
        "login": 0.3,  # 300ms (test env, includes password hashing)
        "register": 0.4,  # 400ms (test env, includes password hashing)
        "strategies_list": 0.1,  # 100ms (test env)
        "backtests_list": 0.1,  # 100ms (test env)
        "backtest_create": 0.5,  # 500ms (test env, 不含执行)
    }


@pytest.mark.performance
async def test_health_check_performance(perf_client: AsyncClient, performance_thresholds):
    """Test health check endpoint performance."""
    start = time.perf_counter()
    response = await perf_client.get("/health")
    duration = time.perf_counter() - start

    assert response.status_code == 200, f"Health check failed: {response.status_code}"
    assert duration < performance_thresholds["health"], (
        f"Health check took {duration:.3f}s, expected < {performance_thresholds['health']}s"
    )
    print(f"✓ Health check: {duration*1000:.1f}ms (threshold: {performance_thresholds['health']*1000:.0f}ms)")


@pytest.mark.performance
@pytest.mark.skip(reason="Performance test is flaky, depends on system load")
async def test_login_performance(perf_client: AsyncClient, performance_thresholds):
    """Test login endpoint performance."""
    # First register a user
    await perf_client.post(
        "/api/v1/auth/register",
        json={
            "username": "perf_test_user",
            "email": "perf@test.com",
            "password": "TestPassword123!",
        },
    )

    start = time.perf_counter()
    response = await perf_client.post(
        "/api/v1/auth/login",
        json={"username": "perf_test_user", "password": "TestPassword123!"},
    )
    duration = time.perf_counter() - start

    assert response.status_code == 200, f"Login failed: {response.status_code}"
    assert duration < performance_thresholds["login"], (
        f"Login took {duration:.3f}s, expected < {performance_thresholds['login']}s"
    )
    print(f"✓ Login: {duration*1000:.1f}ms (threshold: {performance_thresholds['login']*1000:.0f}ms)")


@pytest.mark.performance
@pytest.mark.skip(reason="Performance test is flaky, depends on system load")
async def test_register_performance(perf_client: AsyncClient, performance_thresholds):
    """Test registration endpoint performance."""
    import uuid

    unique_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()
    response = await perf_client.post(
        "/api/v1/auth/register",
        json={
            "username": f"perf_reg_{unique_id}",
            "email": f"perf_reg_{unique_id}@test.com",
            "password": "TestPassword123!",
        },
    )
    duration = time.perf_counter() - start

    assert response.status_code == 200, f"Register failed: {response.status_code}"
    assert duration < performance_thresholds["register"], (
        f"Register took {duration:.3f}s, expected < {performance_thresholds['register']}s"
    )
    print(f"✓ Register: {duration*1000:.1f}ms (threshold: {performance_thresholds['register']*1000:.0f}ms)")


@pytest.mark.performance
@pytest.mark.skip(reason="Performance test is flaky, depends on system load")
async def test_strategies_list_performance(perf_client: AsyncClient, performance_thresholds):
    """Test strategies list endpoint performance."""
    # Register and login first
    await perf_client.post(
        "/api/v1/auth/register",
        json={
            "username": "perf_strat_user",
            "email": "perf_strat@test.com",
            "password": "TestPassword123!",
        },
    )
    login_resp = await perf_client.post(
        "/api/v1/auth/login",
        json={"username": "perf_strat_user", "password": "TestPassword123!"},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    start = time.perf_counter()
    response = await perf_client.get("/api/v1/strategy/", headers=headers)
    duration = time.perf_counter() - start

    assert response.status_code == 200, f"Strategy list failed: {response.status_code}"
    assert duration < performance_thresholds["strategies_list"], (
        f"Strategies list took {duration:.3f}s, expected < {performance_thresholds['strategies_list']}s"
    )
    print(f"✓ Strategies list: {duration*1000:.1f}ms (threshold: {performance_thresholds['strategies_list']*1000:.0f}ms)")


@pytest.mark.performance
@pytest.mark.skip(reason="Performance test is flaky, depends on system load")
async def test_backtests_list_performance(perf_client: AsyncClient, performance_thresholds):
    """Test backtests list endpoint performance."""
    # Register and login first
    await perf_client.post(
        "/api/v1/auth/register",
        json={
            "username": "perf_bt_user",
            "email": "perf_bt@test.com",
            "password": "TestPassword123!",
        },
    )
    login_resp = await perf_client.post(
        "/api/v1/auth/login",
        json={"username": "perf_bt_user", "password": "TestPassword123!"},
    )
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    start = time.perf_counter()
    response = await perf_client.get("/api/v1/backtests/", headers=headers)
    duration = time.perf_counter() - start

    assert response.status_code == 200, f"Backtests list failed: {response.status_code}"
    assert duration < performance_thresholds["backtests_list"], (
        f"Backtests list took {duration:.3f}s, expected < {performance_thresholds['backtests_list']}s"
    )
    print(f"✓ Backtests list: {duration*1000:.1f}ms (threshold: {performance_thresholds['backtests_list']*1000:.0f}ms)")


@pytest.mark.performance
@pytest.mark.skip(reason="Performance test is flaky, depends on system load")
async def test_root_endpoint_performance(perf_client: AsyncClient, performance_thresholds):
    """Test root endpoint performance."""
    start = time.perf_counter()
    response = await perf_client.get("/")
    duration = time.perf_counter() - start

    assert response.status_code == 200, f"Root endpoint failed: {response.status_code}"
    assert duration < performance_thresholds["health"], (
        f"Root endpoint took {duration:.3f}s, expected < {performance_thresholds['health']}s"
    )
    print(f"✓ Root endpoint: {duration*1000:.1f}ms (threshold: {performance_thresholds['health']*1000:.0f}ms)")


@pytest.mark.performance
@pytest.mark.skip(reason="Performance test is flaky, depends on system load")
async def test_api_docs_performance(perf_client: AsyncClient):
    """Test OpenAPI docs endpoint performance."""
    start = time.perf_counter()
    response = await perf_client.get("/docs")
    duration = time.perf_counter() - start

    assert response.status_code == 200, f"Docs endpoint failed: {response.status_code}"
    # Docs can be slower due to schema generation
    assert duration < 0.5, f"Docs took {duration:.3f}s, expected < 0.5s"
    print(f"✓ API Docs: {duration*1000:.1f}ms (threshold: 500ms)")
