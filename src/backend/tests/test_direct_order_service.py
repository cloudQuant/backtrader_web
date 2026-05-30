"""Tests for DirectOrderService - trade execution bridge."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.ai_trading import OrderType, TradeAction, TradingIntent
from app.services.direct_order_service import DirectOrderService


class TestDirectOrderServiceMapOrderType:
    """Test order type mapping."""

    def test_market(self):
        assert DirectOrderService._map_order_type(OrderType.MARKET) == "market"

    def test_limit(self):
        assert DirectOrderService._map_order_type(OrderType.LIMIT) == "limit"

    def test_stop(self):
        assert DirectOrderService._map_order_type(OrderType.STOP) == "stop"

    def test_stop_limit(self):
        assert DirectOrderService._map_order_type(OrderType.STOP_LIMIT) == "stop_limit"


class TestDirectOrderServiceBuildOrderPayload:
    """Test ZMQ order payload building."""

    def test_buy_market_order(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            price=None,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert payload["symbol"] == "rb2501"
        assert payload["side"] == "buy"
        assert payload["size"] == 10
        assert payload["offset"] == "open"
        assert payload["price"] == 0  # Market order
        assert payload["strategy_id"] == "ai_trading"
        assert "request_id" in payload

    def test_sell_limit_order(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="i2501",
            quantity=5,
            price=800.0,
            order_type=OrderType.LIMIT,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert payload["symbol"] == "i2501"
        assert payload["side"] == "sell"
        assert payload["size"] == 5
        assert payload["price"] == 800.0

    def test_close_action_sets_offset_close(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            quantity=10,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert payload["offset"] == "close"

    def test_exchange_mapping_binance(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="BTCUSDT",
            exchange="binance",
            quantity=1,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert payload["exchange_id"] == "BINANCE"

    def test_exchange_mapping_okx(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="ETHUSDT",
            exchange="okx",
            quantity=1,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert payload["exchange_id"] == "OKX"

    def test_exchange_mapping_ctp_no_exchange_id(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            exchange="ctp",
            quantity=1,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        # CTP maps to empty string, so exchange_id should not be set
        assert "exchange_id" not in payload

    def test_no_exchange_no_exchange_id(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert "exchange_id" not in payload

    def test_quantity_defaults_to_1(self):
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=None,
            order_type=OrderType.MARKET,
            confidence=0.9,
        )
        payload = service._build_order_payload(intent)
        assert payload["size"] == 1


class TestDirectOrderServicePaperTrade:
    """Test paper trade execution."""

    @pytest.mark.asyncio
    async def test_query_action(self):
        """QUERY action should query positions."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.QUERY,
            confidence=0.9,
        )

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.list_positions = AsyncMock(return_value=([], 0))

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is True
            assert result["type"] == "query"

    @pytest.mark.asyncio
    async def test_unsupported_action(self):
        """Unsupported actions return error."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CANCEL,
            confidence=0.9,
        )

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is False
            assert "Unsupported action" in result["error"]

    @pytest.mark.asyncio
    async def test_buy_order_success(self):
        """Successful buy order execution."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            price=3500.0,
            order_type=OrderType.LIMIT,
            confidence=0.9,
        )

        mock_order = MagicMock()
        mock_order.id = "order123"
        mock_order.status = "submitted"

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.submit_order = AsyncMock(return_value=mock_order)

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is True
            assert result["type"] == "paper_trade"
            assert result["order_id"] == "order123"
            assert result["symbol"] == "rb2501"
            assert result["quantity"] == 10
            assert result["side"] == "buy"

    @pytest.mark.asyncio
    async def test_sell_order_success(self):
        """Successful sell order execution."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.SELL,
            symbol="BTCUSDT",
            quantity=1,
            price=50000.0,
            order_type=OrderType.LIMIT,
            confidence=0.9,
        )

        mock_order = MagicMock()
        mock_order.id = "order456"
        mock_order.status = "submitted"

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.submit_order = AsyncMock(return_value=mock_order)

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is True
            assert result["side"] == "sell"

    @pytest.mark.asyncio
    async def test_value_error_handled(self):
        """ValueError from paper trading service is handled gracefully."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            confidence=0.9,
        )

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.submit_order = AsyncMock(side_effect=ValueError("Insufficient balance"))

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is False
            assert "Insufficient balance" in result["error"]

    @pytest.mark.asyncio
    async def test_generic_exception_handled(self):
        """Generic exceptions are handled gracefully."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=10,
            confidence=0.9,
        )

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(
            side_effect=RuntimeError("DB connection failed")
        )

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is False
            assert "DB connection failed" in result["error"]

    @pytest.mark.asyncio
    async def test_creates_account_when_none_exists(self):
        """Creates a new account when user has no active accounts."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.QUERY,
            confidence=0.9,
        )

        mock_account = MagicMock()
        mock_account.id = "new_acc"

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([], 0))
        mock_paper_service.create_account = AsyncMock(return_value=mock_account)
        mock_paper_service.list_positions = AsyncMock(return_value=([], 0))

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is True
            mock_paper_service.create_account.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_position_success(self):
        """Close position submits counter-order."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="rb2501",
            confidence=0.9,
        )

        mock_position = MagicMock()
        mock_position.symbol = "RB2501"
        mock_position.size = 10

        mock_order = MagicMock()
        mock_order.id = "close_order"

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.list_positions = AsyncMock(return_value=([mock_position], 1))
        mock_paper_service.submit_order = AsyncMock(return_value=mock_order)

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is True
            assert result["type"] == "close_position"
            assert result["side"] == "sell"
            assert result["size"] == 10

    @pytest.mark.asyncio
    async def test_close_position_not_found(self):
        """Close position fails when no matching position exists."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CLOSE,
            symbol="i2501",
            confidence=0.9,
        )

        mock_paper_service = AsyncMock()
        mock_paper_service.list_accounts = AsyncMock(return_value=([MagicMock(id="acc1")], 1))
        mock_paper_service.list_positions = AsyncMock(return_value=([], 0))

        with patch(
            "app.services.paper_trading_service.PaperTradingService",
            return_value=mock_paper_service,
        ):
            result = await service.execute_paper_trade(intent, user_id="user1")
            assert result["success"] is False
            assert "no_position" in result["error"]


class TestDirectOrderServiceLiveTrade:
    """Test live trade execution."""

    @pytest.mark.asyncio
    async def test_no_gateway_available(self):
        """Returns error when no gateway is connected."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
        )

        with patch.object(service, "_find_available_gateway", return_value=None):
            result = await service.execute_live_trade(intent, user_id="user1")
            assert result["success"] is False
            assert result["error"] == "no_gateway"

    @pytest.mark.asyncio
    async def test_gateway_not_found(self):
        """Returns error when specified gateway is not connected."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=1,
            confidence=0.9,
        )

        with patch.object(service, "_get_gateway_command_endpoint", return_value=None):
            result = await service.execute_live_trade(
                intent, user_id="user1", gateway_id="invalid_gw"
            )
            assert result["success"] is False
            assert result["error"] == "gateway_not_found"

    @pytest.mark.asyncio
    async def test_unsupported_action_live(self):
        """Unsupported actions return error for live trading."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.CANCEL,
            confidence=0.9,
        )

        with patch.object(
            service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")
            assert result["success"] is False
            assert "unsupported_action" in result["error"]

    @pytest.mark.asyncio
    async def test_live_buy_success(self):
        """Successful live buy order."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=5,
            price=3500.0,
            order_type=OrderType.LIMIT,
            confidence=0.9,
        )

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command", return_value={"order_id": "live_123"}),
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")
            assert result["success"] is True
            assert result["type"] == "live_trade"
            assert result["gateway_id"] == "gw1"

    @pytest.mark.asyncio
    async def test_live_order_failed(self):
        """Live order fails when gateway returns None."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.BUY,
            symbol="rb2501",
            quantity=5,
            confidence=0.9,
        )

        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command", return_value=None),
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")
            assert result["success"] is False
            assert result["error"] == "order_failed"

    @pytest.mark.asyncio
    async def test_live_query_positions(self):
        """Query positions from live gateway."""
        service = DirectOrderService()
        intent = TradingIntent(
            action=TradeAction.QUERY,
            confidence=0.9,
        )

        positions = [{"symbol": "rb2501", "size": 10}]
        with (
            patch.object(
                service, "_get_gateway_command_endpoint", return_value="tcp://localhost:5555"
            ),
            patch.object(service, "_send_gateway_command", return_value=positions),
        ):
            result = await service.execute_live_trade(intent, user_id="user1", gateway_id="gw1")
            assert result["success"] is True
            assert result["type"] == "live_query"
            assert len(result["positions"]) == 1


class TestDirectOrderServiceFindGateway:
    """Test gateway discovery."""

    def test_find_gateway_exception_returns_none(self):
        service = DirectOrderService()
        intent = TradingIntent(action=TradeAction.BUY, confidence=0.9)

        with patch.object(service, "_get_gateways_dict", side_effect=ImportError("no module")):
            result = service._find_available_gateway(intent)
            assert result is None
