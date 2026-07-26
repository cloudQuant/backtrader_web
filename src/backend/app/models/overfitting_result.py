from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, String, Text

from app.db.database import Base


class OverfittingResultModel(Base):
    __tablename__ = "overfitting_results"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), unique=True, index=True, nullable=False)
    backtest_id = Column(String(36), ForeignKey("backtest_tasks.id"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    requested_methods = Column(JSON, default=list)
    overall_level = Column(String(16), default="medium", nullable=False)
    robustness_score = Column(Float, default=50.0, nullable=False)
    summary = Column(Text, default="", nullable=False)
    methods = Column(JSON, default=list)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
