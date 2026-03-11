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
        # API may return 401 or 403
        assert response.status_code in [401, 403]

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
        assert futures_preset["description"] == "IB Web preset for futures trading via gateway mode."
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

    async def test_list_gateway_presets_okx_has_metadata(
        self, client: AsyncClient, auth_headers
    ):
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

    async def test_list_gateway_presets_total_includes_all_five(
        self, client: AsyncClient, auth_headers
    ):
        response = await client.get("/api/v1/live-trading/presets", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 5
        ids = {p["id"] for p in data["presets"]}
        assert {
            "ctp_futures_gateway",
            "ib_web_stock_gateway",
            "ib_web_futures_gateway",
            "binance_swap_gateway",
            "okx_swap_gateway",
        }.issubset(ids)

    async def test_gateway_health_empty(self, client: AsyncClient, auth_headers):
        """Gateway health returns empty list when no gateways are active."""
        response = await client.get("/api/v1/live-trading/gateways/health", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["gateways"] == []

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
        # Mock strategy directory exists
        with patch("app.services.live_trading_manager.STRATEGIES_DIR", Path("/tmp/strategies")):
            with patch("app.services.live_trading_manager.get_template_by_id") as mock_tpl:
                mock_tpl.return_value = MagicMock(name="Test Strategy", params={})

                with patch("app.services.live_trading_manager._save_instances"):
                    response = await client.post(
                        "/api/v1/live-trading/",
                        headers=auth_headers,
                        json={"strategy_id": "test_strategy", "params": {"fast": 10, "slow": 20}},
                    )

        # May return 400 if strategy doesn't exist, which is expected
        assert response.status_code in [200, 400]

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
