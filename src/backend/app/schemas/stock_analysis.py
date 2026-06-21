"""Schemas for native stock analysis."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

StockAnalysisStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
StockAnalysisExportFormat = Literal["markdown", "html", "docx", "pdf"]
StockAnalysisModule = Literal["market", "social", "news", "fundamentals", "risk"]


class StockAnalysisParams(BaseModel):
    """User-facing stock analysis parameters."""

    symbol: str = Field(..., min_length=1, max_length=32)
    market_type: str = Field("A股", max_length=32)
    analysis_date: date | None = None
    research_depth: str = Field("标准", max_length=32)
    selected_modules: list[StockAnalysisModule] = Field(
        default_factory=lambda: ["market", "social", "news", "fundamentals", "risk"]
    )
    include_sentiment: bool = True
    include_risk: bool = True
    language: str = Field("zh-CN", max_length=16)
    model_id: str | None = Field(None, max_length=200)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = " ".join(str(value or "").split()).upper()
        if not normalized:
            raise ValueError("symbol must not be blank")
        return normalized


class StockAnalysisTaskCard(BaseModel):
    """Compact task payload embedded in AI chat messages."""

    task_id: str
    symbol: str
    status: StockAnalysisStatus
    progress: int = Field(ge=0, le=100)
    current_step: str | None = None
    message: str | None = None


class StockAnalysisReportCard(BaseModel):
    """Compact report payload embedded in AI chat messages."""

    report_id: str
    symbol: str
    summary: str
    decision_label: str
    risk_level: str
    confidence_score: float | None = None
    export_formats: list[StockAnalysisExportFormat] = Field(
        default_factory=lambda: ["markdown", "html", "docx", "pdf"]
    )


class StockAnalysisTaskResponse(BaseModel):
    """Task detail response."""

    task_id: str
    status: StockAnalysisStatus
    symbol: str
    symbol_name: str | None = None
    market_type: str
    analysis_date: str
    research_depth: str
    selected_modules: list[str]
    progress: int
    current_step: str | None = None
    message: str | None = None
    error_message: str | None = None
    report_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class StockAnalysisResultResponse(BaseModel):
    """Task result response."""

    task_id: str
    report_id: str | None = None
    status: StockAnalysisStatus
    report: dict[str, Any] | None = None


class StockAnalysisExportResponse(BaseModel):
    """Stored export metadata."""

    id: str
    report_id: str
    format: StockAnalysisExportFormat
    file_name: str
    content_type: str
    file_size: int
    status: str
    created_at: datetime


class StockAnalysisSaveToKnowledgeBaseRequest(BaseModel):
    """Persist a stock analysis report as a knowledge base document."""

    knowledge_base_id: str = Field(..., min_length=1)
    title: str | None = Field(None, min_length=1, max_length=500)
    parent_id: str | None = None


class StockAnalysisSaveToKnowledgeBaseResponse(BaseModel):
    """Knowledge base document created from a stock analysis report."""

    document_id: str
    knowledge_base_id: str
    report_id: str
    title: str
    content_type: str
    status: str
    index_status: str
    created_at: datetime


class StockAnalysisSaveToWorkspaceRequest(BaseModel):
    """Persist a stock analysis report reference into a research workspace."""

    workspace_id: str = Field(..., min_length=1)
    title: str | None = Field(None, min_length=1, max_length=500)


class StockAnalysisSaveToWorkspaceResponse(BaseModel):
    """Workspace report reference created from a stock analysis report."""

    workspace_id: str
    report_id: str
    task_id: str
    title: str
    symbol: str
    decision_label: str
    risk_level: str
    saved_at: datetime
