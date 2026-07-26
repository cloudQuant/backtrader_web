import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import seed_simulated_workspaces as seed_module  # noqa: E402
from seed_simulated_workspaces import (  # noqa: E402
    DEFAULT_STRESS_DURATION_SECONDS,
    _stress_slot_from_name,
    build_ctp_gateway_config,
    build_ib_gateway_config,
    build_mt5_gateway_config,
    build_stress_unit_specs,
    build_workspace_specs,
    roll_expired_ctp_contract_symbol,
    stress_duration_seconds,
)


def test_roll_expired_ctp_contract_symbol_moves_current_month_forward():
    now = datetime(2026, 6, 23, 12, 0, 0)

    assert roll_expired_ctp_contract_symbol("au2606", now=now) == "au2608"
    assert roll_expired_ctp_contract_symbol("cu2606", now=now) == "cu2608"
    assert roll_expired_ctp_contract_symbol("IF2609", now=now) == "IF2609"


def test_stress_specs_use_stable_names_and_slots():
    specs = build_stress_unit_specs(
        workspace_key="futures",
        symbols=[{"symbol": "au2606", "name": "黄金主力"}],
        gateway_config={},
        category="future",
        initial_cash=1000000,
        commission=0.0001,
        slippage=0.00005,
        position_size=1,
    )

    assert specs[0]["stress_slot"] == "futures-01"
    assert specs[0]["strategy_name"] == "CTP压测01-短周期均线-1m"
    assert "-au2606-" not in specs[0]["strategy_name"]
    assert specs[0]["unit_settings"]["qcheck"] == 0.5
    assert specs[0]["unit_settings"]["log_ticks"] is False
    assert specs[0]["unit_settings"]["log_positions"] is True
    assert specs[0]["unit_settings"]["log_indicators"] is False
    assert specs[0]["unit_settings"]["log_signals"] is True
    assert specs[0]["unit_settings"]["dispatch_ticks"] is False
    assert specs[0]["unit_settings"]["exactbars"] is True
    assert specs[0]["unit_settings"]["stdstats"] is False
    assert specs[0]["unit_settings"]["duration_seconds"] == DEFAULT_STRESS_DURATION_SECONDS
    assert specs[0]["unit_settings"]["session_timeout"] == DEFAULT_STRESS_DURATION_SECONDS + 60


def test_stress_duration_can_be_configured(monkeypatch):
    monkeypatch.setenv("SIM_STRESS_DURATION_SECONDS", "3600")

    assert stress_duration_seconds() == 3600


def test_all_seeded_workspaces_use_the_same_long_running_duration(monkeypatch):
    monkeypatch.setenv("SIM_STRESS_DURATION_SECONDS", "7200")

    specs = build_workspace_specs()

    for workspace_key in ("futures", "ib", "mt5"):
        assert specs[workspace_key]
        assert {item["unit_settings"]["duration_seconds"] for item in specs[workspace_key]} == {
            7200
        }
        assert {item["unit_settings"]["session_timeout"] for item in specs[workspace_key]} == {7260}


def test_stress_slot_from_legacy_name():
    assert _stress_slot_from_name("CTP压测短周期均线05-au2606-1m") == "futures-05"
    assert _stress_slot_from_name("MT5压测布林突破37-XAUUSD-1m") == "mt5-37"


def test_seed_gateway_configs_do_not_persist_passwords():
    ctp_config = build_ctp_gateway_config(
        {
            "broker_id": "9999",
            "user_id": "089763",
            "password": "ctp-secret",
            "td_front": "tcp://td",
            "md_front": "tcp://md",
        }
    )
    mt5_config = build_mt5_gateway_config(
        {
            "login": "5047785364",
            "password": "mt5-secret",
            "ws_uri": "wss://example.test/terminal",
        }
    )

    assert "password" not in ctp_config["params"]["ctp"]
    assert "password" not in mt5_config["params"]["gateway"]
    assert "password" not in mt5_config["params"]["mt5"]
    assert mt5_config["params"]["gateway"]["login"] == "5047785364"


def test_ib_seed_gateway_uses_runtime_settings_without_persisting_access_token(monkeypatch):
    settings = SimpleNamespace(
        IB_WEB_ACCOUNT_ID="DU123456",
        IB_ACCOUNT_ID="",
        IB_WEB_BASE_URL="https://localhost:5000/v1/api",
        IB_BASE_URL="https://localhost:5000",
        IB_WEB_VERIFY_SSL=False,
        IB_VERIFY_SSL=False,
        IB_WEB_TIMEOUT=30.0,
        IB_TIMEOUT=10.0,
        IB_WEB_COOKIE_SOURCE="file:configs/ibkr_cookies.json",
        IB_COOKIE_SOURCE="",
        IB_WEB_COOKIE_BROWSER="chrome",
        IB_COOKIE_BROWSER="chrome",
        IB_WEB_COOKIE_PATH="/sso",
        IB_COOKIE_PATH="/sso",
    )
    monkeypatch.setattr(seed_module, "get_settings", lambda: settings)

    config = build_ib_gateway_config({"access_token": "sensitive-token"})

    gateway = config["params"]["gateway"]
    assert gateway["account_id"] == "DU123456"
    assert gateway["base_url"] == "https://localhost:5000/v1/api"
    assert gateway["timeout"] == 30.0
    assert "access_token" not in gateway
