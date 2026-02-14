"""
回测结果对比数据模型
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Column, String, DateTime, Float, Integer, ForeignKey, JSON, Boolean, Text, Table
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

from app.db.database import Base


class ComparisonType(str, Enum):
    """对比类型"""
    METRICS = "metrics"  # 指标对比
    EQUITY = "equity"    # 资金曲线对比
    TRADES = "trades"    # 交易对比
    DRAWDOWN = "drawdown"  # 回撤对比


class Comparison(Base):
    """回测结果对比表"""
    __tablename__ = "backtest_comparisons"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)  # 对比名称
    description = Column(Text, nullable=True)
    type = Column(String(20), default=ComparisonType.METRICS, nullable=False)  # 对比类型

    # 对比的回测任务 ID 列表
    backtest_task_ids = Column(JSON, nullable=False)  # 回测任务 ID 列表

    # 对比结果（JSON 存储）
    comparison_data = Column(JSON, nullable=False)  # 对比结果

    # 标记
    is_favorite = Column(Boolean, default=False, nullable=False)  # 是否收藏
    is_public = Column(Boolean, default=False, nullable=False)  # 是否公开

    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 关联
    user = relationship("User", back_populates="comparisons")
    backtest_tasks = relationship("BacktestTask", secondary="comparison_backtest_association")
    shares = relationship("ComparisonShare", back_populates="comparison")


class ComparisonShare(Base):
    """对比分享表"""
    __tablename__ = "comparison_shares"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    comparison_id = Column(String(36), ForeignKey("backtest_comparisons.id"), nullable=False, index=True)
    shared_with_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    can_edit = Column(Boolean, default=False, nullable=False)  # 是否允许编辑
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # 关联
    comparison = relationship("Comparison", back_populates="shares")
    shared_with_user = relationship("User")


# 多对多关联表（对比 - 回测任务）
comparison_backtest_association = Table(
    'comparison_backtest_association',
    Base.metadata,
    Column('comparison_id', String(36), ForeignKey('backtest_comparisons.id'), primary_key=True),
    Column('backtest_task_id', String(36), ForeignKey('backtest_tasks.id'), primary_key=True),
)
