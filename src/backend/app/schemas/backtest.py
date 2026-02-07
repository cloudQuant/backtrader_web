"""
回测相关Pydantic模型
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BacktestRequest(BaseModel):
    """回测请求"""
    strategy_id: str = Field(..., description="策略ID")
    symbol: str = Field(..., description="股票代码")
    start_date: datetime = Field(..., description="开始日期")
    end_date: datetime = Field(..., description="结束日期")
    initial_cash: float = Field(100000.0, description="初始资金")
    commission: float = Field(0.001, description="手续费率")
    params: Dict[str, Any] = Field(default_factory=dict, description="策略参数")
    
    class Config:
        json_schema_extra = {
            "example": {
                "strategy_id": "ma_cross",
                "symbol": "000001.SZ",
                "start_date": "2023-01-01T00:00:00",
                "end_date": "2024-01-01T00:00:00",
                "initial_cash": 100000,
                "commission": 0.001,
                "params": {"fast_period": 5, "slow_period": 20}
            }
        }


class BacktestResponse(BaseModel):
    """回测任务响应"""
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    message: Optional[str] = Field(None, description="状态消息")


class TradeRecord(BaseModel):
    """交易记录"""
    datetime: Optional[str] = None
    date: Optional[str] = None
    direction: Optional[str] = None
    type: Optional[str] = None
    price: float = 0
    size: float = 0
    value: float = 0
    commission: float = 0
    pnl: Optional[float] = None
    pnlcomm: Optional[float] = None
    barlen: Optional[int] = None


class BacktestResult(BaseModel):
    """回测结果"""
    task_id: str
    strategy_id: str
    symbol: str
    start_date: datetime
    end_date: datetime
    status: TaskStatus
    
    # 性能指标
    total_return: float = Field(0, description="总收益率(%)")
    annual_return: float = Field(0, description="年化收益率(%)")
    sharpe_ratio: float = Field(0, description="夏普比率")
    max_drawdown: float = Field(0, description="最大回撤(%)")
    win_rate: float = Field(0, description="胜率(%)")
    
    # 交易统计
    total_trades: int = Field(0, description="总交易次数")
    profitable_trades: int = Field(0, description="盈利交易次数")
    losing_trades: int = Field(0, description="亏损交易次数")
    
    # 资金曲线数据
    equity_curve: List[float] = Field(default_factory=list, description="资金曲线")
    equity_dates: List[str] = Field(default_factory=list, description="日期序列")
    drawdown_curve: List[float] = Field(default_factory=list, description="回撤曲线")
    
    # 交易记录
    trades: List[TradeRecord] = Field(default_factory=list, description="交易记录")
    
    # 元信息
    created_at: datetime
    error_message: Optional[str] = None
    
    class Config:
        from_attributes = True


class BacktestListResponse(BaseModel):
    """回测列表响应"""
    total: int
    items: List[BacktestResult]
