import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_live_trading_api_remove_and_get_instance_success_paths():
    """Cover success returns for remove_instance() and get_instance()."""
    from app.api import live_trading_api as api

    user = SimpleNamespace(sub="u1")

    mgr = MagicMock()
    mgr.remove_instance.return_value = True
    mgr.get_instance.return_value = {"id": "iid", "strategy_id": "s1"}

    resp = await api.remove_instance("iid", current_user=user, mgr=mgr)
    assert resp == {"message": "Deleted successfully"}

    inst = await api.get_instance("iid", current_user=user, mgr=mgr)
    assert inst["strategy_id"] == "s1"


@pytest.mark.asyncio
async def test_live_trading_api_detail_kline_monthly_returns_branches():
    """Cover missing branches in get_live_detail/get_live_kline/get_live_monthly_returns."""
    from app.api import live_trading_api as api

    user = SimpleNamespace(sub="u1")
    mgr = MagicMock()
    mgr.get_instance.return_value = {
        "id": "iid",
        "strategy_id": "s1",
        "strategy_name": "S1",
        "status": "running",
        "created_at": "2026-02-15 00:00:00",
    }

    # get_live_detail: cover trade pnl/cumulative branches.
    log_result = {
        "initial_cash": 100000,
        "final_value": 101000,
        "total_return": 0.01,
        "annual_return": 0.02,
        "max_drawdown": -0.01,
        "sharpe_ratio": 1.1,
        "win_rate": 50.0,
        "total_trades": 1,
        "equity_dates": ["2026-01-01", "2026-01-02"],
        "equity_curve": [100000.0, 101000.0],
        "cash_curve": [50000.0, 50000.0],
        "drawdown_curve": [0.0, -0.01],
        "trades": [
            {
                "pnlcomm": 12.34,
                "datetime": "2026-01-02T00:00:00",
                "price": 1.23,
                "size": 1,
                "value": 1.23,
                "commission": 0.01,
                "barlen": 1,
            }
        ],
    }
    with patch.object(api, "parse_all_logs", return_value=log_result):
        detail = await api.get_live_detail("iid", current_user=user, mgr=mgr)
        assert detail.task_id == "iid"
        assert len(detail.trades) == 1
        assert detail.trades[0].cumulative_pnl == 12.34

    # get_live_kline: cover break when ohlc shorter than dates + signal creation.
    with patch.object(api, "_get_strategy_log_dir", return_value=Path("/tmp/fake")):
        with patch.object(
            api,
            "parse_data_log",
            return_value={
                "dates": ["2026-01-01", "2026-01-02"],
                "ohlc": [
                    [1.0, 1.1, 0.9, 1.2],
                ],
                "volumes": [],
                "indicators": {},
            },
        ):
            with patch.object(
                api,
                "parse_trade_log",
                return_value=[
                    {
                        "direction": "buy",
                        "dtopen": "2026-01-01T00:00:00",
                        "dtclose": "2026-01-02T00:00:00",
                        "price": 1.1,
                    },
                ],
            ):
                kline = await api.get_live_kline("iid", current_user=user, mgr=mgr)
                assert kline.symbol == "s1"
                assert len(kline.klines) == 1  # break executed
                assert len(kline.signals) == 2  # open + close

    # get_live_monthly_returns: cover dt slicing exception path.
    with patch.object(api, "_get_strategy_log_dir", return_value=Path("/tmp/fake")):
        with patch.object(
            api, "parse_value_log", return_value={"dates": [None], "equity_curve": [100000.0]}
        ):
            mr = await api.get_live_monthly_returns("iid", current_user=user, mgr=mgr)
            assert mr.returns == []


@pytest.mark.asyncio
async def test_portfolio_api_overview_positions_equity_missing_branches(tmp_path: Path):
    """Cover portfolio_api missing branches: overview (log_dir exists), positions, equity dates-empty continue."""
    from app.api import portfolio_api as api

    mgr = MagicMock()
    mgr.list_instances.return_value = [
        {"id": "iid1", "strategy_id": "s1", "status": "stopped", "strategy_name": "S1"},
    ]

    fake_log_dir = tmp_path / "logs" / "x"
    fake_log_dir.mkdir(parents=True)

    with patch.object(api, "find_latest_log_dir", return_value=fake_log_dir):
        with patch.object(
            api,
            "parse_value_log",
            return_value={
                "equity_curve": [100.0, 110.0],
                "cash_curve": [50.0, 55.0],
            },
        ):
            with patch.object(api, "parse_trade_log", return_value=[{"pnlcomm": 1.0}]):
                overview = await api.get_portfolio_overview(
                    current_user=SimpleNamespace(sub="u1"), mgr=mgr
                )
                assert overview["strategy_count"] == 1
                assert overview["total_assets"] == 110.0

    with patch.object(api, "find_latest_log_dir", return_value=fake_log_dir):
        with patch.object(
            api,
            "parse_current_position",
            return_value=[
                {"data_name": "BTC/USDT", "size": 1, "price": 1.0, "market_value": 1.0},
            ],
        ):
            positions = await api.get_portfolio_positions(
                current_user=SimpleNamespace(sub="u1"), mgr=mgr
            )
            assert positions["total"] == 1

    # equity: cover "if not dates: continue" branch
    with patch.object(api, "find_latest_log_dir", return_value=fake_log_dir):
        with patch.object(
            api, "parse_value_log", return_value={"dates": [], "equity_curve": [], "cash_curve": []}
        ):
            equity = await api.get_portfolio_equity(current_user=SimpleNamespace(sub="u1"), mgr=mgr)
            assert equity["dates"] == []


@pytest.mark.asyncio
async def test_realtime_data_websocket_disconnect_on_exception(monkeypatch):
    """Cover realtime_data websocket connect/send/exception/disconnect branch."""
    from app.api import realtime_data as api

    ws = object()
    monkeypatch.setattr(api.ws_manager, "connect", AsyncMock())
    monkeypatch.setattr(api.ws_manager, "send_to_task", AsyncMock())
    monkeypatch.setattr(api.ws_manager, "disconnect", MagicMock())

    async def _boom(_):
        raise RuntimeError("boom")

    monkeypatch.setattr(asyncio, "sleep", _boom)
    await api.realtime_tick_websocket(ws, broker_id="binance")
    api.ws_manager.send_to_task.assert_awaited_once()
    task_id, payload = api.ws_manager.send_to_task.await_args.args
    assert task_id == "ticks:binance"
    assert payload["type"] == api.MessageType.CONNECTED
    assert payload["streaming_enabled"] is False
    assert payload["push_mode"] == "keepalive_only"
    api.ws_manager.disconnect.assert_called()


@pytest.mark.asyncio
async def test_strategy_templates_and_config_missing_branches(tmp_path: Path):
    """Cover strategy API missing branches: template filtering, 404s, config read."""
    from app.api import strategy as api

    # get_templates: category filter
    tpl1 = SimpleNamespace(id="t1", name="T1", category="c1")
    tpl2 = SimpleNamespace(id="t2", name="T2", category="c2")
    service = SimpleNamespace(get_templates=AsyncMock(return_value=[tpl1, tpl2]))
    resp = await api.get_templates(category="c1", service=service)
    assert resp["total"] == 1

    # get_template_detail: 404
    with patch.object(api, "get_template_by_id", return_value=None):
        with pytest.raises(HTTPException) as ei:
            await api.get_template_detail("missing")
        assert ei.value.status_code == 404
    # get_template_detail: success return
    with patch.object(api, "get_template_by_id", return_value=tpl1):
        got = await api.get_template_detail("t1")
        assert got.id == "t1"

    # get_template_readme: 404 and success
    with patch.object(api, "get_strategy_readme", return_value=None):
        with pytest.raises(HTTPException) as ei:
            await api.get_template_readme("t1")
        assert ei.value.status_code == 404
    with patch.object(api, "get_strategy_readme", return_value="# readme"):
        ok = await api.get_template_readme("t1")
        assert ok["content"] == "# readme"

    # get_template_config: 404 when missing + success when present
    strategies_dir = tmp_path / "strategies"
    (strategies_dir / "t1").mkdir(parents=True)
    with patch("app.services.strategy_service.STRATEGIES_DIR", strategies_dir):
        with pytest.raises(HTTPException) as ei:
            await api.get_template_config("t1")
        assert ei.value.status_code == 404

        (strategies_dir / "t1" / "config.yaml").write_text(
            "strategy:\n  name: T1\nparams:\n  p: 1\n"
        )
        cfg = await api.get_template_config("t1")
        assert cfg["strategy"]["name"] == "T1"

        with pytest.raises(HTTPException) as ei:
            await api.get_template_config("../escape")
        assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_strategy_version_api_ws_notifications_and_returns(monkeypatch):
    """Cover strategy_version API missing ws notification lines and return statements."""
    from app.api import strategy_version as api
    from app.schemas.strategy_version import (
        VersionComparisonRequest,
        VersionCreate,
        VersionRollbackRequest,
        VersionUpdate,
    )

    monkeypatch.setattr(api.ws_manager, "send_to_task", AsyncMock())

    user = SimpleNamespace(sub="u1")

    version = SimpleNamespace(
        id="v1", strategy_id="u1", status="draft", is_active=True, is_default=False, created_by="u1"
    )
    from datetime import datetime

    comparison = SimpleNamespace(
        id="c1",
        strategy_id="s1",
        from_version_id="a",
        to_version_id="b",
        code_diff="",
        params_diff={},
        performance_diff={},
        created_at=datetime.now(),
    )
    new_version = SimpleNamespace(id="v2", version_name="v2.0")

    service = SimpleNamespace(
        create_version=AsyncMock(return_value=version),
        get_version=AsyncMock(return_value=version),
        update_version=AsyncMock(return_value=version),
        compare_versions=AsyncMock(return_value=comparison),
        rollback_version=AsyncMock(return_value=new_version),
        _to_response=lambda v: {"id": getattr(v, "id", None)},
    )

    created = await api.create_strategy_version(
        VersionCreate(
            strategy_id="s1",
            version_name="v1.0",
            code="x",
            params={},
            branch="main",
            tags=[],
            changelog="",
            is_default=False,
        ),
        current_user=user,
        service=service,
    )
    assert created["id"] == "v1"

    got = await api.get_strategy_version("v1", current_user=user, service=service)
    assert got["id"] == "v1"

    updated = await api.update_strategy_version(
        "v1",
        VersionUpdate(code="y", params={}, description=None, tags=None, status=None),
        current_user=user,
        service=service,
    )
    assert updated["id"] == "v1"

    compared = await api.compare_strategy_versions(
        VersionComparisonRequest(
            strategy_id="s1", from_version_id="a", to_version_id="b", comparison_type="code"
        ),
        current_user=user,
        service=service,
    )
    assert compared["comparison_id"] == "c1"

    rolled = await api.rollback_strategy_version(
        VersionRollbackRequest(strategy_id="s1", target_version_id="t", reason="r"),
        current_user=user,
        service=service,
    )
    assert rolled["id"] == "v2"
