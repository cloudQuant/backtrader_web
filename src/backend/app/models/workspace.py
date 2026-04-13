"""
Workspace and StrategyUnit ORM models.

Supports the "策略研究" (Strategy Research) workspace feature
introduced in iteration 124.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class Workspace(Base):
    """Workspace table.

    A workspace is a logical container for strategy units, allowing users
    to organize, run, and compare multiple strategy configurations.

    Attributes:
        id: Unique workspace identifier (UUID).
        user_id: Owner user ID.
        name: Workspace display name.
        description: Optional description.
        settings: Workspace-level settings JSON (parallel_config, defaults, etc.).
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "workspaces"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    workspace_type = Column(String(32), nullable=False, default="research", index=True)
    settings = Column(JSON, default=dict)
    trading_config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", back_populates="workspaces")
    strategy_units = relationship(
        "StrategyUnit",
        back_populates="workspace",
        cascade="all, delete-orphan",
        order_by="StrategyUnit.sort_order",
    )


class StrategyUnit(Base):
    """Strategy unit table.

    A strategy unit represents a single strategy + symbol + timeframe
    configuration within a workspace.

    Attributes:
        id: Unique unit identifier (UUID).
        workspace_id: Parent workspace ID.
        group_name: Logical grouping label.
        strategy_id: Strategy template ID.
        strategy_name: Strategy display name.
        symbol: Trading symbol code.
        symbol_name: Symbol display name.
        timeframe: K-line timeframe (e.g. '1m', '5m', '15m', '1h', '1d').
        timeframe_n: Timeframe multiplier.
        category: Classification tag.
        sort_order: Display order within workspace.
        data_config: Data source configuration JSON.
        unit_settings: Unit-level settings JSON (margin, commission, slippage, etc.).
        params: Strategy parameters JSON.
        optimization_config: Optimization configuration JSON.
        run_status: Current run status (idle/queued/running/completed/failed/cancelled).
        run_count: Cumulative run count.
        last_run_time: Duration of last run in seconds.
        last_task_id: Most recent backtest task ID (reference to backtest_tasks).
        last_optimization_task_id: Most recent optimization task ID.
        metrics_snapshot: Key metrics from last completed run (JSON).
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "strategy_units"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_name = Column(String(200), nullable=True, default="")
    strategy_id = Column(String(100), nullable=True)
    strategy_name = Column(String(200), nullable=True, default="")
    symbol = Column(String(50), nullable=True, default="")
    symbol_name = Column(String(200), nullable=True, default="")
    timeframe = Column(String(10), nullable=True, default="1d")
    timeframe_n = Column(Integer, default=1)
    category = Column(String(100), nullable=True, default="")
    sort_order = Column(Integer, default=0)

    # Configuration JSON fields
    data_config = Column(JSON, default=dict)
    unit_settings = Column(JSON, default=dict)
    params = Column(JSON, default=dict)
    optimization_config = Column(JSON, default=dict)
    trading_mode = Column(String(20), nullable=False, default="paper")
    gateway_config = Column(JSON, default=dict)
    lock_trading = Column(Boolean, nullable=False, default=False)
    lock_running = Column(Boolean, nullable=False, default=False)
    trading_instance_id = Column(String(36), nullable=True)
    trading_snapshot = Column(JSON, default=dict)

    # Run state
    run_status = Column(String(20), default="idle")
    run_count = Column(Integer, default=0)
    last_run_time = Column(Float, nullable=True)
    last_task_id = Column(String(36), nullable=True)
    last_optimization_task_id = Column(String(36), nullable=True)
    bar_count = Column(Integer, nullable=True)
    metrics_snapshot = Column(JSON, default=dict)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    workspace = relationship("Workspace", back_populates="strategy_units")
