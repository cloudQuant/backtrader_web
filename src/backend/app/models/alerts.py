"""
Monitoring and alerting models.

Supports account monitoring, strategy monitoring, and system monitoring.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.database import Base


class AlertType(str, Enum):
    """Alert type enum."""
    ACCOUNT = "account"           # Account alert
    POSITION = "position"         # Position alert
    ORDER = "order"               # Order alert
    STRATEGY = "strategy"         # Strategy alert
    SYSTEM = "system"             # System alert
    PERFORMANCE = "performance"   # Performance alert
    RISK = "risk"                 # Risk alert


class AlertSeverity(str, Enum):
    """Alert severity enum."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Alert status enum."""
    ACTIVE = "active"           # Active
    RESOLVED = "resolved"       # Resolved
    ACKNOWLEDGED = "acknowledged"  # Acknowledged
    IGNORED = "ignored"         # Ignored


class Alert(Base):
    """Alert table.

    Attributes:
        id: Unique alert identifier (UUID).
        user_id: User ID who owns the alert.
        alert_type: Alert type.
        severity: Alert severity.
        status: Alert status.
        title: Alert title.
        message: Alert message.
        details: Additional details (JSON).
        rule_id: Associated alert rule ID.
        strategy_id: Associated strategy ID.
        backtest_task_id: Associated backtest task ID.
        account_id: Associated paper trading account ID.
        position_id: Associated paper trading position ID.
        order_id: Associated paper trading order ID.
        trigger_type: Trigger type (threshold, rate, manual).
        trigger_value: Trigger value.
        threshold_value: Threshold value.
        is_read: Whether the alert is read.
        is_notification_sent: Whether notification was sent.
        resolved_at: Resolution timestamp.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # Alert information
    alert_type = Column(String(20), nullable=False, index=True)  # Alert type
    severity = Column(String(20), default=AlertSeverity.INFO, nullable=False)  # Alert severity
    status = Column(String(20), default=AlertStatus.ACTIVE, nullable=False, index=True)  # Alert status
    title = Column(String(200), nullable=False)  # Alert title
    message = Column(Text, nullable=False)  # Alert message
    details = Column(JSON, nullable=True)  # Additional details (JSON)

    # Associated objects
    rule_id = Column(String(36), ForeignKey("alert_rules.id"), nullable=True, index=True)
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=True, index=True)
    backtest_task_id = Column(String(36), ForeignKey("backtest_tasks.id"), nullable=True, index=True)
    account_id = Column(String(36), ForeignKey("paper_trading_accounts.id"), nullable=True, index=True)
    position_id = Column(String(36), ForeignKey("paper_trading_positions.id"), nullable=True, index=True)
    order_id = Column(String(36), ForeignKey("paper_trading_orders.id"), nullable=True, index=True)

    # Trigger conditions
    trigger_type = Column(String(50), nullable=False)  # Trigger type (threshold, rate, manual)
    trigger_value = Column(Float, nullable=True)  # Trigger value
    threshold_value = Column(Float, nullable=True)  # Threshold value

    # Meta information
    is_read = Column(Boolean, default=False, nullable=False)  # Whether read
    is_notification_sent = Column(Boolean, default=False, nullable=False)  # Whether notification sent
    resolved_at = Column(DateTime, nullable=True)  # Resolution time
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="alerts")
    strategy = relationship("Strategy", backref="alerts")
    backtest_task = relationship("BacktestTask", backref="alerts")
    account = relationship("Account", backref="alerts")
    position = relationship("Position", backref="alerts")
    order = relationship("Order", backref="alerts")
    notifications = relationship("AlertNotification", back_populates="alert")


class AlertRule(Base):
    """Alert rule table.

    Attributes:
        id: Unique rule identifier (UUID).
        user_id: User ID who owns the rule.
        alert_type: Alert type.
        severity: Alert severity.
        name: Rule name.
        description: Rule description.
        trigger_type: Trigger type (threshold, rate, cross).
        trigger_config: Trigger configuration (JSON).
        notification_enabled: Whether notifications are enabled.
        notification_channels: Notification channels (JSON).
        is_active: Whether the rule is active.
        triggered_count: Number of times triggered.
        last_triggered_at: Last triggered timestamp.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """
    __tablename__ = "alert_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # Rule configuration
    alert_type = Column(String(20), nullable=False)  # Alert type
    severity = Column(String(20), default=AlertSeverity.WARNING, nullable=False)  # Alert severity
    name = Column(String(200), nullable=False)  # Rule name
    description = Column(Text, nullable=True)  # Rule description

    # Trigger conditions
    trigger_type = Column(String(50), nullable=False)  # Trigger type (threshold, rate, cross)
    trigger_config = Column(JSON, nullable=False)  # Trigger configuration

    # Notification configuration
    notification_enabled = Column(Boolean, default=True, nullable=False)  # Whether notifications enabled
    notification_channels = Column(JSON, default=list, nullable=False)  # Notification channels

    # Status
    is_active = Column(Boolean, default=True, nullable=False)  # Whether active
    triggered_count = Column(Integer, default=0, nullable=False)  # Trigger count
    last_triggered_at = Column(DateTime, nullable=True)  # Last triggered time

    # Meta information
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="alert_rules")
    alerts = relationship("Alert", backref="rule")


class AlertNotification(Base):
    """Alert notification record table.

    Attributes:
        id: Unique notification identifier (UUID).
        alert_id: Associated alert ID.
        channel: Notification channel (email, sms, push, webhook).
        status: Notification status (sent, failed, pending).
        message: Notification message.
        error: Error message.
        sent_at: Send timestamp.
        created_at: Creation timestamp.
    """
    __tablename__ = "alert_notifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_id = Column(String(36), ForeignKey("alerts.id"), nullable=False, index=True)
    channel = Column(String(50), nullable=False)  # Notification channel (email, sms, push, webhook)
    status = Column(String(20), nullable=False)  # Notification status (sent, failed, pending)
    message = Column(Text, nullable=True)  # Notification message
    error = Column(Text, nullable=True)  # Error message
    sent_at = Column(DateTime, nullable=True)  # Send time
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    alert = relationship("Alert", back_populates="notifications")
