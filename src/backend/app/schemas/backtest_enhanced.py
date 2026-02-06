"""
回测相关 Pydantic 模型（增强版）

增加了严格的输入验证和范围检查
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Literal
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BacktestRequest(BaseModel):
    """回测请求（增强版）"""
    
    # 基本参数
    strategy_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="策略ID",
        pattern=r'^[a-zA-Z0-9_-]+$'  # 只允许字母、数字、下划线和连字符
    )
    
    symbol: str = Field(
        ...,
        description="股票代码",
        pattern=r'^\d{6}\.(SH|SZ)$'  # 必须是 A 股代码格式：6位数字.SH 或 .SZ
    )
    
    # 日期范围（带验证）
    start_date: datetime = Field(
        ...,
        description="开始日期",
    )
    
    end_date: datetime = Field(
        ...,
        description="结束日期",
    )
    
    # 资金和手续费（带范围限制）
    initial_cash: float = Field(
        ...,
        gt=0,  # 必须大于 0
        le=10000000,  # 最多 1000 万
        description="初始资金",
        examples=[100000, 1000000]
    )
    
    commission: float = Field(
        ...,
        ge=0,  # 必须大于等于 0
        le=0.1,  # 最多 10%
        description="手续费率",
        examples=[0.001, 0.0003, 0.01]
    )
    
    # 策略参数（带类型和范围验证）
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="策略参数（必须符合策略的参数定义）",
    )
    
    @field_validator('end_date')
    @classmethod
    def validate_date_range(cls, v: datetime, info) -> datetime:
        """验证日期范围"""
        start_date = info.data.get('start_date')
        if start_date and v <= start_date:
            raise ValueError('end_date 必须晚于 start_date')
        
        # 限制回测时间范围（最多 10 年）
        max_end_date = start_date + timedelta(days=3650)
        if v > max_end_date:
            raise ValueError('回测时间范围不能超过 10 年')
        
        # 不能使用未来日期
        now = datetime.utcnow()
        if v > now:
            raise ValueError('end_date 不能是未来日期')
        
        return v
    
    @field_validator('params')
    @classmethod
    def validate_params(cls, v: Dict[str, Any], info) -> Dict[str, Any]:
        """验证策略参数"""
        if not v:
            return {}
        
        strategy_id = info.data.get('strategy_id')
        
        # 获取策略的参数定义
        param_specs = get_strategy_params(strategy_id)
        
        # 验证每个参数
        for key, value in v.items():
            if key not in param_specs:
                raise ValueError(f'未知参数: {key}')
            
            spec = param_specs[key]
            
            # 类型验证
            if spec.type == 'int':
                if not isinstance(value, int):
                    raise ValueError(f'{key} 必须是整数')
                if spec.min is not None and value < spec.min:
                    raise ValueError(f'{key} 必须大于等于 {spec.min}')
                if spec.max is not None and value > spec.max:
                    raise ValueError(f'{key} 必须小于等于 {spec.max}')
            
            elif spec.type == 'float':
                if not isinstance(value, (int, float)):
                    raise ValueError(f'{key} 必须是数字')
                if spec.min is not None and value < spec.min:
                    raise ValueError(f'{key} 必须大于等于 {spec.min}')
                if spec.max is not None and value > spec.max:
                    raise ValueError(f'{key} 必须小于等于 {spec.max}')
            
            elif spec.type == 'str':
                if not isinstance(value, str):
                    raise ValueError(f'{key} 必须是字符串')
                if spec.choices and value not in spec.choices:
                    raise ValueError(f'{key} 必须是以下之一: {", ".join(spec.choices)}')
            
            elif spec.type == 'bool':
                if not isinstance(value, bool):
                    raise ValueError(f'{key} 必须是布尔值')
        
        return v
    
    @model_validator(mode='after')
    def validate_backtest_days(self) -> 'BacktestRequest':
        """验证回测天数不少于 30 个交易日"""
        if self.start_date and self.end_date:
            days = (self.end_date - self.start_date).days
            if days < 30:
                raise ValueError('回测时间范围不能少于 30 天（约 20 个交易日）')
        return self
    
    class Config:
        json_schema_extra = {
            "example": {
                "strategy_id": "ma_cross",
                "symbol": "000001.SZ",
                "start_date": "2023-01-01T00:00:00",
                "end_date": "2023-12-31T00:00:00",
                "initial_cash": 100000,
                "commission": 0.001,
                "params": {
                    "fast_period": 5,
                    "slow_period": 20
                }
            }
        }


class BacktestResponse(BaseModel):
    """回测任务响应"""
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    message: Optional[str] = Field(None, description="状态消息")


class TradeRecord(BaseModel):
    """交易记录"""
    date: datetime
    type: Literal['buy', 'sell']  # 只允许 buy 或 sell
    price: float = Field(..., gt=0, description="成交价格")
    size: int = Field(..., gt=0, description="成交数量")
    value: float = Field(..., gt=0, description="成交金额")
    pnl: Optional[float] = Field(None, description="盈亏")


class BacktestResult(BaseModel):
    """回测结果"""
    task_id: str
    strategy_id: str
    symbol: str
    start_date: datetime
    end_date: datetime
    status: TaskStatus
    
    # 性能指标（带范围验证）
    total_return: float = Field(0, ge=-100, le=10000, description="总收益率(%)")
    annual_return: float = Field(0, ge=-100, le=10000, description="年化收益率(%)")
    sharpe_ratio: float = Field(0, description="夏普比率")
    max_drawdown: float = Field(0, ge=0, le=100, description="最大回撤(%)")
    win_rate: float = Field(0, ge=0, le=100, description="胜率(%)")
    
    # 交易统计
    total_trades: int = Field(0, ge=0, description="总交易次数")
    profitable_trades: int = Field(0, ge=0, description="盈利交易次数")
    losing_trades: int = Field(0, ge=0, description="亏损交易次数")
    
    # 资金曲线数据
    equity_curve: List[float] = Field(default_factory=list, description="资金曲线")
    equity_dates: List[str] = Field(default_factory=list, description="日期序列")
    drawdown_curve: List[float] = Field(default_factory=list, description="回撤曲线")
    
    # 交易记录
    trades: List[TradeRecord] = Field(default_factory=list, description="交易记录")
    
    # 元信息
    created_at: datetime
    error_message: Optional[str] = None


class BacktestListResponse(BaseModel):
    """回测列表响应"""
    total: int = Field(..., ge=0, description="总数量")
    items: List[BacktestResult]


class OptimizationRequest(BaseModel):
    """参数优化请求"""
    
    # 优化配置
    strategy_id: str = Field(..., description="策略ID")
    backtest_config: BacktestRequest = Field(..., description="回测配置")
    
    # 优化方法
    method: Literal['grid', 'bayesian'] = Field(
        default='bayesian',
        description="优化方法：grid（网格搜索）或 bayesian（贝叶斯优化）"
    )
    
    # 优化目标
    metric: Literal['sharpe_ratio', 'max_drawdown', 'total_return'] = Field(
        default='sharpe_ratio',
        description="优化目标：sharpe_ratio（夏普比率）、max_drawdown（最小化）、total_return（收益率）"
    )
    
    # 网格搜索参数
    param_grid: Optional[Dict[str, List[Any]]] = Field(
        None,
        description="参数网格（用于网格搜索）"
    )
    
    # 贝叶斯优化参数
    param_bounds: Optional[Dict[str, Dict[str, Any]]] = Field(
        None,
        description="参数边界（用于贝叶斯优化）"
    )
    
    # 试验次数
    n_trials: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="试验次数（用于贝叶斯优化）"
    )
    
    @model_validator(mode='after')
    def validate_optimization_config(self) -> 'OptimizationRequest':
        """验证优化配置"""
        if self.method == 'grid':
            if not self.param_grid:
                raise ValueError('网格搜索需要 param_grid 参数')
        elif self.method == 'bayesian':
            if not self.param_bounds:
                raise ValueError('贝叶斯优化需要 param_bounds 参数')
        
        return self
    
    class Config:
        json_schema_extra = {
            "example_grid": {
                "strategy_id": "ma_cross",
                "method": "grid",
                "metric": "sharpe_ratio",
                "backtest_config": {
                    "strategy_id": "ma_cross",
                    "symbol": "000001.SZ",
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "initial_cash": 100000,
                    "commission": 0.001,
                },
                "param_grid": {
                    "fast_period": [5, 10, 15],
                    "slow_period": [20, 30, 40]
                }
            },
            "example_bayesian": {
                "strategy_id": "ma_cross",
                "method": "bayesian",
                "metric": "sharpe_ratio",
                "n_trials": 100,
                "backtest_config": {
                    "strategy_id": "ma_cross",
                    "symbol": "000001.SZ",
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "initial_cash": 100000,
                    "commission": 0.001,
                },
                "param_bounds": {
                    "fast_period": {"type": "int", "min": 5, "max": 20},
                    "slow_period": {"type": "int", "min": 20, "max": 60}
                }
            }
        }


class OptimizationResult(BaseModel):
    """优化结果"""
    # 最优参数
    best_params: Dict[str, Any] = Field(..., description="最优参数组合")
    # 最优指标
    best_metrics: Dict[str, float] = Field(..., description="最优指标值")
    # 所有试验结果
    all_results: List[Dict[str, Any]] = Field(..., description="所有试验结果")
    # 试验次数
    n_trials: int = Field(..., ge=0, description="实际试验次数")


# 辅助函数
def get_strategy_params(strategy_id: str) -> Dict[str, Any]:
    """
    获取策略的参数定义

    Args:
        strategy_id: 策略ID

    Returns:
        参数定义字典
    """
    # 从策略模板中获取参数定义
    from app.services.strategy_service import STRATEGY_TEMPLATES
    
    for template in STRATEGY_TEMPLATES:
        if template.id == strategy_id:
            return template.params
    
    # 如果没找到，返回空字典
    return {}
