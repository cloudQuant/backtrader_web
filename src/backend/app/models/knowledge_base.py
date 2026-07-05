"""Knowledge base ORM models for iteration 129."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.database import Base


class KnowledgeBase(Base):
    """Knowledge base container."""

    __tablename__ = "knowledge_bases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    document_count = Column(Integer, nullable=False, default=0)
    is_public = Column(Boolean, nullable=False, default=False)
    settings = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    documents = relationship(
        "KBDocument",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
        order_by="KBDocument.sort_order",
    )


class KBDocument(Base):
    """Document or folder inside a knowledge base."""

    __tablename__ = "kb_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    knowledge_base_id = Column(
        String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True)
    content_type = Column(String(50), nullable=False, default="markdown")
    file_path = Column(String(1000), nullable=True)
    is_folder = Column(Boolean, nullable=False, default=False)
    parent_id = Column(
        String(36), ForeignKey("kb_documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sort_order = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="draft")
    index_status = Column(String(20), nullable=False, default="not_indexed")
    indexed_at = Column(DateTime, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    parent = relationship("KBDocument", remote_side=[id])


class DocumentChunk(Base):
    """Chunk metadata for indexed documents."""

    __tablename__ = "document_chunks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(
        String(36), ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    knowledge_base_id = Column(
        String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=True)
    source_type = Column(String(50), nullable=False, default="document")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ChatConversation(Base):
    """Chat conversation, optionally bound to a knowledge base."""

    __tablename__ = "chat_conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    knowledge_base_id = Column(
        String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False, default="新对话")
    model_id = Column(String(200), nullable=True)
    settings = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    messages = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    """Chat message record."""

    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(
        String(36),
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    citations = Column(JSON, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    model_id = Column(String(200), nullable=True)
    reasoning = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    conversation = relationship("ChatConversation", back_populates="messages")


class ModelConfig(Base):
    """Model metadata table."""

    __tablename__ = "model_configs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    api_name = Column(String(200), nullable=False, unique=True)
    category = Column(String(20), nullable=False, default="chat", index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)
    description = Column(Text, nullable=True)
    max_context = Column(Integer, nullable=True)
    max_output = Column(Integer, nullable=True)
    input_price = Column(Integer, nullable=True)
    output_price = Column(Integer, nullable=True)
    parameters = Column(JSON, default=dict)
    features = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ModelUsageLog(Base):
    """Model usage statistics."""

    __tablename__ = "model_usage_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    model_id = Column(String(36), ForeignKey("model_configs.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    request_type = Column(String(20), nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cost = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
