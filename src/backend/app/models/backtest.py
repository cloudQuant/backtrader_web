"""
回测ORM模型
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.db.database import Base


class BacktestTask(Base):
    """回测任务表"""
    __tablename__ = "backtest_tasks"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    strategy_id = Column(String(36), index=True)
    strategy_version_id = Column(String(36), ForeignKey("strategy_versions.id"), nullable=True, index=True)
    symbol = Column(String(20), index=True)
    status = Column(String(20), default="pending")  # pending/running/completed/failed
    request_data = Column(JSON)  # 请求参数
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联
    user = relationship("User", back_populates="backtest_tasks")
    result = relationship("BacktestResultModel", back_populates="task", uselist=False)
    strategy_version = relationship("StrategyVersion", back_populates="backtest_tasks")


class BacktestResultModel(Base):
    """回测结果表"""
    __tablename__ = "backtest_results"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("backtest_tasks.id"), unique=True, index=True)
    
    # 性能指标
    total_return = Column(Float, default=0)
    annual_return = Column(Float, default=0)
    sharpe_ratio = Column(Float, default=0)
    max_drawdown = Column(Float, default=0)
    win_rate = Column(Float, default=0)
    
    # 交易统计
    total_trades = Column(Integer, default=0)
    profitable_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    
    # 数据
    equity_curve = Column(JSON, default=list)
    equity_dates = Column(JSON, default=list)
    drawdown_curve = Column(JSON, default=list)
    trades = Column(JSON, default=list)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联
    task = relationship("BacktestTask", back_populates="result")
