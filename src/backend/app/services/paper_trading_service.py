"""
模拟交易服务

基于 Backtrader 的模拟交易环境
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
    """
    模拟交易服务

    功能：
    1. 创建和管理模拟账户
    2. 提交和管理模拟订单
    3. 模拟订单成交
    4. 计算持仓和盈亏
    5. WebSocket 实时推送
    """

    def __init__(self):
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
        """
        创建模拟账户

        Args:
            user_id: 用户 ID
            name: 账户名称
            initial_cash: 初始资金
            commission_rate: 手续费率
            slippage_rate: 滑点率

        Returns:
            Account: 创建的账户
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

        # 推送通知
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
        """
        提交模拟订单

        Args:
            account_id: 账户 ID
            symbol: 标的代码
            order_type: 订单类型
            side: 买卖方向
            size: 数量
            price: 价格（限价单）
            stop_price: 止损价格
            limit_price: 止盈价格

        Returns:
            Order: 创建的订单
        """
        # 获取账户
        account = await self.account_repo.get_by_id(account_id)
        if not account:
            raise ValueError(f"Account not found: {account_id}")

        # 计算保证金和手续费
        commission = size * price * account.commission_rate if price else 0

        # 创建订单
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

        # 推送订单创建通知
        await self._notify_order_update(account_id, order)

        # 异步处理订单成交
        asyncio.create_task(self._process_order(order.id, account_id, account))

        return order

    async def _process_order(self, order_id: str, account_id: str, account: Account):
        """
        处理订单成交（模拟）

        Args:
            order_id: 订单 ID
            account_id: 账户 ID
            account: 账户对象
        """
        # 获取订单
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            logger.error(f"Order not found: {order_id}")
            return

        # 获取当前价格（模拟）
        current_price = await self._get_simulated_price(order.symbol)

        # 计算滑点
        slippage = self._calculate_slippage(
            order.price,
            current_price,
            account.slippage_rate,
            order.side,
            order.order_type,
        )

        fill_price = current_price + slippage
        commission = order.size * fill_price * account.commission_rate

        # 检查是否有足够资金
        if order.side == OrderSide.BUY:
            required_cash = order.size * fill_price + commission
            if account.current_cash < required_cash:
                # 拒绝订单
                await self._reject_order(order, "Insufficient funds")
                return
        else:
            # 卖出，检查是否有足够持仓
            position = await self._get_position(account_id, order.symbol)
            if not position or abs(position.size) < order.size:
                await self._reject_order(order, "Insufficient position")
                return

        # 执行成交
        await self._fill_order(order, fill_price, commission)

        # 更新持仓
        await self._update_position(account, order, fill_price, commission)

        # 更新账户
        await self._update_account(account, order, fill_price, commission)

        logger.info(f"Order filled: {order_id} at {fill_price}")

    async def _fill_order(self, order: Order, price: float, commission: float):
        """
        填充订单

        Args:
            order: 订单对象
            price: 成交价格
            commission: 手续费
        """
        # 更新订单状态
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

        # 创建成交记录
        trade = PaperTrade(
            account_id=order.account_id,
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            size=order.size,
            price=price,
            commission=commission,
            slippage=0.0,  # 滑点已包含在价格中
            pnl=0.0,  # 暂时为 0，后续在更新持仓时计算
            pnl_pct=0.0,
        )

        await self.trade_repo.create(trade)

    async def _reject_order(self, order: Order, reason: str):
        """
        拒绝订单

        Args:
            order: 订单对象
            reason: 拒绝原因
        """
        order.status = OrderStatus.REJECTED
        order.rejected_reason = reason

        await self.order_repo.update(order.id, {
            "status": order.status,
            "rejected_reason": order.rejected_reason,
        })

        # 推送订单更新
        account_id = order.account_id
        await self._notify_order_update(account_id, order)

    async def _get_position(self, account_id: str, symbol: str) -> Optional[Position]:
        """
        获取持仓

        Args:
            account_id: 账户 ID
            symbol: 标的代码

        Returns:
            Position or None
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
    ):
        """
        更新持仓

        Args:
            account: 账户对象
            order: 订单对象
            price: 成交价格
            commission: 手续费
        """
        position = await self._get_position(account.id, order.symbol)

        if not position:
            # 新建持仓
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
            # 更新现有持仓
            old_size = position.size
            old_market_value = position.market_value

            # 更新数量
            if order.side == OrderSide.BUY:
                new_size = old_size + order.size
            else:
                new_size = old_size - order.size

            # 计算新的平均价格
            total_value = abs(old_size) * position.avg_price + order.size * price
            new_avg_price = total_value / abs(new_size) if new_size != 0 else 0

            # 计算新的市值
            new_market_value = new_size * price

            # 计算未实现盈亏
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

            # 更新成交记录的盈亏（如果是平仓）
            if (old_size > 0 and new_size <= 0) or (old_size < 0 and new_size >= 0):
                # 计算已实现盈亏
                if old_size > 0:
                    pnl = (price - position.avg_price) * abs(old_size)
                else:
                    pnl = (position.avg_price - price) * abs(old_size)

                pnl_pct = (pnl / (abs(old_size) * position.avg_price) * 100) if position.avg_price != 0 else 0

                # 更新成交记录
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
    ):
        """
        更新账户

        Args:
            account: 账户对象
            order: 订单对象
            price: 成交价格
            commission: 手续费
        """
        # 计算持仓价值
        positions = await self.position_repo.list(filters={"account_id": account.id})
        total_market_value = sum(p.market_value for p in positions)

        # 更新现金
        if order.side == OrderSide.BUY:
            account.current_cash -= order.size * price + commission
        else:
            account.current_cash += order.size * price - commission

        # 更新总权益
        account.total_equity = account.current_cash + total_market_value

        # 更新盈亏
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

        # 推送账户更新
        await self._notify_account_update(account)

        # 推送持仓更新
        for position in positions:
            await self._notify_position_update(position)

    async def _get_last_trade(self, order_id: str) -> Optional[PaperTrade]:
        """
        获取最后一个成交

        Args:
            order_id: 订单 ID

        Returns:
            PaperTrade or None
        """
        trades = await self.trade_repo.list(
            filters={"order_id": order_id},
            limit=1,
            sort_by="created_at",
            sort_order="desc",
        )

        return trades[0] if trades else None

    async def get_account(self, account_id: str) -> Optional[Account]:
        """
        获取账户

        Args:
            account_id: 账户 ID

        Returns:
            Account or None
        """
        return await self.account_repo.get_by_id(account_id)

    async def list_accounts(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[List[Account], int]:
        """
        列出用户的模拟账户

        Args:
            user_id: 用户 ID
            limit: 每页数量
            offset: 偏移量

        Returns:
            (accounts, total)
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
        """
        获取订单

        Args:
            order_id: 订单 ID

        Returns:
            Order or None
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
        """
        列出订单

        Args:
            filters: 过滤条件
            limit: 每页数量
            offset: 偏移量
            sort_by: 排序字段
            sort_order: 排序方向

        Returns:
            (orders, total)
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
        """
        列出持仓

        Args:
            filters: 过滤条件
            limit: 每页数量
            offset: 偏移量
            sort_by: 排序字段
            sort_order: 排序方向

        Returns:
            (positions, total)
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
        """
        列出成交

        Args:
            filters: 过滤条件
            limit: 每页数量
            offset: 偏移量
            sort_by: 排序字段
            sort_order: 排序方向

        Returns:
            (trades, total)
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
        """
        删除模拟账户

        Args:
            account_id: 账户 ID
            user_id: 用户 ID

        Returns:
            bool: 是否删除成功
        """
        account = await self.account_repo.get_by_id(account_id)
        if not account or account.user_id != user_id:
            return False

        # 软删除：标记为不活跃
        await self.account_repo.update(account_id, {"is_active": False})
        return True

    async def cancel_order(self, order_id: str, user_id: str) -> bool:
        """
        撤销订单

        Args:
            order_id: 订单 ID
            user_id: 用户 ID

        Returns:
            bool: 是否撤销成功
        """
        order = await self.order_repo.get_by_id(order_id)
        if not order:
            return False

        # 检查权限
        account = await self.account_repo.get_by_id(order.account_id)
        if not account or account.user_id != user_id:
            return False

        # 只有待成交的订单可以撤销
        if order.status != OrderStatus.PENDING:
            return False

        # 标记为已撤销
        await self.order_repo.update(order_id, {"status": OrderStatus.CANCELLED})

        # 推送更新
        await self._notify_order_update(order.account_id, order)

        return True

    async def get_position(self, position_id: str) -> Optional[Position]:
        """
        获取持仓

        Args:
            position_id: 持仓 ID

        Returns:
            Position or None
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
        """
        计算滑点

        Args:
            order_price: 订单价格
            market_price: 市场价格
            slippage_rate: 滑点率
            side: 买卖方向
            order_type: 订单类型

        Returns:
            float: 滑点金额
        """
        if order_type == OrderType.MARKET:
            # 市价单，直接按滑点率计算
            if side == OrderSide.BUY:
                return market_price * slippage_rate
            else:
                return -market_price * slippage_rate
        elif order_type == OrderType.LIMIT:
            # 限价单，如果限价优于市价则成交，否则可能不成交
            if order_price and side == OrderSide.BUY:
                if order_price <= market_price:
                    return market_price * slippage_rate
            elif order_price and side == OrderSide.SELL:
                if order_price >= market_price:
                    return -market_price * slippage_rate
            return 0.0
        else:
            # 其他类型，暂时不计算滑点
            return 0.0

    async def _get_simulated_price(self, symbol: str) -> float:
        """
        获取模拟价格

        在实际应用中，这里应该从实时数据源获取价格
        目前使用模拟价格

        Args:
            symbol: 标的代码

        Returns:
            float: 模拟价格
        """
        # 这里应该集成实时行情数据源
        # 目前返回固定价格用于测试
        if "000001" in symbol:
            return 10.5
        elif "600000" in symbol:
            return 10.8
        else:
            return 10.0

    async def _notify_account_update(self, account: Account):
        """
        推送账户更新

        Args:
            account: 账户对象
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

    async def _notify_position_update(self, position: Position):
        """
        推送持仓更新

        Args:
            position: 持仓对象
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

    async def _notify_order_update(self, account_id: str, order: Order):
        """
        推送订单更新

        Args:
            account_id: 账户 ID
            order: 订单对象
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
