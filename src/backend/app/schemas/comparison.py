"""
回测结果对比相关的 Pydantic 模型
"""
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ComparisonCreate(BaseModel):
    """创建对比请求"""
    name: str = Field(..., min_length=1, max_length=200, description="对比名称")
    description: Optional[str] = Field(None, description="对比描述")
    type: str = Field("metrics", description="对比类型：metrics, equity, trades, drawdown")
    backtest_task_ids: List[str] = Field(..., min_items=2, description="回测任务 ID 列表（至少2个）")


class ComparisonUpdate(BaseModel):
    """更新对比请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=200, description="对比名称")
    description: Optional[str] = Field(None, description="对比描述")
    backtest_task_ids: Optional[List[str]] = Field(None, description="回测任务 ID 列表")
    is_public: Optional[bool] = Field(None, description="是否公开")


class ComparisonResponse(BaseModel):
    """对比响应"""
    id: str = Field(..., description="对比 ID")
    user_id: str = Field(..., description="用户 ID")
    name: str = Field(..., description="对比名称")
    description: Optional[str] = Field(None, description="对比描述")
    type: str = Field(..., description="对比类型")
    backtest_task_ids: List[str] = Field(..., description="回测任务 ID 列表")
    comparison_data: Dict[str, Any] = Field(..., description="对比结果")
    is_favorite: bool = Field(..., description="是否收藏")
    is_public: bool = Field(..., description="是否公开")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class ComparisonListResponse(BaseModel):
    """对比列表响应"""
    total: int = Field(..., ge=0, description="总数量")
    items: List[ComparisonResponse] = Field(..., description="对比列表")


class MetricsComparison(BaseModel):
    """指标对比"""
    metrics_comparison: Dict[str, Dict[str, float]] = Field(..., description="指标对比数据")
    best_metrics: Dict[str, Dict[str, Any]] = Field(..., description="最优指标")


class EquityComparison(BaseModel):
    """资金曲线对比"""
    equity_comparison: Dict[str, Any] = Field(..., description="资金曲线对比数据")
    dates: List[str] = Field(..., description="日期列表")
    curves: Dict[str, List[float]] = Field(..., description="各回测的资金曲线")


class TradesComparison(BaseModel):
    """交易对比"""
    trades_comparison: Dict[str, Dict[str, Any]] = Field(..., description="交易对比数据")


class DrawdownComparison(BaseModel):
    """回撤对比"""
    max_drawdowns: Dict[str, float] = Field(..., description="各回测的最大回撤")
    drawdown_curves: Dict[str, List[float]] = Field(..., description="各回测的回撤曲线")


class ComparisonDetail(BaseModel):
    """对比详情"""
    comparison_id: str = Field(..., description="对比 ID")
    type: str = Field(..., description="对比类型")
    name: str = Field(..., description="对比名称")
    description: Optional[str] = Field(None, description="对比描述")
    backtest_task_ids: List[str] = Field(..., description="回测任务 ID 列表")
    created_at: datetime = Field(..., description="创建时间")
    
    # 根据类型包含不同的对比数据
    metrics: Optional[MetricsComparison] = Field(None, description="指标对比")
    equity: Optional[EquityComparison] = Field(None, description="资金曲线对比")
    trades: Optional[TradesComparison] = Field(None, description="交易对比")
    drawdown: Optional[DrawdownComparison] = Field(None, description="回撤对比")
