"""
实盘交易相关的 Pydantic 模型
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class LiveTradingSubmitRequest(BaseModel):
    """提交实盘交易策略请求"""
    strategy_name: Optional[str] = Field(None, description="策略名称（内置策略）")
    strategy_code: Optional[str] = Field(None, description="策略代码")
    exchange: str = Field(..., description="交易所（binance, okex, huobi 等）")
    symbols: List[str] = Field(..., min_items=1, description="标的列表（如 ['BTC/USDT', 'ETH/USDT']）")
    initial_cash: float = Field(100000.0, gt=0, le=10000000, description="初始资金（USDT）")
    strategy_params: Optional[Dict[str, Any]] = Field(None, description="策略参数")
    timeframe: str = Field("1d", description="时间周期（1m, 5m, 15m, 30m, 1h, 1d, 1w, 1M）")
    start_date: Optional[datetime] = Field(None, description="开始时间")
    end_date: Optional[datetime] = Field(None, description="结束时间")
    api_key: str = Field(..., description="API Key")
    secret: str = Field(..., description="Secret Key")
    sandbox: bool = Field(False, description="是否测试环境")


class LiveTradingTaskResponse(BaseModel):
    """实盘交易任务响应"""
    task_id: str = Field(..., description="任务 ID")
    user_id: str = Field(..., description="用户 ID")
    status: str = Field(..., description="任务状态：running, stopped, error")
    config: Dict[str, Any] = Field(..., description="任务配置")
    created_at: datetime = Field(..., description="创建时间")


class LiveTradingTaskListResponse(BaseModel):
    """实盘交易任务列表响应"""
    total: int = Field(..., ge=0, description="总数量")
    tasks: List[LiveTradingTaskResponse] = Field(..., description="任务列表")


class LiveTradingDataResponse(BaseModel):
    """实盘交易数据响应"""
    task_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="任务状态")
    cash: float = Field(..., description="可用现金")
    value: float = Field(..., description="总权益")
    positions: List[Dict[str, Any]] = Field(..., description="持仓列表")
    orders: List[Dict[str, Any]] = Field(..., description="订单列表")


class LiveTradingPosition(BaseModel):
    """实盘持仓"""
    symbol: str = Field(..., description="标的代码")
    size: float = Field(..., description="持仓数量（正数做多，负数做空）")
    avg_price: float = Field(..., description="平均成本价")
    market_value: float = Field(..., description="市值")
    unrealized_pnl: float = Field(..., description="未实现盈亏")
    unrealized_pnl_pct: float = Field(..., description="未实现盈亏百分比")


class LiveTradingOrder(BaseModel):
    """实盘订单"""
    order_id: str = Field(..., description="订单 ID")
    symbol: str = Field(..., description="标的代码")
    order_type: str = Field(..., description="订单类型")
    side: str = Field(..., description="买卖方向")
    size: float = Field(..., description="订单数量")
    price: Optional[float] = Field(None, description="限价单价格")
    status: str = Field(..., description="订单状态")
    filled_size: float = Field(..., description="已成交数量")
    created_at: datetime = Field(..., description="创建时间")


class LiveTradingTrade(BaseModel):
    """实盘成交"""
    trade_id: str = Field(..., description="成交 ID")
    order_id: str = Field(..., description="订单 ID")
    symbol: str = Field(..., description="标的代码")
    side: str = Field(..., description="买卖方向")
    size: float = Field(..., description="成交数量")
    price: float = Field(..., description="成交价格")
    commission: float = Field(..., description="手续费")
    pnl: float = Field(..., description="盈亏")
    pnl_pct: float = Field(..., description="盈亏百分比")
    created_at: datetime = Field(..., description="成交时间")


class LiveAccountInfo(BaseModel):
    """实盘账户信息"""
    cash: float = Field(..., description="可用现金")
    value: float = Field(..., description="总权益")
    available_cash: float = Field(..., description="可用现金（含保证金）")
    buying_power: float = Field(..., description="购买力")
    margin: float = Field(..., description="保证金")
    maintenance_margin: float = Field(..., description="维持保证金")


class LiveTick(BaseModel):
    """实盘行情"""
    symbol: str = Field(..., description="标的代码")
    timestamp: datetime = Field(..., description="时间戳")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: float = Field(..., description="成交量")
    bid: Optional[float] = Field(None, description="买一价")
    ask: Optional[float] = Field(None, description="卖一价")
    bid_size: Optional[float] = Field(None, description="买一量")
    ask_size: Optional[float] = Field(None, description="卖一量")


class LiveTickUpdate(BaseModel):
    """实盘行情更新"""
    type: str = Field("tick_update", description="消息类型")
    symbol: str = Field(..., description="标的代码")
    timestamp: str = Field(..., description="时间戳（ISO 8601）")
    data: LiveTick = Field(..., description="行情数据")


class LivePositionUpdate(BaseModel):
    """实盘持仓更新"""
    type: str = Field("position_update", description="消息类型")
    symbol: str = Field(..., description="标的代码")
    data: LiveTradingPosition = Field(..., description="持仓数据")


class LiveOrderUpdate(BaseModel):
    """实盘订单更新"""
    type: str = Field("order_update", description="消息类型")
    order_id: str = Field(..., description="订单 ID")
    data: Dict[str, Any] = Field(..., description="订单数据")


class LiveTradeUpdate(BaseModel):
    """实盘成交更新"""
    type: str = Field("trade_update", description="消息类型")
    trade_id: str = Field(..., description="成交 ID")
    data: LiveTradingTrade = Field(..., description="成交数据")


class LiveAccountUpdate(BaseModel):
    """实盘账户更新"""
    type: str = Field("account_update", description="消息类型")
    cash: float = Field(..., description="现金")
    value: float = Field(..., description="总权益")


class LiveSignalUpdate(BaseModel):
    """策略信号更新"""
    type: str = Field("signal_update", description="消息类型")
    symbol: str = Field(..., description="标的代码")
    signal: str = Field(..., description="信号类型：buy, sell, close")
    data: Dict[str, Any] = Field(..., description="信号数据")
