from types import SimpleNamespace

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
