import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.database import Base


class NewsSourceModel(Base):
    __tablename__ = "news_sources"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_news_sources_owner_name"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    url = Column(String(1000), nullable=False)
    tier = Column(Integer, nullable=False, default=2)
    status = Column(String(20), nullable=False, default="active")
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    articles = relationship(
        "NewsArticleModel",
        back_populates="source_ref",
        cascade="all, delete-orphan",
        order_by="NewsArticleModel.created_at",
    )


class NewsArticleModel(Base):
    __tablename__ = "news_articles"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "canonical_url",
            name="uq_news_articles_owner_canonical_url",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    source_id = Column(
        String(36),
        ForeignKey("news_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source = Column(String(120), nullable=False, default="unknown")
    headline = Column(String(1000), nullable=False)
    url = Column(String(2000), nullable=False)
    # NOTE: canonical_url participates in a unique index (owner_id, canonical_url)
    # and a standalone index. MySQL/utf8mb4 caps index keys at 3072 bytes
    # (768 chars), so keep this column short enough to be indexable.
    canonical_url = Column(String(512), nullable=False, index=True)
    tickers = Column(JSON, nullable=False, default=list)
    priority = Column(String(10), nullable=False, default="P2")
    tier = Column(Integer, nullable=False, default=2)
    source_flag = Column(String(30), nullable=False, default="rss")
    sentiment = Column(String(20), nullable=False, default="NEUTRAL")
    impact = Column(String(20), nullable=False, default="LOW")
    threat = Column(String(20), nullable=False, default="LOW")
    cluster_id = Column(String(36), nullable=False, index=True)
    summary = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="ok")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    source_ref = relationship("NewsSourceModel", back_populates="articles")
    analyses = relationship(
        "NewsAnalysisModel",
        back_populates="article",
        cascade="all, delete-orphan",
        order_by="NewsAnalysisModel.created_at",
    )


class NewsAnalysisModel(Base):
    __tablename__ = "news_analyses"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    article_id = Column(
        String(36),
        ForeignKey("news_articles.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    headline = Column(String(1000), nullable=False)
    sentiment = Column(String(20), nullable=False, default="NEUTRAL")
    impact = Column(String(20), nullable=False, default="LOW")
    threat = Column(String(20), nullable=False, default="LOW")
    status = Column(String(20), nullable=False, default="ok")
    provider = Column(String(50), nullable=False, default="rules")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    article = relationship("NewsArticleModel", back_populates="analyses")
