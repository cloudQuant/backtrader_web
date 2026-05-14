"""KB chat schemas for iteration 129."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.strategy import AIStrategyDraft

KBAssistantMode = Literal[
    'knowledge_qa',
    'strategy_idea',
    'backtrader_strategy',
    'strategy_review',
]


class ConversationCreate(BaseModel):
    """Create conversation request."""

    knowledge_base_id: str = Field(..., min_length=1)
    title: str = Field('新对话', min_length=1, max_length=200)
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
    knowledge_base_id: str
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
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatHistoryResponse(BaseModel):
    """Conversation history response."""

    conversation_id: str
    messages: list[ChatMessageResponse]


class KBChatRequest(BaseModel):
    """Send chat message request."""

    knowledge_base_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1, max_length=2000)
    conversation_id: str | None = Field(None, min_length=1)
    model_id: str | None = None
    assistant_mode: KBAssistantMode = 'knowledge_qa'
    thinking_mode: bool = False

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must not be blank")
        return normalized


class KBChatResponse(BaseModel):
    """Send chat response."""

    conversation_id: str
    answer: str
    citations: list[dict]
    context_chunks_used: int
    tokens_used: int
    model_id: str | None = None
    assistant_mode: KBAssistantMode = 'knowledge_qa'
    strategy_draft: AIStrategyDraft | None = None
    reasoning: str | None = None
    reason_code: str | None = None
    diagnostic_message: str | None = None
