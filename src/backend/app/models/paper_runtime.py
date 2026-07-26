"""Structured audit, risk, and equity records for workspace paper runtimes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

from app.db.database import Base


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class PaperReviewReport(Base):
    """A persisted paper-trading observation report for one runtime."""

    __tablename__ = "paper_review_reports"
    __table_args__ = (
        Index("ix_paper_review_reports_runtime_created", "instance_id", "created_at"),
        Index("ix_paper_review_reports_user_runtime", "user_id", "instance_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    unit_id = Column(String(36), ForeignKey("strategy_units.id"), nullable=False, index=True)
    instance_id = Column(String(36), nullable=False, index=True)
    paper_account_id = Column(String(36), ForeignKey("paper_trading_accounts.id"), nullable=True)
    source_record_id = Column(String(36), nullable=True, unique=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    observation_start_at = Column(DateTime, nullable=True)
    observation_end_at = Column(DateTime, nullable=True)
    report = Column(JSON, nullable=False, default=dict)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class LiveHandoffReview(Base):
    """An explicit, auditable decision on a paper-runtime live handoff."""

    __tablename__ = "live_handoff_reviews"
    __table_args__ = (
        Index("ix_live_handoff_reviews_runtime_created", "instance_id", "created_at"),
        Index("ix_live_handoff_reviews_user_runtime", "user_id", "instance_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    unit_id = Column(String(36), ForeignKey("strategy_units.id"), nullable=False, index=True)
    instance_id = Column(String(36), nullable=False, index=True)
    paper_account_id = Column(String(36), ForeignKey("paper_trading_accounts.id"), nullable=True)
    source_record_id = Column(String(36), nullable=True, unique=True, index=True)
    decision = Column(String(32), nullable=False, default="pending", index=True)
    rationale = Column(Text, nullable=True)
    checklist = Column(JSON, nullable=False, default=dict)
    decided_by = Column(String(120), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class RiskRule(Base):
    """A user-owned risk rule scoped to an optional workspace paper runtime."""

    __tablename__ = "risk_rules"
    __table_args__ = (
        Index("ix_risk_rules_user_scope", "user_id", "workspace_id", "unit_id", "instance_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=True, index=True)
    unit_id = Column(String(36), ForeignKey("strategy_units.id"), nullable=True, index=True)
    instance_id = Column(String(36), nullable=True, index=True)
    paper_account_id = Column(String(36), ForeignKey("paper_trading_accounts.id"), nullable=True)
    name = Column(String(200), nullable=False)
    rule_type = Column(String(64), nullable=False, index=True)
    config = Column(JSON, nullable=False, default=dict)
    severity = Column(String(20), nullable=False, default="warning")
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class PaperEquitySnapshot(Base):
    """An idempotent mark-to-market equity snapshot for a paper runtime."""

    __tablename__ = "paper_equity_snapshots"
    __table_args__ = (
        Index("ix_paper_equity_snapshots_user_runtime_at", "user_id", "instance_id", "observed_at"),
        Index("ix_paper_equity_snapshots_runtime_at", "instance_id", "observed_at"),
        Index(
            "uq_paper_equity_snapshots_idempotency",
            "instance_id",
            "source",
            "observed_at",
            unique=True,
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    unit_id = Column(String(36), ForeignKey("strategy_units.id"), nullable=False, index=True)
    instance_id = Column(String(36), nullable=False, index=True)
    paper_account_id = Column(String(36), ForeignKey("paper_trading_accounts.id"), nullable=True)
    observed_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    source = Column(String(32), nullable=False, default="mark_to_market")
    total_equity = Column(Float, nullable=False)
    cash = Column(Float, nullable=False, default=0.0)
    position_value = Column(Float, nullable=False, default=0.0)
    unrealized_pnl = Column(Float, nullable=False, default=0.0)
    realized_pnl = Column(Float, nullable=False, default=0.0)
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utc_now)
