"""
Optimization task ORM model.

Persists parameter optimization task state and results for multi-instance
support and restart resilience.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.database import Base


class OptimizationTask(Base):
    """Parameter optimization task table.

    Attributes:
        id: Unique task identifier (UUID).
        user_id: User ID who owns the task.
        strategy_id: Strategy ID being optimized.
        status: Task status (pending/running/completed/failed/cancelled).
        total: Total number of parameter combinations.
        completed: Number of completed trials.
        failed: Number of failed trials.
        results: JSON array of trial results.
        param_ranges: Original parameter range specification (JSON).
        n_workers: Number of parallel workers.
        error_message: Error message if failed.
        created_at: Task creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "optimization_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    strategy_id = Column(String(36), nullable=False, index=True)
    status = Column(String(20), default="pending")  # pending/running/completed/failed/cancelled
    total = Column(Integer, default=0)
    completed = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    results = Column(JSON, default=list)
    param_ranges = Column(JSON, nullable=True)
    n_workers = Column(Integer, default=4)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", back_populates="optimization_tasks")
