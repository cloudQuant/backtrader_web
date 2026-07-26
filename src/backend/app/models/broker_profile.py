import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Index, String, UniqueConstraint

from app.db.database import Base


class BrokerConnectionProfile(Base):
    __tablename__ = "broker_connection_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    broker_id = Column(String(50), nullable=False, index=True)
    account_alias = Column(String(100), nullable=False)
    capabilities = Column(JSON, nullable=False, default=list)
    credentials_ref = Column(JSON, nullable=False, default=dict)
    runtime_gateway_key = Column(String(120), nullable=True, index=True)
    runtime_account_id = Column(String(100), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    last_health = Column(JSON, nullable=True)
    created_by = Column(String(36), nullable=False, index=True)
    is_destructive_enabled = Column(Boolean, nullable=False, default=False)
    credentials_rotated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "created_by",
            "broker_id",
            "account_alias",
            name="uq_broker_connection_profiles_owner_alias",
        ),
        Index("ix_broker_connection_profiles_enabled", "enabled"),
    )
