"""Strategy score ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, String, Text

from app.db.database import Base


class StrategyScoreModel(Base):
    """Persisted strategy score result."""

    __tablename__ = "strategy_scores"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    backtest_id = Column(String(36), ForeignKey("backtest_tasks.id"), unique=True, index=True)
    total_score = Column(Float, default=0)
    level = Column(String(5), default="D")
    model_version = Column(String(32), default="v1")
    disclaimer = Column(Text, nullable=False)
    dimensions = Column(JSON, default=list)
    weights = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
