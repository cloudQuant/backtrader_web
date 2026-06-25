import json
from types import SimpleNamespace

import pytest
import yaml

from app.services import trading_workspace_service as trading_workspace_service_module
from app.services import workspace_unit_runtime
from app.services.trading_workspace_service import TradingWorkspaceService


def _make_strategy_template(tmp_path, strategy_id: str, module_basename: str):
    """Create a self-contained strategy template dir.

    The runtime sync copies every ``*.py`` from the template dir resolved via
    ``get_strategy_dir``. The real templates live under the gitignored
    ``src/strategies/`` tree, so tests must not depend on them being present;
    we build a minimal template on disk and point ``get_strategy_dir`` at it.
    """
    template_dir = tmp_path / "templates" / strategy_id.replace("/", "__")
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "run.py").write_text("# runtime entrypoint\n", encoding="utf-8")
    (template_dir / f"{module_basename}.py").write_text(
        "import backtrader as bt\n\n\nclass S(bt.Strategy):\n    pass\n",
        encoding="utf-8",
    )
    return template_dir


def _make_basic_trading_unit(strategy_id: str = "simulate/gateway_dual_ma"):
    return SimpleNamespace(
        workspace_id="ws-refresh",
        id="unit-refresh",
        group_name="均线金叉",
        strategy_id=strategy_id,
        strategy_name="Refresh Runner",
        symbol="EURUSD",
        symbol_name="EURUSD",
        timeframe="1m",
        timeframe_n=1,
        category="forex",
        data_config={},
        unit_settings={},
        params={},
        optimization_config={},
        gateway_config={},
    )


def test_build_instance_params_keeps_explicit_gateway_for_paper_units():
    unit = SimpleNamespace(
        workspace_id="ws-1",
        id="unit-1",
        group_name="均线金叉",
        strategy_name="Paper MA",
        params={"fast_period": 5},
        symbol="AAPL",
        symbol_name="Apple",
        timeframe="1m",
        timeframe_n=1,
        category="stock",
        data_config={},
        unit_settings={},
        trading_mode="paper",
        gateway_config={
            "preset_id": "ib_web_stock_gateway",
            "params": {
                "gateway": {
                    "enabled": True,
                    "provider": "gateway",
                    "exchange_type": "IB_WEB",
                    "asset_type": "STK",
                    "account_id": "DU123456",
                },
                "ib_web": {
                    "account_id": "DU123456",
                    "base_url": "https://localhost:5000",
                },
            },
        },
    )

    params = TradingWorkspaceService._build_instance_params(unit)

    assert params["trading_mode"] == "paper"
    assert params["gateway"]["exchange_type"] == "IB_WEB"
    assert params["ib_web"]["account_id"] == "DU123456"


def test_default_snapshot_and_normalized_trade_rows_expose_trades():
    unit = SimpleNamespace(
        trading_instance_id="inst-1",
        trading_mode="live",
        gateway_config={},
        symbol="IF2609",
        symbol_name="沪深300",
        strategy_name="CTP Demo",
    )

    snapshot = TradingWorkspaceService.default_snapshot(unit=unit)
    rows = TradingWorkspaceService._normalize_trade_rows(
        [
            {
                "ref": 7,
                "datetime": "2026-06-22",
                "dtopen": "2026-06-22 09:31:00",
                "dtclose": "2026-06-22 09:42:00",
                "data_name": "IF2609",
                "direction": "sell",
                "size": -2,
                "price": 3910.1234,
                "value": 7820.246,
                "commission": 3.4567,
                "pnl": 20,
                "pnlcomm": 18.25,
                "barlen": "5",
            }
        ],
        unit=unit,
    )

    assert snapshot["trades"] == []
    assert rows == [
        {
            "id": "7",
            "datetime": "2026-06-22",
            "dtopen": "2026-06-22 09:31:00",
            "dtclose": "2026-06-22 09:42:00",
            "data_name": "IF2609",
            "direction": "short",
            "size": 2.0,
            "price": 3910.1234,
            "value": 7820.25,
            "commission": 3.4567,
            "pnl": 20.0,
            "pnlcomm": 18.25,
            "barlen": 5,
        }
    ]


def test_sync_trading_unit_runtime_copies_template_and_merges_unit_config(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path)
    template_dir = _make_strategy_template(
        tmp_path, "simulate/gateway_boll_breakout", "strategy_gateway_boll_breakout"
    )
    monkeypatch.setattr(workspace_unit_runtime, "get_strategy_dir", lambda _sid: template_dir)
    unit = SimpleNamespace(
        workspace_id="ws-1",
        id="unit-1",
        group_name="布林突破",
        strategy_id="simulate/gateway_boll_breakout",
        strategy_name="Boll AAPL",
        symbol="AAPL",
        symbol_name="Apple",
        timeframe="1m",
        timeframe_n=1,
        category="stock",
        data_config={"range_type": "sample", "sample_count": 300},
        unit_settings={
            "duration_seconds": 1800,
            "session_timeout": 1860,
            "qcheck_seconds": 0.25,
            "log_ticks": True,
            "log_positions": False,
            "log_indicators": True,
            "log_signals": False,
            "dispatch_ticks": True,
            "exactbars": -1,
            "stdstats": True,
        },
        params={"boll_period": 16, "boll_dev": 2.2},
        optimization_config={},
        gateway_config={
            "params": {
                "gateway": {
                    "enabled": True,
                    "provider": "gateway",
                    "exchange_type": "IB_WEB",
                    "asset_type": "STK",
                    "account_id": "DU123456",
                },
                "ib_web": {
                    "account_id": "DU123456",
                    "base_url": "https://localhost:5000",
                },
            }
        },
    )

    runtime_dir = workspace_unit_runtime.sync_trading_unit_runtime(unit, {})

    assert (runtime_dir / "run.py").is_file()
    assert (runtime_dir / "strategy_gateway_boll_breakout.py").is_file()
    config_text = (runtime_dir / "config.yaml").read_text("utf-8")
    assert "Boll AAPL" in config_text
    assert "DU123456" in config_text
    assert "boll_period: 16" in config_text
    config = yaml.safe_load(config_text)
    assert config["live"]["qcheck"] == 0.25
    assert config["live"]["log_ticks"] is True
    assert config["live"]["log_positions"] is False
    assert config["live"]["log_indicators"] is True
    assert config["live"]["log_signals"] is False
    assert config["live"]["dispatch_ticks"] is True
    assert config["live"]["exactbars"] == -1
    assert config["live"]["stdstats"] is True


def test_sync_trading_unit_runtime_refreshes_existing_template_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path)
    template_dir = _make_strategy_template(
        tmp_path, "simulate/gateway_dual_ma", "strategy_gateway_dual_ma"
    )
    monkeypatch.setattr(workspace_unit_runtime, "get_strategy_dir", lambda _sid: template_dir)
    unit = _make_basic_trading_unit()
    runtime_dir = workspace_unit_runtime.unit_dir(unit.workspace_id, unit.id)
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "run.py").write_text("# stale runtime entrypoint\n", encoding="utf-8")
    (runtime_dir / "strategy_gateway_dual_ma.py").write_text("# stale strategy\n", encoding="utf-8")
    (template_dir / "run.py").write_text("# refreshed runtime entrypoint\n", encoding="utf-8")

    workspace_unit_runtime.sync_trading_unit_runtime(unit, {})

    assert (runtime_dir / "run.py").read_text("utf-8") == "# refreshed runtime entrypoint\n"
    assert "class S" in (runtime_dir / "strategy_gateway_dual_ma.py").read_text("utf-8")

    (template_dir / "run.py").write_text("# refreshed runtime entrypoint v2\n", encoding="utf-8")

    workspace_unit_runtime.sync_trading_unit_runtime(unit, {})

    assert (runtime_dir / "run.py").read_text("utf-8") == "# refreshed runtime entrypoint v2\n"


def test_sync_trading_unit_runtime_normalizes_futures_data_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path)
    template_dir = _make_strategy_template(
        tmp_path, "simulate/gateway_dual_ma", "strategy_gateway_dual_ma"
    )
    monkeypatch.setattr(workspace_unit_runtime, "get_strategy_dir", lambda _sid: template_dir)
    unit = SimpleNamespace(
        workspace_id="ws-ctp",
        id="unit-ctp",
        group_name="均线金叉",
        strategy_id="simulate/gateway_dual_ma",
        strategy_name="IF Future",
        symbol="IF2609",
        symbol_name="沪深300主力",
        timeframe="1m",
        timeframe_n=1,
        category="future",
        data_config={"range_type": "sample", "sample_count": 300},
        unit_settings={},
        params={"fast_period": 3, "slow_period": 8},
        optimization_config={},
        gateway_config={
            "params": {
                "gateway": {
                    "enabled": True,
                    "provider": "ctp_gateway",
                    "exchange_type": "CTP",
                    "asset_type": "FUTURE",
                    "account_id": "089763",
                    "password": "gateway-secret",
                    "access_token": "gateway-token",
                },
                "ctp": {
                    "broker_id": "9999",
                    "investor_id": "089763",
                    "user_id": "089763",
                    "password": "secret",
                    "auth_code": "auth-secret",
                },
            }
        },
    )

    runtime_dir = workspace_unit_runtime.sync_trading_unit_runtime(unit, {})
    config = yaml.safe_load((runtime_dir / "config.yaml").read_text("utf-8"))

    assert config["data"]["asset_type"] == "future"
    assert config["data"]["data_type"] == "futures"
    assert config["data"]["exchange"] == "CTP"
    assert config["live"]["qcheck"] == 0.5
    assert config["live"]["log_ticks"] is False
    assert config["live"]["log_positions"] is True
    assert config["live"]["log_indicators"] is False
    assert config["live"]["log_signals"] is True
    assert config["live"]["dispatch_ticks"] is False
    assert config["live"]["exactbars"] is True
    assert config["live"]["stdstats"] is False
    config_text = yaml.safe_dump(config, allow_unicode=True)
    assert "gateway-secret" not in config_text
    assert "gateway-token" not in config_text
    assert "auth-secret" not in config_text
    assert "secret" not in config_text
    assert "password" not in config["gateway"]
    assert "access_token" not in config["gateway"]
    assert "password" not in config["ctp"]
    assert "auth_code" not in config["ctp"]


def test_build_status_responses_tolerates_malformed_snapshot_values():
    unit = SimpleNamespace(
        id="unit-1",
        run_status="running",
        last_task_id=None,
        metrics_snapshot=["unexpected"],
        run_count=2,
        last_run_time=12.5,
        bar_count=30,
        trading_instance_id="inst-1",
        trading_snapshot="unexpected",
        trading_mode="paper",
        lock_trading=False,
        lock_running=False,
    )

    responses = TradingWorkspaceService().build_status_responses([unit])

    assert len(responses) == 1
    assert responses[0].id == "unit-1"
    assert responses[0].metrics_snapshot == {}
    assert responses[0].trading_snapshot == {}


def test_build_snapshot_falls_back_to_runtime_logs_when_log_dir_missing(tmp_path):
    runtime_dir = tmp_path / "runtime"
    log_dir = runtime_dir / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "position.log").write_text(
        json.dumps(
            {
                "log_time": "2026-06-25T07:17:41.329+08:00",
                "datetime": "2026-06-25 09:17:00",
                "data_name": "IF2609",
                "size": -1,
                "price": 4814.3593,
                "value": 4810.6,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    unit = SimpleNamespace(
        trading_instance_id="inst-1",
        trading_mode="paper",
        gateway_config={},
        symbol="IF2609",
        symbol_name="沪深300",
        strategy_name="CTP压测01",
    )

    snapshot, _metrics, _bar_count, _elapsed = TradingWorkspaceService._build_snapshot(
        unit,
        {
            "id": "inst-1",
            "status": "running",
            "runtime_dir": str(runtime_dir),
            "log_dir": None,
        },
    )

    assert snapshot["instance_status"] == "running"
    assert snapshot["short_position"] == 1.0
    assert snapshot["short_market_value"] == 4810.6
    assert snapshot["positions"][0]["updated_at"] == "2026-06-25T07:17:41.329+08:00"
    assert snapshot["positions"][0]["data_time"] == "2026-06-25 09:17:00"
    assert snapshot["updated_at"] == "2026-06-25T07:17:41.329+08:00"


def test_build_snapshot_light_hydrate_skips_full_log_and_preserves_summary(
    tmp_path, monkeypatch
):
    runtime_dir = tmp_path / "runtime"
    log_dir = runtime_dir / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "position.log").write_text(
        json.dumps(
            {
                "datetime": "2026-06-25 09:18:00",
                "data_name": "XAUUSD",
                "size": 0.01,
                "price": 4001.66,
                "value": 40.02,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    unit = SimpleNamespace(
        trading_instance_id="inst-1",
        trading_mode="paper",
        gateway_config={},
        symbol="XAUUSD",
        symbol_name="黄金/美元",
        strategy_name="MT5压测01",
        trading_snapshot={
            "today_pnl": 12.34,
            "cumulative_pnl": 56.78,
            "trades": [{"id": "old-trade"}],
        },
    )

    def fail_parse_log_dir(_log_dir):
        raise AssertionError("parse_log_dir should not run for light hydrate")

    monkeypatch.setattr(
        trading_workspace_service_module,
        "parse_log_dir",
        fail_parse_log_dir,
    )

    snapshot, metrics, bar_count, elapsed = TradingWorkspaceService._build_snapshot(
        unit,
        {
            "id": "inst-1",
            "status": "running",
            "runtime_dir": str(runtime_dir),
            "log_dir": None,
        },
        full_log=False,
    )

    assert snapshot["positions"][0]["updated_at"] == "2026-06-25 09:18:00"
    assert snapshot["long_position"] == 0.01
    assert snapshot["today_pnl"] == 12.34
    assert snapshot["cumulative_pnl"] == 56.78
    assert snapshot["trades"] == [{"id": "old-trade"}]
    assert metrics == {}
    assert bar_count is None
    assert elapsed is None


@pytest.mark.asyncio
async def test_build_positions_response_can_skip_hydration(monkeypatch):
    service = TradingWorkspaceService()
    unit = SimpleNamespace(
        id="unit-1",
        strategy_name="Unit One",
        strategy_id="simulate/gateway_dual_ma",
        symbol="EURUSD",
        symbol_name="Euro",
        trading_mode="paper",
        trading_snapshot={
            "positions": [
                {
                    "size": 2,
                    "price": 1.2,
                    "updated_at": "2026-06-25 09:00:00",
                    "data_time": "2026-06-25 08:59:00",
                }
            ],
            "long_position": 2.0,
            "short_position": 0.0,
            "latest_price": 1.25,
            "position_pnl": 0.1,
            "long_market_value": 2.5,
            "short_market_value": 0.0,
            "updated_at": "2026-06-25 09:00:00",
        },
    )

    async def fail_hydrate(_units, _user_id):
        raise AssertionError("hydrate_units should not run when hydrate=False")

    monkeypatch.setattr(service, "hydrate_units", fail_hydrate)

    result = await service.build_positions_response([unit], "user-1", hydrate=False)

    assert result.positions[0].unit_id == "unit-1"
    assert result.positions[0].updated_at == "2026-06-25 09:00:00"
    assert result.positions[0].data_time == "2026-06-25 08:59:00"
    assert result.total_long_value == 2.5


@pytest.mark.asyncio
async def test_start_units_keeps_already_running_instance_running(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    log_dir = runtime_dir / "logs"
    log_dir.mkdir(parents=True)
    stale_tick_log = log_dir / "tick.log"
    stale_tick_log.write_text("keep-running-log\n", encoding="utf-8")
    unit = SimpleNamespace(
        id="unit-1",
        workspace_id="ws-1",
        group_name="压测",
        strategy_id="simulate/gateway_dual_ma",
        strategy_name="CTP压测01",
        symbol="IF2609",
        symbol_name="沪深300",
        timeframe="1m",
        timeframe_n=1,
        category="future",
        data_config={},
        unit_settings={},
        params={},
        optimization_config={},
        gateway_config={},
        trading_mode="paper",
        lock_running=False,
        lock_trading=False,
        trading_instance_id="inst-1",
        run_status="failed",
        run_count=7,
        trading_snapshot={},
        metrics_snapshot={},
        bar_count=None,
        last_run_time=None,
    )

    monkeypatch.setattr(
        workspace_unit_runtime,
        "sync_trading_unit_runtime",
        lambda *_args, **_kwargs: runtime_dir,
    )

    class FakeManager:
        def get_instance(self, instance_id, user_id=None):
            assert instance_id == "inst-1"
            assert user_id == "user-1"
            return {
                "id": "inst-1",
                "status": "running",
                "pid": 12345,
                "runtime_dir": str(runtime_dir),
                "log_dir": None,
                "error": None,
            }

        async def start_instance(self, _instance_id):
            raise AssertionError("start_instance should not be called for running units")

        def add_instance(self, *_args, **_kwargs):
            raise AssertionError("add_instance should not be called for existing units")

        def remove_instance(self, *_args, **_kwargs):
            raise AssertionError("remove_instance should not be called for matching runtime dirs")

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    results = await TradingWorkspaceService().start_units([unit], user_id="user-1")

    assert results == [
        {
            "unit_id": "unit-1",
            "task_id": "inst-1",
            "status": "running",
            "already_running": True,
        }
    ]
    assert unit.run_status == "running"
    assert unit.run_count == 7
    assert unit.trading_snapshot["instance_status"] == "running"
    assert stale_tick_log.read_text("utf-8") == "keep-running-log\n"


@pytest.mark.asyncio
async def test_start_units_cleans_stale_runtime_logs_before_new_start(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    log_dir = runtime_dir / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "tick.log").write_text("old ticks\n", encoding="utf-8")
    (log_dir / "trade.log").write_text("old trades\n", encoding="utf-8")
    unit = SimpleNamespace(
        id="unit-1",
        workspace_id="ws-1",
        group_name="压测",
        strategy_id="simulate/gateway_dual_ma",
        strategy_name="CTP压测02",
        symbol="IF2609",
        symbol_name="沪深300",
        timeframe="1m",
        timeframe_n=1,
        category="future",
        data_config={},
        unit_settings={},
        params={},
        optimization_config={},
        gateway_config={},
        trading_mode="paper",
        lock_running=False,
        lock_trading=False,
        trading_instance_id="inst-1",
        run_status="idle",
        run_count=2,
        trading_snapshot={},
        metrics_snapshot={},
        bar_count=None,
        last_run_time=None,
    )

    monkeypatch.setattr(
        workspace_unit_runtime,
        "sync_trading_unit_runtime",
        lambda *_args, **_kwargs: runtime_dir,
    )

    class FakeManager:
        def get_instance(self, instance_id, user_id=None):
            assert instance_id == "inst-1"
            assert user_id == "user-1"
            return {
                "id": "inst-1",
                "status": "stopped",
                "pid": None,
                "runtime_dir": str(runtime_dir),
                "log_dir": str(log_dir),
                "error": None,
            }

        async def start_instance(self, instance_id):
            assert instance_id == "inst-1"
            assert log_dir.is_dir()
            assert list(log_dir.iterdir()) == []
            return {
                "id": "inst-1",
                "status": "running",
                "pid": 12346,
                "runtime_dir": str(runtime_dir),
                "log_dir": str(log_dir),
                "error": None,
                "started_at": "2026-06-24 12:00:00",
            }

        def add_instance(self, *_args, **_kwargs):
            raise AssertionError("add_instance should not be called for existing units")

        def remove_instance(self, *_args, **_kwargs):
            raise AssertionError("remove_instance should not be called")

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    results = await TradingWorkspaceService().start_units([unit], user_id="user-1")

    assert results == [
        {
            "unit_id": "unit-1",
            "task_id": "inst-1",
            "status": "running",
            "already_running": False,
        }
    ]
    assert unit.run_status == "running"
    assert unit.run_count == 3
    assert unit.trading_snapshot["instance_status"] == "running"
    assert list(log_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_start_units_reattaches_missing_instance_record_to_running_pid(
    tmp_path, monkeypatch
):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    unit = SimpleNamespace(
        id="unit-1",
        workspace_id="ws-1",
        group_name="压测",
        strategy_id="simulate/gateway_dual_ma",
        strategy_name="CTP压测08",
        symbol="rb2610",
        symbol_name="螺纹钢",
        timeframe="1m",
        timeframe_n=1,
        category="future",
        data_config={},
        unit_settings={},
        params={},
        optimization_config={},
        gateway_config={},
        trading_mode="paper",
        lock_running=False,
        lock_trading=False,
        trading_instance_id="stale-inst",
        run_status="idle",
        run_count=3,
        trading_snapshot={},
        metrics_snapshot={},
        bar_count=None,
        last_run_time=None,
    )

    monkeypatch.setattr(
        workspace_unit_runtime,
        "sync_trading_unit_runtime",
        lambda *_args, **_kwargs: runtime_dir,
    )

    class FakeManager:
        def get_instance(self, instance_id, user_id=None):
            assert user_id == "user-1"
            if instance_id == "stale-inst":
                return None
            assert instance_id == "new-inst"
            return {
                "id": "new-inst",
                "status": "running",
                "pid": 23456,
                "runtime_dir": str(runtime_dir),
                "log_dir": None,
                "error": None,
            }

        def add_instance(self, strategy_id, params, user_id=None, runtime_dir=None):
            assert strategy_id == "simulate/gateway_dual_ma"
            assert user_id == "user-1"
            assert runtime_dir == str(tmp_path / "runtime")
            return {"id": "new-inst"}

        async def start_instance(self, _instance_id):
            raise AssertionError("start_instance should not be called after reattaching PID")

        def remove_instance(self, *_args, **_kwargs):
            raise AssertionError("remove_instance should not be called")

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    results = await TradingWorkspaceService().start_units([unit], user_id="user-1")

    assert results == [
        {
            "unit_id": "unit-1",
            "task_id": "new-inst",
            "status": "running",
            "already_running": True,
        }
    ]
    assert unit.trading_instance_id == "new-inst"
    assert unit.run_status == "running"
    assert unit.run_count == 3
    assert unit.trading_snapshot["instance_status"] == "running"


def test_instance_log_result_falls_back_to_runtime_logs_when_log_dir_missing(
    tmp_path, monkeypatch
):
    runtime_dir = tmp_path / "runtime"
    log_dir = runtime_dir / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "value.log").write_text(
        "dt\tvalue\tcash\n2026-06-25\t100000\t100000\n",
        encoding="utf-8",
    )
    unit = SimpleNamespace(trading_instance_id="inst-1")

    class FakeManager:
        def get_instance(self, instance_id, user_id=None):
            assert instance_id == "inst-1"
            assert user_id == "u1"
            return {
                "id": "inst-1",
                "status": "running",
                "runtime_dir": str(runtime_dir),
                "log_dir": None,
            }

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    result = TradingWorkspaceService._instance_log_result(unit, "u1")

    assert result is not None
    assert result["log_dir"] == str(log_dir)
    assert result["equity_curve"] == [100000.0]


@pytest.mark.asyncio
async def test_daily_summary_counts_trades_once_per_day(monkeypatch):
    unit = SimpleNamespace(trading_instance_id="inst-1")

    def fake_log_result(_unit, _user_id):
        return {
            "equity_dates": ["2026-06-22 09:31:00", "2026-06-22 09:32:00"],
            "equity_curve": [100000.0, 100120.0],
            "drawdown_curve": [0.0, 0.1],
            "initial_cash": 100000.0,
            "trades": [
                {"dtclose": "2026-06-22 09:31:00"},
                {"dtclose": "2026-06-22 09:32:00"},
            ],
        }

    monkeypatch.setattr(
        TradingWorkspaceService,
        "_instance_log_result",
        staticmethod(fake_log_result),
    )

    result = await TradingWorkspaceService().build_daily_summary_response([unit], "u1")

    assert len(result.summaries) == 1
    assert result.summaries[0].trading_date == "2026-06-22"
    assert result.summaries[0].daily_pnl == 120.0
    assert result.summaries[0].cumulative_pnl == 120.0
    assert result.summaries[0].trade_count == 2
