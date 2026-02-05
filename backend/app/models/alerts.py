"""
监控告警数据模型

支持账户监控、策略监控、系统监控
"""
import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, DateTime, Text, Float, Integer, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

from app.db.database import Base


class AlertType(str, Enum):
    """告警类型"""
    ACCOUNT = "account"           # 账户告警
    POSITION = "position"       # 持仓告警
    ORDER = "order"             # 订单告警
    STRATEGY = "strategy"        # 策略告警
    SYSTEM = "system"           # 系统告警
    PERFORMANCE = "performance" # 性能告警
    RISK = "risk"               # 风险告警


class AlertSeverity(str, Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """告警状态"""
    ACTIVE = "active"      # 活跃
    RESOLVED = "resolved"  # 已解决
    ACKNOWLEDGED = "acknowledged"  # 已确认
    IGNORED = "ignored"   # 已忽略


class Alert(Base):
    """告警表"""
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # 告警信息
    alert_type = Column(String(20), nullable=False, index=True)  # 告警类型
    severity = Column(String(20), default=AlertSeverity.INFO, nullable=False)  # 告警级别
    status = Column(String(20), default=AlertStatus.ACTIVE, nullable=False, index=True)  # 告警状态
    title = Column(String(200), nullable=False)  # 告警标题
    message = Column(Text, nullable=False)  # 告警消息
    details = Column(JSON, nullable=True)  # 详细信息（JSON）

    # 关联对象
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=True, index=True)
    backtest_task_id = Column(String(36), ForeignKey("backtest_tasks.id"), nullable=True, index=True)
    account_id = Column(String(36), ForeignKey("paper_trading_accounts.id"), nullable=True, index=True)
    position_id = Column(String(36), ForeignKey("paper_trading_positions.id"), nullable=True, index=True)
    order_id = Column(String(36), ForeignKey("paper_trading_orders.id"), nullable=True, index=True)

    # 触发条件
    trigger_type = Column(String(50), nullable=False)  # 触发类型（threshold、rate、manual）
    trigger_value = Column(Float, nullable=True)  # 触发值
    threshold_value = Column(Float, nullable=True)  # 阈值

    # 元信息
    is_read = Column(Boolean, default=False, nullable=False)  # 是否已读
    is_notification_sent = Column(Boolean, default=False, nullable=False)  # 是否已发送通知
    resolved_at = Column(DateTime, nullable=True)  # 解决时间
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    user = relationship("User", back_populates="alerts")
    strategy = relationship("Strategy", backref="alerts")
    backtest_task = relationship("BacktestTask", backref="alerts")
    account = relationship("Account", backref="alerts")
    position = relationship("Position", backref="alerts")
    order = relationship("Order", backref="alerts")
    notifications = relationship("AlertNotification", back_populates="alert")


class AlertRule(Base):
    """告警规则表"""
    __tablename__ = "alert_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # 规则配置
    alert_type = Column(String(20), nullable=False)  # 告警类型
    severity = Column(String(20), default=AlertSeverity.WARNING, nullable=False)  # 告警级别
    name = Column(String(200), nullable=False)  # 规则名称
    description = Column(Text, nullable=True)  # 规则描述

    # 触发条件
    trigger_type = Column(String(50), nullable=False)  # 触发类型（threshold、rate、cross）
    trigger_config = Column(JSON, nullable=False)  # 触发配置

    # 通知配置
    notification_enabled = Column(Boolean, default=True, nullable=False)  # 是否启用通知
    notification_channels = Column(JSON, default=list, nullable=False)  # 通知渠道

    # 状态
    is_active = Column(Boolean, default=True, nullable=False)  # 是否启用
    triggered_count = Column(Integer, default=0, nullable=False)  # 触发次数
    last_triggered_at = Column(DateTime, nullable=True)  # 上次触发时间

    # 元信息
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    user = relationship("User", back_populates="alert_rules")
    alerts = relationship("Alert", backref="rule")


class AlertNotification(Base):
    """告警通知记录表"""
    __tablename__ = "alert_notifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_id = Column(String(36), ForeignKey("alerts.id"), nullable=False, index=True)
    channel = Column(String(50), nullable=False)  # 通知渠道（email、sms、push、webhook）
    status = Column(String(20), nullable=False)  # 通知状态（sent、failed、pending）
    message = Column(Text, nullable=True)  # 通知消息
    error = Column(Text, nullable=True)  # 错误信息
    sent_at = Column(DateTime, nullable=True)  # 发送时间
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关联
    alert = relationship("Alert", back_populates="notifications")
