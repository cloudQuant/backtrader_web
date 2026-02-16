import builtins
import datetime as dt
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_me_user_not_found_returns_404(client: AsyncClient, auth_headers: dict):
    with patch("app.api.auth.AuthService.get_user_by_id", new=AsyncMock(return_value=None)):
        resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_health_check_exception_branch(client: AsyncClient, monkeypatch):
    import app.db.database as db_module

    class BadSessionCtx:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(db_module, "async_session_maker", lambda: BadSessionCtx(), raising=True)
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"


def test_deps_permissions_get_current_user_delegates(monkeypatch):
    import app.api.deps as deps_module
    import app.api.deps_permissions as deps_perm_module

    monkeypatch.setattr(deps_module, "get_current_user", lambda: "ok", raising=True)
    assert deps_perm_module.get_current_user() == "ok"


def test_drawdown_analyzer_updates_peak_branch():
    from app.services.backtest_analyzers import DrawdownAnalyzer

    analyzer = DrawdownAnalyzer()
    analyzer.drawdown_curve = []
    analyzer.peak = 100

    analyzer.strategy = SimpleNamespace(broker=SimpleNamespace(getvalue=lambda: 200))
    analyzer.datas = [
        SimpleNamespace(
            datetime=SimpleNamespace(datetime=lambda _i: dt.datetime(2024, 1, 2, 0, 0, 0))
        )
    ]

    analyzer.next()
    assert analyzer.peak == 200
    assert analyzer.drawdown_curve


@pytest.mark.asyncio
async def test_websocket_manager_broadcast_error_disconnects():
    from app.websocket_manager import ConnectionManager

    class BadWebSocket:
        async def send_json(self, _msg):
            raise RuntimeError("send failed")

    mgr = ConnectionManager()
    ws = BadWebSocket()
    mgr.active_connections["t1"] = [(ws, "c1")]

    await mgr.broadcast({"x": 1})
    assert "t1" not in mgr.active_connections


def test_report_service_optional_import_branches(monkeypatch):
    """
    Force ImportError for optional report dependencies and verify the module sets flags accordingly.
    """
    import app.services.report_service as report_module

    original_import = builtins.__import__
    blocked = {"jinja2", "pandas", "openpyxl", "weasyprint"}

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.split(".", 1)[0] in blocked:
            raise ImportError(f"blocked import for test: {name}")
        return original_import(name, globals, locals, fromlist, level)

    try:
        builtins.__import__ = _import
        importlib.reload(report_module)
        assert report_module.JINJA2_AVAILABLE is False
        assert report_module.PANDAS_AVAILABLE is False
        assert report_module.OPENPYXL_AVAILABLE is False
        assert report_module.WEASYPRINT_AVAILABLE is False
    finally:
        builtins.__import__ = original_import
        importlib.reload(report_module)


@pytest.mark.asyncio
async def test_report_service_raises_when_disabled(monkeypatch):
    import app.services.report_service as report_module
    from app.services.report_service import ReportService

    monkeypatch.setattr(report_module, "JINJA2_AVAILABLE", False, raising=True)
    monkeypatch.setattr(report_module, "WEASYPRINT_AVAILABLE", False, raising=True)
    monkeypatch.setattr(report_module, "PANDAS_AVAILABLE", False, raising=True)
    monkeypatch.setattr(report_module, "OPENPYXL_AVAILABLE", False, raising=True)

    svc = ReportService()
    with pytest.raises(ImportError):
        await svc.generate_html_report({}, {"name": "s"})
    with pytest.raises(ImportError):
        await svc.generate_pdf_report({}, {"name": "s"})
    with pytest.raises(ImportError):
        await svc.generate_excel_report({}, {"name": "s"})


@pytest.mark.asyncio
async def test_backtest_api_success_paths(client: AsyncClient, auth_headers: dict):
    from app.api import backtest as backtest_api
    from app.schemas.backtest import (
        BacktestListResponse,
        BacktestResponse,
        BacktestResult,
        TaskStatus,
    )

    now = dt.datetime(2024, 1, 1, 0, 0, 0)
    result_obj = BacktestResult(
        task_id="t1",
        strategy_id="001_ma_cross",
        symbol="000001.SZ",
        start_date=now,
        end_date=now + dt.timedelta(days=180),
        status=TaskStatus.RUNNING,
        created_at=now,
    )

    # app.api.backtest.get_backtest_service is lru_cached; clear it to ensure our patch is used.
    backtest_api.get_backtest_service.cache_clear()
    with patch("app.api.backtest.BacktestService") as mock_cls:
        svc = AsyncMock()
        svc.get_result = AsyncMock(return_value=result_obj)
        svc.get_task_status = AsyncMock(return_value=TaskStatus.RUNNING)
        svc.cancel_task = AsyncMock(return_value=True)
        svc.delete_result = AsyncMock(return_value=True)
        svc.run_backtest = AsyncMock(
            return_value=BacktestResponse(task_id="t1", status=TaskStatus.PENDING, message="ok")
        )
        svc.list_results = AsyncMock(return_value=BacktestListResponse(total=0, items=[]))
        mock_cls.return_value = svc

        run = await client.post("/api/v1/backtest/run", headers=auth_headers, json={
            "strategy_id": "001_ma_cross",
            "symbol": "000001.SZ",
            "start_date": "2023-01-01T00:00:00",
            "end_date": "2023-06-30T00:00:00",
            "initial_cash": 100000,
            "commission": 0.001,
            "params": {},
        })
        assert run.status_code == 200

        r1 = await client.get("/api/v1/backtest/t1", headers=auth_headers)
        assert r1.status_code == 200

        s1 = await client.get("/api/v1/backtest/t1/status", headers=auth_headers)
        assert s1.status_code == 200

        l1 = await client.get("/api/v1/backtest/?sort_order=desc", headers=auth_headers)
        assert l1.status_code == 200

        c1 = await client.post("/api/v1/backtest/t1/cancel", headers=auth_headers)
        assert c1.status_code == 200

        d1 = await client.delete("/api/v1/backtest/t1", headers=auth_headers)
        assert d1.status_code == 200

    backtest_api.get_backtest_service.cache_clear()
