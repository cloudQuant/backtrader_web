"""Market data trust and robustness ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text, UniqueConstraint

from app.db.database import Base


class AssetSpecModel(Base):
    """Normalized asset trading specification."""

    __tablename__ = "asset_specs"
    __table_args__ = (
        UniqueConstraint("asset_type", "symbol", "exchange", name="uq_asset_specs_lookup"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_type = Column(String(32), nullable=False, index=True)
    symbol = Column(String(64), nullable=False, index=True)
    name = Column(String(200), default="", nullable=False)
    exchange = Column(String(64), default="", nullable=False, index=True)
    currency = Column(String(16), default="CNY", nullable=False)
    contract_multiplier = Column(Float, nullable=True)
    margin_rate = Column(Float, nullable=True)
    tick_size = Column(Float, nullable=True)
    lot_size = Column(Float, nullable=True)
    min_order_size = Column(Float, nullable=True)
    commission_rate = Column(Float, nullable=True)
    commission_fixed = Column(Float, nullable=True)
    slippage_model = Column(String(64), default="bps", nullable=False)
    trading_calendar = Column(String(64), default="CN", nullable=False)
    metadata_json = Column("metadata", JSON, default=dict)
    source = Column(String(120), default="", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class MarketDataCoverageModel(Base):
    """Coverage summary for one asset/timeframe/provider."""

    __tablename__ = "market_data_coverage"
    __table_args__ = (
        UniqueConstraint(
            "asset_type",
            "symbol",
            "timeframe",
            "provider",
            name="uq_market_data_coverage_lookup",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_type = Column(String(32), nullable=False, index=True)
    symbol = Column(String(64), nullable=False, index=True)
    timeframe = Column(String(16), nullable=False, index=True)
    provider = Column(String(64), nullable=False, index=True)
    start_date = Column(String(32), nullable=True)
    end_date = Column(String(32), nullable=True)
    row_count = Column(Integer, default=0, nullable=False)
    missing_count = Column(Integer, default=0, nullable=False)
    missing_ratio = Column(Float, default=0.0, nullable=False)
    latest_bar_time = Column(String(64), nullable=True)
    quality_status = Column(String(20), default="unknown", nullable=False)
    source_path = Column(Text, nullable=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class MarketDataQualityReportModel(Base):
    """One market data quality issue summary."""

    __tablename__ = "market_data_quality_reports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_type = Column(String(32), nullable=False, index=True)
    symbol = Column(String(64), nullable=False, index=True)
    timeframe = Column(String(16), nullable=False, index=True)
    provider = Column(String(64), nullable=False, index=True)
    issue_type = Column(String(64), nullable=False, index=True)
    severity = Column(String(16), nullable=False, index=True)
    issue_count = Column(Integer, default=0, nullable=False)
    sample_payload = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RobustnessTestResultModel(Base):
    """Persisted robustness validation result for a backtest or strategy version."""

    __tablename__ = "robustness_test_results"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    run_id = Column(String(64), nullable=True, index=True)
    strategy_version_id = Column(String(36), nullable=True, index=True)
    backtest_id = Column(String(36), nullable=False, index=True)
    method = Column(String(64), nullable=False, index=True)
    status = Column(String(20), default="completed", nullable=False, index=True)
    metrics = Column(JSON, default=dict)
    gate_evaluations = Column(JSON, default=list)
    report = Column(JSON, default=dict)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
