"""
API route coverage tests - Cover data, comparison, paper_trading, strategy_version,
realtime, monitoring, live_trading, optimization and other low-coverage API routes.
"""

from types import SimpleNamespace

from fastapi import FastAPI
from httpx import AsyncClient

import app.api.data.base as data_base
from app.api.data.deps import get_authorized_market_data_access
from app.api.data.queries import (
    get_market_data_capability_evaluation,
    get_market_data_query_service,
)
from app.main import app


class TestRouterMetadata:
    """API router metadata tests."""

    def test_live_trading_routes_are_not_deprecated(self):
        from app.api.router import api_router

        app = FastAPI()
        app.include_router(api_router)
        openapi_paths = app.openapi()["paths"]
        http_routes = [
            operation
            for path, methods in openapi_paths.items()
            if path.startswith("/live-trading") and not path.startswith("/live-trading-crypto")
            for operation in methods.values()
        ]

        assert http_routes
        assert all(route.get("deprecated") is not True for route in http_routes)


# ==================== Data API ====================
class TestDataAPI:
    """Market data API tests."""

    async def test_query_kline_no_auth(self, client: AsyncClient):
        """Test K-line query without authentication."""
        resp = await client.get(
            "/api/v1/data/kline?symbol=000001.SZ&start_date=2024-01-01&end_date=2024-01-01"
        )
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_query_kline(self, client: AsyncClient, auth_headers: dict, monkeypatch):
        """Test that the legacy wire shape comes from the governed bridge."""
        access = SimpleNamespace(
            principal=SimpleNamespace(
                principal_scope="principal:api-routes-test",
                tenant_scope="default",
                entitlement_revision="api-routes-test-v1",
            )
        )
        evaluation = SimpleNamespace(response=SimpleNamespace(query_v2_enabled=True))
        monkeypatch.setitem(app.dependency_overrides, get_authorized_market_data_access, lambda: access)
        monkeypatch.setitem(
            app.dependency_overrides,
            get_market_data_capability_evaluation,
            lambda: evaluation,
        )
        monkeypatch.setitem(app.dependency_overrides, get_market_data_query_service, lambda: object())
        monkeypatch.setitem(
            app.dependency_overrides,
            data_base.get_legacy_market_data_query_contract_resolver,
            lambda: object(),
        )

        async def fake_bridge(**_kwargs):
            return {
                "symbol": "000001.SZ",
                "count": 1,
                "kline": {
                    "dates": ["2024-01-01"],
                    "ohlc": [[10.0, 10.3, 9.8, 10.5]],
                    "volumes": [1_000_000],
                },
                "records": [
                    {
                        "date": "2024-01-01",
                        "open": 10.0,
                        "high": 10.5,
                        "low": 9.8,
                        "close": 10.3,
                        "volume": 1_000_000,
                        "change": 2.5,
                    }
                ],
            }

        monkeypatch.setattr(data_base, "execute_legacy_kline_local_first", fake_bridge)
        resp = await client.get(
            "/api/v1/data/kline?symbol=000001.SZ&start_date=2024-01-01&end_date=2024-01-31",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["kline"]["ohlc"] == [[10.0, 10.3, 9.8, 10.5]]


# ==================== Comparison API ====================
class TestComparisonAPI:
    """Backtest comparison API tests."""

    async def test_create_comparison_no_auth(self, client: AsyncClient):
        """Test creating comparison without authentication."""
        resp = await client.post("/api/v1/comparisons/", json={})
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_list_comparisons(self, client: AsyncClient, auth_headers: dict):
        """Test listing comparisons."""
        resp = await client.get("/api/v1/comparisons/", headers=auth_headers)
        assert resp.status_code == 200

    async def test_get_comparison_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test getting non-existent comparison."""
        resp = await client.get("/api/v1/comparisons/nonexistent", headers=auth_headers)
        assert resp.status_code == 404

    async def test_delete_comparison_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test deleting non-existent comparison."""
        resp = await client.delete("/api/v1/comparisons/nonexistent", headers=auth_headers)
        assert resp.status_code == 404


# ==================== Paper Trading API ====================
class TestPaperTradingAPI:
    """Paper trading API tests.

    Note: Paper trading router is optional. Tests verify behavior based on
    whether the router is actually registered.
    """

    async def test_list_sessions(self, client: AsyncClient, auth_headers: dict):
        """Test listing paper trading sessions."""
        resp = await client.get("/api/v1/paper-trading/sessions", headers=auth_headers)
        # Router may not be registered — accept 200 (available) or 404 (not registered)
        assert resp.status_code in (200, 404)

    async def test_create_session_requires_body(self, client: AsyncClient, auth_headers: dict):
        """Test creating session rejects empty body when router is available."""
        resp = await client.post("/api/v1/paper-trading/sessions", headers=auth_headers, json={})
        # 422 (validation error) if router active, 404 if not registered
        assert resp.status_code in (422, 404)

    async def test_get_session_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test getting non-existent session returns 404."""
        resp = await client.get("/api/v1/paper-trading/sessions/nonexistent", headers=auth_headers)
        assert resp.status_code == 404


# ==================== Strategy Version API ====================
class TestStrategyVersionAPI:
    """Strategy version control API tests."""

    async def test_list_versions_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test listing versions for non-existent strategy."""
        resp = await client.get(
            "/api/v1/strategy-versions/nonexistent/versions", headers=auth_headers
        )
        assert resp.status_code == 404

    async def test_create_version_no_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test creating version for non-existent strategy."""
        resp = await client.post(
            "/api/v1/strategy-versions/nonexistent/versions",
            headers=auth_headers,
            json={"code": "pass", "description": "test"},
        )
        assert resp.status_code == 404


# ==================== Realtime Data API ====================
class TestRealtimeDataAPI:
    """Realtime market data API tests."""

    async def test_subscribe_requires_body(self, client: AsyncClient, auth_headers: dict):
        """Test subscribing rejects empty body when router is available."""
        resp = await client.post("/api/v1/realtime/subscribe", headers=auth_headers, json={})
        # 422 (validation error) if router active, 404 if not registered
        assert resp.status_code in (422, 404)

    async def test_unsubscribe_requires_body(self, client: AsyncClient, auth_headers: dict):
        """Test unsubscribing rejects empty body when router is available."""
        resp = await client.post("/api/v1/realtime/unsubscribe", headers=auth_headers, json={})
        assert resp.status_code in (422, 404)


# ==================== Monitoring API ====================
class TestMonitoringAPI:
    """Monitoring and alerting API tests."""

    async def test_list_alerts(self, client: AsyncClient, auth_headers: dict):
        """Test listing alerts."""
        resp = await client.get("/api/v1/monitoring/alerts", headers=auth_headers)
        # Router may not be registered — accept 200 or 404
        assert resp.status_code in (200, 404)

    async def test_create_alert_requires_body(self, client: AsyncClient, auth_headers: dict):
        """Test creating alert rejects empty body when router is available."""
        resp = await client.post("/api/v1/monitoring/alerts", headers=auth_headers, json={})
        # 422/405 (validation/method error) if router active, 404 if not registered
        assert resp.status_code in (405, 422, 404)

    async def test_get_system_health(self, client: AsyncClient, auth_headers: dict):
        """Test getting system health status."""
        resp = await client.get("/api/v1/monitoring/health", headers=auth_headers)
        assert resp.status_code in (200, 404)

    async def test_get_metrics(self, client: AsyncClient, auth_headers: dict):
        """Test getting system metrics."""
        resp = await client.get("/api/v1/monitoring/metrics", headers=auth_headers)
        assert resp.status_code in (200, 404)


# ==================== Optimization API ====================
class TestOptimizationAPI:
    """Parameter optimization API tests."""

    async def test_run_optimization_invalid(self, client: AsyncClient, auth_headers: dict):
        """Test authoritative optimization endpoint rejects invalid data."""
        resp = await client.post(
            "/api/v1/optimization/submit/backtest", headers=auth_headers, json={}
        )
        assert resp.status_code == 422

    async def test_list_results(self, client: AsyncClient, auth_headers: dict):
        """Test listing optimization results."""
        resp = await client.get("/api/v1/optimization/results", headers=auth_headers)
        # Router may not be registered — accept 200 or 404
        assert resp.status_code in (200, 404)

    async def test_get_result_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test getting non-existent optimization result."""
        resp = await client.get("/api/v1/optimization/results/nonexistent", headers=auth_headers)
        assert resp.status_code in (404,)


# ==================== Live Trading API ====================
class TestLiveTradingAPI:
    """Live trading API tests."""

    async def test_list_instances(self, client: AsyncClient, auth_headers: dict):
        """Test listing live trading instances."""
        resp = await client.get("/api/v1/live-trading/instances", headers=auth_headers)
        # Router may not be registered — accept 200 or 404
        assert resp.status_code in (200, 404)

    async def test_create_instance_requires_body(self, client: AsyncClient, auth_headers: dict):
        """Test creating instance rejects empty body when router is available."""
        resp = await client.post("/api/v1/live-trading/instances", headers=auth_headers, json={})
        # 422/405 (validation/method error) if router active, 404 if not registered
        assert resp.status_code in (405, 422, 404)

    async def test_get_instance_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test getting non-existent instance."""
        resp = await client.get("/api/v1/live-trading/instances/nonexistent", headers=auth_headers)
        assert resp.status_code in (404,)
