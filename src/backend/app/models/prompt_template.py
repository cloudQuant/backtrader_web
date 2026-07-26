from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text, UniqueConstraint

from app.db.database import Base


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, index=True)
    version = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="draft", index=True)
    variables = Column(JSON, nullable=False, default=list)
    rollout_percentage = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = Column(String(36), nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_prompt_templates_name_version"),
        Index("ix_prompt_templates_name_status", "name", "status"),
    )
