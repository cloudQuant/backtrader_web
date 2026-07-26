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


def _default_knowledge_base_settings() -> "KnowledgeBaseSettings":
    return KnowledgeBaseSettings(
        retrieval_profile="quant_research",
        search_mode="hybrid",
        default_top_k=8,
        min_similarity=0.08,
        title_weight=0.35,
        keyword_weight=0.35,
        phrase_weight=0.2,
        recency_weight=0.1,
        max_context_chunks=6,
        use_conversation_memory=True,
        conversation_lookback_messages=6,
        prioritize_title_matches=True,
        prefer_recent_documents=True,
        quant_focus="strategy_research",
        system_prompt_suffix=None,
    )


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
            self.title_weight + self.keyword_weight + self.phrase_weight + self.recency_weight
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

    name: str = Field(..., min_length=1, max_length=255, examples=["量化策略研究库"])
    description: str | None = Field(
        None, examples=["收录经典量化策略论文、因子研究报告和回测分析文档"]
    )
    is_public: bool = False
    settings: KnowledgeBaseSettings = Field(default_factory=_default_knowledge_base_settings)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "量化策略研究库",
                    "description": "收录经典量化策略论文、因子研究报告和回测分析文档",
                    "is_public": False,
                    "settings": {
                        "retrieval_profile": "quant_research",
                        "search_mode": "hybrid",
                        "default_top_k": 8,
                        "quant_focus": "strategy_research",
                    },
                },
                {
                    "name": "A股市场数据手册",
                    "description": "沪深两市交易规则、数据接口文档和行情数据说明",
                    "is_public": True,
                    "settings": {
                        "retrieval_profile": "precision",
                        "search_mode": "keyword",
                        "default_top_k": 5,
                        "quant_focus": "implementation",
                    },
                },
            ]
        }
    )


class KnowledgeBaseUpdate(BaseModel):
    """Update knowledge base request."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    is_public: bool | None = None
    settings: KnowledgeBaseSettingsUpdate | None = None


class KnowledgeBaseResponse(BaseModel):
    """Knowledge base response."""

    id: str = Field(examples=["kb_1a2b3c4d5e6f"])
    owner_id: str = Field(examples=["usr_a1b2c3d4e5f6"])
    name: str = Field(examples=["量化策略研究库"])
    description: str | None = Field(
        None, examples=["收录经典量化策略论文、因子研究报告和回测分析文档"]
    )
    document_count: int = Field(0, examples=[15])
    is_public: bool = False
    settings: KnowledgeBaseSettings = Field(default_factory=_default_knowledge_base_settings)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "kb_1a2b3c4d5e6f",
                    "owner_id": "usr_a1b2c3d4e5f6",
                    "name": "量化策略研究库",
                    "description": "收录经典量化策略论文、因子研究报告和回测分析文档",
                    "document_count": 15,
                    "is_public": False,
                    "settings": {
                        "retrieval_profile": "quant_research",
                        "search_mode": "hybrid",
                        "default_top_k": 8,
                        "min_similarity": 0.08,
                        "title_weight": 0.35,
                        "keyword_weight": 0.35,
                        "phrase_weight": 0.2,
                        "recency_weight": 0.1,
                        "max_context_chunks": 6,
                        "use_conversation_memory": True,
                        "conversation_lookback_messages": 6,
                        "prioritize_title_matches": True,
                        "prefer_recent_documents": True,
                        "quant_focus": "strategy_research",
                        "system_prompt_suffix": None,
                    },
                    "created_at": "2025-01-05T08:00:00Z",
                    "updated_at": "2025-01-14T16:20:00Z",
                }
            ]
        },
    )

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

    title: str = Field(
        ...,
        min_length=1,
        max_length=500,
        examples=["双均线交叉策略研究报告"],
    )
    content: str | None = Field(
        None, examples=["# 双均线交叉策略\n\n## 策略原理\n\n利用短期均线与长期均线的交叉信号..."]
    )
    content_type: str = Field("markdown", max_length=50, examples=["markdown"])
    parent_id: str | None = None
    is_folder: bool = False

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "title": "双均线交叉策略研究报告",
                    "content": "# 双均线交叉策略\n\n## 策略原理\n\n利用短期均线与长期均线的交叉信号判断趋势方向。\n\n## 参数选择\n\n- 快线周期: 5日\n- 慢线周期: 20日",
                    "content_type": "markdown",
                    "parent_id": None,
                    "is_folder": False,
                },
                {
                    "title": "因子研究",
                    "content": None,
                    "content_type": "markdown",
                    "parent_id": None,
                    "is_folder": True,
                },
            ]
        }
    )


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


class KBDocumentSummaryResponse(BaseModel):
    """Document list response without heavyweight body content."""

    id: str
    knowledge_base_id: str
    title: str
    content_type: str
    file_path: str | None = None
    is_folder: bool = False
    parent_id: str | None = None
    sort_order: int = 0
    status: str = "draft"
    index_status: str = "not_indexed"
    indexed_at: datetime | None = None
    metadata: dict[str, Any] | None = Field(None, validation_alias="metadata_json")
    has_content: bool = False
    content_length: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KBDocumentListResponse(BaseModel):
    """Document list response."""

    total: int
    items: list[KBDocumentSummaryResponse]


class ReqDocsImportDocument(BaseModel):
    """Single ReqDocs import document item."""

    title: str = Field(..., min_length=1, max_length=500)
    content: str | None = None
    content_type: str = Field("markdown", max_length=50)
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
