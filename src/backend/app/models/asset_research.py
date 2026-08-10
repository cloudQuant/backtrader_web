"""Immutable and auditable persistence for multi-asset research.

The legacy stock-analysis tables remain independent compatibility records.  The
models in this module form the new, append-oriented asset-research context.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


_OWNER_SCOPE_CHECK = (
    "(owner_scope = 'USER' AND user_id IS NOT NULL) OR "
    "(owner_scope IN ('PUBLIC_SHADOW', 'ADMIN_EVAL') AND user_id IS NULL)"
)
_ASSET_TYPE_CHECK = "asset_type IN ('stock', 'bond', 'fund', 'futures', 'option', 'fx', 'crypto')"


class RetentionMixin:
    """Lifecycle fields required on every asset-research table."""

    retention_class: Mapped[str] = mapped_column(String(32), nullable=False, default="research-v1")
    retention_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tombstoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssetInstrument(RetentionMixin, Base):
    """Versioned canonical identity, never keyed by a display symbol alone."""

    __tablename__ = "asset_instruments"
    __table_args__ = (
        UniqueConstraint("canonical_id", "metadata_version", name="uq_asset_instrument_version"),
        Index("ix_asset_instruments_type_canonical", "asset_type", "canonical_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    canonical_id: Mapped[str] = mapped_column(String(512), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    identity_level: Mapped[str] = mapped_column(String(16), nullable=False)
    venue: Mapped[str | None] = mapped_column(String(128), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    identity_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    metadata_version: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class AssetDataSourceRegistry(RetentionMixin, Base):
    """Data-license, freshness and allowed-use declaration for a source."""

    __tablename__ = "asset_data_source_registry"

    source_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    asset_types: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    jurisdictions: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    license_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    allowed_uses: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    attribution_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    redistribution_policy: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UNKNOWN"
    )
    derived_data_policy: Mapped[str] = mapped_column(String(64), nullable=False, default="UNKNOWN")
    retention_policy: Mapped[str] = mapped_column(String(64), nullable=False, default="research-v1")
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    freshness_sla: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class AssetPositionContextSnapshot(RetentionMixin, Base):
    """A user-declared, expiring research context rather than an account position."""

    __tablename__ = "asset_position_context_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_asset_position_context_user_idempotency",
        ),
        UniqueConstraint(
            "id",
            "owner_scope",
            "user_id",
            "instrument_id",
            "position_context",
            name="uq_asset_position_context_prediction_binding",
        ),
        UniqueConstraint(
            "id",
            "as_of_at",
            "available_at",
            "expires_at",
            name="uq_asset_position_context_prediction_window",
        ),
        Index(
            "ix_asset_position_context_owner_identity_asof",
            "owner_scope",
            "user_id",
            "canonical_id",
            "as_of_at",
        ),
        Index("ix_asset_position_context_expires_at", "expires_at"),
        CheckConstraint(
            _OWNER_SCOPE_CHECK,
            name="ck_asset_position_context_owner",
        ),
        CheckConstraint(
            "position_context IN ('FLAT', 'LONG', 'SHORT', 'UNKNOWN')",
            name="ck_asset_position_context_value",
        ),
        CheckConstraint(
            "(position_context IN ('FLAT', 'UNKNOWN') AND long_quantity = 0 AND short_quantity = 0) "
            "OR (position_context = 'LONG' AND long_quantity > 0 AND short_quantity = 0) "
            "OR (position_context = 'SHORT' AND short_quantity > 0 AND long_quantity = 0)",
            name="ck_asset_position_context_quantities",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    instrument_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_instruments.id", ondelete="RESTRICT"), nullable=False
    )
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical_id: Mapped[str] = mapped_column(String(512), nullable=False)
    identity_version: Mapped[str] = mapped_column(String(64), nullable=False)
    position_context: Mapped[str] = mapped_column(String(16), nullable=False)
    long_quantity: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False, default=0)
    short_quantity: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False, default=0)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="USER_DECLARED")
    source_manifest_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class AssetSourceSnapshot(RetentionMixin, Base):
    """Raw, point-in-time source payload persisted before data quality gating."""

    __tablename__ = "asset_source_snapshots"
    __table_args__ = (
        Index("ix_asset_source_snapshot_identity_cutoff", "canonical_id", "cutoff_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    instrument_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_instruments.id", ondelete="RESTRICT"), nullable=False
    )
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical_id: Mapped[str] = mapped_column(String(512), nullable=False)
    identity_version: Mapped[str] = mapped_column(String(64), nullable=False)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_fields_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    raw_payload_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_manifest_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    license_tags_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class AssetAnalysisTask(RetentionMixin, Base):
    """User-facing task lifecycle; retries create a new task instead of mutation."""

    __tablename__ = "asset_analysis_tasks"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_asset_task_user_idempotency"),
        Index("ix_asset_task_user_status_created", "user_id", "status", "created_at"),
        CheckConstraint("owner_scope = 'USER'", name="ck_asset_task_owner"),
        CheckConstraint(_ASSET_TYPE_CHECK, name="ck_asset_task_asset_type"),
        CheckConstraint(
            "position_context IN ('FLAT', 'LONG', 'SHORT', 'UNKNOWN')",
            name="ck_asset_task_position_context",
        ),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="ck_asset_task_status",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="ck_asset_task_progress"),
        CheckConstraint("attempt_count >= 0", name="ck_asset_task_attempt_count"),
        CheckConstraint(
            "(lease_token IS NULL AND lease_expires_at IS NULL AND lease_heartbeat_at IS NULL) OR "
            "(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL "
            "AND lease_heartbeat_at IS NOT NULL)",
            name="ck_asset_task_lease_pair",
        ),
        Index(
            "ix_asset_task_runner_claim",
            "status",
            "lease_expires_at",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    owner_scope: Mapped[str] = mapped_column(String(32), nullable=False, default="USER")
    instrument_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_instruments.id", ondelete="RESTRICT"), nullable=False
    )
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical_id: Mapped[str] = mapped_column(String(512), nullable=False)
    identity_version: Mapped[str] = mapped_column(String(64), nullable=False)
    request_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    position_context: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    position_context_snapshot_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("asset_position_context_snapshots.id", ondelete="RESTRICT"),
        nullable=True,
    )
    horizon_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retry_of_task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("asset_analysis_tasks.id", ondelete="RESTRICT"), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class AssetAnalysisReport(RetentionMixin, Base):
    """Versioned report rendered only from published decisions and eligible facts."""

    __tablename__ = "asset_analysis_reports"
    __table_args__ = (
        UniqueConstraint("task_id", "report_version", name="uq_asset_report_task_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("asset_analysis_tasks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    prediction_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("asset_signal_predictions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    report_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v1")
    sections_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    rendered_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class AssetAnalysisExport(RetentionMixin, Base):
    """Asynchronous export record; reports are not regenerated on read."""

    __tablename__ = "asset_analysis_exports"
    __table_args__ = (
        UniqueConstraint(
            "requested_by", "idempotency_key", name="uq_asset_export_user_idempotency"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("asset_analysis_reports.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")
    storage_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    requested_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssetReportPublication(RetentionMixin, Base):
    """Audit record for saving a report to a workspace or knowledge base."""

    __tablename__ = "asset_report_publications"
    __table_args__ = (
        UniqueConstraint(
            "requested_by",
            "idempotency_key",
            name="uq_asset_publication_user_idempotency",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("asset_analysis_reports.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")
    external_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssetScheduleManifest(RetentionMixin, Base):
    """Immutable approval evidence for a bounded system-owned schedule set."""

    __tablename__ = "asset_schedule_manifests"
    __table_args__ = (
        UniqueConstraint(
            "manifest_key",
            "manifest_version",
            name="uq_asset_schedule_manifest_version",
        ),
        UniqueConstraint(
            "approved_by",
            "idempotency_key",
            name="uq_asset_schedule_manifest_actor_idempotency",
        ),
        Index(
            "ix_asset_schedule_manifest_scope_status",
            "owner_scope",
            "status",
            "approved_at",
        ),
        CheckConstraint(
            "owner_scope IN ('PUBLIC_SHADOW', 'ADMIN_EVAL')",
            name="ck_asset_schedule_manifest_scope",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'RETIRED')",
            name="ck_asset_schedule_manifest_status",
        ),
        CheckConstraint(
            "evidence_uri IS NOT NULL AND evidence_content_hash IS NOT NULL",
            name="ck_asset_schedule_manifest_evidence",
        ),
        CheckConstraint(
            "(status = 'ACTIVE' AND retired_by IS NULL AND retired_at IS NULL) OR "
            "(status = 'RETIRED' AND retired_by IS NOT NULL AND retired_at IS NOT NULL)",
            name="ck_asset_schedule_manifest_retirement",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    manifest_key: Mapped[str] = mapped_column(String(128), nullable=False)
    manifest_version: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    evidence_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    evidence_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    approved_by: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retired_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retirement_reason_codes_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class AssetSignalSchedule(RetentionMixin, Base):
    """A single confirmed asset's calendar-aware shadow schedule."""

    __tablename__ = "asset_signal_schedules"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_asset_schedule_user_idempotency"),
        UniqueConstraint("system_target_key", name="uq_asset_schedule_system_target_key"),
        Index("ix_asset_schedule_enabled_next_run", "enabled", "next_run_at"),
        Index("ix_asset_schedule_retry_due", "retry_not_before_at"),
        Index("ix_asset_schedule_manifest_enabled", "approved_manifest_id", "enabled"),
        CheckConstraint(_OWNER_SCOPE_CHECK, name="ck_asset_schedule_owner"),
        CheckConstraint(_ASSET_TYPE_CHECK, name="ck_asset_schedule_asset_type"),
        CheckConstraint(
            "position_context = 'UNKNOWN' AND position_context_snapshot_id IS NULL",
            name="ck_asset_schedule_no_position_context",
        ),
        CheckConstraint("schedule_version >= 1", name="ck_asset_schedule_version"),
        CheckConstraint(
            "misfire_policy IN ('SKIP', 'RUN_ONCE', 'BACKFILL')",
            name="ck_asset_schedule_misfire_policy",
        ),
        CheckConstraint(
            "(lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_asset_schedule_lease_pair",
        ),
        CheckConstraint(
            "(retry_of_run_id IS NULL AND retry_not_before_at IS NULL "
            "AND retry_scheduled_fire_at IS NULL AND retry_cutoff_at IS NULL "
            "AND retry_schedule_version IS NULL AND retry_cutoff_policy_version IS NULL "
            "AND retry_schedule_config_json IS NULL AND retry_attempt = 0) OR "
            "(retry_of_run_id IS NOT NULL AND retry_not_before_at IS NOT NULL "
            "AND retry_scheduled_fire_at IS NOT NULL AND retry_cutoff_at IS NOT NULL "
            "AND retry_schedule_version IS NOT NULL AND retry_cutoff_policy_version IS NOT NULL "
            "AND retry_schedule_config_json IS NOT NULL AND retry_attempt > 0)",
            name="ck_asset_schedule_retry_context",
        ),
        CheckConstraint(
            "(owner_scope = 'USER' AND approved_manifest_id IS NULL "
            "AND manifest_entry_key IS NULL AND manifest_content_hash IS NULL "
            "AND system_target_key IS NULL) OR "
            "(owner_scope IN ('PUBLIC_SHADOW', 'ADMIN_EVAL') "
            "AND approved_manifest_id IS NOT NULL AND manifest_entry_key IS NOT NULL "
            "AND manifest_content_hash IS NOT NULL AND "
            "((enabled = 1 AND system_target_key IS NOT NULL) "
            "OR (enabled = 0 AND system_target_key IS NULL)))",
            name="ck_asset_schedule_manifest_owner",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    approved_manifest_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("asset_schedule_manifests.id", ondelete="RESTRICT"),
        nullable=True,
    )
    manifest_entry_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    manifest_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    system_target_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    instrument_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_instruments.id", ondelete="RESTRICT"), nullable=False
    )
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical_id: Mapped[str] = mapped_column(String(512), nullable=False)
    identity_version: Mapped[str] = mapped_column(String(64), nullable=False)
    horizon_code: Mapped[str] = mapped_column(String(64), nullable=False)
    horizon_spec_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    position_context: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    position_context_snapshot_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("asset_position_context_snapshots.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cron_expression: Mapped[str] = mapped_column(String(128), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    cutoff_policy: Mapped[str] = mapped_column(String(128), nullable=False)
    cutoff_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    misfire_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="SKIP")
    schedule_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retry_of_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "asset_signal_runs.id",
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_asset_schedule_retry_of_run",
        ),
        nullable=True,
    )
    retry_not_before_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_scheduled_fire_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_cutoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_schedule_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_cutoff_policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retry_schedule_config_json: Mapped[Any] = mapped_column(JSON(none_as_null=True), nullable=True)
    retry_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class AssetSignalRun(RetentionMixin, Base):
    """An idempotent task- or schedule-sourced run audit record.

    A terminal successful run keeps its single immutable prediction directly on
    this row.  Keeping the terminal-state cardinality in one table allows
    MySQL to enforce it with a normal CHECK and foreign key instead of a
    binary-log-sensitive trigger.  A prediction remains reusable: multiple
    successful run rows may reference the same immutable prediction.
    """

    __tablename__ = "asset_signal_runs"
    __table_args__ = (
        UniqueConstraint("run_key", name="uq_asset_signal_runs_run_key"),
        Index("ix_asset_run_owner_status_asof", "owner_scope", "user_id", "status", "as_of_at"),
        Index("ix_asset_run_schedule_status_asof", "schedule_id", "status", "as_of_at"),
        Index("ix_asset_run_prediction_created", "prediction_id", "created_at"),
        CheckConstraint(_OWNER_SCOPE_CHECK, name="ck_asset_run_owner"),
        CheckConstraint(_ASSET_TYPE_CHECK, name="ck_asset_run_asset_type"),
        CheckConstraint(
            "(task_id IS NOT NULL AND schedule_id IS NULL AND schedule_version IS NULL "
            "AND schedule_config_json IS NULL) OR "
            "(task_id IS NULL AND schedule_id IS NOT NULL AND schedule_version IS NOT NULL "
            "AND schedule_config_json IS NOT NULL)",
            name="ck_asset_run_exactly_one_source",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="ck_asset_run_status",
        ),
        CheckConstraint(
            "(status = 'SUCCEEDED' AND prediction_id IS NOT NULL "
            "AND prediction_link_role IN ('CREATED', 'REUSED')) OR "
            "(status IN ('PENDING', 'RUNNING', 'FAILED', 'CANCELLED') "
            "AND prediction_id IS NULL AND prediction_link_role IS NULL)",
            name="ck_asset_run_prediction_terminal",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_key: Mapped[str] = mapped_column(String(64), nullable=False)
    schedule_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("asset_signal_schedules.id", ondelete="RESTRICT"), nullable=True
    )
    retry_of_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("asset_signal_runs.id", ondelete="RESTRICT"), nullable=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("asset_analysis_tasks.id", ondelete="RESTRICT"), nullable=True
    )
    schedule_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schedule_config_json: Mapped[Any] = mapped_column(JSON, nullable=True)
    cutoff_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    prediction_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("asset_signal_predictions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    prediction_link_role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    counts_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssetSignalPrediction(RetentionMixin, Base):
    """Immutable decision input, candidate and published decision fact."""

    __tablename__ = "asset_signal_predictions"
    __table_args__ = (
        UniqueConstraint("prediction_key", name="uq_asset_signal_predictions_prediction_key"),
        ForeignKeyConstraint(
            [
                "position_context_snapshot_id",
                "owner_scope",
                "user_id",
                "instrument_id",
                "position_context",
            ],
            [
                "asset_position_context_snapshots.id",
                "asset_position_context_snapshots.owner_scope",
                "asset_position_context_snapshots.user_id",
                "asset_position_context_snapshots.instrument_id",
                "asset_position_context_snapshots.position_context",
            ],
            name="fk_asset_prediction_position_context_binding",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "position_context_snapshot_id",
                "position_context_snapshot_as_of_at",
                "position_context_snapshot_available_at",
                "position_context_snapshot_expires_at",
            ],
            [
                "asset_position_context_snapshots.id",
                "asset_position_context_snapshots.as_of_at",
                "asset_position_context_snapshots.available_at",
                "asset_position_context_snapshots.expires_at",
            ],
            name="fk_asset_prediction_position_context_window",
            ondelete="RESTRICT",
        ),
        Index("ix_asset_prediction_identity_asof", "asset_type", "canonical_id", "as_of_at"),
        Index("ix_asset_prediction_owner_asof", "owner_scope", "user_id", "as_of_at"),
        Index("ix_asset_prediction_owner_identity_asof", "owner_scope", "canonical_id", "as_of_at"),
        Index(
            "ix_asset_prediction_actionability_quality_asof",
            "actionability",
            "quality_status",
            "as_of_at",
        ),
        Index("ix_asset_prediction_versions", "model_version", "policy_version", "horizon_code"),
        Index("ix_asset_prediction_outcome_lease", "outcome_lease_expires_at"),
        CheckConstraint(_OWNER_SCOPE_CHECK, name="ck_asset_prediction_owner"),
        CheckConstraint(_ASSET_TYPE_CHECK, name="ck_asset_prediction_asset_type"),
        CheckConstraint(
            "position_context IN ('FLAT', 'LONG', 'SHORT', 'UNKNOWN')",
            name="ck_asset_prediction_position_context",
        ),
        CheckConstraint(
            "quality_status IN ('ELIGIBLE', 'DEGRADED', 'REJECTED')",
            name="ck_asset_prediction_quality_status",
        ),
        CheckConstraint(
            "actionability IN ('ACTIONABLE', 'RESEARCH_ONLY', 'INSUFFICIENT_DATA', "
            "'REGION_RESTRICTED')",
            name="ck_asset_prediction_actionability",
        ),
        CheckConstraint(
            "asset_type != 'option' OR position_context != 'LONG' "
            "OR position_context_snapshot_id IS NOT NULL",
            name="ck_asset_option_long_context_snapshot",
        ),
        CheckConstraint(
            "asset_type != 'option' OR position_context != 'LONG' OR "
            "(position_context_snapshot_as_of_at IS NOT NULL "
            "AND position_context_snapshot_available_at IS NOT NULL "
            "AND position_context_snapshot_expires_at IS NOT NULL "
            "AND position_context_snapshot_as_of_at <= as_of_at "
            "AND position_context_snapshot_available_at <= as_of_at "
            "AND as_of_at < position_context_snapshot_expires_at)",
            name="ck_asset_option_long_context_window",
        ),
        CheckConstraint(
            "(outcome_lease_token IS NULL AND outcome_lease_expires_at IS NULL) OR "
            "(outcome_lease_token IS NOT NULL AND outcome_lease_expires_at IS NOT NULL)",
            name="ck_asset_prediction_outcome_lease_pair",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    prediction_key: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_input_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    instrument_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_instruments.id", ondelete="RESTRICT"), nullable=False
    )
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical_id: Mapped[str] = mapped_column(String(512), nullable=False)
    identity_version: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_code: Mapped[str] = mapped_column(String(64), nullable=False)
    horizon_spec_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    position_context: Mapped[str] = mapped_column(String(16), nullable=False)
    position_context_snapshot_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("asset_position_context_snapshots.id", ondelete="RESTRICT"),
        nullable=True,
    )
    position_context_snapshot_as_of_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    position_context_snapshot_available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    position_context_snapshot_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    candidate_decision_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    published_decision_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    actionability: Mapped[str] = mapped_column(String(32), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(16), nullable=False)
    quality_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_source_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    mapped_contract_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("asset_instruments.id", ondelete="RESTRICT"), nullable=True
    )
    head_spec_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    calibration_version: Mapped[str] = mapped_column(String(64), nullable=False)
    capability_version: Mapped[str] = mapped_column(String(64), nullable=False)
    compliance_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    cutoff_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    cost_snapshot_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    # These coordination fields are operational metadata, not part of the
    # immutable decision-input hash or the prediction's economic facts.  They
    # only prevent two outcome workers from collecting/scoring one prediction
    # concurrently and are cleared after each attempt.
    outcome_lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    outcome_last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    outcome_last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class AssetSignalOutcome(RetentionMixin, Base):
    """Append-only score record for an individual prediction head and horizon."""

    __tablename__ = "asset_signal_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "prediction_id",
            "horizon_code",
            "outcome_kind",
            "evaluator_version",
            name="uq_asset_outcome_evaluator",
        ),
        Index("ix_asset_outcome_status_maturity", "status", "maturity_at"),
        Index(
            "ix_asset_outcome_head_status_scored",
            "outcome_kind",
            "head_spec_hash",
            "status",
            "scored_at",
        ),
        Index("ix_asset_outcome_prediction_horizon", "prediction_id", "horizon_code"),
        CheckConstraint(
            "status IN ('PENDING', 'PARTIAL', 'SCORED', 'UNSCORABLE')",
            name="ck_asset_outcome_status",
        ),
        CheckConstraint(
            "maturity_reason IS NULL OR maturity_reason IN "
            "('HORIZON_REACHED', 'EXPIRY', 'MATURITY', 'CALL', 'REDEMPTION', "
            "'ROLL', 'DELISTING', 'LIQUIDATION', 'EXERCISE')",
            name="ck_asset_outcome_maturity_reason",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    prediction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_signal_predictions.id", ondelete="RESTRICT"), nullable=False
    )
    outcome_kind: Mapped[str] = mapped_column(String(128), nullable=False)
    head_spec_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    horizon_code: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    maturity_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    maturity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    entry_price_basis: Mapped[str | None] = mapped_column(String(64), nullable=True)
    exit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    exit_price_basis: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gross_return: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    net_return: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    benchmark_return: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    success_label: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    metrics_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    risk_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    reason_codes_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssetModelRegistry(RetentionMixin, Base):
    """Current projection of an evidence-backed model-promotion scope."""

    __tablename__ = "asset_model_registry"
    __table_args__ = (
        UniqueConstraint(
            "promotion_scope_key",
            "signal_head",
            "horizon_code",
            "head_spec_hash",
            "policy_version",
            "model_version",
            "calibration_version",
            name="uq_asset_model_registry_scope_version",
        ),
        Index(
            "ix_asset_model_registry_scope_status",
            "asset_type",
            "instrument_class",
            "signal_head",
            "horizon_code",
            "status",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'SHADOW', 'PROMOTED', 'SUSPENDED', 'RETIRED')",
            name="ck_asset_model_registry_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    promotion_scope_key: Mapped[str] = mapped_column(String(64), nullable=False)
    promotion_scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    instrument_class: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_id_scope: Mapped[str | None] = mapped_column(String(512), nullable=True)
    venue_scope: Mapped[str | None] = mapped_column(String(128), nullable=True)
    product_type_scope: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope_parameters_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    signal_head: Mapped[str] = mapped_column(String(128), nullable=False)
    horizon_code: Mapped[str] = mapped_column(String(64), nullable=False)
    head_spec_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    target_spec_version: Mapped[str] = mapped_column(String(64), nullable=False)
    scoreability_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    probability_artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    calibration_version: Mapped[str] = mapped_column(String(64), nullable=False)
    calibration_artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    training_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    metrics_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    approval_set_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    evidence_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    evidence_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class AssetModelStatusEvent(RetentionMixin, Base):
    """Append-only audit event for every promotion, pause or retirement decision."""

    __tablename__ = "asset_model_status_events"
    __table_args__ = (Index("ix_asset_model_status_events_registry_id", "model_registry_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    model_registry_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("asset_model_registry.id", ondelete="RESTRICT"),
        nullable=False,
    )
    from_status: Mapped[str] = mapped_column(String(16), nullable=False)
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_codes_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    metrics_snapshot_json: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)
    evidence_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    evidence_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


ASSET_RESEARCH_TABLES = {
    "asset_instruments",
    "asset_data_source_registry",
    "asset_position_context_snapshots",
    "asset_source_snapshots",
    "asset_analysis_tasks",
    "asset_analysis_reports",
    "asset_analysis_exports",
    "asset_report_publications",
    "asset_schedule_manifests",
    "asset_signal_schedules",
    "asset_signal_runs",
    "asset_signal_predictions",
    "asset_signal_outcomes",
    "asset_model_registry",
    "asset_model_status_events",
}
