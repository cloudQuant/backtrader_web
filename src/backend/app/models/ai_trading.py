"""ORM models for AI trading logs and history."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, String, Text

from app.db.database import Base


class AITradingLog(Base):
    """Persists every AI trading decision for audit and reflection."""

    __tablename__ = "ai_trading_logs"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    trade_id = Column(String(12), unique=True, nullable=False, index=True)

    # User input
    user_input = Column(Text, nullable=False)
    assistant_mode = Column(String(30), nullable=False, default="trading_execution")

    # Parsed intent
    action = Column(String(20), nullable=False)
    symbol = Column(String(50), nullable=True, index=True)
    exchange = Column(String(20), nullable=True)
    quantity = Column(Float, nullable=True)
    price = Column(Float, nullable=True)
    order_type = Column(String(20), nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    risk_level = Column(String(20), nullable=True)

    # Risk assessment
    risk_approved = Column(Boolean, nullable=False, default=False)
    risk_warnings = Column(JSON, nullable=True)
    risk_blocked_reasons = Column(JSON, nullable=True)
    requires_confirmation = Column(Boolean, nullable=False, default=False)

    # Execution
    status = Column(String(30), nullable=False, default="pending")
    execution_result = Column(JSON, nullable=True)
    gateway_id = Column(String(100), nullable=True)
    dry_run = Column(Boolean, nullable=False, default=True)

    # AI reasoning
    ai_reasoning = Column(Text, nullable=True)
    reflection = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    confirmed_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AITradingLog(trade_id={self.trade_id}, action={self.action}, "
            f"symbol={self.symbol}, status={self.status})>"
        )
