"""
Paper Trading Service Tests.

Tests:
- Creating paper trading accounts
- Submitting paper trading orders
- Order fill processing
- Position updates
- Account updates
- Order cancellation
- Account deletion
- Query functions
- Slippage calculation
- Price simulation
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.models.paper_trading import (
    OrderSide,
    OrderStatus,
)
from app.services.paper_trading_service import PaperTradingService


class TestPaperTradingServiceInitialization:
    """Test paper trading service initialization."""

    def test_initialization(self):
        """Test service initialization with required repositories."""
        service = PaperTradingService()
        assert service.account_repo is not None
        assert service.position_repo is not None
        assert service.order_repo is not None
        assert service.trade_repo is not None


@pytest.mark.asyncio
class TestCreateAccount:
    """Test paper trading account creation."""

    async def test_create_account_success(self):
        """Test successful account creation."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.user_id = "user_123"
        mock_account.name = "Test Account"
        mock_account.current_cash = 100000.0
        mock_account.total_equity = 100000.0

        service.account_repo = AsyncMock()
        service.account_repo.create = AsyncMock(return_value=mock_account)

        with patch.object(service, "_notify_account_update", new_callable=AsyncMock):
            result = await service.create_account("user_123", "Test Account", 100000.0)

            assert result is not None
            assert result.id == "acc_123"

    async def test_create_account_with_custom_rates(self):
        """Test account creation with custom commission and slippage rates."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        service.account_repo = AsyncMock()
        service.account_repo.create = AsyncMock(return_value=mock_account)

        with patch.object(service, "_notify_account_update", new_callable=AsyncMock):
            result = await service.create_account(
                "user_123",
                "Test Account",
                initial_cash=200000.0,
                commission_rate=0.0005,
                slippage_rate=0.0005,
            )

            assert result is not None

    async def test_create_account_sends_notification(self):
        """Test that account creation triggers WebSocket notification."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        service.account_repo = AsyncMock()
        service.account_repo.create = AsyncMock(return_value=mock_account)

        with patch.object(service, "_notify_account_update", new_callable=AsyncMock) as mock_notify:
            await service.create_account("user_123", "Test Account")
            mock_notify.assert_awaited_once_with(mock_account)


@pytest.mark.asyncio
class TestSubmitOrder:
    """Test order submission."""

    async def test_submit_order_success(self):
        """Test successful order submission."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        mock_order = Mock()
        mock_order.id = "order_123"

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.order_repo = AsyncMock()
        service.order_repo.create = AsyncMock(return_value=mock_order)

        with patch.object(service, "_notify_order_update", new_callable=AsyncMock):
            result = await service.submit_order(
                "acc_123", "BTC/USDT", "market", "buy", 10, price=50000.0
            )

            assert result is not None

    async def test_submit_order_preserves_fractional_size(self):
        """Paper orders must support fractional crypto/FX lot sizes."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        mock_order = Mock()
        mock_order.id = "order_123"

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.order_repo = AsyncMock()
        service.order_repo.create = AsyncMock(return_value=mock_order)

        with patch.object(service, "_notify_order_update", new_callable=AsyncMock):
            await service.submit_order(
                "acc_123", "BTC/USDT", "market", "buy", 0.25, price=50000.0
            )

        created_order = service.order_repo.create.await_args.args[0]
        assert created_order.size == pytest.approx(0.25)
        assert created_order.commission == pytest.approx(12.5)

    async def test_submit_order_rejects_fractional_futures_lot_from_local_spec(self):
        """Paper futures should reject quantities that live CTP would reject."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.order_repo = AsyncMock()
        service.order_repo.create = AsyncMock()

        with patch(
            "app.services.paper_trading_service.query_local_asset_spec",
            return_value={
                "symbol": "IF2609",
                "source": "local_futures_fees",
                "multiplier": 300,
                "margin_rate": 0.1,
                "commission_rate": 0.000023,
            },
        ):
            with pytest.raises(ValueError, match="size step 1.0"):
                await service.submit_order(
                    "acc_123",
                    "IF2609",
                    "market",
                    "buy",
                    1.5,
                    price=5000.0,
                )

        service.order_repo.create.assert_not_awaited()

    async def test_submit_order_rejects_price_tick_mismatch_from_local_spec(self):
        """Paper orders should use local exchange price tick metadata."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.order_repo = AsyncMock()
        service.order_repo.create = AsyncMock()

        with patch(
            "app.services.paper_trading_service.query_local_asset_spec",
            return_value={
                "symbol": "IF2609",
                "source": "local_futures_fees",
                "multiplier": 300,
                "margin_rate": 0.1,
                "price_tick": 0.2,
            },
        ):
            with pytest.raises(ValueError, match="tick size 0.2"):
                await service.submit_order(
                    "acc_123",
                    "IF2609",
                    "limit",
                    "buy",
                    1,
                    price=5000.1,
                )

        service.order_repo.create.assert_not_awaited()

    async def test_submit_order_rejects_raw_okx_min_size_and_lot_step(self):
        """Paper simulation should reject raw OKX lot constraints before live trading."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.order_repo = AsyncMock()
        service.order_repo.create = AsyncMock()

        raw_okx_spec = {
            "symbol": "BTC-USDT-SWAP",
            "source": "okx_get_instruments",
            "instType": "SWAP",
            "ctVal": "0.01",
            "minSz": "1",
            "lotSz": "1",
            "tickSz": "0.1",
        }
        with patch(
            "app.services.paper_trading_service.query_local_asset_spec",
            return_value=raw_okx_spec,
        ):
            with pytest.raises(ValueError, match="minimum allowed size 1.0"):
                await service.submit_order(
                    "acc_123",
                    "BTC-USDT-SWAP",
                    "market",
                    "buy",
                    0.5,
                    price=60000.0,
                )
            with pytest.raises(ValueError, match="size step 1.0"):
                await service.submit_order(
                    "acc_123",
                    "BTC-USDT-SWAP",
                    "market",
                    "buy",
                    1.5,
                    price=60000.0,
                )

        service.order_repo.create.assert_not_awaited()

    async def test_submit_order_uses_okx_market_specific_max_size(self):
        """Market paper orders must obey maxMktSz instead of the larger maxLmtSz."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.order_repo = AsyncMock()
        service.order_repo.create = AsyncMock()

        with patch(
            "app.services.paper_trading_service.query_local_asset_spec",
            return_value={
                "symbol": "BTC-USDT-SWAP",
                "source": "okx_get_instruments",
                "instType": "SWAP",
                "ctVal": "0.01",
                "minSz": "1",
                "lotSz": "1",
                "maxLmtSz": "1000",
                "maxMktSz": "500",
            },
        ):
            with pytest.raises(ValueError, match="maximum allowed size 500.0"):
                await service.submit_order(
                    "acc_123",
                    "BTC-USDT-SWAP",
                    "market",
                    "buy",
                    600,
                    price=60000.0,
                )

        service.order_repo.create.assert_not_awaited()

    async def test_submit_order_rejects_raw_bybit_v5_nested_lot_constraints(self):
        """Paper simulation should validate raw Bybit v5 lotSizeFilter fields."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.order_repo = AsyncMock()
        service.order_repo.create = AsyncMock()

        raw_bybit_spec = {
            "symbol": "BTCUSDT",
            "source": "bybit_get_exchange_info",
            "contractType": "LinearPerpetual",
            "lotSizeFilter": {
                "minOrderQty": "0.001",
                "maxOrderQty": "100",
                "maxMktOrderQty": "50",
                "qtyStep": "0.001",
            },
            "priceFilter": {"tickSize": "0.1"},
        }
        with patch(
            "app.services.paper_trading_service.query_local_asset_spec",
            return_value=raw_bybit_spec,
        ):
            with pytest.raises(ValueError, match="minimum allowed size 0.001"):
                await service.submit_order(
                    "acc_123",
                    "BTCUSDT",
                    "market",
                    "buy",
                    0.0005,
                    price=60000.0,
                )
            with pytest.raises(ValueError, match="size step 0.001"):
                await service.submit_order(
                    "acc_123",
                    "BTCUSDT",
                    "market",
                    "buy",
                    0.0015,
                    price=60000.0,
                )
            with pytest.raises(ValueError, match="maximum allowed size 50.0"):
                await service.submit_order(
                    "acc_123",
                    "BTCUSDT",
                    "market",
                    "buy",
                    60,
                    price=60000.0,
                )

        service.order_repo.create.assert_not_awaited()

    async def test_submit_order_rejects_raw_okx_tick_size_alias(self):
        """Paper limit orders should validate raw OKX tickSz before submission."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.order_repo = AsyncMock()
        service.order_repo.create = AsyncMock()

        with patch(
            "app.services.paper_trading_service.query_local_asset_spec",
            return_value={
                "symbol": "BTC-USDT-SWAP",
                "source": "okx_get_instruments",
                "instType": "SWAP",
                "ctVal": "0.01",
                "minSz": "1",
                "lotSz": "1",
                "tickSz": "0.1",
            },
        ):
            with pytest.raises(ValueError, match="tick size 0.1"):
                await service.submit_order(
                    "acc_123",
                    "BTC-USDT-SWAP",
                    "limit",
                    "buy",
                    1,
                    price=60000.05,
                )

        service.order_repo.create.assert_not_awaited()

    async def test_submit_order_account_not_found(self):
        """Test order submission with non-existent account raises ValueError."""
        service = PaperTradingService()

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Account not found"):
            await service.submit_order("nonexistent_acc", "BTC/USDT", "market", "buy", 10)

    async def test_submit_order_rejects_invalid_side_before_create(self):
        """Invalid paper order sides must not be stored as pending shorts."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.order_repo = AsyncMock()
        service.order_repo.create = AsyncMock()

        with pytest.raises(ValueError, match="side"):
            await service.submit_order("acc_123", "BTC/USDT", "market", "hold", 1)

        service.order_repo.create.assert_not_awaited()

    async def test_submit_order_rejects_stop_limit_without_limit_price(self):
        """Incomplete stop-limit orders should fail fast instead of staying pending."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.order_repo = AsyncMock()
        service.order_repo.create = AsyncMock()

        with pytest.raises(ValueError, match="stop_limit"):
            await service.submit_order(
                "acc_123",
                "BTC/USDT",
                "stop_limit",
                "buy",
                1,
                stop_price=50000.0,
            )

        service.order_repo.create.assert_not_awaited()

    async def test_submit_order_with_stop_limit(self):
        """Test submitting stop-loss and take-profit orders."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        mock_order = Mock()
        mock_order.id = "order_123"

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.order_repo = AsyncMock()
        service.order_repo.create = AsyncMock(return_value=mock_order)

        with patch.object(service, "_notify_order_update", new_callable=AsyncMock):
            result = await service.submit_order(
                "acc_123",
                "BTC/USDT",
                "limit",
                "buy",
                10,
                price=49000.0,
                stop_price=48000.0,
                limit_price=51000.0,
            )

            assert result is not None


@pytest.mark.asyncio
class TestProcessOrder:
    """Test order processing."""

    async def test_process_order_buy_success(self):
        """Test successful buy order processing."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.BUY
        mock_order.size = 10
        mock_order.price = 50000.0
        mock_order.order_type = "market"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.001
        mock_account.current_cash = 600000.0
        mock_account.commission_rate = 0.001

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)

        with patch.object(service, "_get_simulated_price", return_value=50000.0):
            with patch.object(service, "_fill_order", new_callable=AsyncMock):
                with patch.object(service, "_update_position", new_callable=AsyncMock):
                    with patch.object(service, "_update_account", new_callable=AsyncMock):
                        await service._process_order("order_123", "acc_123", mock_account)

    async def test_process_order_order_not_found(self):
        """Test processing of non-existent order logs without exception."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=None)

        with patch.object(service, "_get_simulated_price", return_value=50000.0):
            await service._process_order("nonexistent_order", "acc_123", mock_account)
            # Should not raise exception, only log

    async def test_process_order_rejects_invalid_pending_order(self):
        """Persisted invalid pending orders should become rejected, not stuck pending."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = "hold"
        mock_order.size = 1
        mock_order.price = None
        mock_order.stop_price = None
        mock_order.limit_price = None
        mock_order.order_type = "market"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.id = "acc_123"

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)

        with patch.object(service, "_reject_order", new_callable=AsyncMock) as mock_reject:
            with patch.object(service, "_get_simulated_price", new_callable=AsyncMock) as mock_price:
                await service._process_order("order_123", "acc_123", mock_account)

        mock_reject.assert_awaited_once()
        assert "side" in mock_reject.await_args.args[1]
        mock_price.assert_not_awaited()

    async def test_process_order_rejects_legacy_fractional_futures_pending_order(self):
        """Legacy pending futures paper orders must still pass exchange lot validation."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "IF2609"
        mock_order.side = OrderSide.BUY
        mock_order.size = 1.5
        mock_order.price = 5000.0
        mock_order.stop_price = None
        mock_order.limit_price = None
        mock_order.order_type = "market"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.0
        mock_account.current_cash = 1_000_000.0
        mock_account.commission_rate = 0.001

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)

        with patch(
            "app.services.paper_trading_service.query_local_asset_spec",
            return_value={
                "symbol": "IF2609",
                "source": "local_futures_fees",
                "multiplier": 300,
                "margin_rate": 0.1,
            },
        ):
            with patch.object(service, "_reject_order", new_callable=AsyncMock) as mock_reject:
                with patch.object(service, "_get_simulated_price", new_callable=AsyncMock) as mock_price:
                    await service._process_order("order_123", "acc_123", mock_account)

        mock_reject.assert_awaited_once()
        assert "size step 1.0" in mock_reject.await_args.args[1]
        mock_price.assert_not_awaited()

    async def test_process_order_rejects_okx_market_size_above_raw_max_mkt_sz(self):
        """Legacy pending OKX market orders must be rechecked against maxMktSz."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC-USDT-SWAP"
        mock_order.side = OrderSide.BUY
        mock_order.size = 600
        mock_order.price = 60000.0
        mock_order.stop_price = None
        mock_order.limit_price = None
        mock_order.order_type = "market"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.0
        mock_account.current_cash = 1_000_000.0
        mock_account.commission_rate = 0.001

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)

        with patch(
            "app.services.paper_trading_service.query_local_asset_spec",
            return_value={
                "symbol": "BTC-USDT-SWAP",
                "source": "okx_get_instruments",
                "instType": "SWAP",
                "ctVal": "0.01",
                "minSz": "1",
                "lotSz": "1",
                "maxLmtSz": "1000",
                "maxMktSz": "500",
            },
        ):
            with patch.object(service, "_reject_order", new_callable=AsyncMock) as mock_reject:
                with patch.object(service, "_get_simulated_price", new_callable=AsyncMock) as mock_price:
                    await service._process_order("order_123", "acc_123", mock_account)

        mock_reject.assert_awaited_once()
        assert "maximum allowed size 500.0" in mock_reject.await_args.args[1]
        mock_price.assert_not_awaited()

    async def test_process_order_skips_cancelled_order(self):
        """Cancelled pending orders must not be filled by the async processor."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.BUY
        mock_order.size = 1
        mock_order.order_type = "market"
        mock_order.status = OrderStatus.CANCELLED

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.001
        mock_account.current_cash = 100000.0
        mock_account.commission_rate = 0.001

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)

        with patch.object(service, "_get_simulated_price", new_callable=AsyncMock) as mock_price:
            with patch.object(service, "_fill_order", new_callable=AsyncMock) as mock_fill:
                await service._process_order("order_123", "acc_123", mock_account)

        mock_price.assert_not_awaited()
        mock_fill.assert_not_awaited()

    async def test_process_order_insufficient_funds(self):
        """Test order processing with insufficient funds triggers rejection."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.BUY
        mock_order.size = 100
        mock_order.order_type = "market"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.001
        mock_account.current_cash = 100.0  # Insufficient funds
        mock_account.commission_rate = 0.001

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.order_repo.update = AsyncMock()

        with patch.object(service, "_get_simulated_price", return_value=50000.0):
            with patch.object(service, "_reject_order", new_callable=AsyncMock) as mock_reject:
                await service._process_order("order_123", "acc_123", mock_account)
                mock_reject.assert_awaited_once_with(mock_order, "Insufficient funds")

    async def test_process_order_limit_order_not_triggered_remains_pending(self):
        """Non-marketable limit orders must not be filled immediately."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.BUY
        mock_order.size = 1
        mock_order.price = 49000.0
        mock_order.limit_price = None
        mock_order.order_type = "limit"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.001
        mock_account.current_cash = 100000.0
        mock_account.commission_rate = 0.001

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)

        with patch.object(service, "_get_simulated_price", return_value=50000.0):
            with patch.object(service, "_fill_order", new_callable=AsyncMock) as mock_fill:
                with patch.object(service, "_update_position", new_callable=AsyncMock) as mock_pos:
                    with patch.object(service, "_update_account", new_callable=AsyncMock) as mock_acct:
                        with patch.object(
                            service,
                            "_reject_order",
                            new_callable=AsyncMock,
                        ) as mock_reject:
                            await service._process_order("order_123", "acc_123", mock_account)

        mock_fill.assert_not_awaited()
        mock_pos.assert_not_awaited()
        mock_acct.assert_not_awaited()
        mock_reject.assert_not_awaited()

    async def test_process_order_sell_without_position_opens_short(self):
        """Sell orders without an existing long position should open a short."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.SELL
        mock_order.size = 100
        mock_order.order_type = "market"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.001
        mock_account.current_cash = 10000000.0
        mock_account.commission_rate = 0.001

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[])

        with patch.object(service, "_get_simulated_price", return_value=50000.0):
            with patch.object(service, "_fill_order", new_callable=AsyncMock) as mock_fill:
                with patch.object(service, "_update_position", new_callable=AsyncMock) as mock_pos:
                    with patch.object(service, "_update_account", new_callable=AsyncMock) as mock_acct:
                        await service._process_order("order_123", "acc_123", mock_account)

        mock_fill.assert_awaited_once()
        mock_pos.assert_awaited_once()
        mock_acct.assert_awaited_once()

    async def test_process_order_sell_without_position_rejects_insufficient_cash(self):
        """Opening a short position must be backed by available cash."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.SELL
        mock_order.size = 100
        mock_order.order_type = "market"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.001
        mock_account.current_cash = 100.0
        mock_account.commission_rate = 0.001

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[])

        with patch.object(service, "_get_simulated_price", return_value=50000.0):
            with patch.object(service, "_reject_order", new_callable=AsyncMock) as mock_reject:
                with patch.object(service, "_fill_order", new_callable=AsyncMock) as mock_fill:
                    await service._process_order("order_123", "acc_123", mock_account)

        mock_reject.assert_awaited_once_with(mock_order, "Insufficient funds")
        mock_fill.assert_not_awaited()

    async def test_process_order_sell_reducing_long_only_requires_commission_cash(self):
        """Reducing an existing long is risk-reducing and should not need full notional cash."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.SELL
        mock_order.size = 5
        mock_order.order_type = "market"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.001
        mock_account.current_cash = 300.0
        mock_account.commission_rate = 0.001

        mock_position = Mock()
        mock_position.size = 10

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])

        with patch.object(service, "_get_simulated_price", return_value=50000.0):
            with patch.object(service, "_fill_order", new_callable=AsyncMock) as mock_fill:
                with patch.object(service, "_update_position", new_callable=AsyncMock) as mock_pos:
                    with patch.object(service, "_update_account", new_callable=AsyncMock) as mock_acct:
                        await service._process_order("order_123", "acc_123", mock_account)

        mock_fill.assert_awaited_once()
        mock_pos.assert_awaited_once()
        mock_acct.assert_awaited_once()

    async def test_process_order_spot_sell_long_uses_sale_proceeds_for_commission(self):
        """Closing a cash position should be allowed even when idle cash is zero."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.SELL
        mock_order.size = 1
        mock_order.order_type = "market"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.0
        mock_account.current_cash = 0.0
        mock_account.commission_rate = 0.001

        mock_position = Mock()
        mock_position.size = 1

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])

        with patch.object(service, "_get_simulated_price", return_value=50000.0):
            with patch.object(service, "_reject_order", new_callable=AsyncMock) as mock_reject:
                with patch.object(service, "_fill_order", new_callable=AsyncMock) as mock_fill:
                    with patch.object(service, "_update_position", new_callable=AsyncMock) as mock_pos:
                        mock_pos.return_value = {"cash_delta": 49950.0}
                        with patch.object(
                            service,
                            "_update_account",
                            new_callable=AsyncMock,
                        ) as mock_acct:
                            await service._process_order("order_123", "acc_123", mock_account)

        mock_reject.assert_not_awaited()
        _order, _price, commission = mock_fill.await_args.args
        assert commission == pytest.approx(50.0)
        mock_pos.assert_awaited_once()
        mock_acct.assert_awaited_once()

    async def test_process_order_uses_futures_contract_spec_for_margin_and_fee(self):
        """Futures paper orders should use multiplier, margin and exchange fee metadata."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "IF2609"
        mock_order.side = OrderSide.BUY
        mock_order.size = 1
        mock_order.price = 5000.0
        mock_order.order_type = "market"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.0
        mock_account.current_cash = 200000.0
        mock_account.commission_rate = 0.001

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[])

        with patch.object(service, "_get_simulated_price", return_value=5000.0):
            with patch(
                "app.services.paper_trading_service.query_local_asset_spec",
                return_value={
                    "symbol": "IF2609",
                    "multiplier": 300,
                    "margin_rate": 0.1,
                    "commission_rate": 0.000023,
                },
            ):
                with patch.object(service, "_fill_order", new_callable=AsyncMock) as mock_fill:
                    with patch.object(service, "_update_position", new_callable=AsyncMock) as mock_pos:
                        mock_pos.return_value = {"cash_delta": -150034.5}
                        with patch.object(
                            service,
                            "_update_account",
                            new_callable=AsyncMock,
                        ) as mock_acct:
                            await service._process_order("order_123", "acc_123", mock_account)

        _order, _price, commission = mock_fill.await_args.args
        assert commission == pytest.approx(34.5)
        mock_pos.assert_awaited_once()
        mock_acct.assert_awaited_once()

    async def test_process_order_futures_close_uses_released_margin_for_fee(self):
        """Risk-reducing futures closes must not be rejected before margin release."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "IF2609"
        mock_order.side = OrderSide.SELL
        mock_order.size = 1
        mock_order.price = None
        mock_order.order_type = "market"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.0
        mock_account.current_cash = 0.0
        mock_account.commission_rate = 0.001

        mock_position = Mock()
        mock_position.size = 1
        mock_position.avg_price = 5000.0
        mock_position.margin_value = 150_000.0

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])

        with patch.object(service, "_get_simulated_price", return_value=5001.0):
            with patch(
                "app.services.paper_trading_service.query_local_asset_spec",
                return_value={
                    "symbol": "IF2609",
                    "multiplier": 300,
                    "margin_rate": 0.1,
                    "commission_rate": 0.000023,
                },
            ):
                with patch.object(service, "_reject_order", new_callable=AsyncMock) as mock_reject:
                    with patch.object(service, "_fill_order", new_callable=AsyncMock) as mock_fill:
                        with patch.object(
                            service,
                            "_update_position",
                            new_callable=AsyncMock,
                        ) as mock_pos:
                            mock_pos.return_value = {"cash_delta": 150265.4931}
                            with patch.object(
                                service,
                                "_update_account",
                                new_callable=AsyncMock,
                            ) as mock_acct:
                                await service._process_order(
                                    "order_123",
                                    "acc_123",
                                    mock_account,
                                )

        mock_reject.assert_not_awaited()
        _order, _price, commission = mock_fill.await_args.args
        assert commission == pytest.approx(34.5069)
        mock_pos.assert_awaited_once()
        mock_acct.assert_awaited_once()

    async def test_process_order_same_day_futures_close_uses_close_today_fee(self):
        """Same-day futures closes should use close-today commission metadata."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "IF2609"
        mock_order.side = "sell"
        mock_order.size = 1
        mock_order.price = None
        mock_order.order_type = "market"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.0
        mock_account.current_cash = 0.0
        mock_account.commission_rate = 0.001

        mock_position = Mock()
        mock_position.size = 1
        mock_position.avg_price = 5000.0
        mock_position.margin_value = 150_000.0
        mock_position.entry_time = datetime.now(timezone.utc)

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])

        with patch.object(service, "_get_simulated_price", return_value=5001.0):
            with patch(
                "app.services.paper_trading_service.query_local_asset_spec",
                return_value={
                    "symbol": "IF2609",
                    "multiplier": 300,
                    "margin_rate": 0.1,
                    "OpenRatioByMoney": 0.23,
                    "CloseTodayRatioByMoney": 3.45,
                },
            ):
                with patch.object(service, "_reject_order", new_callable=AsyncMock) as mock_reject:
                    with patch.object(service, "_fill_order", new_callable=AsyncMock) as mock_fill:
                        with patch.object(
                            service,
                            "_update_position",
                            new_callable=AsyncMock,
                        ) as mock_pos:
                            mock_pos.return_value = {"cash_delta": 149782.3965}
                            with patch.object(
                                service,
                                "_update_account",
                                new_callable=AsyncMock,
                            ) as mock_acct:
                                await service._process_order(
                                    "order_123",
                                    "acc_123",
                                    mock_account,
                                )

        mock_reject.assert_not_awaited()
        _order, _price, commission = mock_fill.await_args.args
        assert commission == pytest.approx(517.6035)
        kwargs = mock_pos.await_args.kwargs
        assert kwargs["commission_breakdown"]["close_role"] == "close_today"
        mock_acct.assert_awaited_once()

    async def test_close_today_fee_uses_local_trading_day_across_midnight(self):
        """Night-session futures closes after midnight remain close-today."""
        service = PaperTradingService()
        position = Mock()
        position.entry_time = datetime(2026, 6, 25, 15, 30, tzinfo=timezone.utc)
        fill_time = datetime(2026, 6, 26, 0, 30, tzinfo=timezone.utc)

        with patch.dict(
            "os.environ",
            {
                "BT_STORE_LOCAL_TIMEZONE": "Asia/Shanghai",
                "PAPER_TRADING_DAY_ROLLOVER_HOUR": "21",
            },
        ):
            role = service._close_commission_role_for_position(position, as_of=fill_time)

        assert role == "close_today"


@pytest.mark.asyncio
class TestFillOrder:
    """Test order fill execution."""

    async def test_fill_order(self):
        """Test order fill updates order status and creates trade record."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.BUY
        mock_order.size = 10

        mock_trade = Mock()
        mock_trade.id = "trade_123"

        service.order_repo = AsyncMock()
        service.order_repo.update = AsyncMock()
        service.trade_repo = AsyncMock()
        service.trade_repo.create = AsyncMock(return_value=mock_trade)

        await service._fill_order(mock_order, 50000.0, 50.0)

        assert mock_order.status == OrderStatus.FILLED
        assert mock_order.filled_size == 10
        assert mock_order.avg_fill_price == 50000.0
        assert mock_order.commission == 50.0

    async def test_fill_order_preserves_fractional_size(self):
        """Paper fills and trade records must retain fractional size."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.BUY
        mock_order.size = 0.25

        mock_trade = Mock()
        mock_trade.id = "trade_123"

        service.order_repo = AsyncMock()
        service.order_repo.update = AsyncMock()
        service.trade_repo = AsyncMock()
        service.trade_repo.create = AsyncMock(return_value=mock_trade)

        await service._fill_order(mock_order, 50000.0, 12.5)

        assert mock_order.filled_size == pytest.approx(0.25)
        created_trade = service.trade_repo.create.await_args.args[0]
        assert created_trade.size == pytest.approx(0.25)

    async def test_fill_order_uses_supplied_fill_time(self):
        """Order filled_at should use the same timestamp used for fee accounting."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTCUSDT"
        mock_order.side = OrderSide.BUY
        mock_order.size = 1.0
        filled_at = datetime(2026, 6, 26, 0, 30, tzinfo=timezone.utc)

        service.order_repo = AsyncMock()
        service.order_repo.update = AsyncMock()
        service.trade_repo = AsyncMock()
        service.trade_repo.create = AsyncMock()

        await service._fill_order(mock_order, 50000.0, 50.0, filled_at=filled_at)

        _order_id, order_update = service.order_repo.update.await_args.args
        assert order_update["filled_at"] == filled_at


@pytest.mark.asyncio
class TestRejectOrder:
    """Test order rejection."""

    async def test_reject_order(self):
        """Test order rejection updates status and reason."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"

        service.order_repo = AsyncMock()
        service.order_repo.update = AsyncMock()

        with patch.object(service, "_notify_order_update", new_callable=AsyncMock):
            await service._reject_order(mock_order, "Insufficient funds")

        assert mock_order.status == OrderStatus.REJECTED
        assert mock_order.rejected_reason == "Insufficient funds"


@pytest.mark.asyncio
class TestUpdatePosition:
    """Test position updates."""

    async def test_update_position_new_long(self):
        """Test creating a new long position."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.BUY
        mock_order.size = 10

        mock_position = Mock()
        mock_position.id = "pos_123"

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[])
        service.position_repo.create = AsyncMock(return_value=mock_position)

        await service._update_position(mock_account, mock_order, 50000.0, 50.0)

        service.position_repo.create.assert_awaited_once()

    async def test_update_position_accepts_string_buy_side(self):
        """DB-loaded string sides must not invert paper-trading direction."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = "buy"
        mock_order.size = 0.25

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[])
        service.position_repo.create = AsyncMock()

        await service._update_position(mock_account, mock_order, 50000.0, 12.5)

        position = service.position_repo.create.await_args.args[0]
        assert position.size == pytest.approx(0.25)
        assert position.market_value == pytest.approx(12500.0)

    async def test_update_position_existing_long(self):
        """Test updating an existing long position."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.BUY
        mock_order.size = 5

        mock_position = Mock()
        mock_position.id = "pos_123"
        mock_position.size = 10
        mock_position.avg_price = 48000.0
        mock_position.market_value = 480000.0

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])
        service.position_repo.update = AsyncMock()
        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=[])

        await service._update_position(mock_account, mock_order, 50000.0, 25.0)

        service.position_repo.update.assert_awaited_once()

    async def test_update_position_close_long(self):
        """Test closing a long position."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.SELL
        mock_order.size = 10

        mock_position = Mock()
        mock_position.id = "pos_123"
        mock_position.size = 10
        mock_position.avg_price = 48000.0
        mock_position.market_value = 480000.0

        mock_trade = Mock()
        mock_trade.id = "trade_123"
        mock_trade.pnl = 0.0

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])
        service.position_repo.update = AsyncMock()

        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=[mock_trade])
        service.trade_repo.update = AsyncMock()

        await service._update_position(mock_account, mock_order, 50000.0, 50.0)

        service.trade_repo.update.assert_awaited_once()

    async def test_update_position_partial_close_preserves_cost_basis(self):
        """Partial close must not fold sell proceeds into remaining average price."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.SELL
        mock_order.size = 4

        mock_position = Mock()
        mock_position.id = "pos_123"
        mock_position.size = 10
        mock_position.avg_price = 100.0
        mock_position.market_value = 1000.0

        mock_trade = Mock()
        mock_trade.id = "trade_123"

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])
        service.position_repo.update = AsyncMock()

        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=[mock_trade])
        service.trade_repo.update = AsyncMock()

        await service._update_position(mock_account, mock_order, 110.0, 1.0)

        _position_id, position_update = service.position_repo.update.await_args.args
        assert position_update["size"] == pytest.approx(6.0)
        assert position_update["avg_price"] == pytest.approx(100.0)
        assert position_update["market_value"] == pytest.approx(660.0)
        assert position_update["unrealized_pnl"] == pytest.approx(60.0)
        assert position_update["unrealized_pnl_pct"] == pytest.approx(10.0)

        _trade_id, trade_update = service.trade_repo.update.await_args.args
        assert trade_update["pnl"] == pytest.approx(39.0)
        assert trade_update["pnl_pct"] == pytest.approx(9.75)

    async def test_update_position_new_futures_long_uses_multiplier_and_margin(self):
        """New futures positions should store notional value and reserved margin."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.symbol = "IF2609"
        mock_order.side = OrderSide.BUY
        mock_order.size = 1

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[])
        service.position_repo.create = AsyncMock()

        with patch("app.services.paper_trading_service.query_local_asset_spec", return_value={}):
            event = await service._update_position(
                mock_account,
                mock_order,
                5000.0,
                34.5,
                spec=service._contract_spec_for_symbol("IF2609", mock_account),
            )

        _position = service.position_repo.create.await_args.args[0]
        assert _position.market_value == pytest.approx(5000.0)
        assert _position.margin_value == pytest.approx(5000.0)
        assert event["cash_delta"] == pytest.approx(-5034.5)

        futures_spec = {
            "symbol": "IF2609",
            "multiplier": 300,
            "margin_rate": 0.1,
            "commission_rate": 0.000023,
        }
        with patch(
            "app.services.paper_trading_service.query_local_asset_spec",
            return_value=futures_spec,
        ):
            service.position_repo.create.reset_mock()
            event = await service._update_position(mock_account, mock_order, 5000.0, 34.5)

        position = service.position_repo.create.await_args.args[0]
        assert position.market_value == pytest.approx(1_500_000.0)
        assert position.margin_value == pytest.approx(150_000.0)
        assert position.multiplier == pytest.approx(300.0)
        assert position.margin_rate == pytest.approx(0.1)
        assert position.commission_rate == pytest.approx(0.000023)
        assert event["cash_delta"] == pytest.approx(-150_034.5)

    async def test_update_position_new_long_uses_fill_time_as_entry_time(self):
        """Paper positions should store the fill timestamp used for commission roles."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.symbol = "BTCUSDT"
        mock_order.side = OrderSide.BUY
        mock_order.size = 1

        fill_time = datetime(2026, 6, 26, 0, 30, tzinfo=timezone.utc)
        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[])
        service.position_repo.create = AsyncMock()

        await service._update_position(
            mock_account,
            mock_order,
            50000.0,
            50.0,
            fill_time=fill_time,
        )

        position = service.position_repo.create.await_args.args[0]
        assert position.entry_time == fill_time

    async def test_update_position_closing_futures_releases_margin_and_realizes_pnl(self):
        """Closing futures should realize multiplier PnL and release reserved margin."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.symbol = "IF2609"
        mock_order.side = OrderSide.SELL
        mock_order.size = 1

        mock_position = Mock()
        mock_position.id = "pos_123"
        mock_position.size = 1
        mock_position.avg_price = 5000.0
        mock_position.margin_value = 150000.0

        mock_trade = Mock()
        mock_trade.id = "trade_123"

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])
        service.position_repo.update = AsyncMock()
        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=[mock_trade])
        service.trade_repo.update = AsyncMock()

        with patch(
            "app.services.paper_trading_service.query_local_asset_spec",
            return_value={
                "symbol": "IF2609",
                "multiplier": 300,
                "margin_rate": 0.1,
                "commission_rate": 0.000023,
            },
        ):
            event = await service._update_position(mock_account, mock_order, 5001.0, 34.5069)

        _trade_id, trade_update = service.trade_repo.update.await_args.args
        assert trade_update["pnl"] == pytest.approx(265.4931)
        assert event["cash_delta"] == pytest.approx(150265.4931)

    async def test_inverse_contract_notional_margin_fee_and_realized_pnl(self):
        """Paper inverse contracts must use fixed contract value instead of price * value."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        inverse_spec = {
            "symbol": "BTC-USD-SWAP",
            "source": "okx_get_instruments",
            "asset_type": "SWAP",
            "contract_type": "inverse",
            "ctVal": 100,
            "ctValCcy": "USD",
            "baseCcy": "BTC",
            "quoteCcy": "USD",
            "settleCcy": "BTC",
            "margin_rate": 0.1,
            "taker_commission_rate": 0.0005,
        }
        with patch(
            "app.services.paper_trading_service.query_local_asset_spec",
            return_value=inverse_spec,
        ):
            spec = service._contract_spec_for_symbol("BTC-USD-SWAP", mock_account)

        assert service._notional_value(100, 50000.0, spec) == pytest.approx(10000.0)
        assert service._margin_value(100, 50000.0, spec) == pytest.approx(1000.0)
        assert service._commission_value(100, 50000.0, spec, role="open") == pytest.approx(5.0)
        assert service._realized_gross_pnl(100, 50000.0, 55000.0, 100, spec) == pytest.approx(1000.0)
        assert service._realized_gross_pnl(-100, 50000.0, 45000.0, 100, spec) == pytest.approx(1000.0)

        mock_order = Mock()
        mock_order.id = "order_open"
        mock_order.symbol = "BTC-USD-SWAP"
        mock_order.side = OrderSide.BUY
        mock_order.size = 100

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[])
        service.position_repo.create = AsyncMock()

        event = await service._update_position(
            mock_account,
            mock_order,
            50000.0,
            5.0,
            spec=spec,
        )

        opened_position = service.position_repo.create.await_args.args[0]
        assert opened_position.market_value == pytest.approx(10000.0)
        assert opened_position.margin_value == pytest.approx(1000.0)
        assert event["cash_delta"] == pytest.approx(-1005.0)

        close_order = Mock()
        close_order.id = "order_close"
        close_order.symbol = "BTC-USD-SWAP"
        close_order.side = OrderSide.SELL
        close_order.size = 100

        mock_position = Mock()
        mock_position.id = "pos_123"
        mock_position.size = 100
        mock_position.avg_price = 50000.0
        mock_position.margin_value = 1000.0

        mock_trade = Mock()
        mock_trade.id = "trade_123"

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])
        service.position_repo.update = AsyncMock()
        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=[mock_trade])
        service.trade_repo.update = AsyncMock()

        close_event = await service._update_position(
            mock_account,
            close_order,
            55000.0,
            5.0,
            spec=spec,
        )

        _trade_id, trade_update = service.trade_repo.update.await_args.args
        assert trade_update["pnl"] == pytest.approx(995.0)
        assert trade_update["pnl_pct"] == pytest.approx(9.95)
        assert close_event["cash_delta"] == pytest.approx(1995.0)

    async def test_explicit_inverse_flag_prefers_ctval_over_multiplier_aliases(self):
        """Boolean inverse specs still need ctVal, not ctMult/multiplier, as contract value."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        inverse_spec = {
            "symbol": "BTCUSD",
            "source": "gateway.get_symbol_info",
            "asset_type": "SWAP",
            "inverse": True,
            "multiplier": 1,
            "ctVal": 100,
            "ctMult": 1,
            "margin_rate": 0.1,
            "taker_commission_rate": 0.0005,
        }
        with patch(
            "app.services.paper_trading_service.query_local_asset_spec",
            return_value=inverse_spec,
        ):
            spec = service._contract_spec_for_symbol("BTCUSD", mock_account)

        assert spec.is_inverse is True
        assert spec.multiplier == pytest.approx(100.0)
        assert service._notional_value(100, 50000.0, spec) == pytest.approx(10000.0)
        assert service._margin_value(100, 50000.0, spec) == pytest.approx(1000.0)
        assert service._commission_value(100, 50000.0, spec, role="open") == pytest.approx(5.0)

    async def test_inverse_contract_same_side_fill_uses_inverse_average_price(self):
        """Inverse average entry price is harmonic by contract count, not arithmetic."""
        service = PaperTradingService()
        spec = service._contract_spec_for_symbol(
            "BTC-USD-SWAP",
            asset_spec={
                "symbol": "BTC-USD-SWAP",
                "contract_type": "inverse",
                "ctVal": 100,
                "ctValCcy": "USD",
                "baseCcy": "BTC",
                "quoteCcy": "USD",
                "settleCcy": "BTC",
            },
        )

        avg_price = service._average_entry_price(
            old_size=1,
            old_avg_price=50000.0,
            fill_size=1,
            fill_price=60000.0,
            spec=spec,
        )

        assert avg_price == pytest.approx(54545.454545)

    async def test_update_position_reversal_resets_entry_time_for_new_leg(self):
        """A reversed futures position should use the new leg's date for close-today fees."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.symbol = "IF2609"
        mock_order.side = OrderSide.BUY
        mock_order.size = 2

        old_entry_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_position = Mock()
        mock_position.id = "pos_123"
        mock_position.size = -1
        mock_position.avg_price = 5000.0
        mock_position.margin_value = 150000.0
        mock_position.entry_time = old_entry_time

        mock_trade = Mock()
        mock_trade.id = "trade_123"

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])
        service.position_repo.update = AsyncMock()
        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=[mock_trade])
        service.trade_repo.update = AsyncMock()

        local_spec = {
            "symbol": "IF2609",
            "multiplier": 300,
            "margin_rate": 0.1,
            "OpenRatioByMoney": 0.23,
            "CloseRatioByMoney": 0.3,
            "CloseTodayRatioByMoney": 3.45,
        }
        with patch(
            "app.services.paper_trading_service.query_local_asset_spec",
            return_value=local_spec,
        ):
            spec = service._contract_spec_for_symbol("IF2609", mock_account)
            await service._update_position(
                mock_account,
                mock_order,
                4990.0,
                113.772,
                spec=spec,
            )

        _position_id, position_update = service.position_repo.update.await_args.args
        assert position_update["size"] == pytest.approx(1.0)
        assert position_update["avg_price"] == pytest.approx(4990.0)
        assert position_update["entry_price"] == pytest.approx(4990.0)
        assert isinstance(position_update["entry_time"], datetime)
        assert position_update["entry_time"] != old_entry_time

        for key, value in position_update.items():
            setattr(mock_position, key, value)
        next_close = service._fill_commission_breakdown(mock_position, -1, 4991.0, spec)
        assert next_close["close_role"] == "close_today"


@pytest.mark.asyncio
class TestUpdateAccount:
    """Test account updates."""

    async def test_update_account_buy(self):
        """Test account update after buy order."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.initial_cash = 100000.0
        mock_account.current_cash = 100000.0

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.side = OrderSide.BUY
        mock_order.size = 10
        mock_order.symbol = "BTC/USDT"

        mock_position = Mock()
        mock_position.market_value = 0.0

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])
        service.account_repo = AsyncMock()
        service.account_repo.update = AsyncMock()

        with patch.object(service, "_notify_account_update", new_callable=AsyncMock):
            with patch.object(service, "_notify_position_update", new_callable=AsyncMock):
                await service._update_account(mock_account, mock_order, 50000.0, 50.0)

    async def test_update_account_sell(self):
        """Test account update after sell order."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.initial_cash = 100000.0
        mock_account.current_cash = 100000.0

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.side = OrderSide.SELL
        mock_order.size = 10
        mock_order.symbol = "BTC/USDT"

        mock_position = Mock()
        mock_position.market_value = 0.0

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])
        service.account_repo = AsyncMock()
        service.account_repo.update = AsyncMock()

        with patch.object(service, "_notify_account_update", new_callable=AsyncMock):
            with patch.object(service, "_notify_position_update", new_callable=AsyncMock):
                await service._update_account(mock_account, mock_order, 50000.0, 50.0)

    async def test_update_account_uses_margin_equity_for_futures(self):
        """Futures account equity should be cash + margin + unrealized PnL."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.initial_cash = 200000.0
        mock_account.current_cash = 200000.0

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.side = OrderSide.BUY
        mock_order.size = 1
        mock_order.symbol = "IF2609"

        mock_position = Mock()
        mock_position.market_value = 1_500_000.0
        mock_position.margin_value = 150_000.0
        mock_position.unrealized_pnl = 0.0

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])
        service.account_repo = AsyncMock()
        service.account_repo.update = AsyncMock()

        with patch.object(service, "_notify_account_update", new_callable=AsyncMock):
            with patch.object(service, "_notify_position_update", new_callable=AsyncMock):
                await service._update_account(
                    mock_account,
                    mock_order,
                    5000.0,
                    34.5,
                    position_event={"cash_delta": -150034.5},
                )

        _account_id, account_update = service.account_repo.update.await_args.args
        assert account_update["current_cash"] == pytest.approx(49965.5)
        assert account_update["total_equity"] == pytest.approx(199965.5)
        assert account_update["profit_loss"] == pytest.approx(-34.5)

    async def test_update_account_prefers_filled_position_snapshot_for_equity(self):
        """Account PnL should use the just-computed position, not stale repository state."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.initial_cash = 200000.0
        mock_account.current_cash = 200000.0

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.side = OrderSide.BUY
        mock_order.size = 1
        mock_order.symbol = "IF2609"

        stale_position = Mock()
        stale_position.id = "pos_123"
        stale_position.account_id = "acc_123"
        stale_position.symbol = "IF2609"
        stale_position.size = 1
        stale_position.market_value = 0.0
        stale_position.margin_value = 0.0
        stale_position.unrealized_pnl = 0.0
        stale_position.multiplier = 300.0
        stale_position.margin_rate = 0.1

        fresh_position = Mock()
        fresh_position.id = "pos_123"
        fresh_position.account_id = "acc_123"
        fresh_position.symbol = "IF2609"
        fresh_position.size = 1
        fresh_position.market_value = 1_500_000.0
        fresh_position.margin_value = 150_000.0
        fresh_position.unrealized_pnl = 300.0
        fresh_position.multiplier = 300.0
        fresh_position.margin_rate = 0.1

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[stale_position])
        service.account_repo = AsyncMock()
        service.account_repo.update = AsyncMock()

        with patch.object(service, "_notify_account_update", new_callable=AsyncMock):
            with patch.object(service, "_notify_position_update", new_callable=AsyncMock) as notify_pos:
                await service._update_account(
                    mock_account,
                    mock_order,
                    5000.0,
                    34.5,
                    position_event={
                        "cash_delta": -150034.5,
                        "position_snapshot": fresh_position,
                    },
                )

        _account_id, account_update = service.account_repo.update.await_args.args
        assert account_update["current_cash"] == pytest.approx(49965.5)
        assert account_update["total_equity"] == pytest.approx(200265.5)
        assert account_update["profit_loss"] == pytest.approx(265.5)
        notify_pos.assert_awaited_once_with(fresh_position)

    async def test_position_equity_component_uses_margin_for_full_margin_short_contract(self):
        """Full-margin contract shorts still use positive margin equity, not negative notional."""
        mock_position = Mock()
        mock_position.market_value = -10_000.0
        mock_position.margin_value = 10_000.0
        mock_position.unrealized_pnl = 500.0
        mock_position.multiplier = 100.0
        mock_position.margin_rate = 1.0

        assert PaperTradingService._position_equity_component(mock_position) == pytest.approx(
            10_500.0
        )

    async def test_position_equity_component_keeps_spot_short_market_value_accounting(self):
        """Non-margin spot-style shorts keep the legacy signed market-value component."""
        mock_position = Mock()
        mock_position.market_value = -10_000.0
        mock_position.margin_value = 10_000.0
        mock_position.unrealized_pnl = 500.0
        mock_position.multiplier = 1.0
        mock_position.margin_rate = 1.0

        assert PaperTradingService._position_equity_component(mock_position) == pytest.approx(
            -10_000.0
        )


@pytest.mark.asyncio
class TestGetAccount:
    """Test account retrieval."""

    async def test_get_account_found(self):
        """Test retrieving an existing account."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        result = await service.get_account("acc_123")

        assert result is not None
        assert result.id == "acc_123"

    async def test_get_account_not_found(self):
        """Test retrieving a non-existent account returns None."""
        service = PaperTradingService()

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.get_account("nonexistent")

        assert result is None


@pytest.mark.asyncio
class TestListAccounts:
    """Test account listing."""

    async def test_list_accounts(self):
        """Test listing user accounts."""
        service = PaperTradingService()

        mock_accounts = [Mock(id=f"acc_{i}") for i in range(5)]

        service.account_repo = AsyncMock()
        service.account_repo.list = AsyncMock(return_value=mock_accounts)
        service.account_repo.count = AsyncMock(return_value=5)

        accounts, total = await service.list_accounts("user_123")

        assert len(accounts) == 5
        assert total == 5

    async def test_list_accounts_empty(self):
        """Test listing when user has no accounts."""
        service = PaperTradingService()

        service.account_repo = AsyncMock()
        service.account_repo.list = AsyncMock(return_value=[])
        service.account_repo.count = AsyncMock(return_value=0)

        accounts, total = await service.list_accounts("user_123")

        assert accounts == []
        assert total == 0


@pytest.mark.asyncio
class TestListOrders:
    """Test order listing."""

    async def test_list_orders(self):
        """Test listing orders with filters."""
        service = PaperTradingService()

        mock_orders = [Mock(id=f"order_{i}") for i in range(3)]

        service.order_repo = AsyncMock()
        service.order_repo.list = AsyncMock(return_value=mock_orders)
        service.order_repo.count = AsyncMock(return_value=3)

        orders, total = await service.list_orders({"account_id": "acc_123"})

        assert len(orders) == 3
        assert total == 3

    async def test_list_orders_scopes_user_id_to_owned_accounts(self):
        """User filters must be converted to account_id filters before querying orders."""
        service = PaperTradingService()

        mock_accounts = [Mock(id="acc_1"), Mock(id="acc_2")]
        mock_orders = [Mock(id="order_1")]

        service.account_repo = AsyncMock()
        service.account_repo.count = AsyncMock(return_value=2)
        service.account_repo.list = AsyncMock(return_value=mock_accounts)
        service.order_repo = AsyncMock()
        service.order_repo.list = AsyncMock(return_value=mock_orders)
        service.order_repo.count = AsyncMock(return_value=1)

        orders, total = await service.list_orders({"user_id": "user_123", "symbol": "IF2609"})

        assert orders == mock_orders
        assert total == 1
        service.order_repo.list.assert_awaited_once()
        assert service.order_repo.list.await_args.kwargs["filters"] == {
            "symbol": "IF2609",
            "account_id": ["acc_1", "acc_2"],
        }
        assert service.order_repo.count.await_args.kwargs["filters"] == {
            "symbol": "IF2609",
            "account_id": ["acc_1", "acc_2"],
        }

    async def test_list_orders_rejects_foreign_account_filter(self):
        """A user-scoped query for another account must not hit the order table."""
        service = PaperTradingService()

        service.account_repo = AsyncMock()
        service.account_repo.count = AsyncMock(return_value=1)
        service.account_repo.list = AsyncMock(return_value=[Mock(id="owned_acc")])
        service.order_repo = AsyncMock()
        service.order_repo.list = AsyncMock()
        service.order_repo.count = AsyncMock()

        orders, total = await service.list_orders({"user_id": "user_123", "account_id": "other"})

        assert orders == []
        assert total == 0
        service.order_repo.list.assert_not_awaited()
        service.order_repo.count.assert_not_awaited()


@pytest.mark.asyncio
class TestListPositions:
    """Test position listing."""

    async def test_list_positions(self):
        """Test listing positions with filters."""
        service = PaperTradingService()

        mock_positions = [Mock(id=f"pos_{i}", size=1) for i in range(2)]

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=mock_positions)
        service.position_repo.count = AsyncMock(return_value=2)

        positions, total = await service.list_positions({"account_id": "acc_123"})

        assert len(positions) == 2
        assert total == 2

    async def test_list_positions_filters_zero_size_positions(self):
        """Current paper positions should not include fully closed rows."""
        service = PaperTradingService()

        open_long = Mock(id="pos_long", size=2)
        closed = Mock(id="pos_flat", size=0)
        open_short = Mock(id="pos_short", size=-1)

        service.position_repo = AsyncMock()
        service.position_repo.count = AsyncMock(return_value=3)
        service.position_repo.list = AsyncMock(return_value=[open_long, closed, open_short])

        positions, total = await service.list_positions({"account_id": "acc_123"})

        assert positions == [open_long, open_short]
        assert total == 2
        service.position_repo.list.assert_awaited_once()
        assert service.position_repo.list.await_args.kwargs["skip"] == 0
        assert service.position_repo.list.await_args.kwargs["limit"] == 20

    async def test_list_positions_scopes_user_id_to_owned_accounts(self):
        """Position listing must not rely on ignored user_id filters."""
        service = PaperTradingService()

        service.account_repo = AsyncMock()
        service.account_repo.count = AsyncMock(return_value=1)
        service.account_repo.list = AsyncMock(return_value=[Mock(id="acc_1")])
        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[])
        service.position_repo.count = AsyncMock(return_value=0)

        positions, total = await service.list_positions({"user_id": "user_123"})

        assert positions == []
        assert total == 0
        assert service.position_repo.list.await_args.kwargs["filters"] == {"account_id": ["acc_1"]}


@pytest.mark.asyncio
class TestListTrades:
    """Test trade listing."""

    async def test_list_trades(self):
        """Test listing trades with filters."""
        service = PaperTradingService()

        mock_trades = [Mock(id=f"trade_{i}") for i in range(4)]

        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=mock_trades)
        service.trade_repo.count = AsyncMock(return_value=4)

        trades, total = await service.list_trades({"account_id": "acc_123"})

        assert len(trades) == 4
        assert total == 4

    async def test_list_trades_scopes_user_id_to_owned_accounts(self):
        """Trade listing must restrict rows to the current user's accounts."""
        service = PaperTradingService()

        service.account_repo = AsyncMock()
        service.account_repo.count = AsyncMock(return_value=1)
        service.account_repo.list = AsyncMock(return_value=[Mock(id="acc_1")])
        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=[])
        service.trade_repo.count = AsyncMock(return_value=0)

        trades, total = await service.list_trades({"user_id": "user_123", "side": "buy"})

        assert trades == []
        assert total == 0
        assert service.trade_repo.list.await_args.kwargs["filters"] == {
            "side": "buy",
            "account_id": ["acc_1"],
        }


@pytest.mark.asyncio
class TestDeleteAccount:
    """Test account deletion."""

    async def test_delete_account_success(self):
        """Test successful account deletion."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.user_id = "user_123"

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.account_repo.update = AsyncMock()

        result = await service.delete_account("acc_123", "user_123")

        assert result is True

    async def test_delete_account_not_found(self):
        """Test deleting non-existent account returns False."""
        service = PaperTradingService()

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.delete_account("nonexistent", "user_123")

        assert result is False

    async def test_delete_account_wrong_user(self):
        """Test deleting account owned by another user returns False."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.user_id = "other_user"

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        result = await service.delete_account("acc_123", "user_123")

        assert result is False


@pytest.mark.asyncio
class TestCancelOrder:
    """Test order cancellation."""

    async def test_cancel_order_success(self):
        """Test successful order cancellation."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.user_id = "user_123"

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.order_repo.update = AsyncMock()

        with patch.object(service, "_notify_order_update", new_callable=AsyncMock):
            result = await service.cancel_order("order_123", "user_123")

            assert result is True
            assert mock_order.status == OrderStatus.CANCELLED

    async def test_cancel_order_notifies_cancelled_status(self):
        """Cancel notifications should carry the updated cancelled status."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.user_id = "user_123"

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.order_repo.update = AsyncMock()
        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        with patch.object(service, "_notify_order_update", new_callable=AsyncMock) as notify:
            result = await service.cancel_order("order_123", "user_123")

        assert result is True
        notify.assert_awaited_once_with("acc_123", mock_order)
        assert notify.await_args.args[1].status == OrderStatus.CANCELLED

    async def test_cancel_order_not_found(self):
        """Test cancelling non-existent order returns False."""
        service = PaperTradingService()

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.cancel_order("nonexistent", "user_123")

        assert result is False

    async def test_cancel_order_wrong_user(self):
        """Test cancelling order from another user's account returns False."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.user_id = "other_user"

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        result = await service.cancel_order("order_123", "user_123")

        assert result is False

    async def test_cancel_order_already_filled(self):
        """Test cancelling already filled order returns False."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.status = OrderStatus.FILLED

        mock_account = Mock()
        mock_account.user_id = "user_123"

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        result = await service.cancel_order("order_123", "user_123")

        assert result is False


@pytest.mark.asyncio
class TestGetPosition:
    """Test position retrieval."""

    async def test_get_position_found(self):
        """Test retrieving an existing position."""
        service = PaperTradingService()

        mock_position = Mock()
        mock_position.id = "pos_123"

        service.position_repo = AsyncMock()
        service.position_repo.get_by_id = AsyncMock(return_value=mock_position)

        result = await service.get_position("pos_123")

        assert result is not None
        assert result.id == "pos_123"

    async def test_get_position_not_found(self):
        """Test retrieving non-existent position returns None."""
        service = PaperTradingService()

        service.position_repo = AsyncMock()
        service.position_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.get_position("nonexistent")

        assert result is None


class TestCalculateSlippage:
    """Test slippage calculation."""

    def test_calculate_slippage_market_order_buy(self):
        """Test slippage calculation for market buy order."""
        service = PaperTradingService()

        slippage = service._calculate_slippage(
            order_price=None,
            market_price=50000.0,
            slippage_rate=0.001,
            side="buy",
            order_type="market",
        )

        assert slippage == 50.0  # 50000 * 0.001

    def test_calculate_slippage_market_order_sell(self):
        """Test slippage calculation for market sell order."""
        service = PaperTradingService()

        slippage = service._calculate_slippage(
            order_price=None,
            market_price=50000.0,
            slippage_rate=0.001,
            side="sell",
            order_type="market",
        )

        assert slippage == -50.0  # -50000 * 0.001

    def test_calculate_slippage_limit_order_buy_executed(self):
        """Test slippage for marketable limit buy order."""
        service = PaperTradingService()

        slippage = service._calculate_slippage(
            order_price=51000.0,
            market_price=50000.0,
            slippage_rate=0.001,
            side="buy",
            order_type="limit",
        )

        assert slippage == 50.0  # Market price * slippage rate

    def test_calculate_slippage_limit_order_buy_not_executed(self):
        """Test slippage for unexecuted limit buy order."""
        service = PaperTradingService()

        slippage = service._calculate_slippage(
            order_price=49000.0,
            market_price=50000.0,
            slippage_rate=0.001,
            side="buy",
            order_type="limit",
        )

        assert slippage == 0.0

    def test_calculate_slippage_limit_order_sell_executed(self):
        """Test slippage for marketable limit sell order."""
        service = PaperTradingService()

        slippage = service._calculate_slippage(
            order_price=49000.0,
            market_price=50000.0,
            slippage_rate=0.001,
            side="sell",
            order_type="limit",
        )

        assert slippage == -50.0

    def test_execution_price_clamps_limit_buy_to_limit_price(self):
        """A marketable limit buy must not fill above its limit after slippage."""
        service = PaperTradingService()
        order = Mock()
        order.order_type = "limit"
        order.side = OrderSide.BUY
        order.price = 50010.0
        order.limit_price = None

        price = service._execution_price(order, 50000.0, 0.001)

        assert price == pytest.approx(50010.0)

    def test_execution_price_stop_order_waits_until_triggered(self):
        """Stop orders should stay pending until the stop condition is reached."""
        service = PaperTradingService()
        order = Mock()
        order.order_type = "stop"
        order.side = OrderSide.BUY
        order.price = None
        order.stop_price = 50100.0

        assert service._execution_price(order, 50000.0, 0.001) is None
        assert service._execution_price(order, 50100.0, 0.001) == pytest.approx(50150.1)

    def test_execution_price_stop_limit_requires_trigger_and_limit(self):
        """Stop-limit orders require both stop trigger and marketable limit."""
        service = PaperTradingService()
        order = Mock()
        order.order_type = "stop_limit"
        order.side = OrderSide.BUY
        order.price = None
        order.stop_price = 50100.0
        order.limit_price = 50120.0

        assert service._execution_price(order, 50090.0, 0.0) is None
        assert service._execution_price(order, 50130.0, 0.0) is None
        assert service._execution_price(order, 50110.0, 0.0) == pytest.approx(50110.0)

    def test_calculate_slippage_other_order_type(self):
        """Test slippage calculation for other order types."""
        service = PaperTradingService()

        slippage = service._calculate_slippage(
            order_price=50000.0,
            market_price=50000.0,
            slippage_rate=0.001,
            side="buy",
            order_type="stop",
        )

        assert slippage == 0.0


@pytest.mark.asyncio
class TestGetSimulatedPrice:
    """Test simulated price retrieval."""

    async def test_get_simulated_price_000001(self):
        """Test getting price for symbol 000001."""
        service = PaperTradingService()

        price = await service._get_simulated_price("000001")

        assert price == 10.5

    async def test_get_simulated_price_600000(self):
        """Test getting price for symbol 600000."""
        service = PaperTradingService()

        price = await service._get_simulated_price("600000")

        assert price == 10.8

    async def test_get_simulated_price_default(self):
        """Test getting default price for unknown symbols."""
        service = PaperTradingService()

        price = await service._get_simulated_price("BTC/USDT")

        assert price == 10.0


@pytest.mark.asyncio
class TestWebSocketNotifications:
    """Test WebSocket notification functions."""

    async def test_notify_account_update(self):
        """Test account update WebSocket notification."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.current_cash = 100000.0
        mock_account.total_equity = 100000.0
        mock_account.profit_loss = 0.0
        mock_account.profit_loss_pct = 0.0

        with patch("app.services.paper_trading_service.ws_manager") as mock_ws:
            mock_ws.send_to_task = AsyncMock()
            await service._notify_account_update(mock_account)
            mock_ws.send_to_task.assert_awaited_once_with(
                "account:acc_123",
                {
                    "type": "progress",
                    "account_id": "acc_123",
                    "data": {
                        "current_cash": 100000.0,
                        "total_equity": 100000.0,
                        "profit_loss": 0.0,
                        "profit_loss_pct": 0.0,
                    },
                },
            )

    async def test_notify_position_update(self):
        """Test position update WebSocket notification."""
        service = PaperTradingService()

        mock_position = Mock()
        mock_position.id = "pos_123"
        mock_position.symbol = "BTC/USDT"
        mock_position.size = 10
        mock_position.avg_price = 50000.0
        mock_position.market_value = 500000.0
        mock_position.margin_value = 500000.0
        mock_position.multiplier = 1.0
        mock_position.margin_rate = 1.0
        mock_position.commission_rate = 0.001
        mock_position.commission_amount = 0.0
        mock_position.unrealized_pnl = 0.0
        mock_position.unrealized_pnl_pct = 0.0

        with patch("app.services.paper_trading_service.ws_manager") as mock_ws:
            mock_ws.send_to_task = AsyncMock()
            await service._notify_position_update(mock_position)
            mock_ws.send_to_task.assert_awaited_once_with(
                "position:pos_123",
                {
                    "type": "progress",
                    "position_id": "pos_123",
                    "data": {
                        "symbol": "BTC/USDT",
                        "size": 10,
                        "avg_price": 50000.0,
                        "market_value": 500000.0,
                        "margin_value": 500000.0,
                        "multiplier": 1.0,
                        "margin_rate": 1.0,
                        "commission_rate": 0.001,
                        "commission_amount": 0.0,
                        "unrealized_pnl": 0.0,
                        "unrealized_pnl_pct": 0.0,
                    },
                },
            )

    async def test_notify_order_update(self):
        """Test order update WebSocket notification."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = "buy"
        mock_order.size = 10
        mock_order.price = 50000.0
        mock_order.status = OrderStatus.FILLED
        mock_order.filled_size = 10

        with patch("app.services.paper_trading_service.ws_manager") as mock_ws:
            mock_ws.send_to_task = AsyncMock()
            await service._notify_order_update("acc_123", mock_order)
            mock_ws.send_to_task.assert_awaited_once_with(
                "account:acc_123",
                {
                    "type": "progress",
                    "order_id": "order_123",
                    "data": {
                        "symbol": "BTC/USDT",
                        "side": "buy",
                        "size": 10,
                        "price": 50000.0,
                        "status": OrderStatus.FILLED,
                        "filled_size": 10,
                    },
                },
            )


@pytest.mark.asyncio
class TestHelperFunctions:
    """Test helper functions."""

    async def test_get_position_exists(self):
        """Test retrieving existing position for account and symbol."""
        service = PaperTradingService()

        mock_position = Mock()
        mock_position.id = "pos_123"

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])

        result = await service._get_position("acc_123", "BTC/USDT")

        assert result is not None
        assert result.id == "pos_123"

    async def test_get_position_not_exists(self):
        """Test retrieving non-existent position returns None."""
        service = PaperTradingService()

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[])

        result = await service._get_position("acc_123", "BTC/USDT")

        assert result is None

    async def test_get_last_trade_exists(self):
        """Test retrieving last trade for an order."""
        service = PaperTradingService()

        mock_trade = Mock()
        mock_trade.id = "trade_123"

        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=[mock_trade])

        result = await service._get_last_trade("order_123")

        assert result is not None

    async def test_get_last_trade_not_exists(self):
        """Test retrieving last trade when no trades exist returns None."""
        service = PaperTradingService()

        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=[])

        result = await service._get_last_trade("order_123")

        assert result is None
