import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class DgJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DgProvider(Base):
    __tablename__ = "dg_providers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_id = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False, index=True)
    auth_type = Column(String(50), default="none", nullable=False)
    api_key_env = Column(String(100), nullable=True)
    rate_limit = Column(Integer, default=60, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    endpoints = relationship("DgEndpoint", back_populates="provider", cascade="all, delete-orphan")


class DgEndpoint(Base):
    __tablename__ = "dg_endpoints"
    __table_args__ = (
        UniqueConstraint("provider_id", "endpoint_name", name="uq_dg_endpoint_provider_name"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_id = Column(String(36), ForeignKey("dg_providers.id"), nullable=False, index=True)
    endpoint_name = Column(String(100), nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    function_path = Column(String(255), nullable=True)
    category = Column(String(50), nullable=False, index=True)
    params_schema = Column(JSON, default=dict, nullable=False)
    auth_type = Column(String(50), default="none", nullable=False)
    api_key_env = Column(String(100), nullable=True)
    rate_limit = Column(Integer, default=60, nullable=False)
    cache_ttl_sec = Column(Integer, default=300, nullable=False)
    target_database = Column(String(100), default="akshare_data", nullable=False)
    target_table = Column(String(100), nullable=True)
    normalization_profile = Column(JSON, default=dict, nullable=False)
    quality_profile = Column(JSON, default=dict, nullable=False)
    incremental_sync_key = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    legacy_interface_name = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    provider = relationship("DgProvider", back_populates="endpoints")
    params = relationship(
        "DgEndpointParam", back_populates="endpoint", cascade="all, delete-orphan"
    )
    jobs = relationship("DgIngestJob", back_populates="endpoint", cascade="all, delete-orphan")


class DgEndpointParam(Base):
    __tablename__ = "dg_endpoint_params"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    endpoint_id = Column(String(36), ForeignKey("dg_endpoints.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    param_type = Column(String(50), default="string", nullable=False)
    required = Column(Boolean, default=False, nullable=False)
    default_value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    options = Column(JSON, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)

    endpoint = relationship("DgEndpoint", back_populates="params")


class DgIngestJob(Base):
    __tablename__ = "dg_ingest_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    endpoint_id = Column(String(36), ForeignKey("dg_endpoints.id"), nullable=False, index=True)
    status = Column(Enum(DgJobStatus), default=DgJobStatus.QUEUED, nullable=False)
    params = Column(JSON, default=dict, nullable=False)
    row_count = Column(Integer, default=0, nullable=False)
    idempotency_key = Column(String(128), nullable=True, index=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    endpoint = relationship("DgEndpoint", back_populates="jobs")


class DgQualityRule(Base):
    __tablename__ = "dg_quality_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    endpoint_id = Column(String(36), ForeignKey("dg_endpoints.id"), nullable=False, index=True)
    rule_name = Column(String(100), nullable=False)
    rule_type = Column(String(50), nullable=False)
    rule_config = Column(JSON, default=dict, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
