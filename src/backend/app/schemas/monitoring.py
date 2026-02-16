"""
Monitoring and alerting schemas.
"""
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class AlertType(str, Enum):
    """Alert type."""
    ACCOUNT = "account"
    POSITION = "position"
    ORDER = "order"
    STRATEGY = "strategy"
    SYSTEM = "system"
    PERFORMANCE = "performance"
    RISK = "risk"


class AlertSeverity(str, Enum):
    """Alert severity."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Alert status."""
    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"
    IGNORED = "ignored"


class TriggerType(str, Enum):
    """Trigger type."""
    THRESHOLD = "threshold"
    RATE = "rate"
    CROSS = "cross"
    MANUAL = "manual"


class AlertCreate(BaseModel):
    """Create an alert rule request payload."""
    name: str = Field(..., min_length=1, max_length=200, description="Rule name.")
    description: Optional[str] = Field(None, description="Rule description.")
    alert_type: AlertType = Field(..., description="Alert type.")
    severity: AlertSeverity = Field(AlertSeverity.WARNING, description="Alert severity.")
    trigger_type: TriggerType = Field(..., description="Trigger type.")
    trigger_config: Dict[str, Any] = Field(..., description="Trigger configuration.")
    notification_enabled: bool = Field(True, description="Whether notifications are enabled.")
    notification_channels: Optional[List[str]] = Field(None, description="Notification channels (e.g. ['web', 'email']).")


class AlertUpdate(BaseModel):
    """Update an alert rule request payload."""
    name: Optional[str] = Field(None, min_length=1, max_length=200, description="Rule name.")
    description: Optional[str] = Field(None, description="Rule description.")
    severity: Optional[AlertSeverity] = Field(None, description="Alert severity.")
    notification_enabled: Optional[bool] = Field(None, description="Whether notifications are enabled.")
    notification_channels: Optional[List[str]] = Field(None, description="Notification channels.")
    is_active: Optional[bool] = Field(None, description="Whether the rule is active.")


class AlertRuleResponse(BaseModel):
    """Alert rule response."""
    id: str = Field(..., description="Rule id.")
    user_id: str = Field(..., description="Owner user id.")
    name: str = Field(..., description="Rule name.")
    description: Optional[str] = Field(None, description="Rule description.")
    alert_type: AlertType = Field(..., description="Alert type.")
    severity: AlertSeverity = Field(..., description="Alert severity.")
    trigger_type: TriggerType = Field(..., description="Trigger type.")
    trigger_config: Dict[str, Any] = Field(..., description="Trigger configuration.")
    notification_enabled: bool = Field(..., description="Whether notifications are enabled.")
    notification_channels: List[str] = Field(..., description="Notification channels.")
    is_active: bool = Field(..., description="Whether the rule is active.")
    triggered_count: int = Field(..., ge=0, description="Trigger count.")
    last_triggered_at: Optional[datetime] = Field(None, description="Last triggered time.")
    created_at: datetime = Field(..., description="Created at.")
    updated_at: datetime = Field(..., description="Updated at.")


class AlertRuleListResponse(BaseModel):
    """Alert rule list response."""
    total: int = Field(..., ge=0, description="Total count.")
    items: List[AlertRuleResponse] = Field(..., description="Items.")


class AlertResponse(BaseModel):
    """Alert response."""
    id: str = Field(..., description="Alert id.")
    user_id: str = Field(..., description="Owner user id.")
    alert_type: AlertType = Field(..., description="Alert type.")
    severity: AlertSeverity = Field(..., description="Alert severity.")
    status: AlertStatus = Field(..., description="Alert status.")
    title: str = Field(..., description="Alert title.")
    message: str = Field(..., description="Alert message.")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details.")
    strategy_id: Optional[str] = Field(None, description="Related strategy id (if any).")
    backtest_task_id: Optional[str] = Field(None, description="Related backtest task id (if any).")
    account_id: Optional[str] = Field(None, description="Related paper account id (if any).")
    position_id: Optional[str] = Field(None, description="Related paper position id (if any).")
    order_id: Optional[str] = Field(None, description="Related paper order id (if any).")
    is_read: bool = Field(..., description="Whether the alert is read.")
    is_notification_sent: bool = Field(..., description="Whether notifications were sent.")
    resolved_at: Optional[datetime] = Field(None, description="Resolved at (if any).")
    created_at: datetime = Field(..., description="Created at.")
    updated_at: datetime = Field(..., description="Updated at.")


class AlertListResponse(BaseModel):
    """Alert list response."""
    total: int = Field(..., ge=0, description="Total count.")
    items: List[AlertResponse] = Field(..., description="Items.")


class AccountAlertConfig(BaseModel):
    """Account alert config (used in `trigger_config`)."""
    condition: str = Field("lt", description="Comparison operator: lt, gt, eq.")
    threshold: float = Field(..., description="Threshold value.")
    metric: str = Field("cash", description="Metric name: cash, value, equity.")


class PositionAlertConfig(BaseModel):
    """Position alert config (used in `trigger_config`)."""
    symbol: str = Field(..., description="Symbol.")
    metric: str = Field("unrealized_pnl", description="Metric: unrealized_pnl, unrealized_pnl_pct, market_value.")
    condition: str = Field("lt", description="Comparison operator: lt, gt, eq.")
    threshold: float = Field(..., description="Threshold value.")


class StrategyAlertConfig(BaseModel):
    """Strategy alert config (used in `trigger_config`)."""
    metric: str = Field("sharpe_ratio", description="Metric: sharpe_ratio, total_return, max_drawdown, win_rate.")
    condition: str = Field("lt", description="Comparison operator: lt, gt, eq.")
    threshold: float = Field(..., description="Threshold value.")


class AlertNotificationConfig(BaseModel):
    """Notification config (legacy shape, used in some clients)."""
    email: Optional[bool] = Field(None, description="Whether to send email.")
    sms: Optional[bool] = Field(None, description="Whether to send SMS.")
    push: Optional[bool] = Field(None, description="Whether to send push notification.")
    webhook: Optional[str] = Field(None, description="Webhook URL.")


class WebhookConfig(BaseModel):
    """Webhook config."""
    url: str = Field(..., description="Webhook URL.")
    method: str = Field("POST", description="HTTP method.")
    headers: Optional[Dict[str, str]] = Field(None, description="Optional headers.")


# Aliases kept for API compatibility.
AlertRuleCreate = AlertCreate
AlertRuleUpdate = AlertUpdate
NotificationConfig = AlertNotificationConfig
