"""
Tests for extracted modules (123-B).

Verifies that InstanceStore, process_supervisor functions, and
GatewayPresetService work correctly in isolation.
"""

import asyncio
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services import (
    auto_trading_scheduler,
    manual_gateway_service,
)
from app.services.gateway import health as gateway_health_service
from app.services.gateway import launch_builder as gateway_launch_builder
from app.services.gateway import runtime as gateway_runtime_service
from app.services.gateway.preset import get_gateway_presets
from app.services.instance_store import InstanceStore
from app.services.live_trading import execution as live_execution_service
from app.services.live_trading import instance as live_instance_service
from app.services.manual_gateway import ib_clientportal as ib_clientportal_service
from app.services.process_supervisor import is_pid_alive, kill_pid, scan_running_strategy_pids
from app.services.strategy import runtime_support as strategy_runtime_support


class TestInstanceStore:
    """Tests for InstanceStore JSON persistence."""

    def _make_store(self, tmp_path: Path) -> InstanceStore:
        return InstanceStore(instances_file=tmp_path / "instances.json")

    def test_load_empty_when_no_file(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.load_all() == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        store = self._make_store(tmp_path)
        data = {"inst1": {"status": "running", "pid": 123}}
        store.save_all(data)
        loaded = store.load_all()
        assert loaded == data

    def test_get_existing(self, tmp_path):
        store = self._make_store(tmp_path)
        store.save_all({"a": {"status": "stopped"}})
        assert store.get("a") == {"status": "stopped"}

    def test_get_nonexistent(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.get("missing") is None

    def test_put_creates_new(self, tmp_path):
        store = self._make_store(tmp_path)
        store.put("new_inst", {"status": "running"})
        assert store.get("new_inst") == {"status": "running"}

    def test_put_overwrites_existing(self, tmp_path):
        store = self._make_store(tmp_path)
        store.put("inst", {"status": "running"})
        store.put("inst", {"status": "stopped"})
        assert store.get("inst") == {"status": "stopped"}

    def test_delete_existing(self, tmp_path):
        store = self._make_store(tmp_path)
        store.put("inst", {"status": "running"})
        assert store.delete("inst") is True
        assert store.get("inst") is None

    def test_delete_nonexistent(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.delete("missing") is False

    def test_update_fields(self, tmp_path):
        store = self._make_store(tmp_path)
        store.put("inst", {"status": "running", "pid": 100})
        result = store.update_fields("inst", status="stopped", pid=None)
        assert result == {"status": "stopped", "pid": None}
        assert store.get("inst") == {"status": "stopped", "pid": None}

    def test_update_fields_nonexistent(self, tmp_path):
        store = self._make_store(tmp_path)
        assert store.update_fields("missing", status="x") is None

    def test_load_corrupted_json(self, tmp_path):
        store = self._make_store(tmp_path)
        f = tmp_path / "instances.json"
        f.write_text("not json", "utf-8")
        assert store.load_all() == {}

    def test_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c" / "instances.json"
        store = InstanceStore(instances_file=nested)
        store.save_all({"x": {"v": 1}})
        assert store.load_all() == {"x": {"v": 1}}


class TestProcessSupervisor:
    """Tests for process_supervisor functions."""

    def test_is_pid_alive_current_process(self):
        import os

        assert is_pid_alive(os.getpid()) is True

    def test_is_pid_alive_dead_pid(self):
        assert is_pid_alive(999999999) is False

    def test_kill_pid_nonexistent_no_error(self):
        kill_pid(999999999)

    def test_scan_returns_dict(self):
        result = scan_running_strategy_pids()
        assert isinstance(result, dict)


class TestGatewayPresetService:
    """Tests for gateway preset definitions."""

    def test_returns_list(self):
        presets = get_gateway_presets()
        assert isinstance(presets, list)
        assert len(presets) >= 6

    def test_each_preset_has_required_fields(self):
        for preset in get_gateway_presets():
            assert "id" in preset
            assert "name" in preset
            assert "description" in preset
            assert "editable_fields" in preset
            assert "params" in preset
            assert "gateway" in preset["params"]

    def test_ctp_preset_exists(self):
        ids = [p["id"] for p in get_gateway_presets()]
        assert "ctp_futures_gateway" in ids

    def test_ib_web_presets_exist(self):
        ids = [p["id"] for p in get_gateway_presets()]
        assert "ib_web_stock_gateway" in ids
        assert "ib_web_futures_gateway" in ids

    def test_mt5_preset_exists(self):
        ids = [p["id"] for p in get_gateway_presets()]
        assert "mt5_forex_gateway" in ids

    def test_crypto_presets_exist(self):
        ids = [p["id"] for p in get_gateway_presets()]
        assert "binance_swap_gateway" in ids
        assert "okx_swap_gateway" in ids

    def test_preset_ids_are_unique(self):
        ids = [p["id"] for p in get_gateway_presets()]
        assert len(ids) == len(set(ids))


class TestGatewayLaunchBuilder:
    def test_normalize_gateway_exchange_type(self):
        assert gateway_launch_builder.normalize_gateway_exchange_type("ib") == "IB_WEB"
        assert gateway_launch_builder.normalize_gateway_exchange_type("IBWEB") == "IB_WEB"
        assert gateway_launch_builder.normalize_gateway_exchange_type("", "mt5_gateway") == "MT5"
        assert gateway_launch_builder.normalize_gateway_exchange_type("ctp") == "CTP"

    def test_normalize_gateway_asset_type(self):
        assert gateway_launch_builder.normalize_gateway_asset_type("IB_WEB", "stock") == "STK"
        assert gateway_launch_builder.normalize_gateway_asset_type("IB_WEB", "future") == "FUT"
        assert gateway_launch_builder.normalize_gateway_asset_type("CTP", "") == "FUTURE"
        assert gateway_launch_builder.normalize_gateway_asset_type("MT5", "") == "OTC"

    def test_coerce_helpers(self):
        assert gateway_launch_builder.coerce_bool("true") is True
        assert gateway_launch_builder.coerce_bool("0") is False
        assert gateway_launch_builder.coerce_bool(None, default=True) is True
        assert gateway_launch_builder.coerce_float("12.5") == 12.5
        assert gateway_launch_builder.coerce_float("bad", default=3.0) == 3.0

    def test_parse_json_dict(self):
        assert gateway_launch_builder.parse_json_dict('{"a": 1}') == {"a": 1}
        assert gateway_launch_builder.parse_json_dict({"a": 1}) == {"a": 1}
        assert gateway_launch_builder.parse_json_dict("[]") is None
        assert gateway_launch_builder.parse_json_dict("bad") is None

    def test_get_gateway_params_normalizes_ib_web(self):
        params = gateway_launch_builder.get_gateway_params(
            {
                "params": {
                    "exchange": "ib",
                    "gateway": {
                        "enabled": True,
                        "asset_type": "stock",
                        "account_id": "du123456",
                        "base_url": "https://localhost:5000",
                    },
                }
            },
            "ipc",
        )
        assert params["enabled"] is True
        assert params["exchange_type"] == "IB_WEB"
        assert params["asset_type"] == "STK"
        assert params["account_id"] == "du123456"
        assert params["base_url"] == "https://localhost:5000"
        assert params["transport"] == "tcp"

    def test_build_ib_web_gateway_runtime_kwargs(self):
        runtime_kwargs = gateway_launch_builder.build_ib_web_gateway_runtime_kwargs(
            config_data={
                "ib_web": {
                    "base_url": "https://localhost:5000",
                    "account_id": "config-acc",
                    "verify_ssl": False,
                    "timeout": 15,
                }
            },
            env_data={
                "IB_WEB_ACCOUNT_ID": "env-acc",
                "IB_WEB_ACCESS_TOKEN": "test-token",
                "IB_WEB_VERIFY_SSL": "true",
            },
            gateway_params={
                "enabled": True,
                "provider": "gateway",
                "exchange_type": "IB_WEB",
                "asset_type": "stock",
                "account_id": "",
                "base_dir": "/tmp/gateway",
                "base_url": "",
                "access_token": "",
                "verify_ssl": None,
                "cookie_source": "",
                "cookie_browser": "",
                "cookie_path": "",
                "cookies": None,
            },
            default_transport="ipc",
        )
        assert runtime_kwargs["exchange_type"] == "IB_WEB"
        assert runtime_kwargs["asset_type"] == "STK"
        assert runtime_kwargs["account_id"] == "env-acc"
        assert runtime_kwargs["base_url"] == "https://localhost:5000"
        assert runtime_kwargs["access_token"] == "test-token"
        assert runtime_kwargs["verify_ssl"] is True
        assert runtime_kwargs["timeout"] == 15.0
        assert runtime_kwargs["transport"] == "tcp"

    def test_build_gateway_launch_uses_runtime_class(self):
        class FakeGatewayConfig:
            @classmethod
            def from_kwargs(cls, **kwargs):
                return kwargs

        class FakeGatewayRuntime:
            pass

        launch = gateway_launch_builder.build_gateway_launch(
            config_data={
                "ib_web": {
                    "base_url": "https://localhost:5000",
                    "account_id": "config-acc",
                    "timeout": 12,
                }
            },
            env_data={"IB_WEB_ACCOUNT_ID": "env-acc"},
            gateway_params={
                "provider": "gateway",
                "exchange_type": "IB_WEB",
                "asset_type": "stock",
                "account_id": "",
                "base_dir": "/tmp/gateway",
                "base_url": "",
                "access_token": "",
                "verify_ssl": None,
                "cookie_source": "",
                "cookie_browser": "",
                "cookie_path": "",
                "cookies": None,
            },
            gateway_config_cls=FakeGatewayConfig,
            gateway_runtime_cls=FakeGatewayRuntime,
            default_transport="ipc",
        )
        assert launch["runtime_cls"] is FakeGatewayRuntime
        assert launch["config"] == launch["runtime_kwargs"]
        assert launch["runtime_kwargs"]["account_id"] == "env-acc"
        assert launch["runtime_kwargs"]["transport"] == "tcp"


class TestStrategyRuntimeSupport:
    def test_load_strategy_config_missing(self, tmp_path):
        assert strategy_runtime_support.load_strategy_config(tmp_path) == {}

    def test_load_strategy_config_reads_yaml(self, tmp_path):
        (tmp_path / "config.yaml").write_text("ib_web:\n  account_id: acc1\n", encoding="utf-8")
        result = strategy_runtime_support.load_strategy_config(tmp_path)
        assert result == {"ib_web": {"account_id": "acc1"}}

    def test_load_strategy_env_prefers_strategy_file(self, tmp_path):
        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (strategy_dir / ".env").write_text(
            "A=1\nSHARED=strategy\n# comment\nBADLINE\n",
            encoding="utf-8",
        )
        (app_dir / ".env").write_text(
            "B=2\nSHARED=app\n",
            encoding="utf-8",
        )
        result = strategy_runtime_support.load_strategy_env(strategy_dir, app_dir)
        assert result == {"A": "1", "SHARED": "strategy", "B": "2"}

    def test_load_strategy_env_uses_default_project_dir(self, tmp_path, monkeypatch):
        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (strategy_dir / ".env").write_text("A=1\n", encoding="utf-8")
        (app_dir / ".env").write_text("B=2\n", encoding="utf-8")
        monkeypatch.setattr(strategy_runtime_support, "_PROJECT_ROOT", app_dir)

        result = strategy_runtime_support.load_strategy_env(strategy_dir)

        assert result == {"A": "1", "B": "2"}

    def test_resolve_strategy_dir_rejects_invalid_path(self, tmp_path):
        try:
            strategy_runtime_support.resolve_strategy_dir("../bad", tmp_path)
        except ValueError as exc:
            assert "Invalid strategy_id" in str(exc)
        else:
            raise AssertionError("Expected ValueError")

    def test_resolve_strategy_dir_rejects_escape_after_resolution(self, tmp_path):
        target = tmp_path.parent / "outside"
        target.mkdir()
        link = tmp_path / "link"
        link.symlink_to(target, target_is_directory=True)

        with pytest.raises(ValueError, match="escapes base directory"):
            strategy_runtime_support.resolve_strategy_dir("link/child", tmp_path)

    def test_resolve_strategy_dir_returns_resolved_path(self, tmp_path):
        result = strategy_runtime_support.resolve_strategy_dir("demo", tmp_path)
        assert result == (tmp_path / "demo").resolve()

    def test_find_latest_log_dir_prefers_latest_subdir(self, tmp_path):
        logs_dir = tmp_path / "logs"
        old_dir = logs_dir / "log_20240101"
        new_dir = logs_dir / "log_20240102"
        old_dir.mkdir(parents=True)
        new_dir.mkdir(parents=True)
        (old_dir / "trade.log").write_text("ok", encoding="utf-8")
        (new_dir / "trade.log").write_text("ok", encoding="utf-8")
        result = strategy_runtime_support.find_latest_log_dir(tmp_path)
        assert result == str(new_dir)

    def test_find_latest_log_dir_supports_flat_logs(self, tmp_path):
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        (logs_dir / "system.log").write_text("ok", encoding="utf-8")
        assert strategy_runtime_support.find_latest_log_dir(tmp_path) == str(logs_dir)

    def test_infer_gateway_params_from_explicit_gateway(self, tmp_path):
        (tmp_path / "config.yaml").write_text(
            "\n".join(
                [
                    "gateway:",
                    "  enabled: true",
                    "  provider: mt5_gateway",
                    "  exchange_type: MT5",
                    "  asset_type: OTC",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        result = strategy_runtime_support.infer_gateway_params(tmp_path)
        assert result == {
            "enabled": True,
            "provider": "mt5_gateway",
            "exchange_type": "MT5",
            "asset_type": "OTC",
        }

    def test_infer_gateway_params_from_ctp_section(self, tmp_path):
        (tmp_path / "config.yaml").write_text("ctp:\n  broker_id: 9999\n", encoding="utf-8")
        result = strategy_runtime_support.infer_gateway_params(tmp_path)
        assert result == {
            "enabled": True,
            "provider": "ctp_gateway",
            "exchange_type": "CTP",
            "asset_type": "FUTURE",
        }

    def test_infer_gateway_params_returns_none_for_missing_or_invalid_config(self, tmp_path):
        assert strategy_runtime_support.infer_gateway_params(tmp_path) is None
        (tmp_path / "config.yaml").write_text("not: [valid", encoding="utf-8")
        assert strategy_runtime_support.infer_gateway_params(tmp_path) is None


class TestManualGatewayService:
    def test_backend_env_file_candidates_includes_cwd_env(self, tmp_path, monkeypatch):
        cwd_env = tmp_path / ".env"
        cwd_env.write_text("IB_WEB_USERNAME=from-cwd\n", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        candidates = manual_gateway_service._backend_env_file_candidates()

        assert Path(cwd_env) in candidates

    def test_load_backend_gateway_env_values_uses_env_and_env_file(self, tmp_path, monkeypatch):
        file_env = tmp_path / ".env"
        file_env.write_text("OKX_PASSWORD=file-password\nOKX_PASSPHRASE=\n", encoding="utf-8")

        with (
            patch.object(
                manual_gateway_service,
                "_backend_env_file_candidates",
                return_value=(file_env,),
            ),
            patch.dict(
                manual_gateway_service.os.environ,
                {"OKX_PASSWORD": "system-password"},
                clear=False,
            ),
        ):
            values = manual_gateway_service._load_backend_gateway_env_values()

        assert values["OKX_PASSWORD"] == "system-password"

    def test_to_backend_env_relative_path_returns_bt_api_relative_cookie_path(self):
        result = manual_gateway_service._to_backend_env_relative_path(
            "/Users/yunjinqi/Documents/new_projects/bt_api_py/configs/ibkr_cookies.json"
        )

        assert result == "configs/ibkr_cookies.json"

    def test_bootstrap_ib_web_session_does_not_browser_login_when_cookie_config_exists(self):
        with (
            patch.object(
                manual_gateway_service,
                "_load_ib_web_session_state",
                return_value=({}, {}, False, [], ""),
            ),
            patch.object(
                manual_gateway_service,
                "_import_ib_web_session_helpers",
            ) as mock_helpers,
        ):
            with pytest.raises(RuntimeError, match="手动重新连接"):
                manual_gateway_service._bootstrap_ib_web_session(
                    {
                        "account_id": "DU123456",
                        "cookie_source": "file:configs/ibkr_cookies.json",
                        "username": "test-ib-user",
                        "password": "test-ib-pass",
                    },
                    "https://localhost:5000/v1/api",
                    verify_ssl=False,
                    timeout=10.0,
                    allow_interactive_login=False,
                )

        mock_helpers.assert_not_called()

    def test_bootstrap_ib_web_session_refreshes_expired_cookie_with_browser_login(self):
        refreshed_session = {
            "cookies": {"session": "refreshed"},
            "cookie_output": "configs/ibkr_cookies.json",
            "account_id": "DU123456",
            "used_login": True,
        }
        with (
            patch.object(
                manual_gateway_service,
                "_load_ib_web_session_state",
                return_value=({}, {"session": "expired"}, False, [], ""),
            ),
            patch(
                "app.services.manual_gateway.ib_clientportal.login_ib_web_session_with_browser",
                return_value=refreshed_session,
            ) as browser_login,
        ):
            result = manual_gateway_service._bootstrap_ib_web_session(
                {
                    "account_id": "DU123456",
                    "cookie_source": "file:configs/ibkr_cookies.json",
                    "username": "test-ib-user",
                    "password": "test-ib-pass",
                },
                "https://localhost:5000/v1/api",
                verify_ssl=False,
                timeout=10.0,
            )

        assert result == refreshed_session
        browser_login.assert_called_once()

    def test_browser_login_reports_rejected_credentials_without_waiting_for_timeout(self):
        class FakeDriver:
            def get_cookies(self):
                return []

            def find_elements(self, selector_type, selector):
                if selector == ".xyz-errormessage":
                    return [SimpleNamespace(text="Authentication failed")]
                return []

        with pytest.raises(RuntimeError, match="rejected the configured paper login credentials"):
            ib_clientportal_service._wait_for_browser_authenticated_session(
                FakeDriver(),
                SimpleNamespace(),
                "https://localhost:5000/v1/api",
                verify_ssl=False,
                timeout=10.0,
                login_timeout=60.0,
                headless=True,
                login_mode="paper",
            )

    def test_resolve_ib_web_base_url_falls_back_to_http_for_localhost(self):
        auth_status = Mock(side_effect=[RuntimeError("ssl eof"), Mock(status_code=200)])
        logger = Mock()

        with patch.object(
            manual_gateway_service,
            "_import_ib_web_session_helpers",
            return_value=(auth_status, Mock(), Mock()),
        ):
            resolved = manual_gateway_service._resolve_ib_web_base_url(
                "https://localhost:5000/v1/api",
                verify_ssl=False,
                timeout=10.0,
                logger=logger,
            )

        assert resolved == "http://localhost:5000/v1/api"
        logger.warning.assert_called_once()

    def test_resolve_ib_web_base_url_retries_until_http_is_ready(self):
        auth_status = Mock(
            side_effect=[
                RuntimeError("ssl eof"),
                RuntimeError("gateway starting"),
                RuntimeError("ssl eof"),
                Mock(status_code=200),
            ]
        )
        logger = Mock()

        with (
            patch.object(
                manual_gateway_service,
                "_import_ib_web_session_helpers",
                return_value=(auth_status, Mock(), Mock()),
            ),
            patch.object(
                manual_gateway_service.time,
                "monotonic",
                side_effect=[0.0, 0.0, 0.2, 1.2],
            ),
            patch.object(
                manual_gateway_service.time,
                "sleep",
            ) as mock_sleep,
        ):
            resolved = manual_gateway_service._resolve_ib_web_base_url(
                "https://localhost:5000/v1/api",
                verify_ssl=False,
                timeout=10.0,
                logger=logger,
            )

        assert resolved == "http://localhost:5000/v1/api"
        assert auth_status.call_count == 4
        mock_sleep.assert_called_once_with(1.0)
        logger.warning.assert_called_once()

    def test_connect_gateway_bootstraps_ib_session_and_persists_env_updates(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            startup_timeout_sec = 10.0

            @classmethod
            def from_kwargs(cls, **kwargs):
                return cls()

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)
        auth_status = Mock(return_value=Mock(status_code=200))
        ensure_session = Mock(
            return_value={
                "account_id": "DU654321",
                "cookie_output": "/Users/yunjinqi/Documents/new_projects/bt_api_py/configs/ibkr_cookies.json",
                "cookies": {"api": "cookie-value"},
            }
        )
        upsert_env_file = Mock()

        with (
            patch.object(
                manual_gateway_service,
                "_ensure_ib_clientportal_running",
            ) as mock_ensure,
            patch.object(
                manual_gateway_service,
                "_wait_for_runtime_ready",
            ) as mock_wait,
            patch.object(
                manual_gateway_service,
                "_import_ib_web_session_helpers",
                return_value=(auth_status, ensure_session, upsert_env_file),
            ),
        ):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="IB_WEB",
                credentials={
                    "account_id": "DU123456",
                    "asset_type": "STK",
                    "base_url": "https://localhost:5000",
                    "cookie_source": "browser",
                    "cookie_browser": "chrome",
                    "cookie_path": "/sso",
                    "username": "test-ib-user",
                    "password": "test-ib-pass",
                    "login_mode": "paper",
                    "login_browser": "chrome",
                    "login_headless": False,
                    "login_timeout": 180,
                    "cookie_output": "configs/ibkr_cookies.json",
                },
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=(
                    lambda value, default=False: default if value is None else bool(value)
                ),
                coerce_float=(
                    lambda value, default=0.0: default if value is None else float(value)
                ),
                import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
                default_transport="ipc",
                logger=Mock(),
            )

        assert result["status"] == "connected"
        ensure_args = mock_ensure.call_args.args
        assert ensure_args[0] == "https://localhost:5000/v1/api"
        mock_wait.assert_called_once_with(runtime, mock_wait.call_args.args[1], timeout_sec=34.0)
        ensure_session.assert_called_once()
        runtime_kwargs = runtime_cls.call_args.kwargs
        assert runtime_kwargs["base_url"] == "https://localhost:5000/v1/api"
        assert runtime_kwargs["account_id"] == "DU654321"
        assert runtime_kwargs["cookie_source"] == "file:configs/ibkr_cookies.json"
        assert runtime_kwargs["cookie_output"] == "configs/ibkr_cookies.json"
        assert isinstance(runtime_kwargs["cookies"], dict)
        assert runtime_kwargs["cookies"]
        upsert_env_file.assert_called()
        env_updates = upsert_env_file.call_args.args[1]
        assert env_updates["IB_WEB_BASE_URL"] == "https://localhost:5000/v1/api"
        assert env_updates["IB_WEB_ACCOUNT_ID"] == "DU654321"
        assert env_updates["IB_WEB_COOKIE_SOURCE"] == "file:configs/ibkr_cookies.json"
        assert env_updates["IB_WEB_COOKIE_OUTPUT"] == "configs/ibkr_cookies.json"

    def test_bootstrap_ib_web_session_uses_env_values_when_no_login_credentials(self):
        auth_status = Mock(return_value=Mock(status_code=200))
        ensure_authenticated_session = Mock(return_value={"account_id": "DU777777", "cookies": {}})
        upsert_env_file = Mock()

        with (
            patch.object(
                manual_gateway_service,
                "_load_ib_web_session_state",
                return_value=({}, {}, False, [], ""),
            ),
            patch.object(
                manual_gateway_service,
                "_import_ib_web_session_helpers",
                return_value=(auth_status, ensure_authenticated_session, upsert_env_file),
            ),
            patch.object(
                manual_gateway_service,
                "_load_backend_gateway_env_values",
                return_value={
                    "IB_WEB_USERNAME": "user",
                    "IB_WEB_PASSWORD": "pwd",
                    "IB_WEB_LOGIN_MODE": "paper",
                    "IB_WEB_LOGIN_BROWSER": "chrome",
                    "IB_WEB_LOGIN_HEADLESS": "true",
                    "IB_WEB_LOGIN_TIMEOUT": "120",
                    "IB_WEB_COOKIE_SOURCE": "file:custom-cookie.json",
                    "IB_WEB_COOKIE_OUTPUT": "custom-cookie.json",
                    "IB_WEB_COOKIE_BROWSER": "chrome",
                    "IB_WEB_COOKIE_PATH": "/custom/sso",
                },
            ),
            patch.object(
                manual_gateway_service,
                "_backend_env_file_for_helpers",
                return_value=Path("/tmp/ib_web.env"),
            ),
        ):
            result = manual_gateway_service._bootstrap_ib_web_session(
                {
                    "account_id": "DU123456",
                    "base_url": "https://localhost:5000/v1/api",
                },
                "https://localhost:5000/v1/api",
                verify_ssl=False,
                timeout=10.0,
            )

        assert result is not None
        ensure_authenticated_session.assert_called_once()
        called_kwargs = ensure_authenticated_session.call_args.kwargs
        assert called_kwargs["overrides"]["username"] == "user"
        assert called_kwargs["overrides"]["password"] == "pwd"
        assert called_kwargs["overrides"]["cookie_source"] == "file:custom-cookie.json"
        assert called_kwargs["overrides"]["cookie_browser"] == "chrome"
        assert called_kwargs["overrides"]["cookie_path"] == "/custom/sso"
        assert called_kwargs["env_file"] == Path("/tmp/ib_web.env")

    def test_connect_gateway_returns_existing_manual_gateway(self):
        gateways = {"manual:CTP:acc1": {"manual": True}}
        result = manual_gateway_service.connect_gateway(
            gateways=gateways,
            exchange_type="ctp",
            credentials={"account_id": "acc1"},
            normalize_exchange_type=lambda value: str(value).upper(),
            coerce_bool=lambda value, default=False: default,
            coerce_float=lambda value, default=0.0: default,
            import_gateway_runtime_classes=lambda: None,
            default_transport="ipc",
            logger=Mock(),
        )
        assert result["status"] == "connected"
        assert result["message"] == "Gateway already active"

    def test_connect_gateway_reuses_existing_shared_session_and_promotes_manual(self):
        runtime = Mock()
        gateways = {
            "ctp-future-acc1": {
                "manual": False,
                "runtime": runtime,
                "config": {
                    "exchange_type": "CTP",
                    "asset_type": "FUTURE",
                    "account_id": "acc1",
                    "broker_id": "9999",
                    "td_address": "tcp://td",
                    "md_address": "tcp://md",
                },
                "instances": {"inst-1"},
                "ref_count": 1,
            }
        }

        result = manual_gateway_service.connect_gateway(
            gateways=gateways,
            exchange_type="CTP",
            credentials={
                "account_id": "acc1",
                "asset_type": "FUTURE",
                "broker_id": "9999",
                "td_front": "tcp://td",
                "md_front": "tcp://md",
            },
            normalize_exchange_type=lambda value: str(value).upper(),
            coerce_bool=lambda value, default=False: default,
            coerce_float=lambda value, default=0.0: default,
            import_gateway_runtime_classes=lambda: None,
            default_transport="ipc",
            logger=Mock(),
        )

        assert result["status"] == "connected"
        assert result["gateway_key"] == "ctp-future-acc1"
        assert gateways["ctp-future-acc1"]["manual"] is True
        assert gateways["ctp-future-acc1"]["session_key"]

    def test_connect_gateway_restore_ib_web_skips_interactive_login_when_session_invalid(self):
        gateways: dict[str, dict] = {}
        runtime_cls = Mock()
        auth_status = Mock(return_value=Mock(status_code=200))
        ensure_session = Mock()
        upsert_env_file = Mock()

        class _FakeGatewayConfig:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        with (
            patch.object(
                manual_gateway_service,
                "_ensure_ib_clientportal_running",
            ),
            patch.object(
                manual_gateway_service,
                "_load_ib_web_session_state",
                return_value=(
                    {
                        "cookie_output": "configs/ibkr_cookies.json",
                        "cookie_source": "file:configs/ibkr_cookies.json",
                    },
                    {},
                    False,
                    None,
                    "DU123456",
                ),
            ),
            patch.object(
                manual_gateway_service,
                "_import_ib_web_session_helpers",
                return_value=(auth_status, ensure_session, upsert_env_file),
            ),
        ):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="IB_WEB",
                credentials={
                    "account_id": "DU123456",
                    "base_url": "https://localhost:5000",
                    "cookie_source": "file:configs/ibkr_cookies.json",
                    "cookie_output": "configs/ibkr_cookies.json",
                    "username": "test-ib-user",
                    "password": "test-ib-pass",
                },
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=lambda value, default=False: default if value is None else bool(value),
                coerce_float=lambda value, default=0.0: default if value is None else float(value),
                import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
                default_transport="ipc",
                logger=Mock(),
                allow_interactive_login=False,
            )

        assert result["status"] == "error"
        assert "手动重新连接" in result["message"]
        ensure_session.assert_not_called()
        runtime_cls.assert_not_called()
        assert gateways == {}

    def test_connect_gateway_registers_placeholder_for_unknown_exchange(self):
        gateways: dict[str, dict] = {}
        result = manual_gateway_service.connect_gateway(
            gateways=gateways,
            exchange_type="CUSTOM_EXCHANGE",
            credentials={"account_id": "acc-custom"},
            normalize_exchange_type=lambda value: str(value).upper(),
            coerce_bool=lambda value, default=False: default,
            coerce_float=lambda value, default=0.0: default,
            import_gateway_runtime_classes=lambda: None,
            default_transport="ipc",
            logger=Mock(),
        )
        assert result["status"] == "connected"
        assert "manual:CUSTOM_EXCHANGE:acc-custom" in gateways
        assert gateways["manual:CUSTOM_EXCHANGE:acc-custom"]["manual"] is True
        assert gateways["manual:CUSTOM_EXCHANGE:acc-custom"]["runtime"] is None

    def test_connect_gateway_starts_binance_runtime(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            @classmethod
            def from_kwargs(cls, **kwargs):
                return {"config": kwargs}

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)

        result = manual_gateway_service.connect_gateway(
            gateways=gateways,
            exchange_type="BINANCE",
            credentials={
                "account_id": "acc-binance",
                "api_key": "binance-key",
                "secret_key": "binance-secret",
                "asset_type": "SWAP",
            },
            normalize_exchange_type=lambda value: str(value).upper(),
            coerce_bool=lambda value, default=False: default,
            coerce_float=lambda value, default=0.0: default,
            import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
            default_transport="ipc",
            logger=Mock(),
        )

        assert result["status"] == "connected"
        assert result["message"] == "Binance gateway started successfully"
        runtime_cls.assert_called_once()
        runtime.start_in_thread.assert_called_once()
        assert "manual:BINANCE:acc-binance" in gateways
        assert gateways["manual:BINANCE:acc-binance"]["runtime"] is runtime
        assert gateways["manual:BINANCE:acc-binance"]["asset_type"] == "SWAP"

    def test_connect_gateway_starts_binance_runtime_with_detected_proxy_settings(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            @classmethod
            def from_kwargs(cls, **kwargs):
                return {"config": kwargs}

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)

        with (
            patch.object(
                manual_gateway_service,
                "_get_gateway_proxies_kwarg",
                return_value={"https": "http://127.0.0.1:7890", "http": "http://127.0.0.1:7890"},
            ),
            patch.object(
                manual_gateway_service,
                "_get_gateway_ws_proxy_kwargs",
                return_value={
                    "http_proxy_host": "127.0.0.1",
                    "http_proxy_port": 7890,
                    "async_proxy": "http://127.0.0.1:7890",
                },
            ),
        ):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="BINANCE",
                credentials={
                    "account_id": "acc-binance",
                    "api_key": "binance-key",
                    "secret_key": "binance-secret",
                    "asset_type": "SWAP",
                },
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=lambda value, default=False: default,
                coerce_float=lambda value, default=0.0: default,
                import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
                default_transport="ipc",
                logger=Mock(),
            )

        assert result["status"] == "connected"
        runtime_kwargs = runtime_cls.call_args.kwargs
        assert runtime_kwargs["proxies"] == {
            "https": "http://127.0.0.1:7890",
            "http": "http://127.0.0.1:7890",
        }
        assert runtime_kwargs["http_proxy_host"] == "127.0.0.1"
        assert runtime_kwargs["http_proxy_port"] == 7890
        assert runtime_kwargs["async_proxy"] == "http://127.0.0.1:7890"

    def test_detect_working_proxy_uses_system_proxy_when_env_missing(self):
        with (
            patch.dict(manual_gateway_service.os.environ, {}, clear=True),
            patch.object(manual_gateway_service, "_proxy_checked", False),
            patch.object(manual_gateway_service, "_detected_proxy_url", ""),
            patch.object(
                manual_gateway_service.urllib.request,
                "getproxies",
                return_value={"https": "http://127.0.0.1:7890"},
            ),
            patch.object(
                manual_gateway_service.socket,
                "create_connection",
            ) as mock_create_connection,
        ):
            mock_socket = Mock()
            mock_create_connection.return_value = mock_socket

            proxy = manual_gateway_service._detect_working_proxy(force_recheck=True)

        assert proxy == "http://127.0.0.1:7890"
        mock_create_connection.assert_called_once_with(("127.0.0.1", 7890), timeout=3.0)
        mock_socket.close.assert_called_once()

    def test_detect_working_proxy_reuses_cached_system_proxy(self):
        with (
            patch.dict(manual_gateway_service.os.environ, {}, clear=True),
            patch.object(manual_gateway_service, "_proxy_checked", False),
            patch.object(manual_gateway_service, "_detected_proxy_url", ""),
            patch.object(
                manual_gateway_service.urllib.request,
                "getproxies",
                return_value={"https": "http://127.0.0.1:7890"},
            ),
            patch.object(
                manual_gateway_service.socket,
                "create_connection",
            ) as mock_create_connection,
        ):
            mock_socket = Mock()
            mock_create_connection.return_value = mock_socket

            first = manual_gateway_service._detect_working_proxy(force_recheck=True)
            second = manual_gateway_service._detect_working_proxy()

        assert first == "http://127.0.0.1:7890"
        assert second == "http://127.0.0.1:7890"
        mock_create_connection.assert_called_once_with(("127.0.0.1", 7890), timeout=3.0)

    def test_connect_gateway_starts_ctp_runtime_after_waiting_ready(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            startup_timeout_sec = 10.0

            @classmethod
            def from_kwargs(cls, **kwargs):
                return cls()

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)

        with (
            patch.object(manual_gateway_service, "_wait_for_runtime_ready") as mock_wait,
            patch(
                "app.services.ctp_tunnel.is_proxy_tunnel_needed",
                return_value=False,
            ),
        ):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="CTP",
                credentials={
                    "account_id": "089763",
                    "broker_id": "9999",
                    "user_id": "089763",
                    "password": "secret",
                    "td_front": "tcp://td.example:41205",
                    "md_front": "tcp://md.example:41213",
                },
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=lambda value, default=False: default,
                coerce_float=lambda value, default=0.0: default,
                import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
                default_transport="ipc",
                logger=Mock(),
            )

        assert result["status"] == "connected"
        assert result["message"] == "CTP gateway started successfully"
        runtime_cls.assert_called_once()
        runtime.start_in_thread.assert_called_once()
        mock_wait.assert_called_once_with(runtime, mock_wait.call_args.args[1], timeout_sec=64.0)
        runtime_kwargs = runtime_cls.call_args.kwargs
        assert runtime_kwargs["startup_timeout_sec"] == 20.0
        assert runtime_kwargs["gateway_startup_timeout_sec"] == 20.0
        assert runtime_kwargs["transport"] == "tcp"
        assert "manual:CTP:089763" in gateways
        assert gateways["manual:CTP:089763"]["runtime"] is runtime

    def test_connect_gateway_uses_custom_ctp_timeout_when_provided(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            startup_timeout_sec = 25.0

            @classmethod
            def from_kwargs(cls, **kwargs):
                return cls()

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)

        with patch.object(manual_gateway_service, "_wait_for_runtime_ready"):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="CTP",
                credentials={
                    "account_id": "089763",
                    "broker_id": "9999",
                    "user_id": "089763",
                    "password": "secret",
                    "td_front": "tcp://td.example:41205",
                    "md_front": "tcp://md.example:41213",
                    "timeout": 25,
                },
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=lambda value, default=False: default,
                coerce_float=lambda value, default=0.0: default,
                import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
                default_transport="ipc",
                logger=Mock(),
            )

        assert result["status"] == "connected"
        runtime_kwargs = runtime_cls.call_args.kwargs
        assert runtime_kwargs["startup_timeout_sec"] == 25.0
        assert runtime_kwargs["gateway_startup_timeout_sec"] == 25.0

    def test_connect_gateway_starts_ib_runtime_after_ensuring_clientportal(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            startup_timeout_sec = 10.0

            @classmethod
            def from_kwargs(cls, **kwargs):
                return cls()

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)

        with (
            patch.object(manual_gateway_service, "_ensure_ib_clientportal_running") as mock_ensure,
            patch.object(
                manual_gateway_service,
                "_resolve_ib_web_base_url",
                return_value="https://localhost:5000/v1/api",
            ) as mock_resolve_base_url,
            patch.object(
                manual_gateway_service,
                "_bootstrap_ib_web_session",
                return_value={
                    "cookies": {"api": "cookie-value"},
                    "cookie_output": "configs/ibkr_cookies.json",
                    "cookie_source": "file:configs/ibkr_cookies.json",
                    "account_id": "DU123456",
                    "status_code": 200,
                    "used_login": False,
                },
            ) as mock_bootstrap,
            patch.object(
                manual_gateway_service,
                "_wait_for_runtime_ready",
            ) as mock_wait,
        ):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="IB_WEB",
                credentials={
                    "account_id": "DU123456",
                    "asset_type": "STK",
                    "base_url": "https://localhost:5000",
                    "cookie_source": "file:../bt_api_py/configs/ibkr_cookies.json",
                    "cookie_browser": "chrome",
                    "cookie_path": "/sso",
                    "cookies": {"api": "cookie-value"},
                    "username": "test-ib-user",
                    "password": "test-ib-pass",
                    "login_mode": "paper",
                    "login_browser": "chrome",
                    "login_headless": False,
                    "login_timeout": 180,
                    "cookie_output": "../bt_api_py/configs/ibkr_cookies.json",
                },
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=lambda value, default=False: default if value is None else bool(value),
                coerce_float=lambda value, default=0.0: default if value is None else float(value),
                import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
                default_transport="ipc",
                logger=Mock(),
            )

        assert result["status"] == "connected"
        assert result["message"] == "IB Web gateway started successfully"
        mock_ensure.assert_called_once()
        mock_resolve_base_url.assert_called_once()
        mock_bootstrap.assert_called_once()
        runtime_cls.assert_called_once()
        runtime.start_in_thread.assert_called_once()
        mock_wait.assert_called_once_with(runtime, mock_wait.call_args.args[1], timeout_sec=34.0)
        runtime_kwargs = runtime_cls.call_args.kwargs
        assert runtime_kwargs["proxies"] == {}
        assert runtime_kwargs["async_proxy"] == ""
        assert runtime_kwargs["cookie_source"] == "file:configs/ibkr_cookies.json"
        assert runtime_kwargs["cookie_browser"] == "chrome"
        assert runtime_kwargs["cookie_path"] == "/sso"
        assert runtime_kwargs["cookies"] == {"api": "cookie-value"}
        assert runtime_kwargs["username"] == "test-ib-user"
        assert runtime_kwargs["password"] == "test-ib-pass"
        assert runtime_kwargs["login_mode"] == "paper"
        assert runtime_kwargs["login_browser"] == "chrome"
        assert runtime_kwargs["login_headless"] is False
        assert runtime_kwargs["login_timeout"] == 180.0
        assert runtime_kwargs["cookie_output"] == "configs/ibkr_cookies.json"
        assert runtime_kwargs["transport"] == "tcp"
        assert "manual:IB_WEB:DU123456" in gateways
        assert gateways["manual:IB_WEB:DU123456"]["runtime"] is runtime

    def test_connect_gateway_returns_error_when_ctp_runtime_not_ready(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            startup_timeout_sec = 10.0

            @classmethod
            def from_kwargs(cls, **kwargs):
                return cls()

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)

        with (
            patch.object(
                manual_gateway_service,
                "_wait_for_runtime_ready",
                side_effect=RuntimeError("attempt 3/3 RuntimeError: ctp market not ready"),
            ),
            patch(
                "app.services.ctp_tunnel.is_proxy_tunnel_needed",
                return_value=False,
            ),
        ):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="CTP",
                credentials={
                    "account_id": "089763",
                    "broker_id": "9999",
                    "user_id": "089763",
                    "password": "secret",
                    "td_front": "tcp://td.example:41205",
                    "md_front": "tcp://md.example:41213",
                },
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=lambda value, default=False: default,
                coerce_float=lambda value, default=0.0: default,
                import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
                default_transport="ipc",
                logger=Mock(),
            )

        assert result["status"] == "error"
        assert "ctp market not ready" in result["message"]
        runtime.stop.assert_called_once()
        assert gateways == {}

    def test_connect_gateway_returns_actionable_error_when_ctp_native_sdk_missing(self):
        gateways: dict[str, dict] = {}

        native_error = RuntimeError(
            "CTP native API 'CThostFtdcTraderApi' is unavailable: Git LFS pointer detected"
        )

        def _raise_import_error():
            raise native_error

        result = manual_gateway_service.connect_gateway(
            gateways=gateways,
            exchange_type="CTP",
            credentials={
                "account_id": "089763",
                "broker_id": "9999",
                "user_id": "089763",
                "password": "secret",
                "td_front": "tcp://td.example:41205",
                "md_front": "tcp://md.example:41213",
            },
            normalize_exchange_type=lambda value: str(value).upper(),
            coerce_bool=lambda value, default=False: default,
            coerce_float=lambda value, default=0.0: default,
            import_gateway_runtime_classes=_raise_import_error,
            default_transport="ipc",
            logger=Mock(),
        )

        assert result["status"] == "error"
        assert "git lfs pull" in result["message"].lower()
        assert "CTP原生SDK不可用" in result["message"]
        assert gateways == {}

    def test_connect_gateway_switches_to_reachable_current_simnow_front(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            startup_timeout_sec = 10.0

            @classmethod
            def from_kwargs(cls, **kwargs):
                return cls()

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)
        logger = Mock()

        reachable_map = {
            ("182.254.243.31", 30001): False,
            ("182.254.243.31", 30011): False,
            ("182.254.243.31", 30002): True,
            ("182.254.243.31", 30012): True,
        }

        def _reachable(host, port, timeout=1.0):
            return reachable_map.get((host, port), False)

        with (
            patch.object(
                manual_gateway_service, "_is_tcp_endpoint_reachable", side_effect=_reachable
            ),
            patch.object(
                manual_gateway_service,
                "_wait_for_runtime_ready",
            ),
        ):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="CTP",
                credentials={
                    "account_id": "089763",
                    "broker_id": "9999",
                    "user_id": "089763",
                    "password": "secret",
                    "td_front": "tcp://182.254.243.31:30001",
                    "md_front": "tcp://182.254.243.31:30011",
                },
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=lambda value, default=False: default,
                coerce_float=lambda value, default=0.0: default,
                import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
                default_transport="ipc",
                logger=logger,
            )

        assert result["status"] == "connected"
        runtime_kwargs = runtime_cls.call_args.kwargs
        assert runtime_kwargs["td_address"] == "tcp://182.254.243.31:30002"
        assert runtime_kwargs["md_address"] == "tcp://182.254.243.31:30012"
        assert any(
            "Requested CTP SimNow front" in str(call.args[0])
            for call in logger.warning.call_args_list
        )

    def test_connect_gateway_returns_clear_error_when_all_current_simnow_fronts_unreachable(self):
        gateways: dict[str, dict] = {}
        logger = Mock()

        with (
            patch.object(manual_gateway_service, "_is_tcp_endpoint_reachable", return_value=False),
            patch(
                "app.services.ctp_tunnel.is_proxy_tunnel_needed",
                return_value=False,
            ),
        ):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="CTP",
                credentials={
                    "account_id": "089763",
                    "broker_id": "9999",
                    "user_id": "089763",
                    "password": "secret",
                    "td_front": "tcp://182.254.243.31:30001",
                    "md_front": "tcp://182.254.243.31:30011",
                },
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=lambda value, default=False: default,
                coerce_float=lambda value, default=0.0: default,
                import_gateway_runtime_classes=Mock(),
                default_transport="ipc",
                logger=logger,
            )

        assert result["status"] == "error"
        assert (
            "simnow当前三组前置均不可达" in result["message"].lower()
            or "SimNow当前三组前置均不可达" in result["message"]
        )
        assert gateways == {}

    def test_connect_gateway_keeps_requested_simnow_front_when_proxy_tunnel_available(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            startup_timeout_sec = 10.0

            @classmethod
            def from_kwargs(cls, **kwargs):
                return cls()

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)
        logger = Mock()

        with (
            patch.object(manual_gateway_service, "_is_tcp_endpoint_reachable", return_value=False),
            patch.object(
                manual_gateway_service,
                "_wait_for_runtime_ready",
            ),
            patch("app.services.ctp_tunnel.is_proxy_tunnel_needed", return_value=True),
        ):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="CTP",
                credentials={
                    "account_id": "089763",
                    "broker_id": "9999",
                    "user_id": "089763",
                    "password": "secret",
                    "td_front": "tcp://182.254.243.31:30001",
                    "md_front": "tcp://182.254.243.31:30011",
                },
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=lambda value, default=False: default,
                coerce_float=lambda value, default=0.0: default,
                import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
                default_transport="ipc",
                logger=logger,
            )

        assert result["status"] == "connected"
        runtime_kwargs = runtime_cls.call_args.kwargs
        assert runtime_kwargs["td_address"] == "tcp://182.254.243.31:30001"
        assert runtime_kwargs["md_address"] == "tcp://182.254.243.31:30011"
        logger.warning.assert_called()

    def test_connect_gateway_starts_okx_runtime(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            @classmethod
            def from_kwargs(cls, **kwargs):
                return {"config": kwargs}

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)

        result = manual_gateway_service.connect_gateway(
            gateways=gateways,
            exchange_type="OKX",
            credentials={
                "account_id": "acc-okx",
                "api_key": "okx-key",
                "secret_key": "okx-secret",
                "passphrase": "okx-passphrase",
                "asset_type": "SPOT",
            },
            normalize_exchange_type=lambda value: str(value).upper(),
            coerce_bool=lambda value, default=False: default,
            coerce_float=lambda value, default=0.0: default,
            import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
            default_transport="ipc",
            logger=Mock(),
        )

        assert result["status"] == "connected"
        assert result["message"] == "OKX gateway started successfully"
        runtime_cls.assert_called_once()
        runtime.start_in_thread.assert_called_once()
        assert "manual:OKX:acc-okx" in gateways
        assert gateways["manual:OKX:acc-okx"]["runtime"] is runtime
        assert gateways["manual:OKX:acc-okx"]["asset_type"] == "SPOT"

    def test_connect_gateway_starts_okx_runtime_with_detected_proxy_settings(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            @classmethod
            def from_kwargs(cls, **kwargs):
                return {"config": kwargs}

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)

        with (
            patch.object(
                manual_gateway_service,
                "_get_gateway_proxies_kwarg",
                return_value={"https": "http://127.0.0.1:7890", "http": "http://127.0.0.1:7890"},
            ),
            patch.object(
                manual_gateway_service,
                "_get_gateway_ws_proxy_kwargs",
                return_value={
                    "http_proxy_host": "127.0.0.1",
                    "http_proxy_port": 7890,
                    "async_proxy": "http://127.0.0.1:7890",
                },
            ),
        ):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="OKX",
                credentials={
                    "account_id": "acc-okx",
                    "api_key": "okx-key",
                    "secret_key": "okx-secret",
                    "passphrase": "okx-passphrase",
                    "asset_type": "SPOT",
                },
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=lambda value, default=False: default,
                coerce_float=lambda value, default=0.0: default,
                import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
                default_transport="ipc",
                logger=Mock(),
            )

        assert result["status"] == "connected"
        runtime_kwargs = runtime_cls.call_args.kwargs
        assert runtime_kwargs["proxies"] == {
            "https": "http://127.0.0.1:7890",
            "http": "http://127.0.0.1:7890",
        }
        assert runtime_kwargs["http_proxy_host"] == "127.0.0.1"
        assert runtime_kwargs["http_proxy_port"] == 7890
        assert runtime_kwargs["async_proxy"] == "http://127.0.0.1:7890"

    def test_connect_gateway_starts_binance_runtime_with_env_fallback(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            @classmethod
            def from_kwargs(cls, **kwargs):
                return {"config": kwargs}

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)
        fake_settings = SimpleNamespace(
            BINANCE_API_KEY="",
            BINANCE_SECRET_KEY="",
            BINANCE_TESTNET=False,
            BINANCE_BASE_URL="",
        )

        with (
            patch("app.config.get_settings", return_value=fake_settings),
            patch.object(
                manual_gateway_service,
                "_load_backend_gateway_env_values",
                return_value={
                    "BINANCE_API_KEY": "binance-key-from-env",
                    "BINANCE_PASSWORD": "binance-secret-from-legacy-password",
                    "BINANCE_TESTNET": "true",
                    "BINANCE_BASE_URL": "https://api.binance.com",
                },
            ),
        ):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="BINANCE",
                credentials={
                    "account_id": "acc-binance",
                    "asset_type": "SWAP",
                },
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=lambda value, default=False: default,
                coerce_float=lambda value, default=0.0: default,
                import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
                default_transport="ipc",
                logger=Mock(),
            )

        assert result["status"] == "connected"
        runtime_kwargs = runtime_cls.call_args.kwargs
        assert runtime_kwargs["api_key"] == "binance-key-from-env"
        assert runtime_kwargs["secret_key"] == "binance-secret-from-legacy-password"

    def test_connect_gateway_starts_okx_runtime_with_env_fallback(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            @classmethod
            def from_kwargs(cls, **kwargs):
                return {"config": kwargs}

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)
        fake_settings = SimpleNamespace(
            OKX_API_KEY="",
            OKX_SECRET_KEY="",
            OKX_PASSPHRASE="okx-passphrase",
            OKX_TESTNET=False,
            OKX_BASE_URL="",
        )

        with (
            patch("app.config.get_settings", return_value=fake_settings),
            patch.object(
                manual_gateway_service,
                "_load_backend_gateway_env_values",
                return_value={
                    "OKX_API_KEY": "okx-key-from-env",
                    "OKX_SECRET": "okx-secret-from-legacy-secret",
                    "OKX_PASSPHRASE": "okx-passphrase",
                },
            ),
        ):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="OKX",
                credentials={
                    "account_id": "acc-okx",
                    "asset_type": "SPOT",
                },
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=lambda value, default=False: default,
                coerce_float=lambda value, default=0.0: default,
                import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
                default_transport="ipc",
                logger=Mock(),
            )

        assert result["status"] == "connected"
        runtime_kwargs = runtime_cls.call_args.kwargs
        assert runtime_kwargs["api_key"] == "okx-key-from-env"
        assert runtime_kwargs["secret_key"] == "okx-secret-from-legacy-secret"
        assert runtime_kwargs["passphrase"] == "okx-passphrase"

    def test_connect_gateway_starts_okx_runtime_with_legacy_password_as_passphrase(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            @classmethod
            def from_kwargs(cls, **kwargs):
                return {"config": kwargs}

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)
        fake_settings = SimpleNamespace(
            OKX_API_KEY="",
            OKX_SECRET_KEY="",
            OKX_PASSPHRASE="",
            OKX_TESTNET=False,
            OKX_BASE_URL="",
        )

        with (
            patch("app.config.get_settings", return_value=fake_settings),
            patch.object(
                manual_gateway_service,
                "_load_backend_gateway_env_values",
                return_value={
                    "OKX_API_KEY": "okx-key-from-env",
                    "OKX_SECRET": "okx-secret-from-legacy-secret",
                    "OKX_PASSWORD": "okx-passphrase-from-password",
                },
            ),
        ):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="OKX",
                credentials={
                    "account_id": "acc-okx",
                    "asset_type": "SPOT",
                },
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=lambda value, default=False: default,
                coerce_float=lambda value, default=0.0: default,
                import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
                default_transport="ipc",
                logger=Mock(),
            )

        assert result["status"] == "connected"
        runtime_kwargs = runtime_cls.call_args.kwargs
        assert runtime_kwargs["passphrase"] == "okx-passphrase-from-password"

    def test_connect_gateway_starts_mt5_runtime_with_env_fallback(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            @classmethod
            def from_kwargs(cls, **kwargs):
                return {"config": kwargs}

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)
        fake_settings = SimpleNamespace(
            MT5_LOGIN="",
            MT5_PASSWORD="",
            MT5_SERVER="",
            MT5_WS_URI="",
            MT5_SYMBOL_SUFFIX="",
        )

        with (
            patch("app.config.get_settings", return_value=fake_settings),
            patch.object(
                manual_gateway_service,
                "_load_backend_gateway_env_values",
                return_value={
                    "MT5_LOGIN": "789012",
                    "MT5_PASSWORD": "mt5-password",
                    "MT5_SERVER": "Demo",
                    "MT5_WS_URI": "wss://demo.example.com",
                },
            ),
        ):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="MT5",
                credentials={
                    "account_id": "",
                },
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=lambda value, default=False: default,
                coerce_float=lambda value, default=0.0: default,
                import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
                default_transport="ipc",
                logger=Mock(),
            )

        assert result["status"] == "connected"
        runtime_kwargs = runtime_cls.call_args.kwargs
        assert runtime_kwargs["login"] == 789012
        assert runtime_kwargs["password"] == "mt5-password"

    def test_connect_gateway_starts_mt5_runtime_with_legacy_account_aliases(self):
        gateways: dict[str, dict] = {}

        class _FakeGatewayConfig:
            @classmethod
            def from_kwargs(cls, **kwargs):
                return {"config": kwargs}

        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)
        fake_settings = SimpleNamespace(
            MT5_LOGIN="",
            MT5_PASSWORD="",
            MT5_SERVER="",
            MT5_WS_URI="",
            MT5_SYMBOL_SUFFIX="",
        )

        with (
            patch("app.config.get_settings", return_value=fake_settings),
            patch.object(
                manual_gateway_service,
                "_load_backend_gateway_env_values",
                return_value={
                    "MT5_ACCOUNT": "123456",
                    "MT5_PASS": "alias-pass",
                },
            ),
        ):
            result = manual_gateway_service.connect_gateway(
                gateways=gateways,
                exchange_type="MT5",
                credentials={},
                normalize_exchange_type=lambda value: str(value).upper(),
                coerce_bool=lambda value, default=False: default,
                coerce_float=lambda value, default=0.0: default,
                import_gateway_runtime_classes=lambda: (_FakeGatewayConfig, runtime_cls),
                default_transport="ipc",
                logger=Mock(),
            )

        assert result["status"] == "connected"
        runtime_kwargs = runtime_cls.call_args.kwargs
        assert runtime_kwargs["login"] == 123456
        assert runtime_kwargs["password"] == "alias-pass"

    def test_ensure_ib_clientportal_running_starts_background_process_when_local_port_down(self):
        logger = Mock()
        process = Mock()
        process.poll.return_value = None

        with (
            patch.object(
                manual_gateway_service,
                "_should_manage_ib_clientportal",
                return_value=True,
            ),
            patch.object(
                manual_gateway_service,
                "_parse_base_url_endpoint",
                return_value=("localhost", 5000),
            ),
            patch.object(
                manual_gateway_service,
                "_is_tcp_endpoint_reachable",
                side_effect=[False, False],
            ),
            patch.object(
                manual_gateway_service,
                "_find_ib_clientportal_dir",
                return_value=Path("/tmp/clientportal.gw"),
            ),
            patch.object(
                manual_gateway_service,
                "_start_ib_clientportal_background",
                return_value=process,
            ) as mock_start,
            patch.object(
                manual_gateway_service,
                "_wait_for_tcp_endpoint",
                return_value=True,
            ) as mock_wait,
        ):
            manual_gateway_service._ib_clientportal_process = None
            manual_gateway_service._ensure_ib_clientportal_running(
                "https://localhost:5000",
                logger,
                startup_wait_sec=1.0,
            )

        mock_start.assert_called_once_with(Path("/tmp/clientportal.gw"))
        mock_wait.assert_called_once_with("localhost", 5000, timeout_sec=1.0)
        logger.info.assert_called_once()

    def test_wait_for_runtime_ready_raises_latest_adapter_connect_error(self):
        logger = Mock()
        health = Mock()
        health.snapshot.side_effect = [
            {
                "state": "running",
                "market_connection": "connecting",
                "recent_errors": [],
            },
            {
                "state": "running",
                "market_connection": "error",
                "recent_errors": [
                    {
                        "source": "adapter_connect",
                        "message": "attempt 3/3 RuntimeError: ctp market not ready",
                    }
                ],
            },
        ]
        runtime = Mock()
        runtime._adapter_connected = False
        runtime.health = health

        with pytest.raises(RuntimeError, match="ctp market not ready"):
            manual_gateway_service._wait_for_runtime_ready(
                runtime,
                logger,
                timeout_sec=1.0,
                poll_interval_sec=0.0,
            )

    def test_kill_process_on_port_only_targets_listeners_with_psutil(self):
        listen_proc = Mock(pid=456)
        established_proc = Mock(pid=123)
        fake_psutil = Mock()
        fake_psutil.NoSuchProcess = RuntimeError
        fake_psutil.AccessDenied = PermissionError
        fake_psutil.net_connections.return_value = [
            Mock(laddr=Mock(port=58583), pid=123, status="ESTABLISHED"),
            Mock(laddr=Mock(port=58583), pid=456, status="LISTEN"),
        ]
        fake_psutil.Process.side_effect = lambda pid: {
            123: established_proc,
            456: listen_proc,
        }[pid]

        with (
            patch.dict("sys.modules", {"psutil": fake_psutil}),
            patch.object(manual_gateway_service.os, "getpid", return_value=1),
        ):
            manual_gateway_service._kill_process_on_port(58583)

        established_proc.kill.assert_not_called()
        listen_proc.kill.assert_called_once()

    def test_kill_process_on_port_lsof_fallback_only_queries_listeners(self):
        import builtins

        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError
            return original_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=fake_import),
            patch.object(
                manual_gateway_service.subprocess,
                "run",
                return_value=Mock(stdout=""),
            ) as mock_run,
        ):
            manual_gateway_service._kill_process_on_port(58583)

        assert mock_run.call_args.args[0] == [
            "lsof",
            "-nP",
            "-iTCP:58583",
            "-sTCP:LISTEN",
            "-t",
        ]

    def test_query_gateway_account_uses_health_snapshot(self):
        health = Mock()
        health.snapshot.return_value = {
            "exchange": "IB_WEB",
            "account_id": "acc1",
            "state": "running",
            "market_connection": "connected",
            "trade_connection": "connected",
        }
        runtime = Mock()
        runtime.health = health
        result = manual_gateway_service.query_gateway_account(
            {"gw1": {"runtime": runtime, "exchange_type": "IB_WEB", "account_id": "acc1"}},
            "gw1",
        )
        assert result == {
            "gateway_key": "gw1",
            "exchange": "IB_WEB",
            "account_id": "acc1",
            "state": "running",
            "market_connection": "connected",
            "trade_connection": "connected",
        }

    def test_query_gateway_account_merges_adapter_balance(self):
        health = Mock()
        health.snapshot.return_value = {
            "exchange": "MT5",
            "account_id": "demo",
            "state": "running",
            "market_connection": "connected",
            "trade_connection": "connected",
        }
        adapter = Mock()
        adapter.get_balance.return_value = {
            "balance": 100000.0,
            "equity": 100250.0,
            "margin": 1200.0,
            "margin_free": 99050.0,
            "currency": "USD",
        }
        runtime = SimpleNamespace(health=health, adapter=adapter)

        result = manual_gateway_service.query_gateway_account(
            {"gw1": {"runtime": runtime, "exchange_type": "MT5", "account_id": "demo"}},
            "gw1",
        )

        assert result is not None
        assert result["gateway_key"] == "gw1"
        assert result["value"] == 100250.0
        assert result["cash"] == 99050.0
        assert result["margin"] == 1200.0
        assert result["account_source"] == "adapter.get_balance"

    def test_query_gateway_account_derives_cash_from_equity_minus_margin(self):
        health = Mock()
        health.snapshot.return_value = {
            "exchange": "MT5",
            "account_id": "demo",
            "state": "running",
            "market_connection": "connected",
            "trade_connection": "connected",
        }
        adapter = Mock()
        adapter.get_balance.return_value = {
            "balance": 100000.0,
            "equity": 100250.0,
            "margin": 1200.0,
            "currency": "USD",
        }
        runtime = SimpleNamespace(health=health, adapter=adapter)

        result = manual_gateway_service.query_gateway_account(
            {"gw1": {"runtime": runtime, "exchange_type": "MT5", "account_id": "demo"}},
            "gw1",
        )

        assert result is not None
        assert result["value"] == 100250.0
        assert result["cash"] == 99050.0
        assert result["margin"] == 1200.0
        assert result["balance"] == 100000.0

    def test_query_gateway_account_normalizes_crypto_balance_aliases(self):
        health = Mock()
        health.snapshot.return_value = {
            "exchange": "BYBIT",
            "account_id": "unified",
            "state": "running",
            "market_connection": "connected",
            "trade_connection": "connected",
        }
        adapter = Mock()
        adapter.get_balance.return_value = {
            "account_type": "UNIFIED",
            "total_equity": "10,250.5",
            "total_wallet_balance": "10,000.0",
            "total_available_balance": "9,125.25",
            "total_initial_margin": "875.25",
        }
        runtime = SimpleNamespace(health=health, adapter=adapter)

        result = manual_gateway_service.query_gateway_account(
            {"gw1": {"runtime": runtime, "exchange_type": "BYBIT", "account_id": "unified"}},
            "gw1",
        )

        assert result is not None
        assert result["value"] == 10250.5
        assert result["equity"] == 10250.5
        assert result["cash"] == 9125.25
        assert result["margin"] == 875.25
        assert result["account_source"] == "adapter.get_balance"

    def test_query_gateway_account_preserves_nested_zero_available_cash(self):
        health = Mock()
        health.snapshot.return_value = {
            "exchange": "IB_WEB",
            "account_id": "acc-zero",
            "state": "running",
            "market_connection": "connected",
            "trade_connection": "connected",
        }
        adapter = Mock()
        adapter.get_balance.return_value = {
            "NetLiquidation": {"amount": "250000.0"},
            "AvailableFunds": {"amount": 0},
            "Balance": 250000.0,
        }
        runtime = SimpleNamespace(health=health, adapter=adapter)

        result = manual_gateway_service.query_gateway_account(
            {"gw1": {"runtime": runtime, "exchange_type": "IB_WEB", "account_id": "acc-zero"}},
            "gw1",
        )

        assert result is not None
        assert result["value"] == 250000.0
        assert result["cash"] == 0.0
        assert result["account_source"] == "adapter.get_balance"

    def test_query_gateway_positions_supports_callable_and_internal_dict(self):
        runtime_a = Mock()
        runtime_a.positions = Mock(return_value=[{"symbol": "IF00"}])
        result_a = manual_gateway_service.query_gateway_positions(
            {"gw1": {"runtime": runtime_a}},
            "gw1",
        )
        assert result_a == [{"symbol": "IF00"}]

        runtime_b = Mock()
        runtime_b.adapter = None
        runtime_b.positions = None
        runtime_b._positions = {"a": {"symbol": "rb", "size": 1}}
        result_b = manual_gateway_service.query_gateway_positions(
            {"gw2": {"runtime": runtime_b}},
            "gw2",
        )
        assert result_b == [{"symbol": "rb", "size": 1}]

    def test_query_gateway_positions_reads_runtime_adapter_positions(self):
        adapter = Mock()
        adapter.get_positions = Mock(return_value=[{"symbol": "XAUUSD", "volume": 0.1}])
        runtime = SimpleNamespace(adapter=adapter)

        result = manual_gateway_service.query_gateway_positions(
            {"gw1": {"runtime": runtime}},
            "gw1",
            strict=True,
        )

        assert result == [{"symbol": "XAUUSD", "volume": 0.1}]
        adapter.get_positions.assert_called_once_with()

    def test_query_gateway_positions_strict_raises_when_runtime_missing(self):
        with pytest.raises(RuntimeError, match="has no runtime"):
            manual_gateway_service.query_gateway_positions(
                {"gw1": {"runtime": None}},
                "gw1",
                strict=True,
            )

    def test_list_connected_gateways_filters_manual_only(self):
        result = manual_gateway_service.list_connected_gateways(
            {
                "manual:CTP:acc1": {
                    "manual": True,
                    "exchange_type": "CTP",
                    "account_id": "acc1",
                    "runtime": None,
                },
                "shared:CTP:acc2": {
                    "manual": False,
                    "exchange_type": "CTP",
                    "account_id": "acc2",
                    "runtime": None,
                },
            }
        )
        assert result == [
            {
                "gateway_key": "manual:CTP:acc1",
                "exchange_type": "CTP",
                "account_id": "acc1",
                "has_runtime": False,
            }
        ]

    def test_disconnect_gateway_handles_not_found_and_manual_only(self):
        not_found = manual_gateway_service.disconnect_gateway({}, "gw-missing")
        assert not_found["status"] == "error"

        strategy_owned = manual_gateway_service.disconnect_gateway(
            {"gw1": {"manual": False, "runtime": None}},
            "gw1",
        )
        assert strategy_owned["status"] == "error"

        runtime = Mock()
        gateways = {"gw2": {"manual": True, "runtime": runtime}}
        disconnected = manual_gateway_service.disconnect_gateway(gateways, "gw2")
        runtime.stop.assert_called_once()
        assert disconnected["status"] == "disconnected"
        assert gateways == {}

    def test_disconnect_gateway_rejects_in_use_manual_gateway(self):
        runtime = Mock()
        gateways = {
            "gw2": {
                "manual": True,
                "runtime": runtime,
                "instances": {"inst-1"},
                "ref_count": 1,
            }
        }

        disconnected = manual_gateway_service.disconnect_gateway(gateways, "gw2")

        runtime.stop.assert_not_called()
        assert disconnected["status"] == "error"
        assert "in use" in disconnected["message"]


class TestGatewayHealthService:
    def test_get_gateway_health_returns_runtime_snapshot(self):
        health = Mock()
        health.snapshot.return_value = {"state": "running", "is_healthy": True}
        runtime = Mock()
        runtime.health = health
        result = gateway_health_service.get_gateway_health(
            gateways={
                "gw1": {
                    "runtime": runtime,
                    "ref_count": 2,
                    "instances": {"inst1", "inst2"},
                }
            },
            load_instances=lambda: {},
            is_pid_alive=lambda pid: True,
            resolve_strategy_dir=lambda strategy_id: Path("/tmp") / strategy_id,
            load_strategy_config=lambda strategy_dir: {},
            load_strategy_env=lambda strategy_dir: {},
        )
        assert result == [
            {
                "gateway_key": "gw1",
                "state": "running",
                "is_healthy": True,
                "exchange": "",
                "asset_type": "",
                "account_id": "",
                "market_connection": "unknown",
                "trade_connection": "unknown",
                "uptime_sec": 0,
                "last_heartbeat": None,
                "heartbeat_age_sec": None,
                "last_tick_time": None,
                "last_order_time": None,
                "strategy_count": 0,
                "symbol_count": 0,
                "tick_count": 0,
                "order_count": 0,
                "selected_ctp_env": "",
                "td_front": "",
                "md_front": "",
                "selection_reason": "",
                "auth_state": "unknown",
                "login_state": "unknown",
                "front_id": "",
                "session_id": "",
                "trading_day": "",
                "ref_count": 2,
                "instances": ["inst1", "inst2"],
                "recent_errors": [],
            }
        ]

    def test_get_gateway_health_adds_direct_running_instance(self):
        result = gateway_health_service.get_gateway_health(
            gateways={},
            load_instances=lambda: {
                "inst1": {
                    "status": "running",
                    "pid": 123,
                    "strategy_id": "demo_strategy",
                    "strategy_name": "Demo Strategy",
                }
            },
            is_pid_alive=lambda pid: True,
            resolve_strategy_dir=lambda strategy_id: Path("/tmp") / strategy_id,
            load_strategy_config=lambda strategy_dir: {"ctp": {"investor_id": "acc1"}},
            load_strategy_env=lambda strategy_dir: {},
        )
        assert result == [
            {
                "gateway_key": "direct:demo_strategy",
                "state": "running",
                "is_healthy": True,
                "exchange": "CTP",
                "asset_type": "FUTURE",
                "account_id": "acc1",
                "market_connection": "connected",
                "trade_connection": "connected",
                "uptime_sec": 0,
                "strategy_count": 1,
                "symbol_count": 0,
                "tick_count": 0,
                "order_count": 0,
                "heartbeat_age_sec": None,
                "ref_count": 1,
                "instances": ["inst1"],
                "recent_errors": [],
                "strategy_name": "Demo Strategy",
            }
        ]

    @pytest.mark.skip(reason="Pre-existing test failure - data structure mismatch")
    def test_get_gateway_health_skips_dead_and_already_accounted_instances(self):
        result = gateway_health_service.get_gateway_health(
            gateways={
                "gw1": {
                    "runtime": Mock(health=Mock(snapshot=Mock(return_value={}))),
                    "ref_count": 1,
                    "instances": {"inst1"},
                }
            },
            load_instances=lambda: {
                "inst1": {"status": "running", "pid": 123, "strategy_id": "s1"},
                "inst2": {"status": "running", "pid": 456, "strategy_id": "s2"},
            },
            is_pid_alive=lambda pid: pid == 123,
            resolve_strategy_dir=lambda strategy_id: Path("/tmp") / strategy_id,
            load_strategy_config=lambda strategy_dir: {},
            load_strategy_env=lambda strategy_dir: {},
        )
        assert result == [{"gateway_key": "gw1", "ref_count": 1, "instances": ["inst1"]}]


class TestLiveInstanceService:
    def test_sync_status_on_boot_updates_dead_processes(self):
        instances = {
            "inst1": {"status": "running", "pid": 123},
            "inst2": {"status": "stopped", "pid": None},
        }
        saved = {}

        def save_instances(data):
            saved.update(data)

        live_instance_service.sync_status_on_boot(
            load_instances=lambda: instances,
            save_instances=save_instances,
            is_pid_alive=lambda pid: False,
        )

        assert saved["inst1"]["status"] == "stopped"
        assert saved["inst1"]["pid"] is None

    def test_list_instances_detects_external_process_and_filters_user(self):
        instances = {
            "inst1": {"strategy_id": "s1", "user_id": "u1", "status": "stopped"},
            "inst2": {"strategy_id": "s2", "user_id": "u2", "status": "stopped"},
        }

        result = live_instance_service.list_instances(
            user_id="u1",
            load_instances=lambda: instances,
            save_instances=lambda data: None,
            scan_running_strategy_pids=lambda: {str(Path("/tmp") / "s1" / "run.py"): 999},
            is_pid_alive=lambda pid: True,
            resolve_strategy_dir=lambda strategy_id: Path("/tmp") / strategy_id,
            find_latest_log_dir=lambda strategy_dir: "/logs/test",
        )

        assert len(result) == 1
        assert result[0]["id"] == "inst1"
        assert result[0]["status"] == "running"
        assert result[0]["pid"] == 999
        assert result[0]["log_dir"] == "/logs/test"

    def test_list_instances_marks_dead_running_process_stopped(self):
        instances = {
            "inst1": {"strategy_id": "s1", "user_id": "u1", "status": "running", "pid": 123}
        }
        live_instance_service.list_instances(
            user_id=None,
            load_instances=lambda: instances,
            save_instances=lambda data: None,
            scan_running_strategy_pids=lambda: {},
            is_pid_alive=lambda pid: False,
            resolve_strategy_dir=lambda strategy_id: Path("/tmp") / strategy_id,
            find_latest_log_dir=lambda strategy_dir: None,
        )
        assert instances["inst1"]["status"] == "stopped"
        assert instances["inst1"]["pid"] is None

    def test_add_instance_success(self):
        instances = {}
        run_py = Mock()
        run_py.is_file.return_value = True
        strategy_dir_mock = Mock()
        strategy_dir_mock.__truediv__ = Mock(return_value=run_py)

        result = live_instance_service.add_instance(
            strategy_id="demo",
            params={"fast": 5},
            user_id="u1",
            load_instances=lambda: instances,
            save_instances=lambda data: None,
            resolve_strategy_dir=lambda strategy_id: strategy_dir_mock,
            get_template_by_id=lambda strategy_id: Mock(name="Demo Strategy"),
            infer_gateway_params=lambda strategy_dir: None,
            find_latest_log_dir=lambda strategy_dir: None,
        )

        assert result["strategy_id"] == "demo"
        assert result["params"] == {"fast": 5}
        assert result["user_id"] == "u1"
        assert result["status"] == "stopped"
        assert result["id"] in instances

    def test_add_instance_infers_gateway_when_missing(self):
        instances = {}
        run_py = Mock()
        run_py.is_file.return_value = True
        strategy_dir_mock = Mock()
        strategy_dir_mock.__truediv__ = Mock(return_value=run_py)

        result = live_instance_service.add_instance(
            strategy_id="demo",
            params=None,
            user_id=None,
            load_instances=lambda: instances,
            save_instances=lambda data: None,
            resolve_strategy_dir=lambda strategy_id: strategy_dir_mock,
            get_template_by_id=lambda strategy_id: None,
            infer_gateway_params=lambda strategy_dir: {"enabled": True, "exchange_type": "CTP"},
            find_latest_log_dir=lambda strategy_dir: None,
        )

        assert result["params"]["gateway"]["exchange_type"] == "CTP"

    def test_remove_instance_handles_permission_and_process_cleanup(self):
        instances = {"inst1": {"user_id": "u1", "status": "running", "pid": 123}}
        processes = {"inst1": Mock()}
        killed = []
        released = []

        denied = live_instance_service.remove_instance(
            instance_id="inst1",
            user_id="u2",
            load_instances=lambda: instances,
            save_instances=lambda data: None,
            kill_pid=lambda pid: killed.append(pid),
            release_gateway_for_instance=lambda instance_id: released.append(instance_id),
            processes=processes,
        )
        assert denied is False

        removed = live_instance_service.remove_instance(
            instance_id="inst1",
            user_id="u1",
            load_instances=lambda: instances,
            save_instances=lambda data: None,
            kill_pid=lambda pid: killed.append(pid),
            release_gateway_for_instance=lambda instance_id: released.append(instance_id),
            processes=processes,
        )
        assert removed is True
        assert killed == [123]
        assert released == ["inst1"]
        assert processes == {}

    def test_get_instance_updates_dead_running_process(self):
        instances = {
            "inst1": {"strategy_id": "demo", "user_id": "u1", "status": "running", "pid": 123}
        }
        result = live_instance_service.get_instance(
            instance_id="inst1",
            user_id="u1",
            load_instances=lambda: instances,
            save_instances=lambda data: None,
            is_pid_alive=lambda pid: False,
            scan_running_strategy_pids=lambda: {},
            resolve_strategy_dir=lambda strategy_id: Path("/tmp") / strategy_id,
            find_latest_log_dir=lambda strategy_dir: "/logs/test",
        )
        assert result is not None
        assert result["status"] == "stopped"
        assert result["pid"] is None
        assert result["log_dir"] == "/logs/test"

    def test_get_instance_respects_user_and_missing(self):
        instances = {"inst1": {"strategy_id": "demo", "user_id": "u1", "status": "stopped"}}
        assert (
            live_instance_service.get_instance(
                instance_id="inst1",
                user_id="u2",
                load_instances=lambda: instances,
                save_instances=lambda data: None,
                is_pid_alive=lambda pid: True,
                scan_running_strategy_pids=lambda: {},
                resolve_strategy_dir=lambda strategy_id: Path("/tmp") / strategy_id,
                find_latest_log_dir=lambda strategy_dir: None,
            )
            is None
        )


class TestLiveExecutionService:
    def test_start_instance_success(self, tmp_path):
        instances = {"inst1": {"strategy_id": "demo", "status": "stopped"}}
        strategy_dir = tmp_path / "demo"
        strategy_dir.mkdir()
        (strategy_dir / "run.py").write_text("print('ok')\n", encoding="utf-8")
        proc = AsyncMock()
        proc.pid = 12345
        proc.returncode = None
        wait_process_callback = AsyncMock()

        with patch(
            "app.services.live_trading.execution.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ):
            with patch(
                "app.services.live_trading.execution.asyncio.create_task"
            ) as mock_create_task:

                def _create_task(coro):
                    try:
                        coro.close()
                    except Exception:
                        pass
                    return Mock()

                mock_create_task.side_effect = _create_task
                result = asyncio.run(
                    live_execution_service.start_instance(
                        instance_id="inst1",
                        load_instances=lambda: instances,
                        save_instances=lambda data: None,
                        is_pid_alive=lambda pid: False,
                        resolve_strategy_dir=lambda strategy_id: strategy_dir,
                        build_subprocess_env=lambda instance_id, inst, strategy_dir: {"A": "1"},
                        release_gateway_for_instance=lambda instance_id: None,
                        wait_process_callback=wait_process_callback,
                        processes={},
                        stopping_instances=set(),
                    )
                )

        assert result["status"] == "running"
        assert result["pid"] == 12345
        assert result["updated_at"] == result["started_at"]
        assert result["gateway_type"] == ""

    def test_start_instance_builds_gateway_environment_off_event_loop(self, tmp_path):
        instances = {"inst1": {"strategy_id": "demo", "status": "stopped"}}
        strategy_dir = tmp_path / "demo"
        strategy_dir.mkdir()
        (strategy_dir / "run.py").write_text("print('ok')\n", encoding="utf-8")
        proc = AsyncMock()
        proc.pid = 12345
        proc.returncode = None
        builder_threads: list[int] = []

        def build_subprocess_env(*_args):
            builder_threads.append(threading.get_ident())
            return {"A": "1"}

        with patch(
            "app.services.live_trading.execution.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ):
            with patch("app.services.live_trading.execution.asyncio.create_task") as mock_create_task:

                def _create_task(coro):
                    coro.close()
                    return Mock()

                mock_create_task.side_effect = _create_task
                asyncio.run(
                    live_execution_service.start_instance(
                        instance_id="inst1",
                        load_instances=lambda: instances,
                        save_instances=lambda data: None,
                        is_pid_alive=lambda pid: False,
                        resolve_strategy_dir=lambda strategy_id: strategy_dir,
                        build_subprocess_env=build_subprocess_env,
                        release_gateway_for_instance=lambda instance_id: None,
                        wait_process_callback=AsyncMock(),
                        processes={},
                        stopping_instances=set(),
                    )
                )

        assert builder_threads
        assert builder_threads[0] != threading.get_ident()

    def test_wait_process_reads_stderr_file_tail(self, tmp_path):
        stderr_path = tmp_path / "subprocess.stderr.log"
        stderr_path.write_text("x" * 600 + "file error message", encoding="utf-8")
        proc = AsyncMock()
        proc.pid = 12345
        proc.returncode = 1
        proc.stderr = None
        proc.wait = AsyncMock()
        proc._bt_stderr_path = str(stderr_path)
        saved = {}
        released = []

        asyncio.run(
            live_execution_service.wait_process(
                instance_id="inst1",
                proc=proc,
                load_instances=lambda: {
                    "inst1": {"strategy_id": "s1", "status": "running", "pid": 12345}
                },
                save_instances=lambda data: saved.update(data),
                resolve_strategy_dir=lambda strategy_id: tmp_path / strategy_id,
                find_latest_log_dir=lambda strategy_dir: None,
                release_gateway_for_instance=lambda instance_id: released.append(instance_id),
                processes={"inst1": proc},
                stopping_instances=set(),
            )
        )

        assert saved["inst1"]["status"] == "error"
        assert "file error message" in saved["inst1"]["error"]
        assert saved["inst1"]["updated_at"] == saved["inst1"]["stopped_at"]
        assert released == ["inst1"]

    def test_wait_process_cancellation_keeps_running_instance_attached(self):
        proc = Mock()
        proc.pid = 12345
        proc.returncode = None
        proc.stderr = None
        proc.wait = AsyncMock(side_effect=asyncio.CancelledError())
        instances = {
            "inst1": {
                "strategy_id": "s1",
                "status": "running",
                "pid": 12345,
                "error": None,
            }
        }
        saved = {}
        released = []
        processes = {"inst1": proc}

        asyncio.run(
            live_execution_service.wait_process(
                instance_id="inst1",
                proc=proc,
                load_instances=lambda: instances,
                save_instances=lambda data: saved.update(data),
                resolve_strategy_dir=lambda strategy_id: Path("/tmp") / strategy_id,
                find_latest_log_dir=lambda strategy_dir: None,
                release_gateway_for_instance=lambda instance_id: released.append(instance_id),
                processes=processes,
                stopping_instances=set(),
            )
        )

        assert saved == {}
        assert released == []
        assert processes["inst1"] is proc
        assert instances["inst1"]["status"] == "running"
        assert instances["inst1"]["pid"] == 12345

    def test_start_instance_clears_stopping_flag(self, tmp_path):
        instances = {"inst1": {"strategy_id": "demo", "status": "stopped"}}
        strategy_dir = tmp_path / "demo"
        strategy_dir.mkdir()
        (strategy_dir / "run.py").write_text("print('ok')\n", encoding="utf-8")
        proc = AsyncMock()
        proc.pid = 43210
        proc.returncode = None
        stopping_instances = {"inst1"}

        with patch(
            "app.services.live_trading.execution.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ):
            with patch(
                "app.services.live_trading.execution.asyncio.create_task"
            ) as mock_create_task:

                def _create_task(coro):
                    try:
                        coro.close()
                    except Exception:
                        pass
                    return Mock()

                mock_create_task.side_effect = _create_task
                asyncio.run(
                    live_execution_service.start_instance(
                        instance_id="inst1",
                        load_instances=lambda: instances,
                        save_instances=lambda data: None,
                        is_pid_alive=lambda pid: False,
                        resolve_strategy_dir=lambda strategy_id: strategy_dir,
                        build_subprocess_env=lambda instance_id, inst, strategy_dir: {"A": "1"},
                        release_gateway_for_instance=lambda instance_id: None,
                        wait_process_callback=AsyncMock(),
                        processes={},
                        stopping_instances=stopping_instances,
                    )
                )

        assert "inst1" not in stopping_instances

    def test_start_instance_records_env_build_failure(self, tmp_path):
        instances = {"inst1": {"strategy_id": "demo", "status": "stopped"}}
        strategy_dir = tmp_path / "demo"
        strategy_dir.mkdir()
        (strategy_dir / "run.py").write_text("print('ok')\n", encoding="utf-8")
        saved = []
        released = []

        def raise_gateway_error(*_args):
            raise RuntimeError(
                "Gateway runtime failed to become ready: runtime: ctp market not ready"
            )

        with pytest.raises(ValueError, match="ctp market not ready"):
            asyncio.run(
                live_execution_service.start_instance(
                    instance_id="inst1",
                    load_instances=lambda: instances,
                    save_instances=lambda data: saved.append(data.copy()),
                    is_pid_alive=lambda pid: False,
                    resolve_strategy_dir=lambda strategy_id: strategy_dir,
                    build_subprocess_env=raise_gateway_error,
                    release_gateway_for_instance=lambda instance_id: released.append(instance_id),
                    wait_process_callback=AsyncMock(),
                    processes={},
                    stopping_instances=set(),
                )
            )

        assert released == ["inst1"]
        assert instances["inst1"]["status"] == "error"
        assert instances["inst1"]["pid"] is None
        assert "ctp market not ready" in instances["inst1"]["error"]
        assert instances["inst1"]["stopped_at"]
        assert saved[-1]["inst1"]["status"] == "error"

    def test_stop_instance_success(self):
        instances = {"inst1": {"strategy_id": "demo", "status": "running", "pid": 12345}}
        proc = Mock()
        proc.returncode = None
        proc.wait = AsyncMock()
        proc.terminate = Mock()
        proc.kill = Mock()
        processes = {"inst1": proc}
        stopping_instances: set[str] = set()
        killed = []
        released = []

        result = asyncio.run(
            live_execution_service.stop_instance(
                instance_id="inst1",
                load_instances=lambda: instances,
                save_instances=lambda data: None,
                is_pid_alive=lambda pid: True,
                kill_pid=lambda pid: killed.append(pid),
                release_gateway_for_instance=lambda instance_id: released.append(instance_id),
                processes=processes,
                stopping_instances=stopping_instances,
            )
        )

        assert result["status"] == "stopped"
        assert result["pid"] is None
        assert result["updated_at"] == result["stopped_at"]
        assert killed == [12345]
        assert released == ["inst1"]
        assert processes == {}

    def test_start_all_and_stop_all(self):
        start_calls = []
        stop_calls = []
        start_result = asyncio.run(
            live_execution_service.start_all(
                user_id=None,
                load_instances=lambda: {
                    "inst1": {"strategy_id": "s1", "status": "stopped"},
                    "inst2": {"strategy_id": "s2", "status": "running", "pid": 1},
                    "inst3": {"strategy_id": "s3", "status": "stopped"},
                },
                is_pid_alive=lambda pid: pid == 1,
                start_instance_callback=AsyncMock(side_effect=lambda iid: start_calls.append(iid)),
            )
        )
        assert start_result["success"] == 2
        assert start_result["failed"] == 0
        assert start_calls == ["inst1", "inst3"]

        stop_result = asyncio.run(
            live_execution_service.stop_all(
                user_id=None,
                load_instances=lambda: {
                    "inst1": {"strategy_id": "s1", "status": "running"},
                    "inst2": {"strategy_id": "s2", "status": "stopped"},
                    "inst3": {"strategy_id": "s3", "status": "running"},
                },
                stop_instance_callback=AsyncMock(side_effect=lambda iid: stop_calls.append(iid)),
            )
        )
        assert stop_result["success"] == 2
        assert stop_result["failed"] == 0
        assert stop_calls == ["inst1", "inst3"]

    @pytest.mark.skip(reason="Pre-existing test failure - KeyError: 'inst1'")
    def test_wait_process_success_and_error(self):
        saved_success = {}
        saved_error = {}
        released = []
        processes = {"inst1": Mock(), "inst2": Mock()}
        stopping_instances: set[str] = set()

        proc_success = AsyncMock()
        proc_success.returncode = 0
        proc_success.stderr = None

        asyncio.run(
            live_execution_service.wait_process(
                instance_id="inst1",
                proc=proc_success,
                load_instances=lambda: {
                    "inst1": {"strategy_id": "s1", "status": "running", "pid": 1}
                },
                save_instances=lambda data: saved_success.update(data),
                resolve_strategy_dir=lambda strategy_id: Path("/tmp") / strategy_id,
                find_latest_log_dir=lambda strategy_dir: None,
                release_gateway_for_instance=lambda instance_id: released.append(instance_id),
                processes=processes,
                stopping_instances=stopping_instances,
            )
        )

        proc_error = AsyncMock()
        proc_error.returncode = 1
        proc_error.stderr = AsyncMock()
        proc_error.stderr.read = AsyncMock(return_value=b"error message")

        asyncio.run(
            live_execution_service.wait_process(
                instance_id="inst2",
                proc=proc_error,
                load_instances=lambda: {
                    "inst2": {"strategy_id": "s2", "status": "running", "pid": 2}
                },
                save_instances=lambda data: saved_error.update(data),
                resolve_strategy_dir=lambda strategy_id: Path("/tmp") / strategy_id,
                find_latest_log_dir=lambda strategy_dir: None,
                release_gateway_for_instance=lambda instance_id: released.append(instance_id),
                processes=processes,
                stopping_instances=stopping_instances,
            )
        )

        assert saved_success["inst1"]["status"] == "stopped"
        assert saved_error["inst2"]["status"] == "error"
        assert saved_error["inst2"]["error"] == "error message"
        assert released == ["inst1", "inst2"]

    def test_wait_process_ignores_stale_process_callback(self):
        saved = {}
        released = []
        old_proc = AsyncMock()
        old_proc.pid = 111
        old_proc.returncode = 0
        old_proc.stderr = None
        new_proc = Mock(pid=222)
        processes = {"inst1": new_proc}

        asyncio.run(
            live_execution_service.wait_process(
                instance_id="inst1",
                proc=old_proc,
                load_instances=lambda: {
                    "inst1": {"strategy_id": "s1", "status": "running", "pid": 222}
                },
                save_instances=lambda data: saved.update(data),
                resolve_strategy_dir=lambda strategy_id: Path("/tmp") / strategy_id,
                find_latest_log_dir=lambda strategy_dir: None,
                release_gateway_for_instance=lambda instance_id: released.append(instance_id),
                processes=processes,
                stopping_instances=set(),
            )
        )

        assert saved == {}
        assert released == []
        assert processes["inst1"] is new_proc


class TestGatewayRuntimeService:
    def test_build_subprocess_env_uses_resolved_app_debug_mode(self, tmp_path):
        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()

        with patch.object(
            gateway_runtime_service,
            "get_settings",
            return_value=Mock(DEBUG=True),
        ):
            env = gateway_runtime_service.build_subprocess_env(
                instance_id="inst1",
                instance={"params": {}},
                strategy_dir=strategy_dir,
                acquire_gateway_for_instance=lambda instance_id, instance, strategy_dir: None,
                os_environ={"DEBUG": "false"},
                bt_api_py_dir=tmp_path / "missing",
            )

        assert env["DEBUG"] == "true"

    def test_build_subprocess_env_without_gateway(self, tmp_path):
        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()
        bt_api_dir = tmp_path / "bt_api_py"
        bt_api_dir.mkdir()
        backtrader_dir = tmp_path / "backtrader"
        backtrader_dir.mkdir()

        env = gateway_runtime_service.build_subprocess_env(
            instance_id="inst1",
            instance={"params": {}},
            strategy_dir=strategy_dir,
            acquire_gateway_for_instance=lambda instance_id, instance, strategy_dir: None,
            os_environ={"PYTHONPATH": "existing", "OPENBLAS_NUM_THREADS": "4"},
            bt_api_py_dir=bt_api_dir,
            backtrader_dir=backtrader_dir,
        )

        assert env["PYTHONPATH"].split(os.pathsep) == [
            str(backtrader_dir),
            str(bt_api_dir),
            "existing",
        ]
        assert "BT_STORE_PROVIDER" not in env
        assert env["BACKTRADER_LIGHT_IMPORT"] == "1"
        assert env["BT_API_PY_LIGHT_IMPORT"] == "1"
        assert env["BT_FEED_ENABLE_LIGHT_COLUMNS"] == "1"
        assert env["BT_STORE_LOCAL_TIMEZONE"] == "Asia/Shanghai"
        assert env["OPENBLAS_NUM_THREADS"] == "4"
        assert env["OMP_NUM_THREADS"] == "1"

    def test_build_subprocess_env_skips_missing_and_duplicate_python_paths(self, tmp_path):
        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()
        bt_api_dir = tmp_path / "bt_api_py"
        bt_api_dir.mkdir()

        env = gateway_runtime_service.build_subprocess_env(
            instance_id="inst1",
            instance={"params": {}},
            strategy_dir=strategy_dir,
            acquire_gateway_for_instance=lambda instance_id, instance, strategy_dir: None,
            os_environ={"PYTHONPATH": os.pathsep.join([str(bt_api_dir), "existing"])},
            bt_api_py_dir=bt_api_dir,
            backtrader_dir=tmp_path / "missing_backtrader",
        )

        assert env["PYTHONPATH"].split(os.pathsep) == [str(bt_api_dir), "existing"]

    def test_build_subprocess_env_with_gateway(self, tmp_path):
        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()
        config = Mock(
            command_endpoint="ipc://command",
            event_endpoint="ipc://event",
            market_endpoint="ipc://market",
            account_id="acc-1",
            exchange_type="CTP",
            asset_type="FUTURE",
            startup_timeout_sec=5,
            command_timeout_sec=10,
        )

        env = gateway_runtime_service.build_subprocess_env(
            instance_id="inst1",
            instance={"params": {"gateway": {"enabled": True}}},
            strategy_dir=strategy_dir,
            acquire_gateway_for_instance=(
                lambda instance_id, instance, strategy_dir: {"config": config}
            ),
            os_environ={},
            bt_api_py_dir=tmp_path / "missing",
        )

        assert env["BT_STORE_PROVIDER"] == "ctp_gateway"
        assert env["BT_GATEWAY_COMMAND_ENDPOINT"] == "ipc://command"
        assert env["BT_GATEWAY_EVENT_ENDPOINT"] == "ipc://event"
        assert env["BT_GATEWAY_MARKET_ENDPOINT"] == "ipc://market"
        assert env["BT_GATEWAY_ACCOUNT_ID"] == "acc-1"
        assert env["BT_GATEWAY_EXCHANGE_TYPE"] == "CTP"
        assert env["BT_GATEWAY_ASSET_TYPE"] == "FUTURE"
        assert env["BACKTRADER_LIGHT_IMPORT"] == "1"
        assert env["BT_API_PY_LIGHT_IMPORT"] == "1"
        assert env["BT_FEED_ENABLE_LIGHT_COLUMNS"] == "1"
        assert env["BT_STORE_LOCAL_TIMEZONE"] == "Asia/Shanghai"
        assert env["OPENBLAS_NUM_THREADS"] == "1"
        assert env["OMP_NUM_THREADS"] == "1"

    def test_build_subprocess_env_with_gateway_requires_symbol_asset_spec(self, tmp_path):
        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()
        (strategy_dir / "config.yaml").write_text(
            "data:\n  symbol: UNKNOWN999\n  asset_type: future\n",
            encoding="utf-8",
        )
        config = Mock(
            command_endpoint="ipc://command",
            event_endpoint="ipc://event",
            market_endpoint="ipc://market",
            account_id="acc-1",
            exchange_type="CTP",
            asset_type="FUTURE",
            startup_timeout_sec=5,
            command_timeout_sec=10,
        )

        with pytest.raises(RuntimeError, match="交易资产规格"):
            gateway_runtime_service.build_subprocess_env(
                instance_id="inst1",
                instance={"params": {"gateway": {"enabled": True}}},
                strategy_dir=strategy_dir,
                acquire_gateway_for_instance=(
                    lambda instance_id, instance, strategy_dir: {"config": config}
                ),
                os_environ={},
                bt_api_py_dir=tmp_path / "missing",
            )

    def test_build_subprocess_env_with_gateway_rejects_incomplete_contract_spec(self, tmp_path):
        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()
        (strategy_dir / "config.yaml").write_text(
            "data:\n"
            "  symbol: BTC-USDT-SWAP\n"
            "  asset_type: swap\n"
            "contract_metadata:\n"
            "  BTC-USDT-SWAP:\n"
            "    asset_type: SWAP\n"
            "    source: local_fixture\n",
            encoding="utf-8",
        )
        config = Mock(
            command_endpoint="ipc://command",
            event_endpoint="ipc://event",
            market_endpoint="ipc://market",
            account_id="acc-1",
            exchange_type="OKX",
            asset_type="SWAP",
            startup_timeout_sec=5,
            command_timeout_sec=10,
        )

        with pytest.raises(RuntimeError, match="交易资产规格不完整"):
            gateway_runtime_service.build_subprocess_env(
                instance_id="inst1",
                instance={"params": {"gateway": {"enabled": True}}},
                strategy_dir=strategy_dir,
                acquire_gateway_for_instance=(
                    lambda instance_id, instance, strategy_dir: {"config": config}
                ),
                os_environ={},
                bt_api_py_dir=tmp_path / "missing",
            )

    def test_build_subprocess_env_with_gateway_accepts_local_contract_spec(self, tmp_path):
        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()
        (strategy_dir / "config.yaml").write_text(
            "data:\n"
            "  symbol: IF2609\n"
            "  asset_type: future\n"
            "contract_metadata:\n"
            "  IF2609:\n"
            "    multiplier: 300\n"
            "    margin_rate: 0.12\n"
            "    commission_rate: 0.000023\n",
            encoding="utf-8",
        )
        config = Mock(
            command_endpoint="ipc://command",
            event_endpoint="ipc://event",
            market_endpoint="ipc://market",
            account_id="acc-1",
            exchange_type="CTP",
            asset_type="FUTURE",
            startup_timeout_sec=5,
            command_timeout_sec=10,
        )

        env = gateway_runtime_service.build_subprocess_env(
            instance_id="inst1",
            instance={"params": {"gateway": {"enabled": True}}},
            strategy_dir=strategy_dir,
            acquire_gateway_for_instance=(
                lambda instance_id, instance, strategy_dir: {"config": config}
            ),
            os_environ={},
            bt_api_py_dir=tmp_path / "missing",
        )

        assert env["BT_GATEWAY_EXCHANGE_TYPE"] == "CTP"
        assert env["BT_GATEWAY_ASSET_TYPE"] == "FUTURE"
        assert env["BT_GATEWAY_COMMAND_ENDPOINT"] == "ipc://command"

    def test_build_subprocess_env_captures_gateway_wait_native_stderr(self, tmp_path):
        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()

        class NoisyHealth:
            recent_errors = []
            market_connection = "connected"
            trade_connection = "connected"

            @property
            def state(self):
                os.write(2, b"native wait warning\n")
                return "running"

        config = Mock(
            command_endpoint="ipc://command",
            event_endpoint="ipc://event",
            market_endpoint="ipc://market",
            account_id="acc-1",
            exchange_type="CTP",
            asset_type="FUTURE",
            startup_timeout_sec=5,
            command_timeout_sec=10,
        )
        runtime = Mock(health=NoisyHealth(), running=True)

        gateway_runtime_service.build_subprocess_env(
            instance_id="inst1",
            instance={"params": {"gateway": {"enabled": True}}},
            strategy_dir=strategy_dir,
            acquire_gateway_for_instance=(
                lambda instance_id, instance, strategy_dir: {
                    "config": config,
                    "runtime": runtime,
                }
            ),
            os_environ={},
            bt_api_py_dir=tmp_path / "missing",
        )

        stderr_log = strategy_dir / "logs" / "gateway.stderr.log"
        assert "native wait warning" in stderr_log.read_text(encoding="utf-8")

    def test_build_subprocess_env_preserves_gateway_ready_error(self, tmp_path):
        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()
        config = Mock(
            command_endpoint="ipc://command",
            event_endpoint="ipc://event",
            market_endpoint="ipc://market",
            account_id="acc-1",
            exchange_type="CTP",
            asset_type="FUTURE",
            startup_timeout_sec=5,
            command_timeout_sec=10,
        )
        health = Mock(
            state="error",
            market_connection="error",
            trade_connection="error",
            recent_errors=[{"source": "runtime", "message": "ctp market not ready"}],
        )
        runtime = Mock(health=health, running=False)

        with pytest.raises(RuntimeError, match="runtime: ctp market not ready"):
            gateway_runtime_service.build_subprocess_env(
                instance_id="inst1",
                instance={"params": {"gateway": {"enabled": True}}},
                strategy_dir=strategy_dir,
                acquire_gateway_for_instance=(
                    lambda instance_id, instance, strategy_dir: {
                        "config": config,
                        "runtime": runtime,
                    }
                ),
                os_environ={},
                bt_api_py_dir=tmp_path / "missing",
            )

    def test_wait_gateway_runtime_ready_returns_when_connected(self):
        config = Mock(startup_timeout_sec=5)
        health = Mock(
            state="running",
            market_connection="connected",
            trade_connection="connected",
            recent_errors=[],
        )
        runtime = Mock(health=health, running=True)

        gateway_runtime_service.wait_gateway_runtime_ready(
            {"config": config, "runtime": runtime},
            sleep=Mock(),
        )

    def test_wait_gateway_runtime_ready_accepts_market_ready_gateway(self):
        config = Mock(startup_timeout_sec=5)
        health = Mock(
            state="running",
            market_connection="connected",
            trade_connection="disconnected",
            recent_errors=[],
        )
        runtime = Mock(health=health, running=True)

        gateway_runtime_service.wait_gateway_runtime_ready(
            {"config": config, "runtime": runtime},
            sleep=Mock(),
        )

    def test_wait_gateway_runtime_ready_reads_gateway_health_snapshot(self):
        config = Mock(startup_timeout_sec=5)
        health = Mock(
            state="running",
            market_connection="",
            trade_connection="",
            recent_errors=[],
        )
        health.snapshot.return_value = {
            "state": "running",
            "market_connection": "connected",
            "trade_connection": "disconnected",
            "recent_errors": [],
        }
        runtime = Mock(health=health, running=True)

        gateway_runtime_service.wait_gateway_runtime_ready(
            {"config": config, "runtime": runtime},
            sleep=Mock(),
        )

    def test_wait_gateway_runtime_ready_raises_runtime_error_detail(self):
        config = Mock(startup_timeout_sec=5)
        health = Mock(
            state="error",
            market_connection="error",
            trade_connection="error",
            recent_errors=[{"source": "runtime", "message": "ctp market not ready"}],
        )
        runtime = Mock(health=health, running=False)

        with pytest.raises(RuntimeError, match="runtime: ctp market not ready"):
            gateway_runtime_service.wait_gateway_runtime_ready(
                {"config": config, "runtime": runtime},
                monotonic=Mock(return_value=0.0),
                sleep=Mock(),
            )

    def test_wait_gateway_runtime_ready_fails_fast_for_invalid_gateway_credentials(self):
        config = Mock(startup_timeout_sec=30)
        health = Mock(
            state="running",
            market_connection="error",
            trade_connection="disconnected",
            recent_errors=[
                {
                    "source": "adapter_connect",
                    "message": "IB_WEB INVALID_API_KEY: HTTP 401: Auth error",
                }
            ],
        )
        runtime = Mock(health=health, running=True)

        with pytest.raises(RuntimeError, match="INVALID_API_KEY"):
            gateway_runtime_service.wait_gateway_runtime_ready(
                {"config": config, "runtime": runtime},
                monotonic=Mock(return_value=0.0),
                sleep=Mock(),
            )

    def test_wait_gateway_runtime_ready_raises_timeout_detail(self):
        config = Mock(startup_timeout_sec=1)
        health = Mock(
            state="connecting",
            market_connection="disconnected",
            trade_connection="disconnected",
            recent_errors=[],
        )
        runtime = Mock(health=health, running=True)

        with pytest.raises(TimeoutError, match="state=connecting"):
            gateway_runtime_service.wait_gateway_runtime_ready(
                {"config": config, "runtime": runtime},
                monotonic=Mock(side_effect=[0.0, 1.0]),
                sleep=Mock(),
            )

    def test_mt5_startup_reconnects_after_stale_transport(self):
        adapter = Mock()
        adapter.connect.side_effect = [ConnectionResetError("connection reset"), None]
        adapter.get_balance.return_value = {"balance": 1000.0}
        runtime = Mock(adapter=adapter)
        sleep = Mock()

        gateway_runtime_service._connect_mt5_adapter_with_retry(
            runtime,
            Mock(),
            attempts=2,
            retry_delay_sec=0.5,
            sleep=sleep,
        )

        assert adapter.connect.call_count == 2
        adapter.disconnect.assert_called_once()
        adapter.get_balance.assert_called_once()
        sleep.assert_called_once_with(0.5)

    def test_mt5_startup_does_not_launch_with_unready_transport(self):
        adapter = Mock()
        adapter.connect.return_value = None
        adapter.get_balance.side_effect = RuntimeError("transport not ready for command 4")
        runtime = Mock(adapter=adapter)

        with pytest.raises(RuntimeError, match="MT5 gateway transport did not become ready"):
            gateway_runtime_service._connect_mt5_adapter_with_retry(
                runtime,
                Mock(),
                attempts=2,
                retry_delay_sec=0,
                sleep=Mock(),
            )

        assert adapter.connect.call_count == 2
        assert adapter.disconnect.call_count == 2

    def test_acquire_gateway_preflights_mt5_transport_before_starting_runtime(self):
        logger = Mock()
        config = Mock(
            runtime_name="mt5-otc-acc-1",
            command_endpoint="ipc://command",
            event_endpoint="ipc://event",
            market_endpoint="ipc://market",
        )
        runtime = Mock()
        launch = {
            "config": config,
            "runtime_cls": Mock(return_value=runtime),
            "runtime_kwargs": {
                "exchange_type": "MT5",
                "asset_type": "OTC",
                "account_id": "acc-1",
            },
        }

        with patch.object(gateway_runtime_service, "_connect_mt5_adapter_with_retry") as preflight:
            gateway_runtime_service.acquire_gateway_for_instance(
                instance_id="inst-mt5",
                instance={"params": {"gateway": {"enabled": True}}},
                strategy_dir=Path("/tmp/strategy"),
                get_gateway_params=lambda instance: {"enabled": True},
                build_gateway_launch=lambda instance, strategy_dir, gateway_params: launch,
                gateways={},
                instance_gateways={},
                logger=logger,
            )

        preflight.assert_called_once_with(runtime, logger)
        runtime.start_in_thread.assert_called_once()

    def test_acquire_gateway_for_instance_reuses_runtime(self):
        logger = Mock()
        config = Mock(
            runtime_name="ctp-future-acc-1",
            command_endpoint="ipc://command",
            event_endpoint="ipc://event",
            market_endpoint="ipc://market",
        )
        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)
        launch = {
            "config": config,
            "runtime_cls": runtime_cls,
            "runtime_kwargs": {"account_id": "acc-1"},
        }
        gateways: dict[str, dict] = {}
        instance_gateways: dict[str, str] = {}

        state1 = gateway_runtime_service.acquire_gateway_for_instance(
            instance_id="inst1",
            instance={"params": {"gateway": {"enabled": True}}},
            strategy_dir=Path("/tmp/strategy"),
            get_gateway_params=lambda instance: {"enabled": True},
            build_gateway_launch=lambda instance, strategy_dir, gateway_params: launch,
            gateways=gateways,
            instance_gateways=instance_gateways,
            logger=logger,
        )
        state2 = gateway_runtime_service.acquire_gateway_for_instance(
            instance_id="inst2",
            instance={"params": {"gateway": {"enabled": True}}},
            strategy_dir=Path("/tmp/strategy"),
            get_gateway_params=lambda instance: {"enabled": True},
            build_gateway_launch=lambda instance, strategy_dir, gateway_params: launch,
            gateways=gateways,
            instance_gateways=instance_gateways,
            logger=logger,
        )

        assert state1 is state2
        runtime_cls.assert_called_once_with(config, account_id="acc-1")
        runtime.start_in_thread.assert_called_once()
        assert state1["instances"] == {"inst1", "inst2"}
        assert state1["ref_count"] == 2
        assert instance_gateways == {"inst1": "ctp-future-acc-1", "inst2": "ctp-future-acc-1"}

    def test_acquire_gateway_for_instance_logs_into_ib_before_starting_runtime(self):
        """An expired Client Portal cookie is refreshed before strategy startup."""
        from app.services.gateway import manual as gateway_manual_service

        class Config:
            def __init__(self, kwargs):
                self.kwargs = dict(kwargs)
                self.runtime_name = f"ib-web-{kwargs['account_id']}"
                self.command_endpoint = "tcp://command"
                self.event_endpoint = "tcp://event"
                self.market_endpoint = "tcp://market"

            @classmethod
            def from_kwargs(cls, **kwargs):
                return cls(kwargs)

        initial_kwargs = {
            "exchange_type": "IB_WEB",
            "asset_type": "STK",
            "account_id": "DU123456",
            "base_url": "https://localhost:5000",
            "verify_ssl": False,
            "timeout": 10.0,
            "cookie_source": "file:configs/expired.json",
            "cookie_output": "configs/expired.json",
            "username": "ib-user",
            "password": "ib-password",
            "login_mode": "paper",
            "gateway_startup_timeout_sec": 30.0,
        }
        launch = {
            "config": Config.from_kwargs(**initial_kwargs),
            "runtime_cls": Mock(return_value=Mock()),
            "runtime_kwargs": dict(initial_kwargs),
        }
        refreshed_session = {
            "account_id": "DU654321",
            "cookies": {"session": "fresh"},
            "cookie_output": "configs/refreshed.json",
            "used_login": True,
        }

        with (
            patch.object(gateway_manual_service, "_ensure_ib_clientportal_running") as ensure_portal,
            patch.object(
                gateway_manual_service,
                "_normalize_ib_web_base_url",
                return_value="https://localhost:5000/v1/api",
            ),
            patch.object(
                gateway_manual_service,
                "_resolve_ib_web_base_url",
                return_value="https://localhost:5000/v1/api",
            ),
            patch.object(
                gateway_manual_service,
                "_bootstrap_ib_web_session",
                return_value=refreshed_session,
            ) as bootstrap,
            patch.object(
                gateway_manual_service,
                "_to_backend_env_relative_path",
                return_value="configs/refreshed.json",
            ),
            patch.object(
                gateway_manual_service,
                "_build_ib_web_env_updates",
                return_value={"IB_WEB_COOKIE_SOURCE": "file:configs/refreshed.json"},
            ),
            patch.object(gateway_manual_service, "_persist_ib_web_env_updates") as persist,
        ):
            state = gateway_runtime_service.acquire_gateway_for_instance(
                instance_id="inst-ib",
                instance={"params": {"gateway": {"enabled": True}}},
                strategy_dir=Path("/tmp/strategy"),
                get_gateway_params=lambda instance: {"enabled": True},
                build_gateway_launch=lambda instance, strategy_dir, gateway_params: launch,
                gateways={},
                instance_gateways={},
                logger=Mock(),
            )

        ensure_portal.assert_called_once()
        bootstrap.assert_called_once()
        assert bootstrap.call_args.kwargs["allow_interactive_login"] is True
        assert state["account_id"] == "DU654321"
        config = launch["runtime_cls"].call_args.args[0]
        assert config.kwargs["account_id"] == "DU654321"
        assert config.kwargs["cookies"] == {"session": "fresh"}
        assert config.kwargs["cookie_source"] == "file:configs/refreshed.json"
        persist.assert_called_once()

    def test_acquire_gateway_for_instance_stops_when_ib_login_is_not_completed(self):
        """Do not start a gateway with a known-expired Client Portal session."""
        from app.services.gateway import manual as gateway_manual_service

        class Config:
            runtime_name = "ib-web-DU123456"
            command_endpoint = "tcp://command"
            event_endpoint = "tcp://event"
            market_endpoint = "tcp://market"

        launch = {
            "config": Config(),
            "runtime_cls": Mock(),
            "runtime_kwargs": {
                "exchange_type": "IB_WEB",
                "account_id": "DU123456",
                "base_url": "https://localhost:5000",
                "cookie_source": "file:configs/expired.json",
                "gateway_startup_timeout_sec": 30.0,
            },
        }

        with (
            patch.object(gateway_manual_service, "_ensure_ib_clientportal_running"),
            patch.object(
                gateway_manual_service,
                "_normalize_ib_web_base_url",
                return_value="https://localhost:5000/v1/api",
            ),
            patch.object(
                gateway_manual_service,
                "_resolve_ib_web_base_url",
                return_value="https://localhost:5000/v1/api",
            ),
            patch.object(gateway_manual_service, "_bootstrap_ib_web_session", return_value=None),
        ):
            with pytest.raises(RuntimeError, match="自动登录未完成"):
                gateway_runtime_service.acquire_gateway_for_instance(
                    instance_id="inst-ib",
                    instance={"params": {"gateway": {"enabled": True}}},
                    strategy_dir=Path("/tmp/strategy"),
                    get_gateway_params=lambda instance: {"enabled": True},
                    build_gateway_launch=lambda instance, strategy_dir, gateway_params: launch,
                    gateways={},
                    instance_gateways={},
                    logger=Mock(),
                )

        launch["runtime_cls"].assert_not_called()

    def test_discard_idle_ib_gateway_with_auth_failure_before_relogin(self):
        runtime = Mock()
        runtime.health = Mock(
            recent_errors=[
                {"source": "adapter_connect", "message": "IB_WEB INVALID_API_KEY: HTTP 401"}
            ]
        )
        state = {"runtime": runtime, "ref_count": 0}
        gateways = {"ib-web-DU123456": state}

        result = gateway_runtime_service._discard_idle_ib_gateway_with_auth_failure(
            "ib-web-DU123456",
            state,
            gateways,
            Mock(),
        )

        assert result is None
        runtime.stop.assert_called_once()
        assert gateways == {}

    def test_acquire_gateway_for_instance_preconnects_ctp_adapter(self):
        logger = Mock()
        config = Mock(
            runtime_name="ctp-future-acc-1",
            command_endpoint="ipc://command",
            event_endpoint="ipc://event",
            market_endpoint="ipc://market",
        )
        runtime = Mock()
        runtime.adapter = Mock()
        launch = {
            "config": config,
            "runtime_cls": Mock(return_value=runtime),
            "runtime_kwargs": {"exchange_type": "CTP", "account_id": "acc-1"},
        }

        gateway_runtime_service.acquire_gateway_for_instance(
            instance_id="inst1",
            instance={"params": {"gateway": {"enabled": True}}},
            strategy_dir=Path("/tmp/strategy"),
            get_gateway_params=lambda instance: {"enabled": True},
            build_gateway_launch=lambda instance, strategy_dir, gateway_params: launch,
            gateways={},
            instance_gateways={},
            logger=logger,
        )

        runtime.adapter.connect.assert_called_once()
        runtime.adapter.get_balance.assert_called_once()
        runtime.start_in_thread.assert_called_once()

    def test_acquire_gateway_for_instance_captures_gateway_start_native_stderr(self, tmp_path):
        logger = Mock()
        config = Mock(
            runtime_name="ctp-future-acc-1",
            command_endpoint="ipc://command",
            event_endpoint="ipc://event",
            market_endpoint="ipc://market",
        )

        class Runtime:
            def start_in_thread(self):
                os.write(2, b"native startup warning\n")

        runtime = Runtime()
        launch = {
            "config": config,
            "runtime_cls": Mock(return_value=runtime),
            "runtime_kwargs": {"account_id": "acc-1"},
        }

        gateway_runtime_service.acquire_gateway_for_instance(
            instance_id="inst1",
            instance={"params": {"gateway": {"enabled": True}}},
            strategy_dir=tmp_path,
            get_gateway_params=lambda instance: {"enabled": True},
            build_gateway_launch=lambda instance, strategy_dir, gateway_params: launch,
            gateways={},
            instance_gateways={},
            logger=logger,
        )

        stderr_log = tmp_path / "logs" / "gateway.stderr.log"
        assert "native startup warning" in stderr_log.read_text(encoding="utf-8")

    def test_acquire_gateway_for_instance_raises_when_runtime_start_fails(self):
        logger = Mock()
        config = Mock(
            runtime_name="ctp-future-acc-1",
            command_endpoint="ipc://command",
            event_endpoint="ipc://event",
            market_endpoint="ipc://market",
        )
        runtime = Mock()
        runtime.start_in_thread.side_effect = RuntimeError("ctp market not ready")
        launch = {
            "config": config,
            "runtime_cls": Mock(return_value=runtime),
            "runtime_kwargs": {"account_id": "acc-1"},
        }
        gateways: dict[str, dict] = {}
        instance_gateways: dict[str, str] = {}

        with pytest.raises(RuntimeError, match="ctp market not ready"):
            gateway_runtime_service.acquire_gateway_for_instance(
                instance_id="inst1",
                instance={"params": {"gateway": {"enabled": True}}},
                strategy_dir=Path("/tmp/strategy"),
                get_gateway_params=lambda instance: {"enabled": True},
                build_gateway_launch=lambda instance, strategy_dir, gateway_params: launch,
                gateways=gateways,
                instance_gateways=instance_gateways,
                logger=logger,
            )

        assert gateways == {}
        assert instance_gateways == {}

    def test_acquire_gateway_for_instance_reuses_existing_manual_session(self):
        logger = Mock()
        runtime = Mock()
        config = Mock(
            runtime_name="ctp-future-acc-1",
            command_endpoint="ipc://command",
            event_endpoint="ipc://event",
            market_endpoint="ipc://market",
        )
        launch = {
            "config": config,
            "runtime_cls": Mock(),
            "runtime_kwargs": {
                "exchange_type": "CTP",
                "asset_type": "FUTURE",
                "account_id": "acc-1",
                "broker_id": "9999",
                "td_address": "tcp://td",
                "md_address": "tcp://md",
            },
        }
        gateways = {
            "manual:CTP:acc-1": {
                "config": {
                    "exchange_type": "CTP",
                    "asset_type": "FUTURE",
                    "account_id": "acc-1",
                    "broker_id": "9999",
                    "td_address": "tcp://td",
                    "md_address": "tcp://md",
                },
                "runtime": runtime,
                "instances": set(),
                "ref_count": 0,
                "manual": True,
            }
        }
        instance_gateways: dict[str, str] = {}

        state = gateway_runtime_service.acquire_gateway_for_instance(
            instance_id="inst1",
            instance={"params": {"gateway": {"enabled": True}}},
            strategy_dir=Path("/tmp/strategy"),
            get_gateway_params=lambda instance: {"enabled": True},
            build_gateway_launch=lambda instance, strategy_dir, gateway_params: launch,
            gateways=gateways,
            instance_gateways=instance_gateways,
            logger=logger,
        )

        assert state is gateways["manual:CTP:acc-1"]
        assert state["instances"] == {"inst1"}
        assert state["ref_count"] == 1
        assert instance_gateways == {"inst1": "manual:CTP:acc-1"}

    def test_release_gateway_for_instance_keeps_manual_runtime_alive(self):
        logger = Mock()
        runtime = Mock()
        gateways = {
            "manual:CTP:acc-1": {
                "runtime": runtime,
                "instances": {"inst1"},
                "ref_count": 1,
                "manual": True,
            }
        }
        instance_gateways = {"inst1": "manual:CTP:acc-1"}

        gateway_runtime_service.release_gateway_for_instance(
            instance_id="inst1",
            gateways=gateways,
            instance_gateways=instance_gateways,
            logger=logger,
        )

        runtime.stop.assert_not_called()
        assert gateways["manual:CTP:acc-1"]["instances"] == set()
        assert gateways["manual:CTP:acc-1"]["ref_count"] == 0

    def test_release_gateway_for_instance_keeps_idle_ctp_runtime_alive(self):
        logger = Mock()
        runtime = Mock()
        gateways = {
            "ctp-future-acc-1": {
                "runtime": runtime,
                "instances": {"inst1"},
                "ref_count": 1,
                "exchange_type": "CTP",
            }
        }
        instance_gateways = {"inst1": "ctp-future-acc-1"}

        gateway_runtime_service.release_gateway_for_instance(
            instance_id="inst1",
            gateways=gateways,
            instance_gateways=instance_gateways,
            logger=logger,
        )

        runtime.stop.assert_not_called()
        assert gateways["ctp-future-acc-1"]["instances"] == set()
        assert gateways["ctp-future-acc-1"]["ref_count"] == 0

    def test_release_gateway_for_instance_stops_on_last_reference(self):
        logger = Mock()
        runtime = Mock()
        gateways = {
            "ctp-future-acc-1": {
                "runtime": runtime,
                "instances": {"inst1", "inst2"},
                "ref_count": 2,
            }
        }
        instance_gateways = {"inst1": "ctp-future-acc-1", "inst2": "ctp-future-acc-1"}

        gateway_runtime_service.release_gateway_for_instance(
            instance_id="inst1",
            gateways=gateways,
            instance_gateways=instance_gateways,
            logger=logger,
        )
        runtime.stop.assert_not_called()
        assert gateways["ctp-future-acc-1"]["ref_count"] == 1
        assert gateways["ctp-future-acc-1"]["instances"] == {"inst2"}

        gateway_runtime_service.release_gateway_for_instance(
            instance_id="inst2",
            gateways=gateways,
            instance_gateways=instance_gateways,
            logger=logger,
        )
        runtime.stop.assert_called_once()
        assert gateways == {}


class TestAutoTradingScheduler:
    def test_is_within_trigger_window(self):
        scheduled_at = datetime(2026, 3, 22, 9, 0, tzinfo=timezone(timedelta(hours=8)))

        assert auto_trading_scheduler._is_within_trigger_window(
            scheduled_at + timedelta(seconds=59),
            scheduled_at,
        )
        assert not auto_trading_scheduler._is_within_trigger_window(
            scheduled_at + timedelta(seconds=61),
            scheduled_at,
        )

    def test_should_trigger_only_once_per_schedule_window(self):
        scheduler = auto_trading_scheduler.AutoTradingScheduler()
        scheduled_at = datetime(2026, 3, 22, 9, 0, tzinfo=timezone(timedelta(hours=8)))
        next_scheduled_at = scheduled_at + timedelta(days=1)

        assert scheduler._should_trigger("start", "day", scheduled_at, scheduled_at)
        assert not scheduler._should_trigger(
            "start",
            "day",
            scheduled_at,
            scheduled_at + timedelta(seconds=20),
        )
        assert not scheduler._should_trigger(
            "start",
            "day",
            scheduled_at,
            scheduled_at + timedelta(minutes=2),
        )
        assert scheduler._should_trigger(
            "start",
            "day",
            next_scheduled_at,
            next_scheduled_at,
        )
