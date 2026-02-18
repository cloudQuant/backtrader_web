"""
Backtest ORM models.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.db.database import Base


class BacktestTask(Base):
    """Backtest task table.

    Attributes:
        id: Unique task identifier (UUID).
        user_id: User ID who owns the task.
        strategy_id: Strategy ID used for backtest.
        strategy_version_id: Strategy version ID.
        symbol: Trading symbol.
        status: Task status (pending/running/completed/failed/cancelled).
        request_data: Request parameters (JSON).
        error_message: Error message if failed.
        log_dir: Task-specific log directory path.
        created_at: Task creation timestamp.
        updated_at: Last update timestamp.
    """
    __tablename__ = "backtest_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    strategy_id = Column(String(36), index=True)
    strategy_version_id = Column(String(36), ForeignKey("strategy_versions.id"), nullable=True, index=True)
    symbol = Column(String(20), index=True)
    status = Column(String(20), default="pending")  # pending/running/completed/failed/cancelled
    request_data = Column(JSON)  # Request parameters
    error_message = Column(Text, nullable=True)
    log_dir = Column(Text, nullable=True)  # Task-specific log directory path
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="backtest_tasks")
    result = relationship("BacktestResultModel", back_populates="task", uselist=False)
    strategy_version = relationship("StrategyVersion", back_populates="backtest_tasks")


class BacktestResultModel(Base):
    """Backtest result table.

    Attributes:
        id: Unique result identifier (UUID).
        task_id: Associated backtest task ID.
        total_return: Total return percentage.
        annual_return: Annualized return percentage.
        sharpe_ratio: Sharpe ratio.
        max_drawdown: Maximum drawdown percentage.
        win_rate: Win rate percentage.
        total_trades: Total number of trades.
        profitable_trades: Number of profitable trades.
        losing_trades: Number of losing trades.
        equity_curve: Equity curve data points (JSON).
        equity_dates: Equity curve dates (JSON).
        drawdown_curve: Drawdown curve data points (JSON).
        trades: Trade records (JSON).
        created_at: Result creation timestamp.
    """
    __tablename__ = "backtest_results"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("backtest_tasks.id"), unique=True, index=True)

    # Performance metrics
    total_return = Column(Float, default=0)
    annual_return = Column(Float, default=0)
    sharpe_ratio = Column(Float, default=0)
    max_drawdown = Column(Float, default=0)
    win_rate = Column(Float, default=0)

    # Trade statistics
    total_trades = Column(Integer, default=0)
    profitable_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)

    # Data
    equity_curve = Column(JSON, default=list)
    equity_dates = Column(JSON, default=list)
    drawdown_curve = Column(JSON, default=list)
    trades = Column(JSON, default=list)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    task = relationship("BacktestTask", back_populates="result")
