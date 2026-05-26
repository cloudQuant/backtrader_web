"""ORM model for AI provider call observability."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text

from app.db.database import Base


class AICallLog(Base):
    """Persists privacy-preserving metadata for AI provider calls."""

    __tablename__ = "ai_call_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    request_id = Column(String(64), nullable=True, index=True)
    service_name = Column(String(50), nullable=False, index=True)
    mode = Column(String(50), nullable=False, index=True)
    model_name = Column(String(100), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    prompt_template_id = Column(String(100), nullable=True, index=True)
    prompt_template_version = Column(String(50), nullable=True, index=True)

    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    estimated_cost_usd = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, index=True)
    error_code = Column(String(100), nullable=True, index=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    response_chars = Column(Integer, nullable=False, default=0)
    prompt_hash = Column(String(64), nullable=False, index=True)

    __table_args__ = (
        Index("ix_ai_call_logs_created_at", "created_at"),
        Index("ix_ai_call_logs_user_created_at", "user_id", "created_at"),
        Index("ix_ai_call_logs_service_created_at", "service_name", "created_at"),
        Index("ix_ai_call_logs_status_created_at", "status", "created_at"),
    )
