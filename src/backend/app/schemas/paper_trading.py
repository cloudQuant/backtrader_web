"""
模拟交易相关的 Pydantic 模型
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class AccountCreate(BaseModel):
    """创建模拟账户请求"""
    name: str = Field(..., min_length=1, max_length=100, description="账户名称")
    initial_cash: float = Field(100000.0, gt=0, le=10000000, description="初始资金")
    commission_rate: float = Field(0.001, ge=0, le=0.01, description="手续费率（默认 0.1%），例如 0.001 表示 0.1%，0.003 表示 0.3%")
    slippage_rate: float = Field(0.001, ge=0, le=0.01, description="滑点率（默认 0.1%），例如 0.001 表示 0.1%，即每笔交易产生 0.1% 的价格滑点")


class AccountResponse(BaseModel):
    """模拟账户响应"""
    id: str = Field(..., description="账户 ID")
    user_id: str = Field(..., description="用户 ID")
    name: str = Field(..., description="账户名称")
    initial_cash: float = Field(..., description="初始资金")
    current_cash: float = Field(..., description="当前现金")
    total_equity: float = Field(..., description="总权益（现金 + 持仓价值）")
    profit_loss: float = Field(..., description="盈亏")
    profit_loss_pct: float = Field(..., description="盈亏百分比（%），例如 10.0 表示 10% 收益，-5.0 表示 5% 亏损")
    commission_rate: float = Field(..., description="手续费率")
    slippage_rate: float = Field(..., description="滑点率")
    is_active: bool = Field(..., description="是否激活")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class AccountListResponse(BaseModel):
    """账户列表响应"""
    total: int = Field(..., ge=0, description="总数量")
    items: List[AccountResponse]


class OrderRequest(BaseModel):
    """提交模拟订单请求"""
    account_id: str = Field(..., description="账户 ID")
    symbol: str = Field(..., pattern=r'^\d{6}\.(SH|SZ)$', description="股票代码，例如 000001.SZ 或 600000.SH，必须是 A 股代码格式：6位数字.SH 或 .SZ")
    order_type: str = Field(..., description="订单类型：market（市价单）、limit（限价单）、stop（止损单）、stop_limit（止损限价单）")
    side: str = Field(..., description="买卖方向：buy（做多）或 sell（平多或做空）")
    size: int = Field(..., gt=0, description="订单数量，必须是正整数")
    price: Optional[float] = Field(None, gt=0, description="限价单价格（市价单不需要）")
    stop_price: Optional[float] = Field(None, gt=0, description="止损价格（止损单需要）")
    limit_price: Optional[float] = Field(None, gt=0, description="止盈价格（止损限价单需要）")


class OrderResponse(BaseModel):
    """模拟订单响应"""
    id: str = Field(..., description="订单 ID")
    account_id: str = Field(..., description="账户 ID")
    symbol: str = Field(..., description="股票代码")
    order_type: str = Field(..., description="订单类型")
    side: str = Field(..., description="买卖方向")
    size: int = Field(..., description="订单数量")
    price: Optional[float] = Field(None, description="限价单价格")
    stop_price: Optional[float] = Field(None, description="止损价格")
    limit_price: Optional[float] = Field(None, description="止盈价格")
    filled_size: int = Field(default=0, description="已成交数量")
    avg_fill_price: float = Field(default=0, description="平均成交价格")
    status: str = Field(..., description="订单状态：pending（等待）、partial_filled（部分成交）、filled（已成交）、cancelled（已撤销）、rejected（已拒绝）")
    rejected_reason: Optional[str] = Field(None, description="拒绝原因")
    commission: float = Field(default=0, description="手续费")
    slippage: float = Field(default=0, description="滑点")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    filled_at: Optional[datetime] = Field(None, description="成交时间")


class OrderListResponse(BaseModel):
    """订单列表响应"""
    total: int = Field(..., ge=0, description="总数量")
    items: List[OrderResponse]


class PositionResponse(BaseModel):
    """模拟持仓响应"""
    id: str = Field(..., description="持仓 ID")
    account_id: str = Field(..., description="账户 ID")
    symbol: str = Field(..., description="股票代码")
    size: int = Field(..., description="持仓数量（正数表示多头头寸，负数表示空头头寸，例如 100 表示持有多头 100 股，-50 表示持有空头 50 股）")
    avg_price: float = Field(default=0, description="平均成本价")
    market_value: float = Field(default=0, description="市值（持仓数量 * 当前市价），例如 size=100, market_price=105.5，则 market_value=10550")
    unrealized_pnl: float = Field(default=0, description="未实现盈亏（持仓按当前市价计算的盈亏，正数表示盈利，负数表示亏损）")
    unrealized_pnl_pct: float = Field(default=0, description="未实现盈亏百分比，例如 15.5 表示 15.5% 的盈利，-8.2 表示 8.2% 的亏损")
    entry_price: float = Field(default=0, description="入场价格")
    entry_time: Optional[datetime] = Field(None, description="入场时间")
    updated_at: datetime = Field(..., description="更新时间")


class PositionListResponse(BaseModel):
    """持仓列表响应"""
    total: int = Field(..., ge=0, description="总数量")
    items: List[PositionResponse]


class TradeResponse(BaseModel):
    """模拟成交响应"""
    id: str = Field(..., description="成交 ID")
    account_id: str = Field(..., description="账户 ID")
    order_id: Optional[str] = Field(None, description="订单 ID")
    symbol: str = Field(..., description="股票代码")
    side: str = Field(..., description="买卖方向：buy（买入）或 sell（卖出）")
    size: int = Field(..., description="成交数量")
    price: float = Field(..., description="成交价格")
    commission: float = Field(default=0, description="手续费")
    slippage: float = Field(default=0, description="滑点")
    pnl: float = Field(default=0, description="盈亏（已实现盈亏）")
    pnl_pct: float = Field(default=0, description="盈亏百分比")
    created_at: datetime = Field(..., description="成交时间")


class TradeListResponse(BaseModel):
    """成交列表响应"""
    total: int = Field(..., ge=0, description="总数量")
    items: List[TradeResponse]
