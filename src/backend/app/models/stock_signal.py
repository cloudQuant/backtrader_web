"""Persisted, versioned stock-signal predictions and batch runs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StockSignalRun(Base):
    """An idempotent audit record for a scheduled signal batch."""

    __tablename__ = "stock_signal_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    run_key = Column(String(64), nullable=False, unique=True)
    owner_scope = Column(String(80), nullable=False, default="system", index=True)
    source = Column(String(32), nullable=False, default="nightly_sse50", index=True)
    universe_code = Column(String(32), nullable=False, default="SSE50", index=True)
    as_of_date = Column(Date, nullable=False, index=True)
    scheduled_for_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    expected_count = Column(Integer, nullable=False, default=0)
    created_count = Column(Integer, nullable=False, default=0)
    eligible_count = Column(Integer, nullable=False, default=0)
    degraded_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    universe_snapshot_json = Column(JSON, nullable=False, default=list)
    config_snapshot_json = Column(JSON, nullable=False, default=dict)
    error_summary_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)


class StockSignalPrediction(Base):
    """A point-in-time prediction and its later, immutable market outcome."""

    __tablename__ = "stock_signal_predictions"
    __table_args__ = (
        UniqueConstraint("prediction_key", name="uq_stock_signal_predictions_prediction_key"),
        Index("ix_stock_signal_prediction_symbol_date", "symbol", "as_of_date"),
        Index("ix_stock_signal_prediction_scope_symbol_date", "owner_scope", "symbol", "as_of_date"),
        Index("ix_stock_signal_prediction_universe_date", "universe_code", "as_of_date"),
        Index("ix_stock_signal_prediction_outcome_next_date", "outcome_status", "next_trading_date"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    prediction_key = Column(String(64), nullable=False)
    run_id = Column(String(36), ForeignKey("stock_signal_runs.id"), nullable=True, index=True)
    report_id = Column(String(36), ForeignKey("stock_analysis_reports.id"), nullable=True, index=True)
    owner_scope = Column(String(80), nullable=False, default="system", index=True)
    source = Column(String(32), nullable=False, default="manual", index=True)
    universe_code = Column(String(32), nullable=False, default="MANUAL", index=True)
    symbol = Column(String(32), nullable=False, index=True)
    symbol_name = Column(String(255), nullable=True)
    market_type = Column(String(32), nullable=False, default="A股")
    as_of_date = Column(Date, nullable=False, index=True)
    as_of_at = Column(DateTime, nullable=False)
    available_at = Column(DateTime, nullable=False)
    next_trading_date = Column(Date, nullable=True, index=True)

    signal_action = Column(String(16), nullable=False, default="WATCH", index=True)
    confidence_score = Column(Float, nullable=False, default=0.0)
    buy_probability = Column(Float, nullable=True)
    sell_probability = Column(Float, nullable=True)
    watch_probability = Column(Float, nullable=True)
    expected_excess_return = Column(Float, nullable=True)
    risk_score = Column(Float, nullable=False, default=1.0)
    eligibility_status = Column(String(20), nullable=False, default="rejected", index=True)
    quality_reasons_json = Column(JSON, nullable=False, default=list)
    data_freshness_json = Column(JSON, nullable=False, default=dict)

    feature_version = Column(String(64), nullable=False)
    decision_policy_version = Column(String(64), nullable=False)
    model_version = Column(String(64), nullable=False)
    feature_snapshot_json = Column(JSON, nullable=False, default=dict)
    policy_snapshot_json = Column(JSON, nullable=False, default=dict)
    source_snapshot_hash = Column(String(64), nullable=False)

    outcome_status = Column(String(20), nullable=False, default="pending", index=True)
    outcome_reason = Column(Text, nullable=True)
    entry_date = Column(Date, nullable=True)
    entry_price = Column(Float, nullable=True)
    horizon_1d_return = Column(Float, nullable=True)
    horizon_5d_return = Column(Float, nullable=True)
    horizon_20d_return = Column(Float, nullable=True)
    benchmark_1d_return = Column(Float, nullable=True)
    benchmark_5d_return = Column(Float, nullable=True)
    benchmark_20d_return = Column(Float, nullable=True)
    excess_1d_return = Column(Float, nullable=True)
    excess_5d_return = Column(Float, nullable=True)
    excess_20d_return = Column(Float, nullable=True)
    buy_is_correct_20d = Column(Boolean, nullable=True)
    sell_is_correct_20d = Column(Boolean, nullable=True)
    scored_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)
