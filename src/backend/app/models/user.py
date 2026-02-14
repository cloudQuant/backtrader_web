"""
用户ORM模型
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.orm import relationship

from app.db.database import Base


class User(Base):
    """用户表"""
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(128), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # 关联
    strategies = relationship("Strategy", back_populates="user")
    backtest_tasks = relationship("BacktestTask", back_populates="user")
    comparisons = relationship("Comparison", back_populates="user")
    paper_trading_accounts = relationship("Account", back_populates="user")
    alerts = relationship("Alert", back_populates="user")
    alert_rules = relationship("AlertRule", back_populates="user")
