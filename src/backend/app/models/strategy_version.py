"""
策略版本管理数据模型

支持策略的版本控制、回滚、分支管理
"""
import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

from app.db.database import Base


class VersionStatus(str, Enum):
    """版本状态"""
    DRAFT = "draft"
    STABLE = "stable"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class VersionTag(str, Enum):
    """版本标签"""
    LATEST = "latest"
    STABLE = "stable"
    ALPHA = "alpha"
    BETA = "beta"
    RC = "rc"


class StrategyVersion(Base):
    """策略版本表"""
    __tablename__ = "strategy_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)  # 版本号（1, 2, 3, ...）
    version_name = Column(String(50), nullable=False)  # 版本名称（如 v1.0.0）
    branch = Column(String(50), default="main")  # 分支名称（如 main, dev, feature/xxx）
    status = Column(String(20), default=VersionStatus.DRAFT, nullable=False)
    tags = Column(JSON, default=list)  # 版本标签列表

    # 版本内容
    code = Column(Text, nullable=False)  # 策略代码
    params = Column(JSON, default=dict)  # 默认参数
    description = Column(Text, nullable=True)  # 版本描述
    changelog = Column(Text, nullable=True)  # 变更日志

    # 元信息
    is_active = Column(Boolean, default=True, nullable=False)  # 是否为活跃版本
    is_default = Column(Boolean, default=False, nullable=False)  # 是否为默认版本
    is_current = Column(Boolean, default=False, nullable=False)  # 是否为当前版本（每个分支的头部）

    # 关联
    parent_version_id = Column(String(36), ForeignKey("strategy_versions.id"), nullable=True)
    parent_version = relationship("StrategyVersion", remote_side=[id], backref="child_versions")

    # 审计
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    strategy = relationship("Strategy", back_populates="versions")
    backtest_tasks = relationship("BacktestTask", back_populates="strategy_version")


class VersionComparison(Base):
    """版本对比记录"""
    __tablename__ = "version_comparisons"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=False, index=True)
    from_version_id = Column(String(36), ForeignKey("strategy_versions.id"), nullable=False)
    to_version_id = Column(String(36), ForeignKey("strategy_versions.id"), nullable=False)

    # 对比结果
    code_diff = Column(Text, nullable=True)  # 代码差异（Unified diff）
    params_diff = Column(JSON, default=dict)  # 参数差异
    performance_diff = Column(JSON, default=dict)  # 性能差异（回测结果对比）

    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)


class VersionRollback(Base):
    """版本回滚记录"""
    __tablename__ = "version_rollbacks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=False, index=True)
    from_version_id = Column(String(36), ForeignKey("strategy_versions.id"), nullable=False)
    to_version_id = Column(String(36), ForeignKey("strategy_versions.id"), nullable=False)

    reason = Column(Text, nullable=True)  # 回滚原因
    snapshot_data = Column(JSON, nullable=True)  # 回滚前的快照数据

    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)


class VersionBranch(Base):
    """策略分支表"""
    __tablename__ = "strategy_branches"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=False, index=True)
    branch_name = Column(String(50), nullable=False, index=True)  # 分支名称（main, dev, feature/xxx）
    parent_branch = Column(String(50), nullable=True)  # 父分支名称

    # 分支信息
    version_count = Column(Integer, default=0, nullable=False)  # 分支上的版本数量
    last_version_id = Column(String(36), ForeignKey("strategy_versions.id"), nullable=True)
    is_default = Column(Boolean, default=False, nullable=False)  # 是否为默认分支

    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
