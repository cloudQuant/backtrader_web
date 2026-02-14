"""
模拟交易数据模型

支持虚拟账户、模拟订单、模拟持仓管理
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Column, String, DateTime, Float, Integer, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

from app.db.database import Base


class OrderType(str, Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(str, Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """订单状态"""
    PENDING = "pending"
    PARTIAL_FILLED = "partial_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Account(Base):
    """模拟交易账户"""
    __tablename__ = "paper_trading_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    initial_cash = Column(Float, default=100000.0, nullable=False)
    current_cash = Column(Float, default=100000.0, nullable=False)
    total_equity = Column(Float, default=100000.0, nullable=False)  # 总权益（现金 + 持仓价值）
    profit_loss = Column(Float, default=0.0, nullable=False)  # 盈亏
    profit_loss_pct = Column(Float, default=0.0, nullable=False)  # 盈亏百分比
    commission_rate = Column(Float, default=0.001, nullable=False)  # 手续费率
    slippage_rate = Column(Float, default=0.001, nullable=False)  # 滑点率
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 关联
    user = relationship("User", back_populates="paper_trading_accounts")
    positions = relationship("Position", back_populates="account", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="account", cascade="all, delete-orphan")
    trades = relationship("PaperTrade", back_populates="account", cascade="all, delete-orphan")


class Position(Base):
    """模拟持仓"""
    __tablename__ = "paper_trading_positions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(String(36), ForeignKey("paper_trading_accounts.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    size = Column(Integer, default=0, nullable=False)  # 持仓数量（正数做多，负数做空）
    avg_price = Column(Float, default=0.0, nullable=False)  # 平均成本
    market_value = Column(Float, default=0.0, nullable=False)  # 市值
    unrealized_pnl = Column(Float, default=0.0, nullable=False)  # 浮盈
    unrealized_pnl_pct = Column(Float, default=0.0, nullable=False)  # 浮盈百分比
    entry_price = Column(Float, default=0.0, nullable=False)  # 入场价格
    entry_time = Column(DateTime, nullable=True)  # 入场时间
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 关联
    account = relationship("Account", back_populates="positions")


class Order(Base):
    """模拟订单"""
    __tablename__ = "paper_trading_orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(String(36), ForeignKey("paper_trading_accounts.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    order_type = Column(String(20), nullable=False)  # MARKET, LIMIT, STOP, STOP_LIMIT
    side = Column(String(10), nullable=False)  # BUY, SELL
    size = Column(Integer, nullable=False)  # 订单数量
    price = Column(Float, nullable=True)  # 限价单价格
    stop_price = Column(Float, nullable=True)  # 止损单价格
    limit_price = Column(Float, nullable=True)  # 止盈单价格
    filled_size = Column(Integer, default=0, nullable=False)  # 已成交数量
    avg_fill_price = Column(Float, default=0.0, nullable=False)  # 平均成交价
    status = Column(String(20), default=OrderStatus.PENDING.value, nullable=False, index=True)
    rejected_reason = Column(String(255), nullable=True)  # 拒绝原因
    commission = Column(Float, default=0.0, nullable=False)  # 手续费
    slippage = Column(Float, default=0.0, nullable=False)  # 滑点
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    filled_at = Column(DateTime, nullable=True)  # 成交时间

    # 关联
    account = relationship("Account", back_populates="orders")


class PaperTrade(Base):
    """模拟成交"""
    __tablename__ = "paper_trades"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id = Column(String(36), ForeignKey("paper_trading_accounts.id"), nullable=False, index=True)
    order_id = Column(String(36), ForeignKey("paper_trading_orders.id"), nullable=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False)  # BUY, SELL
    size = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    commission = Column(Float, default=0.0, nullable=False)
    slippage = Column(Float, default=0.0, nullable=False)
    pnl = Column(Float, default=0.0, nullable=False)  # 盈亏
    pnl_pct = Column(Float, default=0.0, nullable=False)  # 盈亏百分比
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # 关联
    account = relationship("Account", back_populates="trades")
    order = relationship("Order")
