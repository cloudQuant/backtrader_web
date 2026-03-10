"""
Paper trading models.

Supports accounts, orders, and position management.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.database import Base


class OrderType(str, Enum):
    """Order type enum."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(str, Enum):
    """Order side enum."""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """Order status enum."""

    PENDING = "pending"
    PARTIAL_FILLED = "partial_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Account(Base):
    """Paper trading account table.

    Attributes:
        id: Unique account identifier (UUID).
        user_id: User ID who owns the account.
        name: Account name.
        initial_cash: Initial cash amount.
        current_cash: Current cash amount.
        total_equity: Total equity (cash + position value).
        profit_loss: Profit/loss amount.
        profit_loss_pct: Profit/loss percentage.
        commission_rate: Commission rate.
        slippage_rate: Slippage rate.
        is_active: Whether the account is active.
        created_at: Account creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "paper_trading_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    initial_cash = Column(Float, default=100000.0, nullable=False)
    current_cash = Column(Float, default=100000.0, nullable=False)
    total_equity = Column(
        Float, default=100000.0, nullable=False
    )  # Total equity (cash + position value)
    profit_loss = Column(Float, default=0.0, nullable=False)  # Profit/loss
    profit_loss_pct = Column(Float, default=0.0, nullable=False)  # Profit/loss percentage
    commission_rate = Column(Float, default=0.001, nullable=False)  # Commission rate
    slippage_rate = Column(Float, default=0.001, nullable=False)  # Slippage rate
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", back_populates="paper_trading_accounts")
    positions = relationship("Position", back_populates="account", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="account", cascade="all, delete-orphan")
    trades = relationship("PaperTrade", back_populates="account", cascade="all, delete-orphan")


class Position(Base):
    """Paper trading position table.

    Attributes:
        id: Unique position identifier (UUID).
        account_id: Associated account ID.
        symbol: Trading symbol.
        size: Position size (positive for long, negative for short).
        avg_price: Average cost price.
        market_value: Market value.
        unrealized_pnl: Unrealized profit/loss.
        unrealized_pnl_pct: Unrealized profit/loss percentage.
        entry_price: Entry price.
        entry_time: Entry time.
        updated_at: Last update timestamp.
    """

    __tablename__ = "paper_trading_positions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(
        String(36), ForeignKey("paper_trading_accounts.id"), nullable=False, index=True
    )
    symbol = Column(String(20), nullable=False, index=True)
    size = Column(
        Integer, default=0, nullable=False
    )  # Position size (positive for long, negative for short)
    avg_price = Column(Float, default=0.0, nullable=False)  # Average cost
    market_value = Column(Float, default=0.0, nullable=False)  # Market value
    unrealized_pnl = Column(Float, default=0.0, nullable=False)  # Unrealized profit/loss
    unrealized_pnl_pct = Column(
        Float, default=0.0, nullable=False
    )  # Unrealized profit/loss percentage
    entry_price = Column(Float, default=0.0, nullable=False)  # Entry price
    entry_time = Column(DateTime, nullable=True)  # Entry time
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    account = relationship("Account", back_populates="positions")


class Order(Base):
    """Paper trading order table.

    Attributes:
        id: Unique order identifier (UUID).
        account_id: Associated account ID.
        symbol: Trading symbol.
        order_type: Order type (MARKET, LIMIT, STOP, STOP_LIMIT).
        side: Order side (BUY, SELL).
        size: Order size.
        price: Limit order price.
        stop_price: Stop loss price.
        limit_price: Take profit price.
        filled_size: Filled size.
        avg_fill_price: Average fill price.
        status: Order status.
        rejected_reason: Rejection reason.
        commission: Commission amount.
        slippage: Slippage amount.
        created_at: Order creation timestamp.
        updated_at: Last update timestamp.
        filled_at: Fill timestamp.
    """

    __tablename__ = "paper_trading_orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(
        String(36), ForeignKey("paper_trading_accounts.id"), nullable=False, index=True
    )
    symbol = Column(String(20), nullable=False, index=True)
    order_type = Column(String(20), nullable=False)  # MARKET, LIMIT, STOP, STOP_LIMIT
    side = Column(String(10), nullable=False)  # BUY, SELL
    size = Column(Integer, nullable=False)  # Order size
    price = Column(Float, nullable=True)  # Limit order price
    stop_price = Column(Float, nullable=True)  # Stop loss price
    limit_price = Column(Float, nullable=True)  # Take profit price
    filled_size = Column(Integer, default=0, nullable=False)  # Filled size
    avg_fill_price = Column(Float, default=0.0, nullable=False)  # Average fill price
    status = Column(String(20), default=OrderStatus.PENDING.value, nullable=False, index=True)
    rejected_reason = Column(String(255), nullable=True)  # Rejection reason
    commission = Column(Float, default=0.0, nullable=False)  # Commission
    slippage = Column(Float, default=0.0, nullable=False)  # Slippage
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    filled_at = Column(DateTime, nullable=True)  # Fill time

    # Relationships
    account = relationship("Account", back_populates="orders")


class PaperTrade(Base):
    """Paper trading trade record table.

    Attributes:
        id: Unique trade identifier (UUID).
        account_id: Associated account ID.
        order_id: Associated order ID.
        symbol: Trading symbol.
        side: Trade side (BUY, SELL).
        size: Trade size.
        price: Trade price.
        commission: Commission amount.
        slippage: Slippage amount.
        pnl: Profit/loss.
        pnl_pct: Profit/loss percentage.
        created_at: Trade timestamp.
    """

    __tablename__ = "paper_trades"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(
        String(36), ForeignKey("paper_trading_accounts.id"), nullable=False, index=True
    )
    order_id = Column(String(36), ForeignKey("paper_trading_orders.id"), nullable=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False)  # BUY, SELL
    size = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    commission = Column(Float, default=0.0, nullable=False)
    slippage = Column(Float, default=0.0, nullable=False)
    pnl = Column(Float, default=0.0, nullable=False)  # Profit/loss
    pnl_pct = Column(Float, default=0.0, nullable=False)  # Profit/loss percentage
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    account = relationship("Account", back_populates="trades")
    order = relationship("Order")
