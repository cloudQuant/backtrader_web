"""
监控告警相关的 Pydantic 模型
"""
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class AlertType(str, Enum):
    """告警类型"""
    ACCOUNT = "account"
    POSITION = "position"
    ORDER = "order"
    STRATEGY = "strategy"
    SYSTEM = "system"
    PERFORMANCE = "performance"
    RISK = "risk"


class AlertSeverity(str, Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """告警状态"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"
    IGNORED = "ignored"


class TriggerType(str, Enum):
    """触发类型"""
    THRESHOLD = "threshold"
    RATE = "rate"
    CROSS = "cross"
    MANUAL = "manual"


class AlertCreate(BaseModel):
    """创建告警规则请求"""
    name: str = Field(..., min_length=1, max_length=200, description="规则名称")
    description: Optional[str] = Field(None, description="规则描述")
    alert_type: AlertType = Field(..., description="告警类型")
    severity: AlertSeverity = Field(AlertSeverity.WARNING, description="告警级别")
    trigger_type: TriggerType = Field(..., description="触发类型")
    trigger_config: Dict[str, Any] = Field(..., description="触发配置")
    notification_enabled: bool = Field(True, description="是否启用通知")
    notification_channels: Optional[List[str]] = Field(None, description="通知渠道")


class AlertUpdate(BaseModel):
    """更新告警规则请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=200, description="规则名称")
    description: Optional[str] = Field(None, description="规则描述")
    severity: Optional[AlertSeverity] = Field(None, description="告警级别")
    notification_enabled: Optional[bool] = Field(None, description="是否启用通知")
    notification_channels: Optional[List[str]] = Field(None, description="通知渠道")
    is_active: Optional[bool] = Field(None, description="是否启用")


class AlertRuleResponse(BaseModel):
    """告警规则响应"""
    id: str = Field(..., description="规则 ID")
    user_id: str = Field(..., description="用户 ID")
    name: str = Field(..., description="规则名称")
    description: Optional[str] = Field(None, description="规则描述")
    alert_type: AlertType = Field(..., description="告警类型")
    severity: AlertSeverity = Field(..., description="告警级别")
    trigger_type: TriggerType = Field(..., description="触发类型")
    trigger_config: Dict[str, Any] = Field(..., description="触发配置")
    notification_enabled: bool = Field(..., description="是否启用通知")
    notification_channels: List[str] = Field(..., description="通知渠道")
    is_active: bool = Field(..., description="是否启用")
    triggered_count: int = Field(..., ge=0, description="触发次数")
    last_triggered_at: Optional[datetime] = Field(None, description="上次触发时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class AlertRuleListResponse(BaseModel):
    """告警规则列表响应"""
    total: int = Field(..., ge=0, description="总数量")
    items: List[AlertRuleResponse] = Field(..., description="规则列表")


class AlertResponse(BaseModel):
    """告警响应"""
    id: str = Field(..., description="告警 ID")
    user_id: str = Field(..., description="用户 ID")
    alert_type: AlertType = Field(..., description="告警类型")
    severity: AlertSeverity = Field(..., description="告警级别")
    status: AlertStatus = Field(..., description="告警状态")
    title: str = Field(..., description="告警标题")
    message: str = Field(..., description="告警消息")
    details: Optional[Dict[str, Any]] = Field(None, description="详细信息")
    strategy_id: Optional[str] = Field(None, description="关联的策略 ID")
    backtest_task_id: Optional[str] = Field(None, description="关联的回测任务 ID")
    account_id: Optional[str] = Field(None, description="关联的模拟账户 ID")
    position_id: Optional[str] = Field(None, description="关联的持仓 ID")
    order_id: Optional[str] = Field(None, description="关联的订单 ID")
    is_read: bool = Field(..., description="是否已读")
    is_notification_sent: bool = Field(..., description="是否已发送通知")
    resolved_at: Optional[datetime] = Field(None, description="解决时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class AlertListResponse(BaseModel):
    """告警列表响应"""
    total: int = Field(..., ge=0, description="总数量")
    items: List[AlertResponse] = Field(..., description="告警列表")


class AccountAlertConfig(BaseModel):
    """账户告警配置"""
    condition: str = Field("lt", description="条件：lt, gt, eq")
    threshold: float = Field(..., description="阈值")
    metric: str = Field("cash", description="指标：cash, value, equity")


class PositionAlertConfig(BaseModel):
    """持仓告警配置"""
    symbol: str = Field(..., description="标的代码")
    metric: str = Field("unrealized_pnl", description="指标：unrealized_pnl, unrealized_pnl_pct, market_value")
    condition: str = Field("lt", description="条件：lt, gt, eq")
    threshold: float = Field(..., description="阈值")


class StrategyAlertConfig(BaseModel):
    """策略告警配置"""
    metric: str = Field("sharpe_ratio", description="指标：sharpe_ratio, total_return, max_drawdown, win_rate")
    condition: str = Field("lt", description="条件：lt, gt, eq")
    threshold: float = Field(..., description="阈值")


class AlertNotificationConfig(BaseModel):
    """通知配置"""
    email: Optional[bool] = Field(None, description="是否发送邮件")
    sms: Optional[bool] = Field(None, description="是否发送短信")
    push: Optional[bool] = Field(None, description="是否发送推送通知")
    webhook: Optional[str] = Field(None, description="Webhook URL")


class WebhookConfig(BaseModel):
    """Webhook 配置"""
    url: str = Field(..., description="Webhook URL")
    method: str = Field("POST", description="HTTP 方法")
    headers: Optional[Dict[str, str]] = Field(None, description="请求头")
