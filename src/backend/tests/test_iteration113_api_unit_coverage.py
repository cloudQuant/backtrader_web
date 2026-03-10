from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException
from starlette.websockets import WebSocketDisconnect


@pytest.mark.asyncio
async def test_comparison_api_happy_and_error_branches():
    from app.api import comparison as comparison_api
    from app.schemas.comparison import ComparisonResponse

    user = SimpleNamespace(sub="u1")
    other_user = SimpleNamespace(sub="u2")

    cmp_obj = ComparisonResponse(
        id="c1",
        user_id="u1",
        name="n",
        description=None,
        type="metrics",
        backtest_task_ids=["t1", "t2"],
        comparison_data={
            "metrics_comparison": {"a": 1},
            "equity_comparison": {"b": 2},
            "trades_comparison": {"c": 3},
            "drawdown_comparison": {"d": 4},
        },
        is_favorite=False,
        is_public=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    class _Svc:
        async def create_comparison(self, **kwargs):
            return cmp_obj

        async def get_comparison(self, comparison_id: str, user_id: str):
            if comparison_id == "missing":
                return None
            return cmp_obj

        async def update_comparison(self, comparison_id: str, user_id: str, update_data):
            if comparison_id == "missing":
                return None
            cmp_obj.is_favorite = update_data.get("is_favorite", cmp_obj.is_favorite)  # type: ignore[misc]
            return cmp_obj

        async def delete_comparison(self, comparison_id: str, user_id: str):
            return comparison_id != "missing"

        async def list_comparisons(self, **kwargs):
            return [cmp_obj], 1

    svc = _Svc()

    # create
    req = SimpleNamespace(name="n", description=None, backtest_task_ids=["t1", "t2"], type="metrics")
    assert await comparison_api.create_comparison(req, current_user=user, service=svc) is cmp_obj

    # detail: 404
    with pytest.raises(HTTPException) as e:
        await comparison_api.get_comparison_detail("missing", current_user=user, service=svc)
    assert e.value.status_code == 404

    # detail: 403 when not owner and not public
    with pytest.raises(HTTPException) as e:
        await comparison_api.get_comparison_detail("c1", current_user=other_user, service=svc)
    assert e.value.status_code == 403

    # detail: success
    assert await comparison_api.get_comparison_detail("c1", current_user=user, service=svc) is cmp_obj

    # update: 404
    with pytest.raises(HTTPException) as e:
        await comparison_api.update_comparison("missing", SimpleNamespace(model_dump=lambda **k: {}), current_user=user, service=svc)
    assert e.value.status_code == 404

    # update: success
    assert await comparison_api.update_comparison(
        "c1",
        SimpleNamespace(model_dump=lambda **k: {"name": "new"}),
        current_user=user,
        service=svc,
    ) is cmp_obj

    # delete: 404
    with pytest.raises(HTTPException) as e:
        await comparison_api.delete_comparison("missing", current_user=user, service=svc)
    assert e.value.status_code == 404

    # delete: success
    assert (await comparison_api.delete_comparison("c1", current_user=user, service=svc))["message"] == "Comparison deleted successfully"

    # list
    out = await comparison_api.list_comparisons(current_user=user, service=svc, limit=20, offset=0, is_public=None)
    assert out.total == 1

    # toggle favorite
    fav = await comparison_api.toggle_comparison_favorite("c1", current_user=user, service=svc)
    assert fav["comparison_id"] == "c1"
    assert isinstance(fav["is_favorite"], bool)

    # share: 403 when not owner
    with pytest.raises(HTTPException) as e:
        await comparison_api.share_comparison("c1", {"shared_with_user_ids": ["u3"]}, current_user=other_user, service=svc)
    assert e.value.status_code == 403

    # share: ok
    resp = await comparison_api.share_comparison("c1", {"shared_with_user_ids": ["u3"]}, current_user=user, service=svc)
    assert resp["message"] == "Comparison shared successfully"

    # data endpoints
    assert (await comparison_api.get_metrics_comparison("c1", current_user=user, service=svc))["metrics_comparison"] == {"a": 1}
    assert (await comparison_api.get_equity_comparison("c1", current_user=user, service=svc))["equity_comparison"] == {"b": 2}
    assert (await comparison_api.get_trades_comparison("c1", current_user=user, service=svc))["trades_comparison"] == {"c": 3}
    assert (await comparison_api.get_drawdown_comparison("c1", current_user=user, service=svc))["drawdown_comparison"] == {"d": 4}


@pytest.mark.asyncio
async def test_analytics_api_detail_kline_monthly_export_and_error():
    from app.api import analytics as analytics_api
    from app.schemas.analytics import PerformanceMetrics

    user = SimpleNamespace(sub="u1")

    class _Svc:
        def calculate_metrics(self, result):
            return PerformanceMetrics(
                initial_capital=1,
                final_assets=1,
                total_return=0,
                annualized_return=0,
                max_drawdown=0,
            )

        def process_equity_curve(self, curve):
            return curve

        def process_drawdown_curve(self, curve):
            return curve

        def process_trades(self, trades):
            return trades

        def calculate_indicators(self, klines):
            return {"ma": [1]}

        def process_signals(self, signals):
            return signals

        def process_monthly_returns(self, monthly_returns):
            return {"years": [], "returns": []}

    svc = _Svc()

    fake_result = {
        "task_id": "t1",
        "strategy_name": "s",
        "symbol": "000001.SZ",
        "start_date": "2023-01-01",
        "end_date": "2023-02-01",
        "equity_curve": [{"date": "2023-01-01", "total_assets": 1, "cash": 1, "position_value": 0}],
        "drawdown_curve": [{"date": "2023-01-01", "drawdown": 0, "peak": 1, "trough": 1}],
        "trades": [],
        "signals": [{"date": "2023-01-10", "type": "buy", "price": 1, "size": 1}],
        "klines": [
            {"date": "2023-01-09", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"date": "2023-01-10", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
            {"date": "2023-01-11", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
        ],
        "log_indicators": {},
        # include both tuple and string keys to cover JSON sanitization branches
        "monthly_returns": {(2023, 1): 0.01, "x": 0.0},
        "created_at": "2023-01-01T00:00:00Z",
    }

    async def _fake_get_backtest_data(task_id, backtest_service, user_id=None):
        return fake_result if task_id == "t1" else None

    with patch.object(analytics_api, "get_backtest_data", side_effect=_fake_get_backtest_data):
        detail = await analytics_api.get_backtest_detail("t1", current_user=user, service=svc, backtest_service=object())
        assert detail.task_id == "t1"

        with pytest.raises(HTTPException) as e:
            await analytics_api.get_backtest_detail("missing", current_user=user, service=svc, backtest_service=object())
        assert e.value.status_code == 404

        kline = await analytics_api.get_kline_with_signals(
            "t1",
            start_date="2023-01-10",
            end_date="2023-01-10",
            current_user=user,
            service=svc,
            backtest_service=object(),
        )
        assert len(kline.klines) == 1

        # log indicators branch
        fake_result2 = dict(fake_result)
        fake_result2["log_indicators"] = {"x": [1.0]}

        async def _fake_get_backtest_data2(task_id, backtest_service, user_id=None):
            return fake_result2

        with patch.object(analytics_api, "get_backtest_data", side_effect=_fake_get_backtest_data2):
            kline2 = await analytics_api.get_kline_with_signals(
                "t1",
                current_user=user,
                service=svc,
                backtest_service=object(),
            )
        assert kline2.indicators == {"x": [1.0]}

        monthly = await analytics_api.get_monthly_returns("t1", current_user=user, service=svc, backtest_service=object())
        assert monthly == {"years": [], "returns": []}

        csv_resp = await analytics_api.export_backtest_results(
            "t1",
            format="csv",
            current_user=user,
            service=svc,
            backtest_service=object(),
        )
        assert csv_resp.media_type == "text/csv"

        json_resp = await analytics_api.export_backtest_results(
            "t1",
            format="json",
            current_user=user,
            service=svc,
            backtest_service=object(),
        )
        assert json_resp.media_type == "application/json"

        with pytest.raises(HTTPException) as e:
            await analytics_api.export_backtest_results(
                "t1",
                format="nope",
                current_user=user,
                service=svc,
                backtest_service=object(),
            )
        assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_analytics_get_backtest_data_internal_exception_and_monthly_branch(monkeypatch):
    from app.api import analytics as analytics_api

    # _resolve_log_dir exception branch
    class _RepoBoom:
        def __init__(self, *_a, **_k):
            raise RuntimeError("boom")

    monkeypatch.setattr(analytics_api, "SQLRepository", _RepoBoom, raising=True)
    monkeypatch.setattr(analytics_api, "find_latest_log_dir", lambda p: Path("/tmp/fallback"), raising=True)
    out = await analytics_api._resolve_log_dir("t1", "s1")
    assert isinstance(out, Path)

    # get_backtest_data exception branches + monthly return month-change branch.
    class _BacktestSvc:
        async def get_result(self, task_id: str, user_id: str = None):
            return SimpleNamespace(
                strategy_id="s1",
                symbol="000001.SZ",
                start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
                end_date=datetime(2023, 2, 2, tzinfo=timezone.utc),
                created_at=datetime(2023, 2, 3, tzinfo=timezone.utc),
                equity_dates=["2023-01-01", "2023-02-01"],
                equity_curve=[100.0, 110.0],
                drawdown_curve=[0.0, 0.0],
                trades=[],
            )

    svc = _BacktestSvc()
    monkeypatch.setattr(analytics_api, "_resolve_log_dir", AsyncMock(return_value=Path("/tmp/logs")), raising=True)
    monkeypatch.setattr(analytics_api, "parse_value_log", Mock(side_effect=RuntimeError("parse boom")), raising=True)
    monkeypatch.setattr("app.services.log_parser_service.parse_trade_log", Mock(side_effect=RuntimeError("trade boom")), raising=True)

    data = await analytics_api.get_backtest_data("t1", svc, user_id="u1")
    assert data is not None
    assert (2023, 1) in data["monthly_returns"]


@pytest.mark.asyncio
async def test_backtest_enhanced_api_run_list_and_reports_and_websocket_disconnect():
    from app.api import backtest_enhanced as bt_api
    from app.schemas.backtest_enhanced import (
        BacktestRequest,
        BacktestResponse,
        BacktestResult,
        TaskStatus,
    )

    user = SimpleNamespace(sub="u1")

    req = BacktestRequest(
        strategy_id="001_ma_cross",
        symbol="000001.SZ",
        start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2023, 3, 5, tzinfo=timezone.utc),
        initial_cash=100000,
        commission=0.001,
        params={},
    )

    class _BacktestSvc:
        async def run_backtest(self, user_id: str, request):
            return BacktestResponse(task_id="t1", status=TaskStatus.PENDING, message="ok")

        async def get_result(self, task_id: str, user_id: str = None):
            if task_id == "missing":
                return None
            return BacktestResult(
                task_id=task_id,
                strategy_id="s1",
                symbol="000001.SZ",
                start_date=req.start_date,
                end_date=req.end_date,
                status=TaskStatus.COMPLETED,
                total_return=1.0,
                annual_return=1.0,
                sharpe_ratio=1.0,
                max_drawdown=0.0,
                win_rate=0.0,
                total_trades=0,
                profitable_trades=0,
                losing_trades=0,
                equity_curve=[],
                equity_dates=[],
                drawdown_curve=[],
                trades=[],
                created_at=datetime.now(timezone.utc),
                error_message=None,
            )

        async def get_task_status(self, task_id: str, user_id: str = None):
            return None if task_id == "missing" else TaskStatus.COMPLETED

        async def list_results(self, *args, **kwargs):
            return SimpleNamespace(total=0, items=[])

        async def delete_result(self, task_id: str, user_id: str):
            return task_id != "missing"

    class _ReportSvc:
        async def generate_pdf_report(self, result, strategy):
            return b"%PDF"

        async def generate_excel_report(self, result, strategy):
            return b"PK"

    svc = _BacktestSvc()
    report = _ReportSvc()

    with patch.object(bt_api.ws_manager, "send_to_task", new=AsyncMock()):
        resp = await bt_api.run_backtest(req, current_user=user, service=svc)
        assert resp.task_id == "t1"

    ok = await bt_api.get_backtest_result("t1", current_user=user, service=svc)
    assert ok.task_id == "t1"

    ok_status = await bt_api.get_backtest_status("t1", current_user=user, service=svc)
    assert ok_status["status"] == TaskStatus.COMPLETED.value

    ok_del = await bt_api.delete_backtest("t1", current_user=user, service=svc)
    assert ok_del["message"] == "Deleted successfully"

    with pytest.raises(HTTPException) as e:
        await bt_api.get_backtest_result("missing", current_user=user, service=svc)
    assert e.value.status_code == 404

    with pytest.raises(HTTPException) as e:
        await bt_api.get_backtest_status("missing", current_user=user, service=svc)
    assert e.value.status_code == 404

    with pytest.raises(HTTPException) as e:
        await bt_api.delete_backtest("missing", current_user=user, service=svc)
    assert e.value.status_code == 404

    pdf = await bt_api.get_pdf_report("t1", current_user=user, backtest_service=svc, report_service=report)
    assert pdf.media_type == "application/pdf"

    excel = await bt_api.get_excel_report("t1", current_user=user, backtest_service=svc, report_service=report)
    assert "spreadsheetml" in excel.media_type

    # Optimization method checks.
    opt_req = SimpleNamespace(method="bayesian")

    class _OptSvc:
        async def run_grid_search(self, *_a, **_k):
            raise AssertionError("should not be called")

        async def run_bayesian_optimization(self, *_a, **_k):
            return {"ok": True}

    with pytest.raises(HTTPException) as e:
        await bt_api.grid_search_optimization(SimpleNamespace(method="nope"), current_user=user, service=_OptSvc())
    assert e.value.status_code == 400

    with pytest.raises(HTTPException) as e:
        await bt_api.bayesian_optimization(SimpleNamespace(method="nope"), current_user=user, service=_OptSvc())
    assert e.value.status_code == 400

    assert await bt_api.bayesian_optimization(opt_req, current_user=user, service=_OptSvc()) == {"ok": True}

    # WebSocket disconnect branch.
    ws = object()
    with patch.object(bt_api.ws_manager, "connect", new=AsyncMock()), \
        patch.object(bt_api.ws_manager, "disconnect") as disc, \
        patch.object(bt_api, "get_backtest_service", return_value=svc):
        svc.get_task_status = AsyncMock(side_effect=WebSocketDisconnect())  # type: ignore[method-assign]
        await bt_api.websocket_endpoint(ws, "t1")
        disc.assert_called()
