import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


def _utcnow_naive() -> datetime:
    """Return a UTC timestamp compatible with the schema's naive DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
    created_at = Column(DateTime, default=_utcnow_naive, nullable=False)

    endpoints = relationship("DgEndpoint", back_populates="provider", cascade="all, delete-orphan")


class DgDataset(Base):
    """Stable logical data product, independent of a provider or physical table."""

    __tablename__ = "dg_datasets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dataset_code = Column(String(160), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    domain = Column(String(80), nullable=False, index=True)
    canonical_schema = Column(JSON, default=dict, nullable=False)
    primary_key = Column(JSON, default=list, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_utcnow_naive, nullable=False)

    endpoints = relationship("DgEndpoint", back_populates="dataset")
    storage_bindings = relationship(
        "DgDatasetStorage", back_populates="dataset", cascade="all, delete-orphan"
    )


class DgStorageTarget(Base):
    """A registered physical store that materializes one or more datasets."""

    __tablename__ = "dg_storage_targets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    storage_id = Column(String(100), unique=True, nullable=False, index=True)
    engine = Column(String(32), nullable=False)
    url_env = Column(String(100), nullable=False)
    database_name = Column(String(100), nullable=False)
    role = Column(String(32), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_utcnow_naive, nullable=False)

    dataset_bindings = relationship(
        "DgDatasetStorage", back_populates="storage_target", cascade="all, delete-orphan"
    )


class DgDatasetStorage(Base):
    """A dataset materialization in a registered physical store."""

    __tablename__ = "dg_dataset_storages"
    __table_args__ = (
        UniqueConstraint(
            "storage_target_id",
            "physical_table",
            name="uq_dg_dataset_storage_target_table",
        ),
        UniqueConstraint(
            "primary_dataset_id",
            name="uq_dg_dataset_storages_primary_dataset",
        ),
        CheckConstraint(
            "(is_primary = true AND primary_dataset_id IS NOT NULL "
            "AND primary_dataset_id = dataset_id) "
            "OR (is_primary = false AND primary_dataset_id IS NULL)",
            name="ck_dg_dataset_storages_primary_slot",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dataset_id = Column(String(36), ForeignKey("dg_datasets.id"), nullable=False, index=True)
    storage_target_id = Column(
        String(36), ForeignKey("dg_storage_targets.id"), nullable=False, index=True
    )
    physical_table = Column(String(128), nullable=False)
    write_mode = Column(String(32), default="legacy_read_only", nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    # ``primary_dataset_id`` mirrors ``dataset_id`` only for the primary
    # binding. A UNIQUE constraint then allows many NULL secondary rows but
    # makes two primary rows for a dataset impossible across supported SQL
    # engines.
    primary_dataset_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=_utcnow_naive, nullable=False)

    dataset = relationship("DgDataset", back_populates="storage_bindings")
    storage_target = relationship("DgStorageTarget", back_populates="dataset_bindings")
    data_tables = relationship("DataTable", back_populates="dataset_storage")


@event.listens_for(DgDatasetStorage, "before_insert")
@event.listens_for(DgDatasetStorage, "before_update")
def _sync_primary_dataset_id(_mapper, _connection, target: DgDatasetStorage) -> None:
    """Persist the primary slot used by the portable uniqueness constraint."""
    target.primary_dataset_id = target.dataset_id if target.is_primary else None


class DgEndpoint(Base):
    __tablename__ = "dg_endpoints"
    __table_args__ = (
        UniqueConstraint("provider_id", "endpoint_name", name="uq_dg_endpoint_provider_name"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_id = Column(String(36), ForeignKey("dg_providers.id"), nullable=False, index=True)
    dataset_id = Column(
        String(36),
        ForeignKey("dg_datasets.id", name="fk_dg_endpoints_dataset_id_dg_datasets"),
        nullable=True,
        index=True,
    )
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
    created_at = Column(DateTime, default=_utcnow_naive, nullable=False)

    provider = relationship("DgProvider", back_populates="endpoints")
    dataset = relationship("DgDataset", back_populates="endpoints")
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
    created_at = Column(DateTime, default=_utcnow_naive, nullable=False)
    updated_at = Column(
        DateTime,
        default=_utcnow_naive,
        onupdate=_utcnow_naive,
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
    created_at = Column(DateTime, default=_utcnow_naive, nullable=False)
