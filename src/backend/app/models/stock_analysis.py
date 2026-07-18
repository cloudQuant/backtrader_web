"""ORM models for native stock analysis."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StockAnalysisTaskModel(Base):
    """Persisted stock analysis task lifecycle."""

    __tablename__ = "stock_analysis_tasks"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(String(36), nullable=True, index=True)
    assistant_message_id = Column(String(36), nullable=True, index=True)
    source = Column(String(32), nullable=False, default="ai_assistant")
    symbol = Column(String(32), nullable=False, index=True)
    symbol_name = Column(String(255), nullable=True)
    market_type = Column(String(32), nullable=False, default="A股")
    analysis_date = Column(String(32), nullable=False)
    research_depth = Column(String(32), nullable=False, default="标准")
    selected_modules = Column(JSON, nullable=False, default=list)
    status = Column(String(20), nullable=False, default="pending", index=True)
    progress = Column(Integer, nullable=False, default=0)
    current_step = Column(String(100), nullable=True)
    message = Column(Text, nullable=True)
    request_text = Column(Text, nullable=True)
    parameters_json = Column(JSON, nullable=True)
    step_events_json = Column(JSON, nullable=True)
    data_quality_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    report_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime, default=_now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class StockAnalysisReportModel(Base):
    """Persisted normalized stock analysis report."""

    __tablename__ = "stock_analysis_reports"

    id = Column(String(36), primary_key=True, default=_uuid)
    task_id = Column(String(36), ForeignKey("stock_analysis_tasks.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String(32), nullable=False, index=True)
    market_type = Column(String(32), nullable=False, default="A股")
    analysis_date = Column(String(32), nullable=False)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=False)
    recommendation_label = Column(String(20), nullable=False, default="持有")
    confidence_score = Column(Float, nullable=True)
    risk_level = Column(String(20), nullable=False, default="中等")
    technical_score = Column(Float, nullable=True)
    fundamental_score = Column(Float, nullable=True)
    news_score = Column(Float, nullable=True)
    risk_score = Column(Float, nullable=True)
    source_snapshot_json = Column(JSON, nullable=True)
    data_quality_json = Column(JSON, nullable=True)
    report_json = Column(JSON, nullable=False)
    markdown_content = Column(Text, nullable=True)
    html_content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class StockAnalysisExportModel(Base):
    """Persisted stock analysis export metadata."""

    __tablename__ = "stock_analysis_exports"

    id = Column(String(36), primary_key=True, default=_uuid)
    report_id = Column(
        String(36), ForeignKey("stock_analysis_reports.id"), nullable=False, index=True
    )
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    format = Column(String(20), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(1000), nullable=False)
    content_type = Column(String(120), nullable=False)
    file_size = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="completed")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)
