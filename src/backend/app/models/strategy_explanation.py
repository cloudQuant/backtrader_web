"""Strategy explanation ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, String, Text

from app.db.database import Base


class StrategyExplanationModel(Base):
    """Persisted strategy explanation cache."""

    __tablename__ = "strategy_explanations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code_hash = Column(String(64), unique=True, index=True, nullable=False)
    strategy_name = Column(String(100), nullable=False)
    summary = Column(Text, nullable=False)
    indicators_explanation = Column(Text, nullable=False)
    entry_explanation = Column(Text, nullable=False)
    exit_explanation = Column(Text, nullable=False)
    params_explanation = Column(Text, nullable=False)
    market_fit = Column(Text, nullable=False)
    risk_notes = Column(JSON, default=list)
    ast_payload = Column(JSON, default=dict)
    reason_code = Column(String(64), default="static_fallback")
    model_id = Column(String(128), nullable=True)
    disclaimer = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
