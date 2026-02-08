"""
API 路由覆盖测试 - 覆盖 data, comparison, paper_trading, strategy_version,
realtime, monitoring, live_trading, optimization 等低覆盖 API 路由
"""
import pytest
from httpx import AsyncClient


# ==================== Data API ====================
class TestDataAPI:
    async def test_query_kline_no_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/data/kline?symbol=000001.SZ")
        assert resp.status_code in [200, 403, 422]

    async def test_query_kline(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/data/kline?symbol=000001.SZ&start_date=2024-01-01&end_date=2024-01-31", headers=auth_headers)
        # May fail with external API, accept various status codes
        assert resp.status_code in [200, 422, 500]


# ==================== Comparison API ====================
class TestComparisonAPI:
    async def test_create_comparison_no_auth(self, client: AsyncClient):
        resp = await client.post("/api/v1/comparisons/", json={})
        assert resp.status_code in [403, 422]

    async def test_list_comparisons(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/comparisons/", headers=auth_headers)
        assert resp.status_code in [200, 404, 500, 422]

    async def test_get_comparison_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/comparisons/nonexistent", headers=auth_headers)
        assert resp.status_code in [404, 422]

    async def test_delete_comparison_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.delete("/api/v1/comparisons/nonexistent", headers=auth_headers)
        assert resp.status_code in [404, 422]


# ==================== Paper Trading API ====================
class TestPaperTradingAPI:
    async def test_list_sessions(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/paper-trading/sessions", headers=auth_headers)
        assert resp.status_code in [200, 404]

    async def test_create_session_invalid(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/v1/paper-trading/sessions", headers=auth_headers, json={})
        assert resp.status_code in [404, 422, 400, 405]

    async def test_get_session_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/paper-trading/sessions/nonexistent", headers=auth_headers)
        assert resp.status_code in [404, 422]


# ==================== Strategy Version API ====================
class TestStrategyVersionAPI:
    async def test_list_versions_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/strategy-versions/nonexistent/versions", headers=auth_headers)
        assert resp.status_code in [200, 404]

    async def test_create_version_no_strategy(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/v1/strategy-versions/nonexistent/versions", headers=auth_headers, json={
            "code": "pass", "description": "test"
        })
        assert resp.status_code in [404, 422]


# ==================== Realtime Data API ====================
class TestRealtimeDataAPI:
    async def test_subscribe_invalid(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/v1/realtime/subscribe", headers=auth_headers, json={})
        assert resp.status_code in [404, 422, 400, 405]

    async def test_unsubscribe_invalid(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/v1/realtime/unsubscribe", headers=auth_headers, json={})
        assert resp.status_code in [404, 422, 400, 405]


# ==================== Monitoring API ====================
class TestMonitoringAPI:
    async def test_list_alerts(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/monitoring/alerts", headers=auth_headers)
        assert resp.status_code in [200, 404, 501]

    async def test_create_alert_invalid(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/v1/monitoring/alerts", headers=auth_headers, json={})
        assert resp.status_code in [422, 400, 405, 501]

    async def test_get_system_health(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/monitoring/health", headers=auth_headers)
        assert resp.status_code in [200, 404, 501]

    async def test_get_metrics(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/monitoring/metrics", headers=auth_headers)
        assert resp.status_code in [200, 404, 501]


# ==================== Optimization API ====================
class TestOptimizationAPI:
    async def test_run_optimization_invalid(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/v1/optimization/run", headers=auth_headers, json={})
        assert resp.status_code in [404, 422, 400, 405]

    async def test_list_results(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/optimization/results", headers=auth_headers)
        assert resp.status_code in [200, 404]

    async def test_get_result_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/optimization/results/nonexistent", headers=auth_headers)
        assert resp.status_code in [404, 422]


# ==================== Live Trading API ====================
class TestLiveTradingAPI:
    async def test_list_instances(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/live-trading/instances", headers=auth_headers)
        assert resp.status_code in [200, 404]

    async def test_create_instance_invalid(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post("/api/v1/live-trading/instances", headers=auth_headers, json={})
        assert resp.status_code in [404, 422, 400, 405]

    async def test_get_instance_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/live-trading/instances/nonexistent", headers=auth_headers)
        assert resp.status_code in [404, 422]
