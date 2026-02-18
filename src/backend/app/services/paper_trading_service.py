"""
Paper trading service.

Provides a Backtrader-based paper trading environment.
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import logging

from app.models.paper_trading import (
    Account,
    Position,
    Order,
    OrderType,
    OrderSide,
    OrderStatus,
    PaperTrade,
)
from app.db.sql_repository import SQLRepository
from app.websocket_manager import manager as ws_manager, MessageType, ProgressMessage

logger = logging.getLogger(__name__)


class PaperTradingService:
    """Paper trading service.

    This service provides:
    1. Create and manage paper trading accounts
    2. Submit and manage paper orders
    3. Simulate order execution
    4. Calculate positions and PnL
    5. Real-time WebSocket notifications
    """

    def __init__(self) -> None:
        """Initialize the paper trading service."""
        self.account_repo = SQLRepository(Account)
        self.position_repo = SQLRepository(Position)
        self.order_repo = SQLRepository(Order)
        self.trade_repo = SQLRepository(PaperTrade)

    async def create_account(
        self,
        user_id: str,
        name: str,
        initial_cash: float = 100000.0,
        commission_rate: float = 0.001,
        slippage_rate: float = 0.001,
    ) -> Account:
        """Create a paper trading account.

        Args:
            user_id: The user ID.
            name: Account name.
            initial_cash: Initial cash amount.
            commission_rate: Commission rate.
            slippage_rate: Slippage rate.

        Returns:
            The created account.
        """
        account = Account(
            user_id=user_id,
            name=name,
            initial_cash=initial_cash,
            current_cash=initial_cash,
            total_equity=initial_cash,
            profit_loss=0.0,
            profit_loss_pct=0.0,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
        )

        account = await self.account_repo.create(account)

        logger.info(f"Created paper trading account: {account.id} for user {user_id}")

        # Send notification
        await self._notify_account_update(account)

        return account

    async def submit_order(
        self,
        account_id: str,
        symbol: str,
        order_type: str,
        side: str,
        size: int,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        limit_price: Optional[float] = None,
    ) -> Order:
        """Submit a paper trading order.

        Args:
            account_id: Account ID.
            symbol: Trading symbol.
            order_type: Order type (market, limit, stop, etc.).
            side: Order side (buy/sell).
            size: Order size.
            price: Limit price (for limit orders).
            stop_price: Stop price (for stop orders).
            limit_price: Limit price (for stop-limit orders).

        Returns:
            The created order.
        """
        # Get account
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            raise ValueError(f"Account not found: {account_id}")

        # Calculate margin and commission
        commission = size * price * account.commission_rate if price else 0

        # Create order
        order = Order(
            account_id=account_id,
            symbol=symbol,
            order_type=order_type,
            side=side,
            size=size,
            price=price,
            stop_price=stop_price,
            limit_price=limit_price,
            status=OrderStatus.PENDING,
            commission=commission,
        )

        order = await self.order_repo.create(order)

        logger.info(f"Submitted paper order: {order.id} for account {account_id}")

        # Send order creation notification
        await self._notify_order_update(account_id, order)

        # Process order fill asynchronously
        asyncio.create_task(self._process_order(order.id, account_id, account))

        return order

    async def _process_order(self, order_id: str, account_id: str, account: Account) -> None:
        """Process order execution (simulated).

        Args:
            order_id: Order ID.
            account_id: Account ID.
            account: Account object.
        """
        # Get order
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            logger.error(f"Order not found: {order_id}")
            return

        # Get current price (simulated)
        current_price = await self._get_simulated_price(order.symbol)

        # Calculate slippage
        slippage = self._calculate_slippage(
            order.price,
            current_price,
            account.slippage_rate,
            order.side,
            order.order_type,
        )

        fill_price = current_price + slippage
        commission = order.size * fill_price * account.commission_rate

        # Check sufficient funds
        if order.side == OrderSide.BUY:
            required_cash = order.size * fill_price + commission
            if account.current_cash < required_cash:
                # Reject order
                await self._reject_order(order, "Insufficient funds")
                return
        else:
            # Sell, check sufficient position
            position = await self._get_position(account_id, order.symbol)
            if not position or abs(position.size) < order.size:
                await self._reject_order(order, "Insufficient position")
                return

        # Execute fill
        await self._fill_order(order, fill_price, commission)

        # Update position
        await self._update_position(account, order, fill_price, commission)

        # Update account
        await self._update_account(account, order, fill_price, commission)

        logger.info(f"Order filled: {order_id} at {fill_price}")

    async def _fill_order(self, order: Order, price: float, commission: float) -> None:
        """Fill an order.

        Args:
            order: Order object.
            price: Fill price.
            commission: Commission amount.
        """
        # Update order status
        order.status = OrderStatus.FILLED
        order.filled_size = order.size
        order.avg_fill_price = price
        order.commission = commission
        order.filled_at = datetime.now(timezone.utc)

        await self.order_repo.update(order.id, {
            "status": order.status,
            "filled_size": order.filled_size,
            "avg_fill_price": order.avg_fill_price,
            "commission": order.commission,
            "filled_at": order.filled_at,
        })

        # Create trade record
        trade = PaperTrade(
            account_id=order.account_id,
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            size=order.size,
            price=price,
            commission=commission,
            slippage=0.0,  # Slippage already included in price
            pnl=0.0,  # Will be calculated when updating position
            pnl_pct=0.0,
        )

        await self.trade_repo.create(trade)

    async def _reject_order(self, order: Order, reason: str) -> None:
        """Reject an order.

        Args:
            order: Order object.
            reason: Rejection reason.
        """
        order.status = OrderStatus.REJECTED
        order.rejected_reason = reason

        await self.order_repo.update(order.id, {
            "status": order.status,
            "rejected_reason": order.rejected_reason,
        })

        # Send order update
        account_id = order.account_id
        await self._notify_order_update(account_id, order)

    async def _get_position(self, account_id: str, symbol: str) -> Optional[Position]:
        """Get position by account and symbol.

        Args:
            account_id: Account ID.
            symbol: Trading symbol.

        Returns:
            Position or None.
        """
        positions = await self.position_repo.list(
            filters={"account_id": account_id, "symbol": symbol},
            limit=1
        )

        return positions[0] if positions else None

    async def _update_position(
        self,
        account: Account,
        order: Order,
        price: float,
        commission: float,
    ) -> None:
        """Update position after order fill.

        Args:
            account: Account object.
            order: Order object.
            price: Fill price.
            commission: Commission amount.
        """
        position = await self._get_position(account.id, order.symbol)

        if not position:
            # Create new position
            position = Position(
                account_id=account.id,
                symbol=order.symbol,
                size=order.size if order.side == OrderSide.BUY else -order.size,
                avg_price=price,
                market_value=order.size * price,
                unrealized_pnl=0.0,
                unrealized_pnl_pct=0.0,
                entry_price=price,
                entry_time=datetime.now(timezone.utc),
            )

            await self.position_repo.create(position)

        else:
            # Update existing position
            old_size = position.size
            old_market_value = position.market_value

            # Update size
            if order.side == OrderSide.BUY:
                new_size = old_size + order.size
            else:
                new_size = old_size - order.size

            # Calculate new average price
            total_value = abs(old_size) * position.avg_price + order.size * price
            new_avg_price = total_value / abs(new_size) if new_size != 0 else 0

            # Calculate new market value
            new_market_value = new_size * price

            # Calculate unrealized PnL
            if new_size != 0:
                if new_size > 0:
                    unrealized_pnl = (price - new_avg_price) * new_size
                else:
                    unrealized_pnl = (new_avg_price - price) * abs(new_size)
            else:
                unrealized_pnl = old_market_value - abs(old_size) * new_avg_price

            unrealized_pnl_pct = (unrealized_pnl / abs(new_size * new_avg_price) * 100) if new_avg_price != 0 else 0

            await self.position_repo.update(position.id, {
                "size": new_size,
                "avg_price": new_avg_price,
                "market_value": new_market_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "updated_at": datetime.now(timezone.utc),
            })

            # Update trade record PnL (if closing position)
            if (old_size > 0 and new_size <= 0) or (old_size < 0 and new_size >= 0):
                # Calculate realized PnL
                if old_size > 0:
                    pnl = (price - position.avg_price) * abs(old_size)
                else:
                    pnl = (position.avg_price - price) * abs(old_size)

                pnl_pct = (pnl / (abs(old_size) * position.avg_price) * 100) if position.avg_price != 0 else 0

                # Update trade record
                trade = await self._get_last_trade(order.id)
                if trade:
                    await self.trade_repo.update(trade.id, {
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                    })

    async def _update_account(
        self,
        account: Account,
        order: Order,
        price: float,
        commission: float,
    ) -> None:
        """Update account after order fill.

        Args:
            account: Account object.
            order: Order object.
            price: Fill price.
            commission: Commission amount.
        """
        # Calculate position value
        positions = await self.position_repo.list(filters={"account_id": account.id})
        total_market_value = sum(p.market_value for p in positions)

        # Update cash
        if order.side == OrderSide.BUY:
            account.current_cash -= order.size * price + commission
        else:
            account.current_cash += order.size * price - commission

        # Update total equity
        account.total_equity = account.current_cash + total_market_value

        # Update PnL
        profit_loss = account.total_equity - account.initial_cash
        account.profit_loss = profit_loss
        account.profit_loss_pct = (profit_loss / account.initial_cash) * 100

        await self.account_repo.update(account.id, {
            "current_cash": account.current_cash,
            "total_equity": account.total_equity,
            "profit_loss": account.profit_loss,
            "profit_loss_pct": account.profit_loss_pct,
            "updated_at": datetime.now(timezone.utc),
        })

        # Send account update
        await self._notify_account_update(account)

        # Send position updates
        for position in positions:
            await self._notify_position_update(position)

    async def _get_last_trade(self, order_id: str) -> Optional[PaperTrade]:
        """Get the last trade for an order.

        Args:
            order_id: Order ID.

        Returns:
            PaperTrade or None.
        """
        trades = await self.trade_repo.list(
            filters={"order_id": order_id},
            limit=1,
            sort_by="created_at",
            sort_order="desc",
        )

        return trades[0] if trades else None

    async def get_account(self, account_id: str) -> Optional[Account]:
        """Get account by ID.

        Args:
            account_id: Account ID.

        Returns:
            Account or None.
        """
        return await self.account_repo.get_by_id(account_id)

    async def list_accounts(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[List[Account], int]:
        """List user's paper trading accounts.

        Args:
            user_id: User ID.
            limit: Items per page.
            offset: Offset for pagination.

        Returns:
            Tuple of (accounts list, total count).
        """
        accounts = await self.account_repo.list(
            filters={"user_id": user_id, "is_active": True},
            skip=offset,
            limit=limit,
            sort_by="created_at",
            sort_order="desc",
        )
        total = await self.account_repo.count(
            filters={"user_id": user_id, "is_active": True}
        )

        return accounts, total

    async def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID.

        Args:
            order_id: Order ID.

        Returns:
            Order or None.
        """
        return await self.order_repo.get_by_id(order_id)

    async def list_orders(
        self,
        filters: dict,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[List[Order], int]:
        """List orders with filtering.

        Args:
            filters: Filter conditions.
            limit: Items per page.
            offset: Offset for pagination.
            sort_by: Sort field.
            sort_order: Sort direction.

        Returns:
            Tuple of (orders list, total count).
        """
        orders = await self.order_repo.list(
            filters=filters,
            skip=offset,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        total = await self.order_repo.count(filters=filters)

        return orders, total

    async def list_positions(
        self,
        filters: dict,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[List[Position], int]:
        """List positions with filtering.

        Args:
            filters: Filter conditions.
            limit: Items per page.
            offset: Offset for pagination.
            sort_by: Sort field.
            sort_order: Sort direction.

        Returns:
            Tuple of (positions list, total count).
        """
        positions = await self.position_repo.list(
            filters=filters,
            skip=offset,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        total = await self.position_repo.count(filters=filters)

        return positions, total

    async def list_trades(
        self,
        filters: dict,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[List[PaperTrade], int]:
        """List trades with filtering.

        Args:
            filters: Filter conditions.
            limit: Items per page.
            offset: Offset for pagination.
            sort_by: Sort field.
            sort_order: Sort direction.

        Returns:
            Tuple of (trades list, total count).
        """
        trades = await self.trade_repo.list(
            filters=filters,
            skip=offset,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        total = await self.trade_repo.count(filters=filters)

        return trades, total

    async def delete_account(self, account_id: str, user_id: str) -> bool:
        """Delete a paper trading account.

        Args:
            account_id: Account ID.
            user_id: User ID for authorization.

        Returns:
            True if deleted successfully, False otherwise.
        """
        account = await self.account_repo.get_by_id(account_id)
        if not account or account.user_id != user_id:
            return False

        # Soft delete: mark as inactive
        await self.account_repo.update(account_id, {"is_active": False})
        return True

    async def cancel_order(self, order_id: str, user_id: str) -> bool:
        """Cancel an order.

        Args:
            order_id: Order ID.
            user_id: User ID for authorization.

        Returns:
            True if cancelled successfully, False otherwise.
        """
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            return False

        # Check permission
        account = await self.account_repo.get_by_id(order.account_id)
        if not account or account.user_id != user_id:
            return False

        # Only pending orders can be cancelled
        if order.status != OrderStatus.PENDING:
            return False

        # Mark as cancelled
        await self.order_repo.update(order_id, {"status": OrderStatus.CANCELLED})

        # Send update
        await self._notify_order_update(order.account_id, order)

        return True

    async def get_position(self, position_id: str) -> Optional[Position]:
        """Get position by ID.

        Args:
            position_id: Position ID.

        Returns:
            Position or None.
        """
        return await self.position_repo.get_by_id(position_id)

    def _calculate_slippage(
        self,
        order_price: Optional[float],
        market_price: float,
        slippage_rate: float,
        side: str,
        order_type: str,
    ) -> float:
        """Calculate slippage amount.

        Args:
            order_price: Order price.
            market_price: Current market price.
            slippage_rate: Slippage rate.
            side: Order side (buy/sell).
            order_type: Order type.

        Returns:
            Slippage amount.
        """
        if order_type == OrderType.MARKET:
            # Market order, calculate directly from rate
            if side == OrderSide.BUY:
                return market_price * slippage_rate
            else:
                return -market_price * slippage_rate
        elif order_type == OrderType.LIMIT:
            # Limit order, fill if limit is better than market
            if order_price and side == OrderSide.BUY:
                if order_price <= market_price:
                    return market_price * slippage_rate
            elif order_price and side == OrderSide.SELL:
                if order_price >= market_price:
                    return -market_price * slippage_rate
            return 0.0
        else:
            # Other types, no slippage for now
            return 0.0

    async def _get_simulated_price(self, symbol: str) -> float:
        """Get simulated price for trading.

        In production, this should fetch from real-time data source.
        Currently returns simulated price for testing.

        Args:
            symbol: Trading symbol.

        Returns:
            Simulated price.
        """
        # This should integrate with real-time market data
        # Currently returns fixed price for testing
        if "000001" in symbol:
            return 10.5
        elif "600000" in symbol:
            return 10.8
        else:
            return 10.0

    async def _notify_account_update(self, account: Account) -> None:
        """Send account update notification via WebSocket.

        Args:
            account: Account object.
        """
        await ws_manager.send_to_task(f"account:{account.id}", {
            "type": MessageType.PROGRESS,
            "account_id": account.id,
            "data": {
                "current_cash": account.current_cash,
                "total_equity": account.total_equity,
                "profit_loss": account.profit_loss,
                "profit_loss_pct": account.profit_loss_pct,
            }
        })

    async def _notify_position_update(self, position: Position) -> None:
        """Send position update notification via WebSocket.

        Args:
            position: Position object.
        """
        await ws_manager.send_to_task(f"position:{position.id}", {
            "type": MessageType.PROGRESS,
            "position_id": position.id,
            "data": {
                "symbol": position.symbol,
                "size": position.size,
                "avg_price": position.avg_price,
                "market_value": position.market_value,
                "unrealized_pnl": position.unrealized_pnl,
                "unrealized_pnl_pct": position.unrealized_pnl_pct,
            }
        })

    async def _notify_order_update(self, account_id: str, order: Order) -> None:
        """Send order update notification via WebSocket.

        Args:
            account_id: Account ID.
            order: Order object.
        """
        await ws_manager.send_to_task(f"account:{account_id}", {
            "type": MessageType.PROGRESS,
            "order_id": order.id,
            "data": {
                "symbol": order.symbol,
                "side": order.side,
                "size": order.size,
                "price": order.price,
                "status": order.status,
                "filled_size": order.filled_size,
            }
        })
