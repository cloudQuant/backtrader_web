from types import SimpleNamespace

import yaml

from app.services import workspace_unit_runtime
from app.services.trading_workspace_service import TradingWorkspaceService


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


def test_sync_trading_unit_runtime_copies_template_and_merges_unit_config(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path)
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
        unit_settings={"duration_seconds": 1800, "session_timeout": 1860},
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


def test_sync_trading_unit_runtime_normalizes_futures_data_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path)
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
                },
                "ctp": {
                    "broker_id": "9999",
                    "investor_id": "089763",
                    "user_id": "089763",
                    "password": "secret",
                },
            }
        },
    )

    runtime_dir = workspace_unit_runtime.sync_trading_unit_runtime(unit, {})
    config = yaml.safe_load((runtime_dir / "config.yaml").read_text("utf-8"))

    assert config["data"]["asset_type"] == "future"
    assert config["data"]["data_type"] == "futures"
    assert config["data"]["exchange"] == "CTP"


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
