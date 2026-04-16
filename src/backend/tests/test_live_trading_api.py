"""
Live Trading Management API Tests.

Tests:
    - Live trading strategy list
    - Add/remove live trading strategies
    - Start/stop strategies
    - Batch start/stop
    - Live trading analytics endpoints
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.schemas.live_trading_instance import LiveInstanceCreate


@pytest.mark.asyncio
class TestLiveTradingList:
    """Tests for live trading strategy list endpoint."""

    async def test_list_instances_empty(self, client: AsyncClient, auth_headers):
        """Test empty list response.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        mock_manager = MagicMock()
        mock_manager.list_instances.return_value = []

        with patch("app.api.live_trading_api.get_live_trading_manager", return_value=mock_manager):
            response = await client.get("/api/v1/live-trading/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "instances" in data
        assert data["total"] == 0
        assert len(data["instances"]) == 0

    async def test_list_instances_requires_auth(self, client: AsyncClient):
        """Test that authentication is required.

        Args:
            client: Async HTTP client fixture.
        """
        response = await client.get("/api/v1/live-trading/")
        assert response.status_code == 401  # Unauthorized

    async def test_list_gateway_presets_exposes_ib_web(self, client: AsyncClient, auth_headers):
        response = await client.get("/api/v1/live-trading/presets", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
        ib_presets = {
            item["id"]: item
            for item in data["presets"]
            if item["id"] in {"ib_web_stock_gateway", "ib_web_futures_gateway"}
        }
        assert set(ib_presets) == {"ib_web_stock_gateway", "ib_web_futures_gateway"}
        stock_preset = ib_presets["ib_web_stock_gateway"]
        stock_gateway = stock_preset["params"]["gateway"]
        assert stock_preset["description"] == "IB Web preset for US stock trading via gateway mode."
        assert stock_preset["editable_fields"] == [
            {
                "key": "account_id",
                "label": "账户",
                "input_type": "string",
                "placeholder": "如 DU123456",
            },
            {
                "key": "base_url",
                "label": "Base URL",
                "input_type": "string",
                "placeholder": "如 https://localhost:5000",
            },
            {
                "key": "verify_ssl",
                "label": "SSL校验",
                "input_type": "boolean",
                "placeholder": None,
            },
        ]
        assert stock_gateway["provider"] == "gateway"
        assert stock_gateway["exchange_type"] == "IB_WEB"
        assert stock_gateway["asset_type"] == "STK"

        futures_preset = ib_presets["ib_web_futures_gateway"]
        futures_gateway = futures_preset["params"]["gateway"]
        assert (
            futures_preset["description"] == "IB Web preset for futures trading via gateway mode."
        )
        assert len(futures_preset["editable_fields"]) == 3
        assert futures_gateway["provider"] == "gateway"
        assert futures_gateway["exchange_type"] == "IB_WEB"
        assert futures_gateway["asset_type"] == "FUT"

    async def test_list_gateway_presets_ctp_has_metadata(self, client: AsyncClient, auth_headers):
        response = await client.get("/api/v1/live-trading/presets", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        ctp = next(p for p in data["presets"] if p["id"] == "ctp_futures_gateway")
        assert ctp["description"] == "Shared CTP gateway preset for domestic futures accounts."
        assert len(ctp["editable_fields"]) == 1
        assert ctp["editable_fields"][0]["key"] == "account_id"
        assert ctp["editable_fields"][0]["input_type"] == "string"
        assert ctp["params"]["gateway"]["provider"] == "ctp_gateway"
        assert ctp["params"]["gateway"]["exchange_type"] == "CTP"

    async def test_list_gateway_presets_binance_has_metadata(
        self, client: AsyncClient, auth_headers
    ):
        response = await client.get("/api/v1/live-trading/presets", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        bn = next(p for p in data["presets"] if p["id"] == "binance_swap_gateway")
        assert bn["description"] == "Binance SWAP gateway preset for perpetual futures trading."
        assert len(bn["editable_fields"]) == 3
        field_keys = [f["key"] for f in bn["editable_fields"]]
        assert field_keys == ["account_id", "api_key", "secret_key"]
        assert bn["params"]["gateway"]["exchange_type"] == "BINANCE"
        assert bn["params"]["gateway"]["asset_type"] == "SWAP"

    async def test_list_gateway_presets_okx_has_metadata(self, client: AsyncClient, auth_headers):
        response = await client.get("/api/v1/live-trading/presets", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        okx = next(p for p in data["presets"] if p["id"] == "okx_swap_gateway")
        assert okx["description"] == "OKX SWAP gateway preset for perpetual futures trading."
        assert len(okx["editable_fields"]) == 4
        field_keys = [f["key"] for f in okx["editable_fields"]]
        assert field_keys == ["account_id", "api_key", "secret_key", "passphrase"]
        assert okx["params"]["gateway"]["exchange_type"] == "OKX"
        assert okx["params"]["gateway"]["asset_type"] == "SWAP"
        assert "passphrase" in okx["params"]["gateway"]

    async def test_list_gateway_presets_total_includes_all_six(
        self, client: AsyncClient, auth_headers
    ):
        response = await client.get("/api/v1/live-trading/presets", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 6
        ids = {p["id"] for p in data["presets"]}
        assert {
            "ctp_futures_gateway",
            "ib_web_stock_gateway",
            "ib_web_futures_gateway",
            "binance_swap_gateway",
            "okx_swap_gateway",
            "mt5_forex_gateway",
        }.issubset(ids)

    async def test_list_gateway_presets_mt5_has_metadata(self, client: AsyncClient, auth_headers):
        response = await client.get("/api/v1/live-trading/presets", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        mt5 = next(p for p in data["presets"] if p["id"] == "mt5_forex_gateway")
        assert (
            mt5["description"]
            == "MT5 Forex gateway preset for MetaTrader 5 trading via pymt5 WebSocket."
        )
        assert len(mt5["editable_fields"]) == 4
        field_keys = [f["key"] for f in mt5["editable_fields"]]
        assert field_keys == ["account_id", "login", "password", "ws_uri"]
        assert mt5["params"]["gateway"]["exchange_type"] == "MT5"
        assert mt5["params"]["gateway"]["asset_type"] == "OTC"
        assert mt5["params"]["gateway"]["provider"] == "mt5_gateway"

    async def test_gateway_health_empty(self, client: AsyncClient, auth_headers):
        """Gateway health returns empty list when no gateways are active."""
        response = await client.get("/api/v1/live-trading/gateways/health", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["gateways"] == []

    async def test_gateway_health_with_subprocess_gateways(self, client: AsyncClient, auth_headers):
        with patch("app.api.live_trading_api.get_live_trading_manager") as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_gateway_health.return_value = [
                {
                    "gateway_key": "manual:CTP:089763",
                    "state": "running",
                    "is_healthy": True,
                    "market_connection": "connected",
                    "trade_connection": "connected",
                    "uptime_sec": 0,
                    "last_heartbeat": None,
                    "heartbeat_age_sec": None,
                    "last_tick_time": None,
                    "last_order_time": None,
                    "strategy_count": 0,
                    "symbol_count": 0,
                    "tick_count": 0,
                    "order_count": 0,
                    "recent_errors": [],
                    "ref_count": 0,
                    "instances": [],
                    "exchange": "CTP",
                    "asset_type": "FUTURE",
                    "account_id": "089763",
                }
            ]
            mock_get_mgr.return_value = mock_mgr

            response = await client.get(
                "/api/v1/live-trading/gateways/health", headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["gateways"][0]["gateway_key"] == "manual:CTP:089763"
        assert data["gateways"][0]["market_connection"] == "connected"

    async def test_connect_gateway_error_returns_400_not_500(
        self, client: AsyncClient, auth_headers
    ):
        with patch("app.api.live_trading_api.get_live_trading_manager") as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.connect_gateway.return_value = {
                "gateway_key": "manual:CTP:089763",
                "status": "error",
                "message": "CTP连接失败: RuntimeError: ctp market not ready",
            }
            mock_get_mgr.return_value = mock_mgr

            response = await client.post(
                "/api/v1/live-trading/gateways/connect",
                headers=auth_headers,
                json={
                    "exchange_type": "CTP",
                    "credentials": {
                        "broker_id": "9999",
                        "user_id": "089763",
                        "password": "secret",
                        "td_front": "tcp://127.0.0.1:1",
                        "md_front": "tcp://127.0.0.1:2",
                    },
                },
            )

        assert response.status_code == 400
        payload = response.json()
        assert "CTP连接失败" in str(payload)

    async def test_gateway_credentials_prefers_ib_web_env_values(
        self, client: AsyncClient, auth_headers
    ):
        fake_settings = SimpleNamespace(
            CTP_BROKER_ID="",
            CTP_USER_ID="",
            CTP_INVESTOR_ID="",
            CTP_PASSWORD="",
            CTP_APP_ID="simnow_client_test",
            CTP_AUTH_CODE="0000000000000000",
            MT5_LOGIN="",
            MT5_PASSWORD="",
            MT5_SERVER="",
            MT5_WS_URI="",
            MT5_SYMBOL_SUFFIX="",
            MT5_TIMEOUT=60,
            MT5_DEMO_LOGIN="",
            MT5_DEMO_PASSWORD="",
            MT5_DEMO_SERVER="",
            MT5_DEMO_WS_URI="",
            MT5_LIVE_LOGIN="",
            MT5_LIVE_PASSWORD="",
            MT5_LIVE_SERVER="",
            MT5_LIVE_WS_URI="",
            IB_ACCOUNT_ID="legacy-acc",
            IB_ASSET_TYPE="STK",
            IB_BASE_URL="https://legacy.localhost:5000/v1/api",
            IB_ACCESS_TOKEN="legacy-token",
            IB_VERIFY_SSL=False,
            IB_TIMEOUT=10,
            IB_COOKIE_SOURCE="file:legacy.json",
            IB_COOKIE_BROWSER="chrome",
            IB_COOKIE_PATH="/legacy",
            IB_USERNAME="legacy-user",
            IB_PASSWORD="legacy-pass",
            IB_LOGIN_BROWSER="chrome",
            IB_LOGIN_HEADLESS=False,
            IB_LOGIN_TIMEOUT=180,
            IB_COOKIE_OUTPUT="legacy-output.json",
            IB_WEB_ACCOUNT_ID="DUP447807",
            IB_WEB_ASSET_TYPE="STK",
            IB_WEB_BASE_URL="https://localhost:5000/v1/api",
            IB_WEB_ACCESS_TOKEN="",
            IB_WEB_VERIFY_SSL=False,
            IB_WEB_TIMEOUT=10,
            IB_WEB_COOKIE_SOURCE="file:../bt_api_py/configs/ibkr_cookies.json",
            IB_WEB_COOKIE_BROWSER="chrome",
            IB_WEB_COOKIE_PATH="/sso",
            IB_WEB_USERNAME="test-ib-web-user",
            IB_WEB_PASSWORD="test-ib-web-pass",
            IB_WEB_LOGIN_MODE="paper",
            IB_WEB_LOGIN_BROWSER="chrome",
            IB_WEB_LOGIN_HEADLESS=False,
            IB_WEB_LOGIN_TIMEOUT=180,
            IB_WEB_COOKIE_OUTPUT="../bt_api_py/configs/ibkr_cookies.json",
            IB_PAPER_ACCOUNT_ID="",
            IB_PAPER_ASSET_TYPE="",
            IB_PAPER_BASE_URL="",
            IB_PAPER_ACCESS_TOKEN="",
            IB_PAPER_VERIFY_SSL=False,
            IB_PAPER_TIMEOUT=0,
            IB_PAPER_COOKIE_SOURCE="",
            IB_PAPER_COOKIE_BROWSER="",
            IB_PAPER_COOKIE_PATH="",
            IB_LIVE_ACCOUNT_ID="",
            IB_LIVE_ASSET_TYPE="",
            IB_LIVE_BASE_URL="",
            IB_LIVE_ACCESS_TOKEN="",
            IB_LIVE_VERIFY_SSL=False,
            IB_LIVE_TIMEOUT=0,
            IB_LIVE_COOKIE_SOURCE="",
            IB_LIVE_COOKIE_BROWSER="",
            IB_LIVE_COOKIE_PATH="",
            BINANCE_ACCOUNT_ID="",
            BINANCE_ASSET_TYPE="SWAP",
            BINANCE_API_KEY="",
            BINANCE_SECRET_KEY="",
            BINANCE_TESTNET=False,
            BINANCE_BASE_URL="",
            OKX_ACCOUNT_ID="",
            OKX_ASSET_TYPE="SWAP",
            OKX_API_KEY="",
            OKX_SECRET_KEY="",
            OKX_PASSPHRASE="",
            OKX_TESTNET=False,
            OKX_BASE_URL="",
        )
        with patch("app.config.get_settings", return_value=fake_settings):
            response = await client.get(
                "/api/v1/live-trading/gateways/credentials", headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()["IB_WEB"]
        assert data["account_id"] == "DUP447807"
        assert data["base_url"] == "https://localhost:5000/v1/api"
        assert data["cookie_source"] == "file:../bt_api_py/configs/ibkr_cookies.json"
        assert data["username"] == "test-ib-web-user"
        assert data["password"] == "test-ib-web-pass"
        assert data["paper"]["account_id"] == "DUP447807"
        assert data["paper"]["login_mode"] == "paper"

    async def test_live_instance_create_schema_example_exposes_ib_web_gateway(self):
        schema = LiveInstanceCreate.model_json_schema()
        example = schema["example"]
        gateway = example["params"]["gateway"]
        assert gateway["provider"] == "gateway"
        assert gateway["exchange_type"] == "IB_WEB"
        assert gateway["asset_type"] == "STK"


@pytest.mark.asyncio
class TestLiveTradingCreate:
    """Tests for creating live trading strategies."""

    async def test_add_instance_success(self, client: AsyncClient, auth_headers):
        """Test successful strategy addition.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        mock_manager = MagicMock()
        mock_manager.add_instance.return_value = {
            "id": "instance-123",
            "strategy_id": "test_strategy",
            "strategy_name": "Test Strategy",
            "status": "stopped",
            "pid": None,
            "error": None,
            "params": {"fast": 10, "slow": 20},
            "created_at": "2024-01-01T00:00:00",
            "started_at": None,
            "stopped_at": None,
            "log_dir": None,
        }

        with patch("app.api.live_trading_api.get_live_trading_manager", return_value=mock_manager):
            response = await client.post(
                "/api/v1/live-trading/",
                headers=auth_headers,
                json={"strategy_id": "test_strategy", "params": {"fast": 10, "slow": 20}},
            )

        assert response.status_code == 200

    async def test_add_instance_invalid_strategy(self, client: AsyncClient, auth_headers):
        """Test adding non-existent strategy.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        response = await client.post(
            "/api/v1/live-trading/",
            headers=auth_headers,
            json={"strategy_id": "non_existent_strategy", "params": {}},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
class TestLiveTradingDelete:
    """Tests for deleting live trading strategies."""

    async def test_remove_instance_not_found(self, client: AsyncClient, auth_headers):
        """Test removing non-existent instance.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        response = await client.delete("/api/v1/live-trading/non_existent_id", headers=auth_headers)
        assert response.status_code == 404


@pytest.mark.asyncio
class TestLiveTradingGetDetail:
    """Tests for getting live trading strategy details."""

    async def test_get_instance_not_found(self, client: AsyncClient, auth_headers):
        """Test getting non-existent instance.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        response = await client.get("/api/v1/live-trading/non_existent_id", headers=auth_headers)
        assert response.status_code == 404


@pytest.mark.asyncio
class TestLiveTradingControl:
    """Tests for live trading strategy control."""

    async def test_start_instance_not_found(self, client: AsyncClient, auth_headers):
        """Test starting non-existent instance.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        response = await client.post(
            "/api/v1/live-trading/non_existent_id/start", headers=auth_headers
        )
        assert response.status_code == 400

    async def test_stop_instance_not_found(self, client: AsyncClient, auth_headers):
        """Test stopping non-existent instance.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        response = await client.post(
            "/api/v1/live-trading/non_existent_id/stop", headers=auth_headers
        )
        assert response.status_code == 400

    async def test_start_all(self, client: AsyncClient, auth_headers):
        """Test batch start all instances.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        with patch(
            "app.services.live_trading_manager.LiveTradingManager.start_all", new_callable=AsyncMock
        ) as mock_start:
            mock_start.return_value = {"started": 0, "failed": 0, "errors": []}
            response = await client.post("/api/v1/live-trading/start-all", headers=auth_headers)
            assert response.status_code == 200

    async def test_stop_all(self, client: AsyncClient, auth_headers):
        """Test batch stop all instances.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        with patch(
            "app.services.live_trading_manager.LiveTradingManager.stop_all", new_callable=AsyncMock
        ) as mock_stop:
            mock_stop.return_value = {"stopped": 0, "failed": 0, "errors": []}
            response = await client.post("/api/v1/live-trading/stop-all", headers=auth_headers)
            assert response.status_code == 200


@pytest.mark.asyncio
class TestLiveTradingAnalytics:
    """Tests for live trading analytics endpoints."""

    async def test_get_live_detail_not_found(self, client: AsyncClient, auth_headers):
        """Test getting analytics for non-existent instance.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        response = await client.get(
            "/api/v1/live-trading/non_existent_id/detail", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_get_live_kline_not_found(self, client: AsyncClient, auth_headers):
        """Test getting K-line data for non-existent instance.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        response = await client.get(
            "/api/v1/live-trading/non_existent_id/kline", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_get_live_monthly_returns_not_found(self, client: AsyncClient, auth_headers):
        """Test getting monthly returns for non-existent instance.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        response = await client.get(
            "/api/v1/live-trading/non_existent_id/monthly-returns", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_get_live_detail_with_valid_instance(self, client: AsyncClient, auth_headers):
        """Test getting analytics details for valid instance.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        # Mock the manager and log parser
        with patch("app.api.live_trading_api.get_live_trading_manager") as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_instance.return_value = {
                "instance_id": "inst1",
                "strategy_id": "strategy1",
                "strategy_name": "Dual MA",
            }
            mock_get_mgr.return_value = mock_mgr

            with patch("app.api.live_trading_api.parse_all_logs") as mock_parse:
                mock_parse.return_value = {
                    "total_return": 0.15,
                    "annual_return": 0.20,
                    "sharpe_ratio": 1.5,
                    "max_drawdown": -0.08,
                    "win_rate": 0.60,
                    "total_trades": 50,
                    "equity_dates": ["2024-01-01", "2024-01-02"],
                    "equity_curve": [100000, 101000],
                    "cash_curve": [50000, 50500],
                    "drawdown_curve": [0, -0.02],
                    "initial_cash": 100000,
                    "final_value": 115000,
                    "trades": [],
                }

                response = await client.get(
                    "/api/v1/live-trading/inst1/detail", headers=auth_headers
                )
                assert response.status_code == 200

    async def test_get_live_detail_no_log_data(self, client: AsyncClient, auth_headers):
        """Test getting details when no log data exists.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        with patch("app.api.live_trading_api.get_live_trading_manager") as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_instance.return_value = {
                "instance_id": "inst1",
                "strategy_id": "strategy1",
            }
            mock_get_mgr.return_value = mock_mgr

            with patch("app.api.live_trading_api.parse_all_logs") as mock_parse:
                mock_parse.return_value = None

                response = await client.get(
                    "/api/v1/live-trading/inst1/detail", headers=auth_headers
                )
                assert response.status_code == 404


@pytest.mark.asyncio
class TestLiveTradingKline:
    """Tests for live trading K-line endpoints."""

    async def test_get_kline_with_log_data(self, client: AsyncClient, auth_headers):
        """Test getting K-line with log data.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        with patch("app.api.live_trading_api.get_live_trading_manager") as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_instance.return_value = {
                "instance_id": "inst1",
                "strategy_id": "strategy1",
            }
            mock_get_mgr.return_value = mock_mgr

            with patch("app.api.live_trading_api.find_latest_log_dir") as mock_find:
                with patch("app.api.live_trading_api.parse_data_log") as mock_parse_data:
                    with patch("app.api.live_trading_api.parse_trade_log") as mock_parse_trade:
                        mock_find.return_value = Path("/tmp/logs")
                        mock_parse_data.return_value = {
                            "dates": ["2024-01-01"],
                            "ohlc": [[10, 10.5, 9.5, 10.2]],
                            "volumes": [1000],
                            "indicators": {},
                        }
                        mock_parse_trade.return_value = []

                        response = await client.get(
                            "/api/v1/live-trading/inst1/kline", headers=auth_headers
                        )
                        assert response.status_code == 200

    async def test_get_kline_no_log_dir(self, client: AsyncClient, auth_headers):
        """Test getting K-line when no log directory exists.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        with patch("app.api.live_trading_api.get_live_trading_manager") as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_instance.return_value = {
                "instance_id": "inst1",
                "strategy_id": "strategy1",
            }
            mock_get_mgr.return_value = mock_mgr

            with patch("app.api.live_trading_api.find_latest_log_dir") as mock_find:
                mock_find.return_value = None

                response = await client.get(
                    "/api/v1/live-trading/inst1/kline", headers=auth_headers
                )
                assert response.status_code == 404


@pytest.mark.asyncio
class TestLiveTradingMonthlyReturns:
    """Tests for live trading monthly returns endpoints."""

    async def test_get_monthly_returns_with_data(self, client: AsyncClient, auth_headers):
        """Test getting monthly returns with data.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        with patch("app.api.live_trading_api.get_live_trading_manager") as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_instance.return_value = {
                "instance_id": "inst1",
                "strategy_id": "strategy1",
            }
            mock_get_mgr.return_value = mock_mgr

            with patch("app.api.live_trading_api.find_latest_log_dir") as mock_find:
                with patch("app.api.live_trading_api.parse_value_log") as mock_parse:
                    mock_find.return_value = Path("/tmp/logs")
                    mock_parse.return_value = {
                        "dates": ["2024-01-01", "2024-01-31", "2024-02-01"],
                        "equity_curve": [100000, 105000, 110000],
                    }

                    response = await client.get(
                        "/api/v1/live-trading/inst1/monthly-returns", headers=auth_headers
                    )
                    assert response.status_code == 200

    async def test_get_monthly_returns_empty_data(self, client: AsyncClient, auth_headers):
        """Test getting monthly returns with empty data.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        with patch("app.api.live_trading_api.get_live_trading_manager") as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_instance.return_value = {
                "instance_id": "inst1",
                "strategy_id": "strategy1",
            }
            mock_get_mgr.return_value = mock_mgr

            with patch("app.api.live_trading_api.find_latest_log_dir") as mock_find:
                with patch("app.api.live_trading_api.parse_value_log") as mock_parse:
                    mock_find.return_value = Path("/tmp/logs")
                    mock_parse.return_value = {
                        "dates": [],
                        "equity_curve": [],
                    }

                    response = await client.get(
                        "/api/v1/live-trading/inst1/monthly-returns", headers=auth_headers
                    )
                    assert response.status_code == 200


@pytest.mark.asyncio
class TestLiveTradingStartStop:
    """Extended tests for start/stop endpoints."""

    async def test_start_instance_success(self, client: AsyncClient, auth_headers):
        """Test successful instance start.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        with patch("app.api.live_trading_api.get_live_trading_manager") as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.start_instance = AsyncMock(
                return_value={
                    "id": "inst1",
                    "strategy_id": "strategy1",
                    "status": "running",
                }
            )
            mock_get_mgr.return_value = mock_mgr

            response = await client.post("/api/v1/live-trading/inst1/start", headers=auth_headers)
            assert response.status_code == 200

    async def test_stop_instance_success(self, client: AsyncClient, auth_headers):
        """Test successful instance stop.

        Args:
            client: Async HTTP client fixture.
            auth_headers: Authentication headers fixture.
        """
        with patch("app.api.live_trading_api.get_live_trading_manager") as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.stop_instance = AsyncMock(
                return_value={
                    "id": "inst1",
                    "strategy_id": "strategy1",
                    "status": "stopped",
                }
            )
            mock_get_mgr.return_value = mock_mgr

            response = await client.post("/api/v1/live-trading/inst1/stop", headers=auth_headers)
            assert response.status_code == 200


@pytest.mark.asyncio
class TestLiveTradingManager:
    """Tests for LiveTradingManager service."""

    async def test_manager_singleton(self):
        """Test manager singleton pattern.

        Verifies that get_live_trading_manager returns
        the same instance each time.
        """
        from app.services.live_trading_manager import LiveTradingManager, get_live_trading_manager

        with patch("app.services.live_trading_manager._manager", None):
            with patch("app.services.live_trading_manager._load_instances", return_value={}):
                mgr1 = get_live_trading_manager()
                mgr2 = get_live_trading_manager()
        assert isinstance(mgr1, LiveTradingManager)
        assert mgr1 is mgr2

    async def test_list_instances_filters_by_user(self):
        """Test listing instances filtered by user.

        Verifies that list_instances returns only
        instances belonging to the specified user.
        """
        from app.services.live_trading_manager import LiveTradingManager

        with patch(
            "app.services.live_trading_manager._load_instances",
            return_value={
                "inst1": {
                    "id": "inst1",
                    "strategy_id": "test",
                    "user_id": "user1",
                    "status": "stopped",
                },
                "inst2": {
                    "id": "inst2",
                    "strategy_id": "test",
                    "user_id": "user2",
                    "status": "stopped",
                },
            },
        ):
            mgr = LiveTradingManager()
            instances = mgr.list_instances(user_id="user1")
            assert len(instances) == 1
            assert instances[0]["id"] == "inst1"
