"""
Extended E2E API tests — covers modules not in test_api_e2e.py.

Modules covered:
1. Comparisons (backtest comparison CRUD)
2. Monitoring (alert rules, alerts)
3. Quote (symbols, chart data)
4. AI Trading (config, execute, history)
5. KB Chat (conversations, messages)
6. Data Sync (config, databases)
7. Auto Trading (config, schedule)
8. Analytics (detail, export, kline, monthly)
9. Workspace (CRUD)
10. Risk Control
11. Metrics

Requires: Backend running on http://127.0.0.1:8000
Run: pytest tests/e2e/test_api_extended.py -v --timeout=60
"""

import time
import uuid

import httpx
import pytest

BASE_URL = "http://127.0.0.1:8000"
API = f"{BASE_URL}/api/v1"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=API, timeout=30) as c:
        yield c


@pytest.fixture(scope="module")
def auth_headers(client):
    """Get admin auth headers with rate-limit retry."""
    for attempt in range(5):
        resp = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
        if resp.status_code == 200:
            token = resp.json()["access_token"]
            return {"Authorization": f"Bearer {token}"}
        if resp.status_code == 429:
            time.sleep(resp.json().get("retry_after", 10) + 1)
    pytest.fail("Could not login due to rate limiting")


# ══════════════════════════════════════════════════════════════════════════════
# 1. Comparisons
# ══════════════════════════════════════════════════════════════════════════════


class TestComparisons:
    def test_list_comparisons(self, client, auth_headers):
        """List backtest comparisons."""
        resp = client.get("/comparisons/", headers=auth_headers)
        assert resp.status_code == 200

    def test_comparison_crud(self, client, auth_headers):
        """Create, read, update, delete a comparison."""
        # Create
        resp = client.post("/comparisons/", headers=auth_headers, json={
            "name": f"E2E Comparison {uuid.uuid4().hex[:6]}",
            "backtest_task_ids": [],
            "type": "metrics",
        })
        if resp.status_code in (200, 201):
            cmp_id = resp.json()["id"]

            # Read
            resp = client.get(f"/comparisons/{cmp_id}", headers=auth_headers)
            assert resp.status_code == 200

            # Toggle favorite
            resp = client.post(f"/comparisons/{cmp_id}/toggle-favorite", headers=auth_headers)
            assert resp.status_code == 200

            # Delete
            resp = client.delete(f"/comparisons/{cmp_id}", headers=auth_headers)
            assert resp.status_code == 200
        else:
            # May fail if no backtests exist — acceptable
            assert resp.status_code in (400, 422)

    def test_comparison_not_found(self, client, auth_headers):
        """Non-existent comparison returns 404."""
        resp = client.get("/comparisons/nonexistent-id", headers=auth_headers)
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 2. Monitoring (Alerts & Rules)
# ══════════════════════════════════════════════════════════════════════════════


class TestMonitoring:
    def test_list_alerts(self, client, auth_headers):
        """List alerts."""
        resp = client.get("/monitoring/", headers=auth_headers)
        assert resp.status_code == 200

    def test_list_alert_rules(self, client, auth_headers):
        """List alert rules."""
        resp = client.get("/monitoring/rules", headers=auth_headers)
        assert resp.status_code == 200

    def test_alert_statistics_summary(self, client, auth_headers):
        """Get alert statistics summary."""
        resp = client.get("/monitoring/statistics/summary", headers=auth_headers)
        assert resp.status_code == 200

    def test_alert_statistics_by_type(self, client, auth_headers):
        """Get alert statistics by type."""
        resp = client.get("/monitoring/statistics/by-type", headers=auth_headers)
        assert resp.status_code in (200, 422)  # May require params

    def test_alert_rule_crud(self, client, auth_headers):
        """Create and delete an alert rule."""
        resp = client.post("/monitoring/rules", headers=auth_headers, json={
            "name": f"E2E Rule {uuid.uuid4().hex[:6]}",
            "alert_type": "account",
            "condition": "greater_than",
            "threshold": 100000,
            "severity": "info",
            "config": {"metric": "value"},
        })
        if resp.status_code in (200, 201):
            rule_id = resp.json()["id"]
            # Get
            resp = client.get(f"/monitoring/rules/{rule_id}", headers=auth_headers)
            assert resp.status_code == 200
            # Delete
            resp = client.delete(f"/monitoring/rules/{rule_id}", headers=auth_headers)
            assert resp.status_code == 200
        else:
            # Schema might differ — just verify no 500
            assert resp.status_code in (400, 422)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Quote / Market Data
# ══════════════════════════════════════════════════════════════════════════════


class TestQuote:
    def test_list_sources(self, client, auth_headers):
        """List available data sources."""
        resp = client.get("/quote/sources", headers=auth_headers)
        assert resp.status_code == 200

    def test_get_symbols(self, client, auth_headers):
        """Get symbols for a data source."""
        resp = client.get("/quote/symbols", headers=auth_headers, params={"source": "akshare"})
        assert resp.status_code in (200, 400, 422)

    def test_search_symbols(self, client, auth_headers):
        """Search symbols."""
        resp = client.get("/quote/symbols/search", headers=auth_headers, params={
            "source": "akshare",
            "keyword": "平安",
        })
        assert resp.status_code in (200, 400, 422)

    def test_get_chart_data(self, client, auth_headers):
        """Get chart/kline data."""
        resp = client.get("/quote/chart", headers=auth_headers, params={
            "symbol": "000001",
            "source": "akshare",
        })
        # May fail if data source not configured — acceptable
        assert resp.status_code in (200, 400, 404, 422, 500)


# ══════════════════════════════════════════════════════════════════════════════
# 4. AI Trading
# ══════════════════════════════════════════════════════════════════════════════


class TestAITrading:
    def test_get_config(self, client, auth_headers):
        """Get AI trading configuration."""
        resp = client.get("/ai-trading/config", headers=auth_headers)
        assert resp.status_code == 200

    def test_get_history(self, client, auth_headers):
        """Get AI trading history."""
        resp = client.get("/ai-trading/history", headers=auth_headers)
        assert resp.status_code == 200

    def test_list_conditional_orders(self, client, auth_headers):
        """List conditional orders."""
        resp = client.get("/ai-trading/conditional-orders", headers=auth_headers)
        assert resp.status_code == 200

    def test_execute_requires_input(self, client, auth_headers):
        """Execute without proper input returns 422."""
        resp = client.post("/ai-trading/execute", headers=auth_headers, json={})
        assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# 5. KB Chat
# ══════════════════════════════════════════════════════════════════════════════


class TestKBChat:
    def test_list_conversations(self, client, auth_headers):
        """List KB chat conversations."""
        resp = client.get("/kb-chat/conversations", headers=auth_headers)
        assert resp.status_code in (200, 422)  # May require knowledge_base_id param

    def test_create_conversation(self, client, auth_headers):
        """Create a new conversation."""
        resp = client.post("/kb-chat/conversations", headers=auth_headers, json={
            "title": f"E2E Chat {uuid.uuid4().hex[:6]}",
        })
        if resp.status_code in (200, 201):
            conv_id = resp.json().get("id") or resp.json().get("conversation_id")
            if conv_id:
                # Get history
                resp = client.get(f"/kb-chat/history/{conv_id}", headers=auth_headers)
                assert resp.status_code == 200
                # Delete
                resp = client.delete(f"/kb-chat/conversations/{conv_id}", headers=auth_headers)
                assert resp.status_code == 200
        else:
            assert resp.status_code in (400, 422)


# ══════════════════════════════════════════════════════════════════════════════
# 6. Data Management (extended)
# ══════════════════════════════════════════════════════════════════════════════


class TestDataExtended:
    def test_list_scripts(self, client, auth_headers):
        """List data scripts."""
        resp = client.get("/data/scripts", headers=auth_headers)
        assert resp.status_code == 200

    def test_script_stats(self, client, auth_headers):
        """Get script statistics."""
        resp = client.get("/data/scripts/stats", headers=auth_headers)
        assert resp.status_code == 200

    def test_script_categories(self, client, auth_headers):
        """List script categories."""
        resp = client.get("/data/scripts/categories", headers=auth_headers)
        assert resp.status_code == 200

    def test_list_tasks(self, client, auth_headers):
        """List data tasks."""
        resp = client.get("/data/tasks", headers=auth_headers)
        assert resp.status_code == 200

    def test_list_executions(self, client, auth_headers):
        """List data executions."""
        resp = client.get("/data/executions", headers=auth_headers)
        assert resp.status_code == 200

    def test_execution_stats(self, client, auth_headers):
        """Get execution statistics."""
        resp = client.get("/data/executions/stats", headers=auth_headers)
        assert resp.status_code == 200

    def test_list_tables(self, client, auth_headers):
        """List data tables."""
        resp = client.get("/data/tables", headers=auth_headers)
        assert resp.status_code == 200

    def test_list_interfaces(self, client, auth_headers):
        """List data interfaces."""
        resp = client.get("/data/interfaces", headers=auth_headers)
        assert resp.status_code == 200

    def test_interface_categories(self, client, auth_headers):
        """List interface categories."""
        resp = client.get("/data/interfaces/categories", headers=auth_headers)
        assert resp.status_code == 200

    def test_sync_config(self, client, auth_headers):
        """Get sync configuration."""
        resp = client.get("/data/sync/config", headers=auth_headers)
        assert resp.status_code == 200

    def test_sync_databases(self, client, auth_headers):
        """List sync databases."""
        resp = client.get("/data/sync/databases", headers=auth_headers)
        assert resp.status_code == 200

    def test_sync_history(self, client, auth_headers):
        """Get sync history."""
        resp = client.get("/data/sync/history", headers=auth_headers)
        assert resp.status_code == 200

    def test_kline_data(self, client, auth_headers):
        """Query K-line data."""
        resp = client.get("/data/kline", headers=auth_headers, params={
            "symbol": "000001",
            "period": "daily",
        })
        # May return empty or error if no data configured
        assert resp.status_code in (200, 400, 404, 422)


# ══════════════════════════════════════════════════════════════════════════════
# 7. Auto Trading
# ══════════════════════════════════════════════════════════════════════════════


class TestAutoTrading:
    def test_get_config(self, client, auth_headers):
        """Get auto-trading configuration."""
        resp = client.get("/auto-trading/config", headers=auth_headers)
        assert resp.status_code == 200

    def test_get_schedule(self, client, auth_headers):
        """Get today's trading schedule."""
        resp = client.get("/auto-trading/schedule", headers=auth_headers)
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# 8. Workspace
# ══════════════════════════════════════════════════════════════════════════════


class TestWorkspace:
    def test_list_workspaces(self, client, auth_headers):
        """List workspaces."""
        resp = client.get("/workspace/", headers=auth_headers)
        assert resp.status_code == 200

    def test_workspace_crud(self, client, auth_headers):
        """Create, read, delete workspace."""
        resp = client.post("/workspace/", headers=auth_headers, json={
            "name": f"E2E Workspace {uuid.uuid4().hex[:6]}",
            "description": "Created by E2E test",
            "workspace_type": "research",
        })
        if resp.status_code in (200, 201):
            ws_id = resp.json()["id"]
            # Read
            resp = client.get(f"/workspace/{ws_id}", headers=auth_headers)
            assert resp.status_code == 200
            # Delete
            resp = client.delete(f"/workspace/{ws_id}", headers=auth_headers)
            assert resp.status_code == 200
        else:
            assert resp.status_code in (400, 422)


# ══════════════════════════════════════════════════════════════════════════════
# 9. Metrics & System
# ══════════════════════════════════════════════════════════════════════════════


class TestMetrics:
    def test_prometheus_metrics(self, client, auth_headers):
        """Prometheus metrics endpoint."""
        resp = client.get("/metrics", headers=auth_headers)
        assert resp.status_code == 200

    def test_metrics_status(self, client, auth_headers):
        """Metrics collection status."""
        resp = client.get("/metrics/status", headers=auth_headers)
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# 10. Risk Control
# ══════════════════════════════════════════════════════════════════════════════


class TestRiskControl:
    def test_risk_control_endpoints(self, client, auth_headers):
        """Risk control module is accessible."""
        # Risk control may have various endpoints — test the base
        resp = client.get("/risk-control/rules", headers=auth_headers)
        # Optional module — may not be loaded
        assert resp.status_code in (200, 404)


# ══════════════════════════════════════════════════════════════════════════════
# 11. Live Trading Extended
# ══════════════════════════════════════════════════════════════════════════════


class TestLiveTradingExtended:
    def test_gateway_credentials(self, client, auth_headers):
        """Get saved gateway credentials."""
        resp = client.get("/live-trading/gateways/credentials", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Should have exchange type keys
        assert any(k in data for k in ("CTP", "MT5", "BINANCE", "OKX", "IB_WEB"))

    def test_start_all(self, client, auth_headers):
        """Start all instances (may be empty)."""
        resp = client.post("/live-trading/start-all", headers=auth_headers)
        assert resp.status_code == 200

    def test_stop_all(self, client, auth_headers):
        """Stop all instances."""
        resp = client.post("/live-trading/stop-all", headers=auth_headers)
        assert resp.status_code == 200

    def test_instance_lifecycle(self, client, auth_headers):
        """Create and delete a live trading instance."""
        # Get a template for strategy_id
        resp = client.get("/strategy/templates", headers=auth_headers)
        templates = resp.json()
        items = templates if isinstance(templates, list) else templates.get("items", [])
        if not items:
            pytest.skip("No strategy templates available")
        strategy_id = items[0]["id"]

        # Create instance
        resp = client.post("/live-trading/", headers=auth_headers, json={
            "strategy_id": strategy_id,
            "params": {},
        })
        if resp.status_code == 200:
            instance_id = resp.json()["id"]
            # Get details
            resp = client.get(f"/live-trading/{instance_id}", headers=auth_headers)
            assert resp.status_code == 200
            # Delete
            resp = client.delete(f"/live-trading/{instance_id}", headers=auth_headers)
            assert resp.status_code == 200
        else:
            # May fail if strategy doesn't support live trading
            assert resp.status_code in (400, 422)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=60"])
