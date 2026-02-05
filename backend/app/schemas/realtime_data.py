"""
实时行情相关的 Pydantic 模型
"""
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class RealtimeTickSubscribeRequest(BaseModel):
    """订阅实时行情请求"""
    symbols: List[str] = Field(..., min_items=1, description="标的代码列表（如 ['BTC/USDT', 'ETH/USDT']）")
    broker_id: Optional[str] = Field(None, description="券商 ID（可选，默认使用所有券商）")


class RealtimeTickUnsubscribeRequest(BaseModel):
    """取消订阅实时行情请求"""
    symbols: List[str] = Field(..., min_items=1, description="标的代码列表")
    broker_id: Optional[str] = Field(None, description="券商 ID")


class RealtimeHistoricalTickRequest(BaseModel):
    """获取历史行情请求"""
    broker_id: str = Field(..., description="券商 ID")
    symbol: str = Field(..., description="标的代码（如 BTC/USDT）")
    start_date: str = Field(..., description="开始日期（ISO 8601 格式）")
    end_date: str = Field(..., description="结束日期（ISO 8601 格式）")
    frequency: str = Field("1d", description="频率（1m, 5m, 15m, 30m, 1h, 1d, 1w, 1M）")


class RealtimeTick(BaseModel):
    """实时行情数据"""
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


class RealtimeTickUpdate(BaseModel):
    """实时行情更新"""
    type: str = Field("tick_update", description="消息类型")
    broker_id: str = Field(..., description="券商 ID")
    symbol: str = Field(..., description="标的代码")
    timestamp: str = Field(..., description="时间戳（ISO 8601 格式）")
    data: RealtimeTick = Field(..., description="行情数据")


class RealtimeTickBatchResponse(BaseModel):
    """批量获取行情响应"""
    symbol: str = Field(..., description="标的代码")
    tick: Optional[RealtimeTick] = Field(None, description="最新行情")
    ticks: Optional[List[RealtimeTick]] = Field(None, description="历史行情列表")


class RealtimeTickListResponse(BaseModel):
    """行情列表响应"""
    total: int = Field(..., ge=0, description="总数量")
    symbols: List[str] = Field(..., description="标的代码列表")
    ticks: Dict[str, Any] = Field(..., description="行情数据字典")
