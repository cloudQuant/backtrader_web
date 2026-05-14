"""RAG schemas for iteration 129."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class RAGIndexRequest(BaseModel):
    """Index document request."""

    knowledge_base_id: str
    document_id: str
    force_reindex: bool = False


class RAGIndexResponse(BaseModel):
    """Index response."""

    document_id: str
    knowledge_base_id: str
    status: str
    chunks_count: int


class RAGSearchRequest(BaseModel):
    """Search request."""

    knowledge_base_id: str
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(10, ge=1, le=100)
    min_similarity: float = Field(0.0, ge=0.0, le=1.0)
    search_mode: str = Field("keyword")

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be blank")
        return normalized


class RAGSearchResult(BaseModel):
    """Search result item."""

    chunk_id: str
    document_id: str
    document_title: str
    chunk_index: int
    content: str
    similarity: float


class RAGSearchResponse(BaseModel):
    """Search response."""

    total: int
    results: list[RAGSearchResult]


class RAGCitation(BaseModel):
    """Answer citation."""

    document_id: str
    document_title: str
    chunk_id: str
    chunk_index: int
    similarity: float


class RAGAskRequest(BaseModel):
    """Ask request."""

    knowledge_base_id: str
    question: str = Field(..., min_length=1, max_length=2000)
    conversation_id: str | None = None
    top_k: int = Field(10, ge=1, le=100)
    min_similarity: float = Field(0.0, ge=0.0, le=1.0)
    include_citations: bool = True
    model_id: str | None = None
    thinking_mode: bool = False

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must not be blank")
        return normalized


class RAGAskResponse(BaseModel):
    """Ask response."""

    answer: str
    citations: list[RAGCitation]
    context_chunks_used: int
    tokens_used: int
    model_id: str | None = None
    reasoning: str | None = None
    reason_code: str | None = None
    diagnostic_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
