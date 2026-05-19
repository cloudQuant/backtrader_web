"""Knowledge base schemas for iteration 129."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.utils.knowledge_base_settings import merge_knowledge_base_settings

KnowledgeBaseRetrievalProfile = Literal["quant_research", "precision", "exploration"]
KnowledgeBaseSearchMode = Literal["hybrid", "keyword"]
KnowledgeBaseQuantFocus = Literal[
    "general",
    "strategy_research",
    "strategy_review",
    "implementation",
]


class KnowledgeBaseSettings(BaseModel):
    """Retrieval and orchestration defaults for a knowledge base."""

    retrieval_profile: KnowledgeBaseRetrievalProfile = "quant_research"
    search_mode: KnowledgeBaseSearchMode = "hybrid"
    default_top_k: int = Field(8, ge=1, le=20)
    min_similarity: float = Field(0.08, ge=0.0, le=1.0)
    title_weight: float = Field(0.35, ge=0.0, le=1.0)
    keyword_weight: float = Field(0.35, ge=0.0, le=1.0)
    phrase_weight: float = Field(0.2, ge=0.0, le=1.0)
    recency_weight: float = Field(0.1, ge=0.0, le=1.0)
    max_context_chunks: int = Field(6, ge=1, le=12)
    use_conversation_memory: bool = True
    conversation_lookback_messages: int = Field(6, ge=0, le=20)
    prioritize_title_matches: bool = True
    prefer_recent_documents: bool = True
    quant_focus: KnowledgeBaseQuantFocus = "strategy_research"
    system_prompt_suffix: str | None = Field(None, max_length=1000)

    @model_validator(mode="after")
    def validate_weights(self) -> "KnowledgeBaseSettings":
        weighted_sum = (
            self.title_weight
            + self.keyword_weight
            + self.phrase_weight
            + self.recency_weight
        )
        if weighted_sum <= 0:
            raise ValueError("At least one retrieval weight must be greater than zero")
        return self


class KnowledgeBaseSettingsUpdate(BaseModel):
    """Partial update payload for knowledge base settings."""

    retrieval_profile: KnowledgeBaseRetrievalProfile | None = None
    search_mode: KnowledgeBaseSearchMode | None = None
    default_top_k: int | None = Field(None, ge=1, le=20)
    min_similarity: float | None = Field(None, ge=0.0, le=1.0)
    title_weight: float | None = Field(None, ge=0.0, le=1.0)
    keyword_weight: float | None = Field(None, ge=0.0, le=1.0)
    phrase_weight: float | None = Field(None, ge=0.0, le=1.0)
    recency_weight: float | None = Field(None, ge=0.0, le=1.0)
    max_context_chunks: int | None = Field(None, ge=1, le=12)
    use_conversation_memory: bool | None = None
    conversation_lookback_messages: int | None = Field(None, ge=0, le=20)
    prioritize_title_matches: bool | None = None
    prefer_recent_documents: bool | None = None
    quant_focus: KnowledgeBaseQuantFocus | None = None
    system_prompt_suffix: str | None = Field(None, max_length=1000)


class KnowledgeBaseCreate(BaseModel):
    """Create knowledge base request."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    is_public: bool = False
    settings: KnowledgeBaseSettings = Field(default_factory=KnowledgeBaseSettings)


class KnowledgeBaseUpdate(BaseModel):
    """Update knowledge base request."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    is_public: bool | None = None
    settings: KnowledgeBaseSettingsUpdate | None = None


class KnowledgeBaseResponse(BaseModel):
    """Knowledge base response."""

    id: str
    owner_id: str
    name: str
    description: str | None = None
    document_count: int = 0
    is_public: bool = False
    settings: KnowledgeBaseSettings = Field(default_factory=KnowledgeBaseSettings)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("settings", mode="before")
    @classmethod
    def normalize_settings(cls, value: Any) -> dict[str, Any]:
        return merge_knowledge_base_settings(value)


class KnowledgeBaseListResponse(BaseModel):
    """Knowledge base list response."""

    total: int
    items: list[KnowledgeBaseResponse]
    skip: int
    limit: int


class KBDocumentCreate(BaseModel):
    """Create document request."""

    title: str = Field(..., min_length=1, max_length=500)
    content: str | None = None
    content_type: str = Field("markdown", max_length=50)
    parent_id: str | None = None
    is_folder: bool = False


class KBDocumentUpdate(BaseModel):
    """Update document request."""

    title: str | None = Field(None, min_length=1, max_length=500)
    content: str | None = None
    content_type: str | None = Field(None, max_length=50)
    parent_id: str | None = None
    sort_order: int | None = None
    status: str | None = Field(None, max_length=20)
    index_status: str | None = Field(None, max_length=20)


class KBDocumentResponse(BaseModel):
    """Document response."""

    id: str
    knowledge_base_id: str
    title: str
    content: str | None = None
    content_type: str
    file_path: str | None = None
    is_folder: bool = False
    parent_id: str | None = None
    sort_order: int = 0
    status: str = "draft"
    index_status: str = "not_indexed"
    indexed_at: datetime | None = None
    metadata: dict[str, Any] | None = Field(None, validation_alias="metadata_json")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KBDocumentListResponse(BaseModel):
    """Document list response."""

    total: int
    items: list[KBDocumentResponse]


class ReqDocsImportDocument(BaseModel):
    """Single ReqDocs import document item."""

    title: str = Field(..., min_length=1, max_length=500)
    content: str | None = None
    content_type: str = Field('markdown', max_length=50)
    is_folder: bool = False
    parent_id: str | None = None


class ReqDocsImportRequest(BaseModel):
    """Import payload exported from ReqDocs."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    documents: list[ReqDocsImportDocument] = Field(default_factory=list)


class ReqDocsImportResponse(BaseModel):
    """Import result."""

    knowledge_base: KnowledgeBaseResponse
    imported_documents: int
