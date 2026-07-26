import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ScannerPlanModel(Base):
    __tablename__ = "scanner_plans"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_scanner_plans_owner_name"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    universe_pool_id = Column(String(120), nullable=False, index=True)
    indicator_rules = Column(JSON, nullable=False, default=list)
    condition = Column(Text, nullable=False)
    lookback_days = Column(Integer, nullable=False, default=20)
    timeframe = Column(String(20), nullable=False, default="1d")
    schedule_enabled = Column(Boolean, nullable=False, default=True)
    schedule_frequency = Column(String(20), nullable=False, default="daily")
    status = Column(String(20), nullable=False, default="active", index=True)
    result_table_name = Column(String(120), nullable=True, index=True)
    result_table_status = Column(String(20), nullable=False, default="missing")
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    runs = relationship(
        "ScannerPlanRunModel",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="ScannerPlanRunModel.started_at.desc()",
    )


class ScannerPlanRunModel(Base):
    __tablename__ = "scanner_plan_runs"
    __table_args__ = (
        UniqueConstraint("plan_id", "run_date", name="uq_scanner_plan_runs_plan_date"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    plan_id = Column(
        String(36),
        ForeignKey("scanner_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_date = Column(String(20), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="completed", index=True)
    universe_pool_id = Column(String(120), nullable=False, index=True)
    condition = Column(Text, nullable=False)
    lookback_days = Column(Integer, nullable=False, default=20)
    timeframe = Column(String(20), nullable=False, default="1d")
    universe_count = Column(Integer, nullable=False, default=0)
    match_count = Column(Integer, nullable=False, default=0)
    matches = Column(JSON, nullable=False, default=list)
    metrics = Column(JSON, nullable=False, default=dict)
    source_task_id = Column(String(36), nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, default=utc_now)
    completed_at = Column(DateTime, nullable=True)

    plan = relationship("ScannerPlanModel", back_populates="runs")
