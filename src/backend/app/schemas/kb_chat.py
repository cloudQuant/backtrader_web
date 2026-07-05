"""KB chat schemas for iteration 129."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.rag import RAGDiagnostics
from app.schemas.stock_analysis import (
    StockAnalysisParams,
    StockAnalysisReportCard,
    StockAnalysisTaskCard,
)
from app.schemas.strategy import AIStrategyDraft

KBAssistantMode = Literal[
    "knowledge_qa",
    "strategy_idea",
    "backtrader_strategy",
    "strategy_review",
    "trading_execution",
    "stock_analysis",
]


class ConversationCreate(BaseModel):
    """Create conversation request."""

    knowledge_base_id: str = Field(..., min_length=1)
    title: str = Field("新对话", min_length=1, max_length=200)
    model_id: str | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized


class ConversationResponse(BaseModel):
    """Conversation response."""

    id: str
    knowledge_base_id: str | None = None
    user_id: str
    title: str
    model_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationListResponse(BaseModel):
    """Conversation list response."""

    total: int
    items: list[ConversationResponse]


class ChatMessageResponse(BaseModel):
    """Chat message response."""

    id: str
    conversation_id: str
    role: str
    content: str
    citations: list[dict] | None = None
    tokens_used: int | None = None
    model_id: str | None = None
    reasoning: str | None = None
    metadata: dict[str, Any] | None = None
    assistant_mode: KBAssistantMode | None = None
    strategy_draft: AIStrategyDraft | None = None
    stock_analysis_task: StockAnalysisTaskCard | None = None
    stock_analysis_report: StockAnalysisReportCard | None = None
    reason_code: str | None = None
    diagnostic_message: str | None = None
    diagnostics: RAGDiagnostics | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def extract_metadata_fields(cls, value):
        if isinstance(value, dict):
            metadata = value.get("metadata") or value.get("metadata_json") or {}
            if isinstance(metadata, dict):
                value.setdefault("metadata", metadata)
                value.setdefault("assistant_mode", metadata.get("assistant_mode"))
                value.setdefault("strategy_draft", metadata.get("strategy_draft"))
                value.setdefault("stock_analysis_task", metadata.get("stock_analysis_task"))
                value.setdefault("stock_analysis_report", metadata.get("stock_analysis_report"))
                value.setdefault("reason_code", metadata.get("reason_code"))
                value.setdefault("diagnostic_message", metadata.get("diagnostic_message"))
                value.setdefault("diagnostics", metadata.get("diagnostics"))
            return value
        metadata = getattr(value, "metadata_json", None) or {}
        if not isinstance(metadata, dict):
            metadata = {}
        return {
            "id": getattr(value, "id", None),
            "conversation_id": getattr(value, "conversation_id", None),
            "role": getattr(value, "role", None),
            "content": getattr(value, "content", None),
            "citations": getattr(value, "citations", None),
            "tokens_used": getattr(value, "tokens_used", None),
            "model_id": getattr(value, "model_id", None),
            "reasoning": getattr(value, "reasoning", None),
            "metadata": metadata,
            "assistant_mode": metadata.get("assistant_mode"),
            "strategy_draft": metadata.get("strategy_draft"),
            "stock_analysis_task": metadata.get("stock_analysis_task"),
            "stock_analysis_report": metadata.get("stock_analysis_report"),
            "reason_code": metadata.get("reason_code"),
            "diagnostic_message": metadata.get("diagnostic_message"),
            "diagnostics": metadata.get("diagnostics"),
            "created_at": getattr(value, "created_at", None),
        }


class ChatHistoryResponse(BaseModel):
    """Conversation history response."""

    conversation_id: str
    messages: list[ChatMessageResponse]


class KBChatRequest(BaseModel):
    """Send chat message request."""

    knowledge_base_id: str | None = Field(None, min_length=1)
    question: str = Field(..., min_length=1, max_length=2000)
    conversation_id: str | None = Field(None, min_length=1)
    model_id: str | None = None
    assistant_mode: KBAssistantMode = "knowledge_qa"
    thinking_mode: bool = False
    stock_analysis_params: StockAnalysisParams | None = None

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must not be blank")
        return normalized

    @model_validator(mode="after")
    def require_knowledge_base_for_qa(self):
        if self.assistant_mode == "knowledge_qa" and not self.knowledge_base_id:
            raise ValueError("knowledge_base_id is required for knowledge_qa")
        return self


class KBChatResponse(BaseModel):
    """Send chat response."""

    conversation_id: str
    answer: str
    citations: list[dict]
    context_chunks_used: int
    tokens_used: int
    model_id: str | None = None
    assistant_mode: KBAssistantMode = "knowledge_qa"
    strategy_draft: AIStrategyDraft | None = None
    stock_analysis_task: StockAnalysisTaskCard | None = None
    stock_analysis_report: StockAnalysisReportCard | None = None
    reasoning: str | None = None
    reason_code: str | None = None
    diagnostic_message: str | None = None
    diagnostics: RAGDiagnostics | None = None
