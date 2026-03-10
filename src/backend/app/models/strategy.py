"""
Strategy ORM models.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.db.database import Base


class Strategy(Base):
    """Strategy table.

    Attributes:
        id: Unique strategy identifier (UUID).
        user_id: User ID who owns the strategy.
        name: Strategy name.
        description: Strategy description.
        code: Strategy code.
        params: Parameter definitions (JSON).
        category: Strategy category.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "strategies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    code = Column(Text, nullable=False)
    params = Column(JSON, default=dict)  # Parameter definitions
    category = Column(String(50), default="custom", index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", back_populates="strategies")
    versions = relationship("StrategyVersion", back_populates="strategy")
