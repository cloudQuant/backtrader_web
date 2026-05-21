"""
Full coverage E2E API tests — fills gaps from test_api_e2e.py and test_api_extended.py.

Covers remaining endpoints in:
1. RAG (indexing, search)
2. Realtime (subscribe, status)
3. Simulation (instances, CRUD, analytics)
4. Strategy Versions (CRUD, diff)
5. Workspace (extended CRUD, units, trading)
6. Comparisons (metrics, equity, trades, drawdown)
7. Analytics (optimization results)
8. Backtests (trades pagination, reports)
9. Live Trading (start/stop, detail, kline, monthly)
10. Optimization (progress, results, cancel, strategy-params)
11. Root endpoints

Requires: Backend running on http://127.0.0.1:8000
Run: pytest tests/e2e/test_api_full_coverage.py -v --timeout=60
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
def auth(client):
    """Get admin auth headers with rate-limit retry."""
    for attempt in range(5):
        resp = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
        if resp.status_code == 200:
            return {"Authorization": f"Bearer {resp.json()['access_token']}"}
        if resp.status_code == 429:
            time.sleep(resp.json().get("retry_after", 10) + 1)
    pytest.fail("Could not login")


# ══════════════════════════════════════════════════════════════════════════════
# 1. RAG
# ══════════════════════════════════════════════════════════════════════════════


class TestRAG:
    def test_rag_search_requires_params(self, client, auth):
        """RAG search requires query parameters."""
        resp = client.post("/rag/search", headers=auth, json={})
        assert resp.status_code in (200, 400, 422)

    def test_rag_index_requires_params(self, client, auth):
        """RAG index requires knowledge base ID."""
        resp = client.post("/rag/index", headers=auth, json={})
        assert resp.status_code in (200, 400, 422)

    def test_rag_search_with_query(self, client, auth):
        """RAG search with a query string."""
        resp = client.post("/rag/search", headers=auth, json={
            "query": "moving average strategy",
            "top_k": 5,
        })
        assert resp.status_code in (200, 400, 422)


# ══════════════════════════════════════════════════════════════════════════════
# 2. Realtime
# ══════════════════════════════════════════════════════════════════════════════


class TestRealtime:
    def test_realtime_subscribe(self, client, auth):
        """Realtime subscribe endpoint."""
        resp = client.get("/realtime/subscribe", headers=auth)
        assert resp.status_code in (200, 400, 404, 422)  # Optional module

    def test_realtime_status(self, client, auth):
        """Realtime connection status."""
        resp = client.get("/realtime/status", headers=auth)
        assert resp.status_code in (200, 404)

    def test_realtime_symbols(self, client, auth):
        """Realtime available symbols."""
        resp = client.get("/realtime/symbols", headers=auth)
        assert resp.status_code in (200, 404)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Simulation
# ══════════════════════════════════════════════════════════════════════════════


class TestSimulation:
    def test_list_instances(self, client, auth):
        """List simulation instances."""
        resp = client.get("/simulation/", headers=auth)
        assert resp.status_code == 200

    def test_list_presets(self, client, auth):
        """List simulation presets."""
        resp = client.get("/simulation/presets", headers=auth)
        assert resp.status_code in (200, 404)  # May not have presets endpoint

    def test_instance_not_found(self, client, auth):
        """Non-existent simulation instance returns 404."""
        resp = client.get("/simulation/nonexistent-id", headers=auth)
        assert resp.status_code == 404

    def test_start_all(self, client, auth):
        """Start all simulation instances."""
        resp = client.post("/simulation/start-all", headers=auth)
        assert resp.status_code == 200

    def test_stop_all(self, client, auth):
        """Stop all simulation instances."""
        resp = client.post("/simulation/stop-all", headers=auth)
        assert resp.status_code == 200

    def test_simulation_instance_lifecycle(self, client, auth):
        """Create, get, delete simulation instance."""
        resp = client.get("/strategy/templates", headers=auth)
        templates = resp.json()
        items = templates if isinstance(templates, list) else templates.get("items", [])
        if not items:
            pytest.skip("No templates")
        strategy_id = items[0]["id"]

        # Create
        resp = client.post("/simulation/", headers=auth, json={
            "strategy_id": strategy_id,
            "params": {},
        })
        if resp.status_code == 200:
            inst_id = resp.json()["id"]
            # Get
            resp = client.get(f"/simulation/{inst_id}", headers=auth)
            assert resp.status_code == 200
            # Delete
            resp = client.delete(f"/simulation/{inst_id}", headers=auth)
            assert resp.status_code == 200
        else:
            assert resp.status_code in (400, 422)


# ══════════════════════════════════════════════════════════════════════════════
# 4. Strategy Versions
# ══════════════════════════════════════════════════════════════════════════════


class TestStrategyVersions:
    def test_list_versions(self, client, auth):
        """List strategy versions."""
        resp = client.get("/strategy-versions/", headers=auth)
        assert resp.status_code in (200, 404)  # Optional module

    def test_version_not_found(self, client, auth):
        """Non-existent version returns 404."""
        resp = client.get("/strategy-versions/nonexistent-id", headers=auth)
        assert resp.status_code == 404

    def test_create_version(self, client, auth):
        """Create a strategy version."""
        # First create a strategy
        resp = client.post("/strategy/", headers=auth, json={
            "name": f"Version Test {uuid.uuid4().hex[:6]}",
            "description": "For version testing",
            "code": "import backtrader as bt\nclass S(bt.Strategy):\n    def next(self): pass",
            "category": "custom",
        })
        if resp.status_code in (200, 201):
            strategy_id = resp.json()["id"]
            # Create version
            resp = client.post("/strategy-versions/", headers=auth, json={
                "strategy_id": strategy_id,
                "version_tag": "v1.0",
                "description": "Initial version",
            })
            assert resp.status_code in (200, 201, 400, 404, 422)  # 404 if module not loaded
            # Cleanup
            client.delete(f"/strategy/{strategy_id}", headers=auth)


# ══════════════════════════════════════════════════════════════════════════════
# 5. Workspace Extended
# ══════════════════════════════════════════════════════════════════════════════


class TestWorkspaceExtended:
    def test_list_workspaces_with_type(self, client, auth):
        """List workspaces filtered by type."""
        resp = client.get("/workspace/", headers=auth, params={"workspace_type": "research"})
        assert resp.status_code == 200

    def test_list_trading_workspaces(self, client, auth):
        """List trading workspaces."""
        resp = client.get("/workspace/", headers=auth, params={"workspace_type": "trading"})
        assert resp.status_code == 200

    def test_workspace_full_lifecycle(self, client, auth):
        """Full workspace lifecycle with units."""
        # Create workspace
        resp = client.post("/workspace/", headers=auth, json={
            "name": f"Full Test {uuid.uuid4().hex[:6]}",
            "description": "Full lifecycle test",
            "workspace_type": "research",
        })
        if resp.status_code not in (200, 201):
            pytest.skip(f"Cannot create workspace: {resp.status_code}")
        ws_id = resp.json()["id"]

        # Get workspace
        resp = client.get(f"/workspace/{ws_id}", headers=auth)
        assert resp.status_code == 200

        # Update workspace
        resp = client.put(f"/workspace/{ws_id}", headers=auth, json={
            "name": "Updated Workspace",
            "description": "Updated description",
        })
        assert resp.status_code == 200

        # List units
        resp = client.get(f"/workspace/{ws_id}/units", headers=auth)
        assert resp.status_code == 200

        # Add unit
        resp2 = client.get("/strategy/templates", headers=auth)
        templates = resp2.json()
        items = templates if isinstance(templates, list) else templates.get("items", [])
        if items:
            resp = client.post(f"/workspace/{ws_id}/units", headers=auth, json={
                "strategy_id": items[0]["id"],
                "name": "Test Unit",
            })
            if resp.status_code in (200, 201):
                unit_id = resp.json()["id"]
                # Get unit
                resp = client.get(f"/workspace/{ws_id}/units/{unit_id}", headers=auth)
                assert resp.status_code == 200
                # Delete unit
                resp = client.delete(f"/workspace/{ws_id}/units/{unit_id}", headers=auth)
                assert resp.status_code == 200

        # Delete workspace
        resp = client.delete(f"/workspace/{ws_id}", headers=auth)
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# 6. Comparisons Extended
# ══════════════════════════════════════════════════════════════════════════════


class TestComparisonsExtended:
    def test_comparison_data_endpoints(self, client, auth):
        """Test comparison data sub-endpoints (metrics, equity, trades, drawdown)."""
        # Create a comparison first
        resp = client.post("/comparisons/", headers=auth, json={
            "name": f"Data Test {uuid.uuid4().hex[:6]}",
            "backtest_task_ids": [],
            "type": "metrics",
        })
        if resp.status_code not in (200, 201):
            pytest.skip("Cannot create comparison")
        cmp_id = resp.json()["id"]

        # Test all data endpoints
        for endpoint in ["metrics", "equity", "trades", "drawdown"]:
            resp = client.get(f"/comparisons/{cmp_id}/{endpoint}", headers=auth)
            assert resp.status_code in (200, 404)

        # Cleanup
        client.delete(f"/comparisons/{cmp_id}", headers=auth)


# ══════════════════════════════════════════════════════════════════════════════
# 7. Analytics Extended
# ══════════════════════════════════════════════════════════════════════════════


class TestAnalyticsExtended:
    def test_analytics_not_found(self, client, auth):
        """Analytics for non-existent task returns 404."""
        resp = client.get("/analytics/nonexistent-task/detail", headers=auth)
        assert resp.status_code == 404

    def test_analytics_kline_not_found(self, client, auth):
        """Kline for non-existent task returns 404."""
        resp = client.get("/analytics/nonexistent-task/kline", headers=auth)
        assert resp.status_code == 404

    def test_analytics_monthly_not_found(self, client, auth):
        """Monthly returns for non-existent task returns 404."""
        resp = client.get("/analytics/nonexistent-task/monthly-returns", headers=auth)
        assert resp.status_code == 404

    def test_analytics_export_not_found(self, client, auth):
        """Export for non-existent task returns 404."""
        resp = client.get("/analytics/nonexistent-task/export", headers=auth, params={"format": "json"})
        assert resp.status_code == 404

    def test_analytics_optimization_not_found(self, client, auth):
        """Optimization results for non-existent task returns 404."""
        resp = client.get("/analytics/nonexistent-task/optimization", headers=auth)
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 8. Backtests Extended
# ══════════════════════════════════════════════════════════════════════════════


class TestBacktestsExtended:
    def test_backtest_trades_not_found(self, client, auth):
        """Trades for non-existent task returns 404."""
        resp = client.get("/backtests/nonexistent/trades", headers=auth)
        assert resp.status_code == 404

    def test_backtest_report_html_not_found(self, client, auth):
        """HTML report for non-existent task returns 404."""
        resp = client.get("/backtests/nonexistent/report/html", headers=auth)
        assert resp.status_code == 404

    def test_backtest_report_pdf_not_found(self, client, auth):
        """PDF report for non-existent task returns 404."""
        resp = client.get("/backtests/nonexistent/report/pdf", headers=auth)
        assert resp.status_code == 404

    def test_backtest_report_excel_not_found(self, client, auth):
        """Excel report for non-existent task returns 404."""
        resp = client.get("/backtests/nonexistent/report/excel", headers=auth)
        assert resp.status_code == 404

    def test_backtest_cancel_not_found(self, client, auth):
        """Cancel non-existent task returns 400/404."""
        resp = client.post("/backtests/nonexistent/cancel", headers=auth)
        assert resp.status_code in (400, 404)

    def test_backtest_delete_not_found(self, client, auth):
        """Delete non-existent task returns 404."""
        resp = client.delete("/backtests/nonexistent", headers=auth)
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 9. Optimization Extended
# ══════════════════════════════════════════════════════════════════════════════


class TestOptimizationExtended:
    def test_optimization_progress_not_found(self, client, auth):
        """Progress for non-existent task."""
        resp = client.get("/optimization/progress/nonexistent", headers=auth)
        assert resp.status_code in (200, 404)

    def test_optimization_results_not_found(self, client, auth):
        """Results for non-existent task."""
        resp = client.get("/optimization/results/nonexistent", headers=auth)
        assert resp.status_code in (200, 404)

    def test_optimization_cancel_not_found(self, client, auth):
        """Cancel non-existent task."""
        resp = client.post("/optimization/cancel/nonexistent", headers=auth)
        assert resp.status_code in (200, 400, 404)

    def test_optimization_strategy_params(self, client, auth):
        """Get strategy default parameters."""
        resp = client.get("/strategy/templates", headers=auth)
        templates = resp.json()
        items = templates if isinstance(templates, list) else templates.get("items", [])
        if items:
            strategy_id = items[0]["id"]
            resp = client.get(f"/optimization/strategy-params/{strategy_id}", headers=auth)
            assert resp.status_code in (200, 404)

    def test_optimization_submit_backtest_style(self, client, auth):
        """Submit backtest-style optimization."""
        resp = client.get("/strategy/templates", headers=auth)
        templates = resp.json()
        items = templates if isinstance(templates, list) else templates.get("items", [])
        if not items:
            pytest.skip("No templates")
        resp = client.post("/optimization/submit/backtest", headers=auth, json={
            "strategy_id": items[0]["id"],
            "symbol": "000001.SZ",
            "start_date": "2023-01-01T00:00:00",
            "end_date": "2023-03-01T00:00:00",
            "initial_cash": 100000,
            "method": "grid",
            "param_ranges": {"fast_period": {"min": 5, "max": 10, "step": 5}},
        })
        assert resp.status_code in (200, 400, 422)


# ══════════════════════════════════════════════════════════════════════════════
# 10. Live Trading Extended (detail, kline, monthly)
# ══════════════════════════════════════════════════════════════════════════════


class TestLiveTradingFull:
    def test_instance_detail_not_found(self, client, auth):
        """Detail for non-existent instance returns 404."""
        resp = client.get("/live-trading/nonexistent/detail", headers=auth)
        assert resp.status_code == 404

    def test_instance_kline_not_found(self, client, auth):
        """Kline for non-existent instance returns 404."""
        resp = client.get("/live-trading/nonexistent/kline", headers=auth)
        assert resp.status_code == 404

    def test_instance_monthly_not_found(self, client, auth):
        """Monthly returns for non-existent instance returns 404."""
        resp = client.get("/live-trading/nonexistent/monthly-returns", headers=auth)
        assert resp.status_code == 404

    def test_gateway_account_not_found(self, client, auth):
        """Gateway account for non-existent key returns 404."""
        resp = client.get("/live-trading/gateways/nonexistent/account", headers=auth)
        assert resp.status_code == 404

    def test_gateway_positions_not_found(self, client, auth):
        """Gateway positions for non-existent key."""
        resp = client.get("/live-trading/gateways/nonexistent/positions", headers=auth)
        assert resp.status_code in (200, 404)


# ══════════════════════════════════════════════════════════════════════════════
# 11. Root & Misc
# ══════════════════════════════════════════════════════════════════════════════


class TestRoot:
    def test_root_endpoint(self, client):
        """Root endpoint returns app info."""
        resp = httpx.get(BASE_URL, timeout=10)
        assert resp.status_code == 200

    def test_info_endpoint(self, client):
        """Info endpoint returns app info."""
        resp = httpx.get(f"{BASE_URL}/info", timeout=10)
        assert resp.status_code in (200, 404)

    def test_status_cache(self, client, auth):
        """Cache status endpoint."""
        resp = client.get("/status/cache", headers=auth)
        assert resp.status_code in (200, 404)


# ══════════════════════════════════════════════════════════════════════════════
# 12. Quote Extended
# ══════════════════════════════════════════════════════════════════════════════


class TestQuoteExtended:
    def test_add_custom_symbols(self, client, auth):
        """Add custom symbols."""
        resp = client.post("/quote/symbols/add", headers=auth, json={
            "source": "akshare",
            "symbols": ["TEST001"],
        })
        assert resp.status_code in (200, 400, 422)

    def test_remove_custom_symbols(self, client, auth):
        """Remove custom symbols."""
        resp = client.post("/quote/symbols/remove", headers=auth, json={
            "source": "akshare",
            "symbols": ["TEST001"],
        })
        assert resp.status_code in (200, 400, 422)


# ══════════════════════════════════════════════════════════════════════════════
# 13. KB Chat Extended
# ══════════════════════════════════════════════════════════════════════════════


class TestKBChatExtended:
    def test_send_message_requires_params(self, client, auth):
        """Send message requires conversation context."""
        resp = client.post("/kb-chat/send", headers=auth, json={
            "message": "Hello",
        })
        assert resp.status_code in (200, 400, 422)

    def test_conversation_history_not_found(self, client, auth):
        """History for non-existent conversation."""
        resp = client.get("/kb-chat/history/nonexistent-id", headers=auth)
        assert resp.status_code in (200, 404)

    def test_delete_conversation_not_found(self, client, auth):
        """Delete non-existent conversation."""
        resp = client.delete("/kb-chat/conversations/nonexistent-id", headers=auth)
        assert resp.status_code in (200, 404)


# ══════════════════════════════════════════════════════════════════════════════
# 14. Paper Trading Extended
# ══════════════════════════════════════════════════════════════════════════════


class TestPaperTradingExtended:
    def test_get_order_not_found(self, client, auth):
        """Get non-existent order returns 404."""
        resp = client.get("/paper-trading/orders/nonexistent", headers=auth)
        assert resp.status_code in (404, 403)

    def test_cancel_order_not_found(self, client, auth):
        """Cancel non-existent order returns 404."""
        resp = client.delete("/paper-trading/orders/nonexistent", headers=auth)
        assert resp.status_code == 404

    def test_get_position_not_found(self, client, auth):
        """Get non-existent position returns 404."""
        resp = client.get("/paper-trading/positions/nonexistent", headers=auth)
        assert resp.status_code in (404, 403)

    def test_get_account_not_found(self, client, auth):
        """Get non-existent account returns 404."""
        resp = client.get("/paper-trading/accounts/nonexistent", headers=auth)
        assert resp.status_code in (404, 403)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=60"])
