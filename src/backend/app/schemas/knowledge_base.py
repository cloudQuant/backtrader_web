"""Knowledge base schemas for iteration 129."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    """Create knowledge base request."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    is_public: bool = False


class KnowledgeBaseUpdate(BaseModel):
    """Update knowledge base request."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    is_public: bool | None = None


class KnowledgeBaseResponse(BaseModel):
    """Knowledge base response."""

    id: str
    owner_id: str
    name: str
    description: str | None = None
    document_count: int = 0
    is_public: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
