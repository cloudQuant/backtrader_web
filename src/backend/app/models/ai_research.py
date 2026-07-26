"""Persistent AI investment research records."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InvestmentMandate(Base):
    """Structured investment demand confirmed before an AI research run."""

    __tablename__ = "investment_mandates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    raw_prompt = Column(Text, nullable=False)
    structured_goal = Column(JSON, nullable=False, default=dict)
    asset_scope = Column(JSON, nullable=False, default=dict)
    timeframe = Column(String(20), nullable=True)
    objective = Column(Text, nullable=True)
    risk_constraints = Column(JSON, nullable=False, default=dict)
    trading_constraints = Column(JSON, nullable=False, default=dict)
    quality_gates = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="confirmed", index=True)
    source = Column(String(30), nullable=False, default="rule")
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class ResearchPipelineEvent(Base):
    """Auditable stage event for one AI research run."""

    __tablename__ = "research_pipeline_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    run_id = Column(String(36), nullable=False, index=True)
    workspace_id = Column(String(36), nullable=True, index=True)
    mandate_id = Column(String(36), ForeignKey("investment_mandates.id"), nullable=True, index=True)
    stage = Column(String(60), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)
    iteration = Column(Integer, nullable=True, index=True)
    summary = Column(Text, nullable=True)
    input_payload = Column(JSON, nullable=False, default=dict)
    output_payload = Column(JSON, nullable=False, default=dict)
    metrics = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)


class AIStrategyResearchVersion(Base):
    """Strategy code version produced by an AI research iteration."""

    __tablename__ = "ai_strategy_research_versions"
    __table_args__ = (
        UniqueConstraint("user_id", "run_id", "version_no", name="uq_ai_research_version_no"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    run_id = Column(String(36), nullable=False, index=True)
    workspace_id = Column(String(36), nullable=True, index=True)
    mandate_id = Column(String(36), ForeignKey("investment_mandates.id"), nullable=True, index=True)
    strategy_id = Column(String(36), nullable=True, index=True)
    unit_id = Column(String(36), nullable=True, index=True)
    backtest_task_id = Column(String(80), nullable=True, index=True)
    version_no = Column(Integer, nullable=False)
    version_name = Column(String(120), nullable=False)
    parent_version_id = Column(
        String(36), ForeignKey("ai_strategy_research_versions.id"), nullable=True
    )
    strategy_name = Column(String(200), nullable=True)
    code = Column(Text, nullable=False, default="")
    params = Column(JSON, nullable=False, default=dict)
    ai_rationale = Column(Text, nullable=True)
    change_summary = Column(Text, nullable=True)
    backtest_metrics = Column(JSON, nullable=False, default=dict)
    quality_gate_evaluations = Column(JSON, nullable=False, default=list)
    quality_gate_status = Column(String(20), nullable=False, default="pending", index=True)
    review = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class AIStrategyResearchVersionComparison(Base):
    """Persisted comparison between two AI research strategy versions."""

    __tablename__ = "ai_strategy_research_version_comparisons"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    run_id = Column(String(36), nullable=False, index=True)
    left_version_id = Column(
        String(36), ForeignKey("ai_strategy_research_versions.id"), nullable=False, index=True
    )
    right_version_id = Column(
        String(36), ForeignKey("ai_strategy_research_versions.id"), nullable=False, index=True
    )
    metric_deltas = Column(JSON, nullable=False, default=dict)
    gate_deltas = Column(JSON, nullable=False, default=dict)
    code_diff = Column(Text, nullable=False, default="")
    verdict = Column(String(30), nullable=False, default="mixed")
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
