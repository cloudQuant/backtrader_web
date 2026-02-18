"""
Strategy versioning models.

Supports versioning, rollback, and branch management.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

from app.db.database import Base


class VersionStatus(str, Enum):
    """Version status enum."""
    DRAFT = "draft"
    STABLE = "stable"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class VersionTag(str, Enum):
    """Version tag enum."""
    LATEST = "latest"
    STABLE = "stable"
    ALPHA = "alpha"
    BETA = "beta"
    RC = "rc"


class StrategyVersion(Base):
    """Strategy version table.

    Attributes:
        id: Unique version identifier (UUID).
        strategy_id: Associated strategy ID.
        version_number: Version number (1, 2, 3, ...).
        version_name: Version name (e.g., v1.0.0).
        branch: Branch name (e.g., main, dev, feature/xxx).
        status: Version status.
        tags: Version tag list.
        code: Strategy code.
        params: Default parameters (JSON).
        description: Version description.
        changelog: Change log.
        is_active: Whether the version is active.
        is_default: Whether this is the default version.
        is_current: Whether this is the current version (branch head).
        parent_version_id: Parent version ID.
        created_by: User ID who created the version.
        created_at: Creation timestamp.
        updated_by: User ID who last updated the version.
        updated_at: Last update timestamp.
    """
    __tablename__ = "strategy_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)  # Version number (1, 2, 3, ...)
    version_name = Column(String(50), nullable=False)  # Version name (e.g., v1.0.0)
    branch = Column(String(50), default="main")  # Branch name (e.g., main, dev, feature/xxx)
    status = Column(String(20), default=VersionStatus.DRAFT, nullable=False)
    tags = Column(JSON, default=list)  # Version tag list

    # Version content
    code = Column(Text, nullable=False)  # Strategy code
    params = Column(JSON, default=dict)  # Default parameters
    description = Column(Text, nullable=True)  # Version description
    changelog = Column(Text, nullable=True)  # Change log

    # Meta info
    is_active = Column(Boolean, default=True, nullable=False)  # Whether version is active
    is_default = Column(Boolean, default=False, nullable=False)  # Whether version is default
    is_current = Column(Boolean, default=False, nullable=False)  # Whether version is current (branch head)

    # Relationships
    parent_version_id = Column(String(36), ForeignKey("strategy_versions.id"), nullable=True)
    parent_version = relationship("StrategyVersion", remote_side=[id], backref="child_versions")

    # Audit
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    strategy = relationship("Strategy", back_populates="versions")
    backtest_tasks = relationship("BacktestTask", back_populates="strategy_version")


class VersionComparison(Base):
    """Version comparison record table.

    Attributes:
        id: Unique comparison identifier (UUID).
        strategy_id: Associated strategy ID.
        from_version_id: Source version ID.
        to_version_id: Target version ID.
        code_diff: Code difference (Unified diff).
        params_diff: Parameter difference (JSON).
        performance_diff: Performance difference (JSON).
        created_at: Creation timestamp.
    """
    __tablename__ = "version_comparisons"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=False, index=True)
    from_version_id = Column(String(36), ForeignKey("strategy_versions.id"), nullable=False)
    to_version_id = Column(String(36), ForeignKey("strategy_versions.id"), nullable=False)

    # Comparison results
    code_diff = Column(Text, nullable=True)  # Code difference (Unified diff)
    params_diff = Column(JSON, default=dict)  # Parameter difference
    performance_diff = Column(JSON, default=dict)  # Performance difference (backtest results)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)


class VersionRollback(Base):
    """Version rollback record table.

    Attributes:
        id: Unique rollback identifier (UUID).
        strategy_id: Associated strategy ID.
        from_version_id: Source version ID.
        to_version_id: Target version ID.
        reason: Rollback reason.
        snapshot_data: Snapshot data before rollback (JSON).
        created_at: Creation timestamp.
        created_by: User ID who initiated the rollback.
    """
    __tablename__ = "version_rollbacks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=False, index=True)
    from_version_id = Column(String(36), ForeignKey("strategy_versions.id"), nullable=False)
    to_version_id = Column(String(36), ForeignKey("strategy_versions.id"), nullable=False)

    reason = Column(Text, nullable=True)  # Rollback reason
    snapshot_data = Column(JSON, nullable=True)  # Snapshot data before rollback

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)


class VersionBranch(Base):
    """Strategy branch table.

    Attributes:
        id: Unique branch identifier (UUID).
        strategy_id: Associated strategy ID.
        branch_name: Branch name (main, dev, feature/xxx).
        parent_branch: Parent branch name.
        version_count: Number of versions on the branch.
        last_version_id: Latest version ID on the branch.
        is_default: Whether this is the default branch.
        created_at: Creation timestamp.
        created_by: User ID who created the branch.
    """
    __tablename__ = "strategy_branches"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=False, index=True)
    branch_name = Column(String(50), nullable=False, index=True)  # Branch name (main, dev, feature/xxx)
    parent_branch = Column(String(50), nullable=True)  # Parent branch name

    # Branch info
    version_count = Column(Integer, default=0, nullable=False)  # Version count on branch
    last_version_id = Column(String(36), ForeignKey("strategy_versions.id"), nullable=True)
    is_default = Column(Boolean, default=False, nullable=False)  # Whether default branch

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
