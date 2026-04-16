"""
Live Trading Manager Service Tests.

Tests:
    - Instance CRUD operations
    - Instance start/stop
    - Subprocess management
    - Process status synchronization
    - Error handling
    - Log directory lookup
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.services.live_trading_manager import (
    LiveTradingManager,
    _find_latest_log_dir,
    _is_pid_alive,
    _load_instances,
    _save_instances,
    get_live_trading_manager,
)


@pytest.fixture(autouse=True)
def disable_restore_background_thread(monkeypatch):
    monkeypatch.setattr(
        LiveTradingManager, "_start_restore_manual_gateways_background", lambda self: None
    )


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_load_instances_from_file(self):
        """Test loading instances from file.

        Verifies that instances are correctly loaded from
        a JSON file.
        """
        # Mock file exists with content
        with patch("app.services.live_trading_manager._INSTANCES_FILE") as mock_file:
            mock_file.is_file.return_value = True
            mock_file.read_text.return_value = '{"test": {"status": "running"}}'

            result = _load_instances()

            assert result == {"test": {"status": "running"}}

    def test_load_instances_file_not_exists(self):
        """Test loading when file doesn't exist.

        Verifies that an empty dictionary is returned when
        the instances file doesn't exist.
        """
        with patch("app.services.live_trading_manager._INSTANCES_FILE") as mock_file:
            mock_file.is_file.return_value = False

            result = _load_instances()

            assert result == {}

    def test_load_instances_invalid_json(self):
        """Test loading with invalid JSON.

        Verifies that an empty dictionary is returned when
        the file contains invalid JSON.
        """
        with patch("app.services.live_trading_manager._INSTANCES_FILE") as mock_file:
            mock_file.is_file.return_value = True
            mock_file.read_text.return_value = "invalid json"

            result = _load_instances()

            assert result == {}

    def test_save_instances(self):
        """Test saving instances to file.

        Verifies that instances are correctly written to
        the JSON file.
        """
        with patch("app.services.live_trading_manager._INSTANCES_FILE") as mock_file:
            test_data = {"test": {"status": "running"}}

            _save_instances(test_data)

            # Verify write was called
            mock_file.write_text.assert_called_once()

    def test_find_latest_log_dir(self):
        """Test finding the latest log directory.

        Verifies that the most recently modified log directory
        is returned.
        """
        with patch("app.services.live_trading_manager.Path"):
            mock_strategy_dir = MagicMock()
            mock_logs_dir = MagicMock()
            mock_subdir1 = MagicMock()
            mock_subdir2 = MagicMock()

            # Setup mock hierarchy
            mock_subdir1.is_dir.return_value = True
            mock_subdir2.is_dir.return_value = True
            mock_subdir1.name = "log1"
            mock_subdir2.name = "log2"
            mock_subdir1.stat.return_value.st_mtime = 1000
            mock_subdir2.stat.return_value.st_mtime = 2000  # Latest

            mock_logs_dir.is_dir.return_value = True
            mock_logs_dir.iterdir.return_value = [mock_subdir1, mock_subdir2]
            mock_strategy_dir.__truediv__.return_value = mock_logs_dir

            result = _find_latest_log_dir(mock_strategy_dir)

            # Should return the latest directory
            assert result is not None

    def test_find_latest_log_dir_no_logs(self):
        """Test finding log directory when none exists.

        Verifies that None is returned when no log directory
        exists for the strategy.
        """
        with patch("app.services.live_trading_manager.Path"):
            mock_strategy_dir = MagicMock()
            mock_logs_dir = MagicMock()
            mock_logs_dir.is_dir.return_value = False
            mock_strategy_dir.__truediv__.return_value = mock_logs_dir

            result = _find_latest_log_dir(mock_strategy_dir)

            assert result is None

    def test_is_pid_alive(self):
        """Test checking if process is alive.

        Verifies that the function correctly identifies
        a running process.
        """
        # Test with a valid PID (current process)
        import os

        current_pid = os.getpid()
        assert _is_pid_alive(current_pid) is True

    def test_is_pid_not_alive(self):
        """Test checking if non-existent process is alive.

        Verifies that the function returns False for a
        non-existent PID.
        """
        # Use an invalid PID
        assert _is_pid_alive(999999) is False


class TestLiveTradingManagerInitialization:
    """Tests for manager initialization."""

    def test_initialization(self):
        """Test basic manager initialization.

        Verifies that a new LiveTradingManager initializes
        with an empty processes dictionary.
        """
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()
            assert manager._processes == {}

    def test_initialization_syncs_status(self):
        """Test status synchronization during initialization.

        Verifies that the manager synchronizes process status
        during initialization by checking if PIDs are alive.
        """
        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {"status": "running", "pid": 12345},  # Will be marked as stopped
                "inst2": {"status": "stopped", "pid": None},
            }

            with patch("app.services.live_trading_manager._is_pid_alive", return_value=False):
                with patch("app.services.live_trading_manager._save_instances") as mock_save:
                    LiveTradingManager()
                    # Should have saved updated status
                    mock_save.assert_called_once()

    def test_initialization_starts_restore_thread(self):
        with (
            patch("app.services.live_trading_manager._load_instances", return_value={}),
            patch.object(
                LiveTradingManager,
                "_start_restore_manual_gateways_background",
            ) as mock_start_restore,
        ):
            LiveTradingManager()

        mock_start_restore.assert_called_once()


class TestGatewayLifecycle:
    def test_connect_gateway_persists_manual_gateway(self):
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            with patch("app.services.live_trading_manager._load_manual_gateways", return_value=[]):
                with patch("app.services.live_trading_manager._save_manual_gateways") as mock_save:
                    with patch(
                        "app.services.live_trading_manager.manual_gateway_service.connect_gateway",
                        return_value={
                            "gateway_key": "manual:MT5:123456",
                            "status": "connected",
                            "message": "ok",
                        },
                    ):
                        manager = LiveTradingManager()
                        result = manager.connect_gateway(
                            "MT5", {"login": 123456, "password": "secret"}
                        )

        assert result["status"] == "connected"
        mock_save.assert_called_once_with(
            [
                {
                    "gateway_key": "manual:MT5:123456",
                    "exchange_type": "MT5",
                    "credentials": {"login": 123456, "password": "secret"},
                }
            ]
        )

    def test_restore_manual_gateways_on_boot(self):
        persisted = [
            {
                "gateway_key": "manual:IB_WEB:DU123456",
                "exchange_type": "IB_WEB",
                "credentials": {"account_id": "DU123456", "base_url": "https://localhost:5000"},
            }
        ]
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            with patch(
                "app.services.live_trading_manager._load_manual_gateways", return_value=persisted
            ):
                with patch(
                    "app.services.live_trading_manager.manual_gateway_service.connect_gateway",
                    return_value={
                        "gateway_key": "manual:IB_WEB:DU123456",
                        "status": "connected",
                        "message": "ok",
                    },
                ) as mock_connect:
                    manager = LiveTradingManager()
                    manager._restore_manual_gateways()

        mock_connect.assert_called_once()
        assert mock_connect.call_args.kwargs["exchange_type"] == "IB_WEB"
        assert mock_connect.call_args.kwargs["credentials"] == {
            "account_id": "DU123456",
            "base_url": "https://localhost:5000",
        }
        assert mock_connect.call_args.kwargs["allow_interactive_login"] is False

    def test_disconnect_gateway_removes_persisted_manual_gateway(self):
        persisted = [
            {
                "gateway_key": "manual:MT5:123456",
                "exchange_type": "MT5",
                "credentials": {"login": 123456, "password": "secret"},
            }
        ]
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            with patch(
                "app.services.live_trading_manager._load_manual_gateways", return_value=persisted
            ):
                with patch("app.services.live_trading_manager._save_manual_gateways") as mock_save:
                    with patch(
                        "app.services.live_trading_manager.manual_gateway_service.disconnect_gateway",
                        return_value={
                            "gateway_key": "manual:MT5:123456",
                            "status": "disconnected",
                            "message": "ok",
                        },
                    ):
                        manager = LiveTradingManager()
                        result = manager.disconnect_gateway("manual:MT5:123456")

        assert result["status"] == "disconnected"
        mock_save.assert_called_once_with([])

    def test_disconnect_gateway_suppresses_mt5_auto_connect(self):
        with (
            patch("app.services.live_trading_manager._load_instances", return_value={}),
            patch(
                "app.services.live_trading_manager.manual_gateway_service.disconnect_gateway",
                return_value={
                    "gateway_key": "manual:MT5:123456",
                    "status": "disconnected",
                    "message": "ok",
                },
            ),
            patch("app.services.live_trading_manager._load_manual_gateways", return_value=[]),
            patch("app.services.live_trading_manager._save_manual_gateways"),
            patch("app.services.quote_service.QuoteService") as mock_quote_service,
        ):
            manager = LiveTradingManager()
            result = manager.disconnect_gateway("manual:MT5:123456")

        assert result["status"] == "disconnected"
        mock_quote_service.return_value.suppress_auto_connect.assert_called_once_with("MT5")

    def test_connect_gateway_resumes_mt5_auto_connect(self):
        with (
            patch("app.services.live_trading_manager._load_instances", return_value={}),
            patch(
                "app.services.live_trading_manager.manual_gateway_service.connect_gateway",
                return_value={
                    "gateway_key": "manual:MT5:123456",
                    "status": "connected",
                    "message": "ok",
                },
            ),
            patch("app.services.live_trading_manager._load_manual_gateways", return_value=[]),
            patch("app.services.live_trading_manager._save_manual_gateways"),
            patch("app.services.quote_service.QuoteService") as mock_quote_service,
        ):
            manager = LiveTradingManager()
            result = manager.connect_gateway("MT5", {"login": 123456, "password": "secret"})

        assert result["status"] == "connected"
        mock_quote_service.return_value.resume_auto_connect.assert_called_once_with("MT5")

    def test_connect_gateway_returns_error_result_when_manual_service_raises(self):
        with (
            patch("app.services.live_trading_manager._load_instances", return_value={}),
            patch(
                "app.services.live_trading_manager.manual_gateway_service.connect_gateway",
                side_effect=RuntimeError("boom"),
            ),
            patch("app.services.live_trading_manager._load_manual_gateways", return_value=[]),
        ):
            manager = LiveTradingManager()
            result = manager.connect_gateway("OKX", {"api_key": "k", "secret_key": "s"})

        assert result["status"] == "error"
        assert "OKX连接失败" in result["message"]
        assert "RuntimeError: boom" in result["message"]

    def test_connect_gateway_reports_persist_failure_without_raising(self):
        with (
            patch("app.services.live_trading_manager._load_instances", return_value={}),
            patch(
                "app.services.live_trading_manager._load_manual_gateways",
                return_value=[],
            ),
            patch(
                "app.services.live_trading_manager._save_manual_gateways",
                side_effect=OSError("disk full"),
            ),
            patch(
                "app.services.live_trading_manager.manual_gateway_service.connect_gateway",
                return_value={
                    "gateway_key": "manual:MT5:123456",
                    "status": "connected",
                    "message": "ok",
                },
            ),
        ):
            manager = LiveTradingManager()
            result = manager.connect_gateway("MT5", {"login": 123456, "password": "secret"})

        assert result["status"] == "connected"
        assert "本地保存失败" in result["message"]

    def test_build_subprocess_env_with_gateway(self):
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()
            gateway_state = {
                "config": MagicMock(
                    command_endpoint="ipc://command",
                    event_endpoint="ipc://event",
                    market_endpoint="ipc://market",
                    account_id="acc-1",
                    exchange_type="CTP",
                    asset_type="FUTURE",
                )
            }
            with patch.dict("os.environ", {}, clear=True):
                with patch.object(
                    manager, "_acquire_gateway_for_instance", return_value=gateway_state
                ):
                    env = manager._build_subprocess_env(
                        "inst1",
                        {"params": {"gateway": {"enabled": True}}},
                        Path("/tmp/strategy"),
                    )

        assert env["BT_STORE_PROVIDER"] == "ctp_gateway"
        assert env["BT_GATEWAY_START_LOCAL_RUNTIME"] == "0"
        assert env["BT_GATEWAY_COMMAND_ENDPOINT"] == "ipc://command"
        assert env["BT_GATEWAY_EVENT_ENDPOINT"] == "ipc://event"
        assert env["BT_GATEWAY_MARKET_ENDPOINT"] == "ipc://market"
        assert env["BT_GATEWAY_ACCOUNT_ID"] == "acc-1"
        assert env["BT_GATEWAY_EXCHANGE_TYPE"] == "CTP"
        assert env["BT_GATEWAY_ASSET_TYPE"] == "FUTURE"

    def test_build_subprocess_env_with_ib_web_gateway(self):
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()
            gateway_state = {
                "config": MagicMock(
                    command_endpoint="ipc://command",
                    event_endpoint="ipc://event",
                    market_endpoint="ipc://market",
                    account_id="du123456",
                    exchange_type="IB_WEB",
                    asset_type="STK",
                )
            }
            with patch.dict("os.environ", {}, clear=True):
                with patch.object(
                    manager, "_acquire_gateway_for_instance", return_value=gateway_state
                ):
                    env = manager._build_subprocess_env(
                        "inst1",
                        {"params": {"gateway": {"enabled": True, "exchange_type": "IB_WEB"}}},
                        Path("/tmp/strategy"),
                    )

        assert env["BT_STORE_PROVIDER"] == "ctp_gateway"
        assert env["BT_GATEWAY_START_LOCAL_RUNTIME"] == "0"
        assert env["BT_GATEWAY_COMMAND_ENDPOINT"] == "ipc://command"
        assert env["BT_GATEWAY_EVENT_ENDPOINT"] == "ipc://event"
        assert env["BT_GATEWAY_MARKET_ENDPOINT"] == "ipc://market"
        assert env["BT_GATEWAY_ACCOUNT_ID"] == "du123456"
        assert env["BT_GATEWAY_EXCHANGE_TYPE"] == "IB_WEB"
        assert env["BT_GATEWAY_ASSET_TYPE"] == "STK"

    def test_get_gateway_params_normalizes_ib_web(self):
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()

        params = manager._get_gateway_params(
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
            }
        )

        assert params["enabled"] is True
        assert params["exchange_type"] == "IB_WEB"
        assert params["asset_type"] == "STK"
        assert params["account_id"] == "du123456"
        assert params["base_url"] == "https://localhost:5000"

    def test_build_gateway_launch_for_ib_web(self, tmp_path):
        strategy_dir = tmp_path / "test_strategy"
        strategy_dir.mkdir()
        (strategy_dir / "config.yaml").write_text(
            "\n".join(
                [
                    "ib_web:",
                    "  base_url: https://localhost:5000",
                    "  account_id: config-acc",
                    "  verify_ssl: false",
                    "  timeout: 15",
                ]
            ),
            encoding="utf-8",
        )
        (strategy_dir / ".env").write_text(
            "\n".join(
                [
                    "IB_WEB_ACCOUNT_ID=env-acc",
                    "IB_WEB_BASE_URL=https://localhost:5000",
                    "IB_WEB_ACCESS_TOKEN=test-token",
                    "IB_WEB_VERIFY_SSL=true",
                    "IB_WEB_USERNAME=test-user",
                    "IB_WEB_PASSWORD=test-pass",
                    "IB_WEB_LOGIN_MODE=paper",
                    "IB_WEB_LOGIN_BROWSER=chrome",
                    "IB_WEB_LOGIN_HEADLESS=false",
                    "IB_WEB_LOGIN_TIMEOUT=180",
                    "IB_WEB_COOKIE_OUTPUT=../bt_api_py/configs/ibkr_cookies.json",
                ]
            ),
            encoding="utf-8",
        )

        class FakeGatewayConfig:
            @classmethod
            def from_kwargs(cls, **kwargs):
                return kwargs

        class FakeGatewayRuntime:
            pass

        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()

        gateway_params = {
            "enabled": True,
            "provider": "ctp_gateway",
            "exchange_type": "IB_WEB",
            "asset_type": "stock",
            "transport": "ipc",
            "account_id": "",
            "base_dir": str(tmp_path / "gateway"),
            "base_url": "",
            "access_token": "",
            "verify_ssl": None,
            "cookie_source": "",
            "cookie_browser": "",
            "cookie_path": "",
            "cookies": None,
        }

        with patch.object(
            manager,
            "_import_gateway_runtime_classes",
            return_value=(FakeGatewayConfig, FakeGatewayRuntime),
        ):
            launch = manager._build_gateway_launch(
                {"params": {"gateway": {"enabled": True, "exchange_type": "IB_WEB"}}},
                strategy_dir,
                gateway_params,
            )

        runtime_kwargs = launch["runtime_kwargs"]
        assert launch["runtime_cls"] is FakeGatewayRuntime
        assert launch["config"] == runtime_kwargs
        assert runtime_kwargs["exchange_type"] == "IB_WEB"
        assert runtime_kwargs["asset_type"] == "STK"
        assert runtime_kwargs["account_id"] == "env-acc"
        assert runtime_kwargs["base_url"] == "https://localhost:5000"
        assert runtime_kwargs["access_token"] == "test-token"
        assert runtime_kwargs["verify_ssl"] is True
        assert runtime_kwargs["timeout"] == 15.0
        assert runtime_kwargs["username"] == "test-user"
        assert runtime_kwargs["password"] == "test-pass"
        assert runtime_kwargs["login_mode"] == "paper"
        assert runtime_kwargs["login_browser"] == "chrome"
        assert runtime_kwargs["login_headless"] is False
        assert runtime_kwargs["login_timeout"] == 180
        assert runtime_kwargs["cookie_source"] == "file:../bt_api_py/configs/ibkr_cookies.json"
        assert runtime_kwargs["cookie_output"] == "../bt_api_py/configs/ibkr_cookies.json"
        assert runtime_kwargs["cookie_base_dir"]

    def test_connect_ib_web_gateway_defaults_to_browser_cookie_source(self, tmp_path):
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()

        fake_settings = SimpleNamespace(
            IB_ACCESS_TOKEN="",
            IB_PAPER_COOKIE_SOURCE="file:../bt_api_py/configs/ibkr_cookies.json",
            IB_LIVE_COOKIE_SOURCE="",
            IB_COOKIE_SOURCE="",
            IB_COOKIE_BROWSER="chrome",
            IB_PAPER_COOKIE_PATH="/sso",
            IB_LIVE_COOKIE_PATH="",
            IB_COOKIE_PATH="/sso",
            IB_COOKIE_OUTPUT="../bt_api_py/configs/ibkr_cookies.json",
            IB_USERNAME="test-ib-user",
            IB_PASSWORD="test-ib-pass",
            IB_LOGIN_BROWSER="chrome",
            IB_LOGIN_HEADLESS=False,
            IB_LOGIN_TIMEOUT=180,
            IB_WEB_LOGIN_MODE="",
            IB_WEB_LOGIN_BROWSER="",
            IB_WEB_LOGIN_HEADLESS=False,
            IB_WEB_LOGIN_TIMEOUT=0,
            IB_WEB_COOKIE_SOURCE="",
            IB_WEB_COOKIE_BROWSER="",
            IB_WEB_COOKIE_PATH="",
            IB_WEB_COOKIE_OUTPUT="",
            IB_WEB_USERNAME="",
            IB_WEB_PASSWORD="",
            IB_WEB_ACCOUNT_ID="",
            IB_WEB_ASSET_TYPE="",
            IB_WEB_BASE_URL="",
            IB_WEB_ACCESS_TOKEN="",
            IB_WEB_VERIFY_SSL=False,
            IB_WEB_TIMEOUT=0.0,
            IB_PAPER_ACCOUNT_ID="",
            IB_PAPER_ASSET_TYPE="",
            IB_PAPER_BASE_URL="",
            IB_PAPER_ACCESS_TOKEN="",
            IB_PAPER_VERIFY_SSL=False,
            IB_PAPER_TIMEOUT=0.0,
            IB_PAPER_COOKIE_BROWSER="",
            IB_LIVE_COOKIE_BROWSER="",
        )

        class FakeGatewayConfig:
            @classmethod
            def from_kwargs(cls, **kwargs):
                return kwargs

        class FakeGatewayRuntime:
            def __init__(self, config, **kwargs):
                self.config = config
                self.kwargs = kwargs

            def start_in_thread(self):
                return None

        with patch("app.config.get_settings", return_value=fake_settings):
            with patch.object(
                manager,
                "_import_gateway_runtime_classes",
                return_value=(FakeGatewayConfig, FakeGatewayRuntime),
            ):
                with patch(
                    "app.services.manual_gateway_service._ensure_ib_clientportal_running",
                    return_value=None,
                ):
                    with patch(
                        "app.services.manual_gateway_service._resolve_ib_web_base_url",
                        side_effect=lambda base_url, *_args: base_url,
                    ):
                        with patch(
                            "app.services.manual_gateway_service._bootstrap_ib_web_session",
                            return_value=None,
                        ):
                            with patch(
                                "app.services.manual_gateway_service._wait_for_runtime_ready",
                                return_value=None,
                            ):
                                with patch(
                                    "app.services.manual_gateway_service._persist_ib_web_env_updates",
                                    return_value=None,
                                ):
                                    result = manager._connect_ib_web_gateway(
                                        "manual:IB_WEB:DU123456",
                                        {
                                            "account_id": "DU123456",
                                            "base_url": "https://localhost:5000/v1/api",
                                        },
                                    )

        assert result["status"] == "connected"
        runtime_kwargs = manager._gateways["manual:IB_WEB:DU123456"]["config"]
        assert runtime_kwargs["cookie_source"] == "file:../bt_api_py/configs/ibkr_cookies.json"
        assert runtime_kwargs["cookie_browser"] == "chrome"
        assert runtime_kwargs["cookie_path"] == "/sso"
        assert runtime_kwargs["cookie_output"] == "../bt_api_py/configs/ibkr_cookies.json"
        assert runtime_kwargs["username"] == "test-ib-user"
        assert runtime_kwargs["password"] == "test-ib-pass"
        assert runtime_kwargs["login_mode"] == "paper"
        assert runtime_kwargs["cookie_base_dir"]

    def test_connect_ib_web_gateway_missing_cookie_file_falls_back_to_browser(self, tmp_path):
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()

        fake_settings = SimpleNamespace(
            IB_ACCESS_TOKEN="",
            IB_PAPER_COOKIE_SOURCE="",
            IB_LIVE_COOKIE_SOURCE="",
            IB_COOKIE_SOURCE="",
            IB_COOKIE_BROWSER="chrome",
            IB_PAPER_COOKIE_PATH="/sso",
            IB_LIVE_COOKIE_PATH="",
            IB_COOKIE_PATH="/sso",
            IB_COOKIE_OUTPUT="../bt_api_py/configs/ibkr_cookies.json",
            IB_USERNAME="test-ib-user",
            IB_PASSWORD="test-ib-pass",
            IB_LOGIN_BROWSER="chrome",
            IB_LOGIN_HEADLESS=False,
            IB_LOGIN_TIMEOUT=180,
            IB_WEB_LOGIN_MODE="",
            IB_WEB_LOGIN_BROWSER="",
            IB_WEB_LOGIN_HEADLESS=False,
            IB_WEB_LOGIN_TIMEOUT=0,
            IB_WEB_COOKIE_SOURCE="",
            IB_WEB_COOKIE_BROWSER="",
            IB_WEB_COOKIE_PATH="",
            IB_WEB_COOKIE_OUTPUT="",
            IB_WEB_USERNAME="",
            IB_WEB_PASSWORD="",
            IB_WEB_ACCOUNT_ID="",
            IB_WEB_ASSET_TYPE="",
            IB_WEB_BASE_URL="",
            IB_WEB_ACCESS_TOKEN="",
            IB_WEB_VERIFY_SSL=False,
            IB_WEB_TIMEOUT=0.0,
            IB_PAPER_ACCOUNT_ID="",
            IB_PAPER_ASSET_TYPE="",
            IB_PAPER_BASE_URL="",
            IB_PAPER_ACCESS_TOKEN="",
            IB_PAPER_VERIFY_SSL=False,
            IB_PAPER_TIMEOUT=0.0,
            IB_PAPER_COOKIE_BROWSER="",
            IB_LIVE_COOKIE_BROWSER="",
        )

        class FakeGatewayConfig:
            @classmethod
            def from_kwargs(cls, **kwargs):
                return kwargs

        class FakeGatewayRuntime:
            def __init__(self, config, **kwargs):
                self.config = config
                self.kwargs = kwargs

            def start_in_thread(self):
                return None

        with patch("app.config.get_settings", return_value=fake_settings):
            with patch.object(
                manager,
                "_import_gateway_runtime_classes",
                return_value=(FakeGatewayConfig, FakeGatewayRuntime),
            ):
                with patch(
                    "app.services.manual_gateway_service._ensure_ib_clientportal_running",
                    return_value=None,
                ):
                    with patch(
                        "app.services.manual_gateway_service._resolve_ib_web_base_url",
                        side_effect=lambda base_url, *_args: base_url,
                    ):
                        with patch(
                            "app.services.manual_gateway_service._bootstrap_ib_web_session",
                            return_value=None,
                        ):
                            with patch(
                                "app.services.manual_gateway_service._wait_for_runtime_ready",
                                return_value=None,
                            ):
                                with patch(
                                    "app.services.manual_gateway_service._persist_ib_web_env_updates",
                                    return_value=None,
                                ):
                                    result = manager._connect_ib_web_gateway(
                                        "manual:IB_WEB:DU123456",
                                        {
                                            "account_id": "DU123456",
                                            "cookie_source": "file:C:/definitely/not/exist/ibkr_cookies.json",
                                        },
                                    )

        assert result["status"] == "connected"
        runtime_kwargs = manager._gateways["manual:IB_WEB:DU123456"]["config"]
        assert runtime_kwargs["cookie_source"] == "file:C:/definitely/not/exist/ibkr_cookies.json"
        assert runtime_kwargs["cookie_output"] == "../bt_api_py/configs/ibkr_cookies.json"
        assert runtime_kwargs["username"] == "test-ib-user"
        assert runtime_kwargs["password"] == "test-ib-pass"

    def test_release_gateway_for_instance_stops_runtime_when_last_instance(self):
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()

        runtime = Mock()
        manager._gateways["ctp-future-acc-1"] = {
            "runtime": runtime,
            "instances": {"inst1"},
            "ref_count": 1,
        }
        manager._instance_gateways["inst1"] = "ctp-future-acc-1"

        manager._release_gateway_for_instance("inst1")

        runtime.stop.assert_called_once()
        assert "ctp-future-acc-1" not in manager._gateways

    def test_release_gateway_for_instance_keeps_runtime_when_shared(self):
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()

        runtime = Mock()
        manager._gateways["ctp-future-acc-1"] = {
            "runtime": runtime,
            "instances": {"inst1", "inst2"},
            "ref_count": 2,
        }
        manager._instance_gateways["inst1"] = "ctp-future-acc-1"
        manager._instance_gateways["inst2"] = "ctp-future-acc-1"

        manager._release_gateway_for_instance("inst1")

        runtime.stop.assert_not_called()
        assert manager._gateways["ctp-future-acc-1"]["ref_count"] == 1
        assert manager._gateways["ctp-future-acc-1"]["instances"] == {"inst2"}

    def test_acquire_gateway_reuses_runtime_across_instances(self):
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()

        config = MagicMock(runtime_name="ctp-future-acc-1")
        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)
        launch = {
            "config": config,
            "runtime_cls": runtime_cls,
            "runtime_kwargs": {"account_id": "acc-1"},
        }

        with patch.object(manager, "_build_gateway_launch", return_value=launch):
            state1 = manager._acquire_gateway_for_instance(
                "inst1",
                {"params": {"gateway": {"enabled": True}}},
                Path("/tmp/strategy"),
            )
            state2 = manager._acquire_gateway_for_instance(
                "inst2",
                {"params": {"gateway": {"enabled": True}}},
                Path("/tmp/strategy"),
            )

        assert state1 is state2
        runtime_cls.assert_called_once_with(config, account_id="acc-1")
        runtime.start_in_thread.assert_called_once()
        assert state1["ref_count"] == 2
        assert state1["instances"] == {"inst1", "inst2"}

        manager._release_gateway_for_instance("inst1")
        runtime.stop.assert_not_called()
        assert manager._gateways["ctp-future-acc-1"]["ref_count"] == 1

        manager._release_gateway_for_instance("inst2")
        runtime.stop.assert_called_once()
        assert "ctp-future-acc-1" not in manager._gateways

    def test_get_gateway_health_subprocess_ready(self, tmp_path):
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()

        stderr_path = tmp_path / "stderr.log"
        stderr_path.write_text("", encoding="utf-8")
        manager._gateways["manual:CTP:089763"] = {
            "process_mode": "subprocess",
            "process": Mock(pid=12345),
            "stderr_path": str(stderr_path),
            "instances": set(),
            "ref_count": 0,
            "manual": True,
            "exchange_type": "CTP",
            "asset_type": "FUTURE",
            "account_id": "089763",
            "config": MagicMock(command_endpoint="tcp://127.0.0.1:33128"),
        }

        with patch("app.services.live_trading_manager._is_pid_alive", return_value=True):
            with patch.object(manager, "_ping_subprocess_gateway_ready", return_value=True):
                result = manager.get_gateway_health()

        assert len(result) == 1
        snap = result[0]
        assert snap["gateway_key"] == "manual:CTP:089763"
        assert snap["state"] == "running"
        assert snap["is_healthy"] is True
        assert snap["market_connection"] == "connected"
        assert snap["trade_connection"] == "connected"
        assert snap["recent_errors"] == []

    def test_get_gateway_health_subprocess_fatal_error(self, tmp_path):
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()

        stderr_path = tmp_path / "stderr.log"
        stderr_path.write_text(
            "Adapter failed to connect after 3 attempts for CTP\n",
            encoding="utf-8",
        )
        manager._gateways["manual:CTP:089763"] = {
            "process_mode": "subprocess",
            "process": Mock(pid=12345),
            "stderr_path": str(stderr_path),
            "instances": set(),
            "ref_count": 0,
            "manual": True,
            "exchange_type": "CTP",
            "asset_type": "FUTURE",
            "account_id": "089763",
            "config": MagicMock(command_endpoint="tcp://127.0.0.1:33128"),
        }

        with patch("app.services.live_trading_manager._is_pid_alive", return_value=True):
            with patch.object(manager, "_ping_subprocess_gateway_ready", return_value=False):
                result = manager.get_gateway_health()

        assert len(result) == 1
        snap = result[0]
        assert snap["state"] == "error"
        assert snap["is_healthy"] is False
        assert snap["market_connection"] == "error"
        assert snap["trade_connection"] == "error"
        assert snap["recent_errors"] == [
            {
                "source": "gateway",
                "message": "Adapter failed to connect after 3 attempts for CTP",
            }
        ]

    def test_get_gateway_health_returns_empty_list_when_health_service_raises(self):
        with (
            patch("app.services.live_trading_manager._load_instances", return_value={}),
            patch(
                "app.services.live_trading_manager.gateway_health_service.get_gateway_health",
                side_effect=RuntimeError("boom"),
            ),
        ):
            manager = LiveTradingManager()
            result = manager.get_gateway_health()

        assert result == []


class TestListInstances:
    """Tests for listing instances."""

    def test_list_all_instances(self):
        """Test listing all instances.

        Verifies that all instances are returned with
        proper formatting.
        """
        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "stopped"},
                "inst2": {"strategy_id": "s2", "user_id": "user2", "status": "running"},
            }

            with patch("app.services.live_trading_manager._save_instances"):
                with patch("app.services.live_trading_manager._is_pid_alive", return_value=True):
                    with patch(
                        "app.services.live_trading_manager._find_latest_log_dir",
                        return_value="/logs/test",
                    ):
                        with patch("app.services.live_trading_manager.STRATEGIES_DIR"):
                            manager = LiveTradingManager()
                            result = manager.list_instances()

                            assert len(result) == 2
                            assert all("id" in r for r in result)

    def test_list_instances_by_user(self):
        """Test listing instances filtered by user.

        Verifies that only instances belonging to the
        specified user are returned.
        """
        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "stopped"},
                "inst2": {"strategy_id": "s2", "user_id": "user2", "status": "running"},
            }

            with patch("app.services.live_trading_manager._save_instances"):
                with patch("app.services.live_trading_manager._is_pid_alive", return_value=True):
                    with patch(
                        "app.services.live_trading_manager._find_latest_log_dir",
                        return_value="/logs/test",
                    ):
                        with patch("app.services.live_trading_manager.STRATEGIES_DIR"):
                            manager = LiveTradingManager()
                            result = manager.list_instances(user_id="user1")

                            assert len(result) == 1
                            assert result[0]["id"] == "inst1"

    def test_list_instances_updates_dead_processes(self):
        """Test updating dead processes when listing.

        Verifies that instances with dead PIDs are marked
        as stopped when listing.
        """
        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {
                    "strategy_id": "s1",
                    "user_id": "user1",
                    "status": "running",
                    "pid": 12345,
                },
            }

            with patch("app.services.live_trading_manager._save_instances"):
                with patch("app.services.live_trading_manager._is_pid_alive", return_value=False):
                    with patch(
                        "app.services.live_trading_manager._find_latest_log_dir", return_value=None
                    ):
                        with patch("app.services.live_trading_manager.STRATEGIES_DIR"):
                            manager = LiveTradingManager()
                            result = manager.list_instances()

                            # Status should be updated to stopped
                            assert result[0]["status"] == "stopped"
                            assert result[0]["pid"] is None


class TestAddInstance:
    """Tests for adding instances."""

    def test_add_instance_success(self):
        """Test successful instance addition.

        Verifies that a new instance can be added with
        proper configuration.
        """
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            with patch("app.services.live_trading_manager._save_instances"):
                with patch("app.services.live_trading_manager.STRATEGIES_DIR") as mock_dir:
                    with patch("app.services.live_trading_manager.get_template_by_id") as mock_tpl:
                        with patch(
                            "app.services.live_trading_manager._find_latest_log_dir",
                            return_value=None,
                        ):
                            mock_strategy_dir = MagicMock()
                            mock_run_py = MagicMock()
                            mock_run_py.is_file.return_value = True
                            mock_strategy_dir.__truediv__.return_value = mock_run_py
                            mock_dir.__truediv__ = Mock(return_value=mock_strategy_dir)
                            mock_tpl.return_value = MagicMock(name="Test Strategy")

                            manager = LiveTradingManager()
                            result = manager.add_instance("test_strategy", user_id="user1")

                            assert result["strategy_id"] == "test_strategy"
                            assert result["status"] == "stopped"
                            assert result["user_id"] == "user1"
                            assert "id" in result

    def test_add_instance_strategy_not_found(self):
        """Test adding non-existent strategy.

        Verifies that a ValueError is raised when trying
        to add an instance for a non-existent strategy.
        """
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            with patch("app.services.live_trading_manager._save_instances"):
                manager = LiveTradingManager()
                # Mock the instance method to raise ValueError
                manager._resolve_strategy_dir = Mock(side_effect=ValueError("not found"))

                with pytest.raises(ValueError, match="Invalid strategy_id"):
                    manager.add_instance("test_strategy")

    def test_add_instance_with_params(self):
        """Test adding instance with parameters.

        Verifies that custom parameters are correctly
        stored when adding an instance.
        """
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            with patch("app.services.live_trading_manager._save_instances"):
                with patch("app.services.live_trading_manager.STRATEGIES_DIR") as mock_dir:
                    with patch("app.services.live_trading_manager.get_template_by_id") as mock_tpl:
                        with patch(
                            "app.services.live_trading_manager._find_latest_log_dir",
                            return_value=None,
                        ):
                            mock_strategy_dir = MagicMock()
                            mock_run_py = MagicMock()
                            mock_run_py.is_file.return_value = True
                            mock_strategy_dir.__truediv__.return_value = mock_run_py
                            mock_dir.__truediv__ = Mock(return_value=mock_strategy_dir)
                            mock_tpl.return_value = MagicMock(name="Test Strategy")

                            manager = LiveTradingManager()
                            params = {"fast": 10, "slow": 20}
                            result = manager.add_instance(
                                "test_strategy", params=params, user_id="user1"
                            )

                            assert result["params"] == params


class TestRemoveInstance:
    """Tests for removing instances."""

    def test_remove_instance_success(self):
        """Test successful instance removal.

        Verifies that an existing instance can be removed.
        """
        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "stopped"},
            }

            with patch("app.services.live_trading_manager._save_instances"):
                manager = LiveTradingManager()
                result = manager.remove_instance("inst1", user_id="user1")

                assert result is True

    def test_remove_instance_not_found(self):
        """Test removing non-existent instance.

        Verifies that removing a non-existent instance
        returns False.
        """
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            with patch("app.services.live_trading_manager._save_instances"):
                manager = LiveTradingManager()
                result = manager.remove_instance("nonexistent")

                assert result is False

    def test_remove_instance_wrong_user(self):
        """Test removing instance belonging to another user.

        Verifies that a user cannot remove instances
        belonging to other users.
        """
        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "stopped"},
            }

            with patch("app.services.live_trading_manager._save_instances"):
                manager = LiveTradingManager()
                result = manager.remove_instance("inst1", user_id="user2")

                assert result is False

    def test_remove_instance_kills_process(self):
        """Test that removing instance kills its process.

        Verifies that the associated process is terminated
        when removing a running instance.
        """
        import os
        import signal

        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {
                    "strategy_id": "s1",
                    "user_id": "user1",
                    "status": "running",
                    "pid": 12345,
                },
            }

            with patch("app.services.live_trading_manager._save_instances"):
                # Patch os.kill directly to verify the kill attempt
                with patch.object(os, "kill") as mock_kill:
                    with patch(
                        "app.services.live_trading_manager._is_pid_alive", return_value=True
                    ):
                        manager = LiveTradingManager()
                    manager.remove_instance("inst1")

                    # Should have called kill with SIGTERM (os.kill is also called by _is_pid_alive with signal 0)
                    mock_kill.assert_any_call(12345, signal.SIGTERM)


class TestGetInstance:
    """Tests for getting instances."""

    def test_get_instance_success(self):
        """Test successful instance retrieval.

        Verifies that an existing instance can be retrieved.
        """
        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "stopped"},
            }

            with patch("app.services.live_trading_manager.STRATEGIES_DIR"):
                with patch(
                    "app.services.live_trading_manager._find_latest_log_dir",
                    return_value="/logs/test",
                ):
                    manager = LiveTradingManager()
                    result = manager.get_instance("inst1", user_id="user1")

                    assert result is not None
                    assert result["id"] == "inst1"

    def test_get_instance_not_found(self):
        """Test getting non-existent instance.

        Verifies that None is returned for a non-existent
        instance.
        """
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()
            result = manager.get_instance("nonexistent")

            assert result is None

    def test_get_instance_wrong_user(self):
        """Test getting instance belonging to another user.

        Verifies that a user cannot retrieve instances
        belonging to other users.
        """
        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "user_id": "user1", "status": "stopped"},
            }

            manager = LiveTradingManager()
            result = manager.get_instance("inst1", user_id="user2")

            assert result is None


class TestStartInstance:
    """Tests for starting instances."""

    @pytest.mark.asyncio
    async def test_start_instance_success(self):
        """Test successful instance start.

        Verifies that an instance can be started and
        its status is updated.
        """
        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "test_strategy", "status": "stopped"},
            }

            with patch("app.services.live_trading_manager._save_instances"):
                with patch("app.services.live_trading_manager.STRATEGIES_DIR") as mock_dir:
                    with patch(
                        "app.services.live_trading_manager._find_latest_log_dir", return_value=None
                    ):
                        mock_strategy_dir = MagicMock()
                        mock_run_py = MagicMock()
                        mock_run_py.is_file.return_value = True
                        mock_strategy_dir.__truediv__.return_value = mock_run_py
                        mock_dir.__truediv__ = Mock(return_value=mock_strategy_dir)

                        manager = LiveTradingManager()

                        # Mock create_subprocess_exec
                        mock_proc = AsyncMock()
                        mock_proc.pid = 12345
                        mock_proc.returncode = None

                        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                            # start_instance schedules _wait_process via asyncio.create_task; when patched,
                            # close the coroutine to avoid "coroutine was never awaited" warnings.
                            with patch("asyncio.create_task") as mock_create_task:

                                def _create_task(coro):
                                    try:
                                        coro.close()
                                    except Exception:
                                        pass
                                    return Mock()

                                mock_create_task.side_effect = _create_task
                                result = await manager.start_instance("inst1")

                                assert result["status"] == "running"
                                assert result["pid"] == 12345

    @pytest.mark.asyncio
    async def test_start_instance_passes_gateway_env_to_subprocess(self):
        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {
                    "strategy_id": "test_strategy",
                    "status": "stopped",
                    "params": {"gateway": {"enabled": True}},
                },
            }

            with patch("app.services.live_trading_manager._save_instances"):
                with patch("app.services.live_trading_manager.STRATEGIES_DIR") as mock_dir:
                    with patch(
                        "app.services.live_trading_manager._find_latest_log_dir", return_value=None
                    ):
                        mock_strategy_dir = MagicMock()
                        mock_run_py = MagicMock()
                        mock_run_py.is_file.return_value = True
                        mock_strategy_dir.__truediv__.return_value = mock_run_py
                        mock_dir.__truediv__ = Mock(return_value=mock_strategy_dir)

                        manager = LiveTradingManager()
                        gateway_env = {
                            "BT_STORE_PROVIDER": "ctp_gateway",
                            "BT_GATEWAY_COMMAND_ENDPOINT": "ipc://command",
                            "BT_GATEWAY_EVENT_ENDPOINT": "ipc://event",
                            "BT_GATEWAY_MARKET_ENDPOINT": "ipc://market",
                            "BT_GATEWAY_ACCOUNT_ID": "acc-1",
                            "BT_GATEWAY_EXCHANGE_TYPE": "CTP",
                            "BT_GATEWAY_ASSET_TYPE": "FUTURE",
                            "BT_GATEWAY_START_LOCAL_RUNTIME": "0",
                        }

                        mock_proc = AsyncMock()
                        mock_proc.pid = 12345
                        mock_proc.returncode = None

                        with patch.object(
                            manager, "_build_subprocess_env", return_value=gateway_env
                        ):
                            with patch(
                                "asyncio.create_subprocess_exec", return_value=mock_proc
                            ) as mock_exec:
                                with patch("asyncio.create_task") as mock_create_task:

                                    def _create_task(coro):
                                        try:
                                            coro.close()
                                        except Exception:
                                            pass
                                        return Mock()

                                    mock_create_task.side_effect = _create_task
                                    await manager.start_instance("inst1")

                        assert mock_exec.call_args.kwargs["env"] == gateway_env

    @pytest.mark.asyncio
    async def test_start_stop_instance_real_subprocess_gateway_smoke(self, tmp_path):
        instances = {
            "inst1": {
                "strategy_id": "test_strategy",
                "status": "stopped",
                "params": {"gateway": {"enabled": True}},
            }
        }
        strategy_dir = tmp_path / "test_strategy"
        strategy_dir.mkdir()
        env_file = strategy_dir / "env.json"
        run_py = strategy_dir / "run.py"
        run_py.write_text(
            "\n".join(
                [
                    "import json",
                    "import os",
                    "import time",
                    "from pathlib import Path",
                    "",
                    "Path('env.json').write_text(",
                    "    json.dumps(",
                    "        {",
                    "            'BT_STORE_PROVIDER': os.environ.get('BT_STORE_PROVIDER'),",
                    "            'BT_GATEWAY_COMMAND_ENDPOINT': os.environ.get('BT_GATEWAY_COMMAND_ENDPOINT'),",
                    "            'BT_GATEWAY_EVENT_ENDPOINT': os.environ.get('BT_GATEWAY_EVENT_ENDPOINT'),",
                    "            'BT_GATEWAY_MARKET_ENDPOINT': os.environ.get('BT_GATEWAY_MARKET_ENDPOINT'),",
                    "            'BT_GATEWAY_ACCOUNT_ID': os.environ.get('BT_GATEWAY_ACCOUNT_ID'),",
                    "            'BT_GATEWAY_EXCHANGE_TYPE': os.environ.get('BT_GATEWAY_EXCHANGE_TYPE'),",
                    "            'BT_GATEWAY_ASSET_TYPE': os.environ.get('BT_GATEWAY_ASSET_TYPE'),",
                    "            'BT_GATEWAY_START_LOCAL_RUNTIME': os.environ.get('BT_GATEWAY_START_LOCAL_RUNTIME'),",
                    "        }",
                    "    ),",
                    "    encoding='utf-8',",
                    ")",
                    "time.sleep(30)",
                ]
            ),
            encoding="utf-8",
        )

        config = MagicMock(
            runtime_name="ctp-future-acc-1",
            command_endpoint="ipc://command",
            event_endpoint="ipc://event",
            market_endpoint="ipc://market",
            account_id="acc-1",
            exchange_type="CTP",
            asset_type="FUTURE",
        )
        runtime = Mock()
        runtime_cls = Mock(return_value=runtime)
        launch = {
            "config": config,
            "runtime_cls": runtime_cls,
            "runtime_kwargs": {"account_id": "acc-1"},
        }

        created_tasks = []
        original_create_task = asyncio.create_task

        def _create_task(coro):
            task = original_create_task(coro)
            created_tasks.append(task)
            return task

        with patch("app.services.live_trading_manager._load_instances", return_value=instances):
            with patch("app.services.live_trading_manager._save_instances"):
                with patch(
                    "app.services.live_trading_manager._find_latest_log_dir", return_value=None
                ):
                    manager = LiveTradingManager()
                    with patch.object(manager, "_resolve_strategy_dir", return_value=strategy_dir):
                        with patch.object(manager, "_build_gateway_launch", return_value=launch):
                            with patch("asyncio.create_task", side_effect=_create_task):
                                started = await manager.start_instance("inst1")
                                assert started["status"] == "running"
                                assert manager._gateways["ctp-future-acc-1"]["ref_count"] == 1

                                for _ in range(40):
                                    if env_file.exists():
                                        break
                                    await asyncio.sleep(0.05)

                                assert env_file.is_file()
                                env_data = json.loads(env_file.read_text("utf-8"))
                                assert env_data["BT_STORE_PROVIDER"] == "ctp_gateway"
                                assert env_data["BT_GATEWAY_COMMAND_ENDPOINT"] == "ipc://command"
                                assert env_data["BT_GATEWAY_EVENT_ENDPOINT"] == "ipc://event"
                                assert env_data["BT_GATEWAY_MARKET_ENDPOINT"] == "ipc://market"
                                assert env_data["BT_GATEWAY_ACCOUNT_ID"] == "acc-1"
                                assert env_data["BT_GATEWAY_EXCHANGE_TYPE"] == "CTP"
                                assert env_data["BT_GATEWAY_ASSET_TYPE"] == "FUTURE"
                                assert env_data["BT_GATEWAY_START_LOCAL_RUNTIME"] == "0"

                                stopped = await manager.stop_instance("inst1")
                                assert stopped["status"] == "stopped"
                                assert "ctp-future-acc-1" not in manager._gateways

        runtime_cls.assert_called_once_with(config, account_id="acc-1")
        runtime.start_in_thread.assert_called_once()
        runtime.stop.assert_called_once()

        for task in created_tasks:
            await asyncio.wait_for(task, timeout=5)

    @pytest.mark.asyncio
    async def test_start_instance_already_running(self):
        """Test starting an already running instance.

        Verifies that a ValueError is raised when trying
        to start an instance that's already running.
        """
        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "test_strategy", "status": "running", "pid": 12345},
            }

            with patch("app.services.live_trading_manager._is_pid_alive", return_value=True):
                manager = LiveTradingManager()

                with pytest.raises(ValueError, match="already running"):
                    await manager.start_instance("inst1")

    @pytest.mark.asyncio
    async def test_start_instance_not_found(self):
        """Test starting non-existent instance.

        Verifies that a ValueError is raised when trying
        to start a non-existent instance.
        """
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()

            with pytest.raises(ValueError, match="Instance does not exist"):
                await manager.start_instance("nonexistent")

    @pytest.mark.asyncio
    async def test_start_instance_no_run_py(self):
        """Test starting instance when run.py doesn't exist.

        Verifies that a ValueError is raised when the
        strategy's run.py file is missing.
        """
        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "test_strategy", "status": "stopped"},
            }

            manager = LiveTradingManager()
            # Mock _resolve_strategy_dir to return a mock path without run.py
            mock_strategy_dir = MagicMock()
            mock_run_py = MagicMock()
            mock_run_py.is_file.return_value = False
            mock_strategy_dir.__truediv__.return_value = mock_run_py
            manager._resolve_strategy_dir = Mock(return_value=mock_strategy_dir)

            with pytest.raises(ValueError, match="run.py does not exist"):
                await manager.start_instance("inst1")


class TestStopInstance:
    """Tests for stopping instances."""

    @pytest.mark.asyncio
    async def test_stop_instance_success(self):
        """Test successful instance stop.

        Verifies that a running instance can be stopped
        and its status is updated.
        """
        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "test_strategy", "status": "running", "pid": 12345},
            }

            with patch("app.services.live_trading_manager._save_instances"):
                with patch("app.services.live_trading_manager._is_pid_alive", return_value=True):
                    manager = LiveTradingManager()

                with patch("app.services.live_trading_manager._is_pid_alive", return_value=False):
                    result = await manager.stop_instance("inst1")

                    assert result["status"] == "stopped"
                    assert result["pid"] is None

    @pytest.mark.asyncio
    async def test_stop_instance_not_found(self):
        """Test stopping non-existent instance.

        Verifies that a ValueError is raised when trying
        to stop a non-existent instance.
        """
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()

            with pytest.raises(ValueError, match="Instance does not exist"):
                await manager.stop_instance("nonexistent")

    @pytest.mark.asyncio
    async def test_stop_instance_kills_process(self):
        """Test that stopping instance kills its process.

        Verifies that the associated process is terminated
        when stopping an instance.
        """
        import os
        import signal

        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "test_strategy", "status": "running", "pid": 12345},
            }

            with patch("app.services.live_trading_manager._save_instances"):
                with patch.object(os, "kill") as mock_kill:
                    with patch(
                        "app.services.live_trading_manager._is_pid_alive", return_value=True
                    ):
                        manager = LiveTradingManager()

                    with patch(
                        "app.services.live_trading_manager._is_pid_alive", return_value=True
                    ):
                        # Add a mock process to the manager's process dict
                        # proc.terminate()/kill() are sync; proc.wait() is async.
                        mock_proc = MagicMock()
                        mock_proc.returncode = None
                        mock_proc.wait = AsyncMock()
                        mock_proc.terminate = Mock()
                        mock_proc.kill = Mock()
                        manager._processes["inst1"] = mock_proc

                        await manager.stop_instance("inst1")

                        # Should have killed the process with SIGTERM
                        mock_kill.assert_any_call(12345, signal.SIGTERM)


class TestStartAllStopAll:
    """Tests for batch start/stop operations."""

    @pytest.mark.asyncio
    async def test_start_all(self):
        """Test starting all instances.

        Verifies that all stopped instances can be
        started in batch.
        """
        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "status": "stopped"},
                "inst2": {"strategy_id": "s2", "status": "stopped"},
            }

            with patch("app.services.live_trading_manager._save_instances"):
                with patch("app.services.live_trading_manager.STRATEGIES_DIR"):
                    with patch(
                        "app.services.live_trading_manager._find_latest_log_dir", return_value=None
                    ):
                        with patch(
                            "app.services.live_trading_manager._is_pid_alive", return_value=False
                        ):
                            manager = LiveTradingManager()

                            # Use AsyncMock for the async start_instance method
                            mock_start = AsyncMock(return_value={"status": "running", "id": "test"})
                            with patch.object(manager, "start_instance", mock_start):
                                result = await manager.start_all()

                                assert result["success"] == 2
                                assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_start_all_partial_failure(self):
        """Test batch start with partial failures.

        Verifies that the result correctly reports successes
        and failures when starting all instances.
        """
        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "status": "stopped"},
                "inst2": {"strategy_id": "s2", "status": "stopped"},
            }

            with patch("app.services.live_trading_manager._save_instances"):
                with patch("app.services.live_trading_manager.STRATEGIES_DIR"):
                    with patch(
                        "app.services.live_trading_manager._find_latest_log_dir", return_value=None
                    ):
                        manager = LiveTradingManager()

                        # Mock start_instance - one succeeds, one fails
                        async def mock_start(iid):
                            if iid == "inst1":
                                return {"status": "running"}
                            else:
                                raise ValueError("Failed")

                        # Use side_effect with AsyncMock wrapper
                        mock_start_async = AsyncMock(side_effect=mock_start)
                        with patch.object(manager, "start_instance", mock_start_async):
                            result = await manager.start_all()

                            assert result["success"] == 1
                            assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_stop_all(self):
        """Test stopping all instances.

        Verifies that all running instances can be
        stopped in batch.
        """
        # Import the module to use patch.object
        from app.services import live_trading_manager

        # Create the data that will be returned consistently
        running_data = {
            "inst1": {"strategy_id": "s1", "status": "running", "pid": 12345},
            "inst2": {"strategy_id": "s2", "status": "running", "pid": 12346},
        }

        with patch.object(live_trading_manager, "_load_instances", return_value=running_data):
            with patch.object(live_trading_manager, "_save_instances"):
                with patch.object(live_trading_manager, "_is_pid_alive", return_value=True):
                    manager = live_trading_manager.LiveTradingManager()

                    # Use AsyncMock for the async stop_instance method
                    mock_stop = AsyncMock(return_value={"status": "stopped", "id": "test"})
                    with patch.object(manager, "stop_instance", mock_stop):
                        result = await manager.stop_all()

                        assert result["success"] == 2
                        assert result["failed"] == 0


class TestWaitProcess:
    """Tests for process waiting."""

    @pytest.mark.asyncio
    async def test_wait_process_success(self):
        """Test process normal completion.

        Verifies that the status is updated to stopped
        when a process completes normally.
        """
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.stderr = None

        # Track what was saved
        saved_data = {}

        def mock_save(data):
            saved_data.update(data)

        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {"inst1": {"strategy_id": "s1", "status": "running"}}
            with patch("app.services.live_trading_manager._save_instances", side_effect=mock_save):
                with patch(
                    "app.services.live_trading_manager._find_latest_log_dir", return_value=None
                ):
                    with patch("app.services.live_trading_manager.STRATEGIES_DIR"):
                        await manager._wait_process("inst1", mock_proc)

                        # Check that status was updated to stopped
                        assert "inst1" in saved_data
                        assert saved_data["inst1"]["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_wait_process_error(self):
        """Test process abnormal completion.

        Verifies that the status is updated to error
        when a process completes with an error.
        """
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()

        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"error message")

        # Track what was saved
        saved_data = {}

        def mock_save(data):
            saved_data.update(data)

        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {"inst1": {"strategy_id": "s1", "status": "running"}}
            with patch("app.services.live_trading_manager._save_instances", side_effect=mock_save):
                with patch(
                    "app.services.live_trading_manager._find_latest_log_dir", return_value=None
                ):
                    with patch("app.services.live_trading_manager.STRATEGIES_DIR"):
                        await manager._wait_process("inst1", mock_proc)

                        # Check that status was updated to error
                        assert "inst1" in saved_data
                        assert saved_data["inst1"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_wait_process_ignores_stale_callback_for_restarted_instance(self):
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            manager = LiveTradingManager()

        old_proc = AsyncMock()
        old_proc.pid = 111
        old_proc.returncode = 0
        old_proc.stderr = None
        new_proc = Mock(pid=222)
        manager._processes["inst1"] = new_proc
        saved_data = {}
        released = []

        def mock_save(data):
            saved_data.update(data)

        with patch("app.services.live_trading_manager._load_instances") as mock_load:
            mock_load.return_value = {
                "inst1": {"strategy_id": "s1", "status": "running", "pid": 222}
            }
            with patch("app.services.live_trading_manager._save_instances", side_effect=mock_save):
                with patch(
                    "app.services.live_trading_manager._find_latest_log_dir", return_value=None
                ):
                    with patch.object(
                        manager, "_release_gateway_for_instance", side_effect=released.append
                    ):
                        await manager._wait_process("inst1", old_proc)

        assert saved_data == {}
        assert released == []
        assert manager._processes["inst1"] is new_proc


class TestKillPid:
    """Tests for process termination."""

    def test_kill_pid_success(self):
        """Test successful process termination.

        Verifies that os.kill is called to terminate
        a process.
        """
        import os

        # Patch os module directly since _kill_pid imports os locally
        with patch.object(os, "kill") as mock_kill:
            LiveTradingManager._kill_pid(12345)
            mock_kill.assert_called_once()

    def test_kill_pid_process_not_found(self):
        """Test terminating non-existent process.

        Verifies that no error is raised when trying
        to kill a non-existent process.
        """
        import os

        # Patch os module directly since _kill_pid imports os locally
        with patch.object(os, "kill", side_effect=ProcessLookupError):
            # Should not raise an error
            LiveTradingManager._kill_pid(999999)


class TestGetLiveTradingManager:
    """Tests for getting the manager singleton."""

    def test_get_manager_singleton(self):
        """Test singleton pattern.

        Verifies that get_live_trading_manager returns
        the same instance on subsequent calls.
        """
        with patch("app.services.live_trading_manager._manager", None):
            with patch("app.services.live_trading_manager._load_instances", return_value={}):
                manager1 = get_live_trading_manager()
                manager2 = get_live_trading_manager()

        assert manager1 is manager2

    def test_manager_processes_dict(self):
        """Test manager's processes dictionary.

        Verifies that the manager has a _processes
        attribute that is a dictionary.
        """
        with patch("app.services.live_trading_manager._manager", None):
            with patch("app.services.live_trading_manager._load_instances", return_value={}):
                manager = get_live_trading_manager()
        assert hasattr(manager, "_processes")
        assert isinstance(manager._processes, dict)


class TestIntegration:
    """Integration tests."""

    def test_full_lifecycle(self):
        """Test complete instance lifecycle.

        Verifies the full lifecycle of an instance:
        add, get, list, and remove.
        """
        with patch("app.services.live_trading_manager._load_instances", return_value={}):
            with patch("app.services.live_trading_manager._save_instances"):
                with patch("app.services.live_trading_manager.STRATEGIES_DIR") as mock_dir:
                    with patch("app.services.live_trading_manager.get_template_by_id") as mock_tpl:
                        with patch(
                            "app.services.live_trading_manager._find_latest_log_dir",
                            return_value=None,
                        ):
                            # Setup strategy directory
                            mock_strategy_dir = MagicMock()
                            mock_run_py = MagicMock()
                            mock_run_py.is_file.return_value = True
                            mock_strategy_dir.__truediv__.return_value = mock_run_py
                            mock_dir.__truediv__ = Mock(return_value=mock_strategy_dir)
                            mock_tpl.return_value = MagicMock(name="Test Strategy")

                            manager = LiveTradingManager()

                            # Add instance
                            inst = manager.add_instance(
                                "test_strategy", {"param": 10}, user_id="user1"
                            )
                            inst_id = inst["id"]

                            # Get instance
                            retrieved = manager.get_instance(inst_id, user_id="user1")
                            assert retrieved is not None

                            # List instances
                            instances = manager.list_instances("user1")
                            assert len(instances) == 1

                            # Remove instance
                            result = manager.remove_instance(inst_id, user_id="user1")
                            assert result is True
