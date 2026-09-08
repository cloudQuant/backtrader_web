"""Persistent aggregates for the trusted AI strategy research v2 protocol.

The legacy AI-research tables remain compatibility records.  These tables are
the authoritative source only for requests explicitly routed to protocol v2.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
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


class ResearchCapabilityProfile(Base):
    """Signed deployment capability evidence bound to a protocol execution."""

    __tablename__ = "ai_research_capability_profiles"
    __table_args__ = (
        UniqueConstraint("profile_id", "version", name="uq_ai_research_capability_profile_version"),
        Index("ix_ai_research_capability_profile_expiry", "profile_id", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    topology: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    db_engine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    service_identities: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    queue_capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    storage_boundaries: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    network_capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    sandbox_capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    approval_capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchHypothesisVersion(Base):
    """One immutable, user-confirmed research specification version."""

    __tablename__ = "ai_research_hypothesis_versions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "hypothesis_id", "version_no", name="uq_ai_research_hypothesis_version"
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'CONFIRMED', 'SUPERSEDED')",
            name="ck_ai_research_hypothesis_status",
        ),
        Index("ix_ai_research_hypothesis_owner_status", "user_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    hypothesis_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_hypothesis_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_mandate_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("investment_mandates.id", ondelete="RESTRICT"), nullable=True
    )
    confirmed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchExperimentEpoch(Base):
    """A bounded search family with a single sealed-holdout disclosure budget."""

    __tablename__ = "ai_research_experiment_epochs"
    __table_args__ = (
        UniqueConstraint("user_id", "family_hash", name="uq_ai_research_epoch_owner_family"),
        CheckConstraint(
            "status IN ('OPEN', 'SELECTED', 'DISCLOSED', 'CLOSED')",
            name="ck_ai_research_epoch_status",
        ),
        Index("ix_ai_research_epoch_owner_status", "user_id", "status", "opened_at"),
        Index("ix_ai_research_epoch_family", "user_id", "family_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    hypothesis_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_hypothesis_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    family_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    search_budget: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    dataset_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    holdout_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")
    selected_candidate_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, unique=True
    )
    parent_epoch_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    disclosed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchDatasetSnapshot(Base):
    """A content-addressed, point-in-time dataset partition reference."""

    __tablename__ = "ai_research_dataset_snapshots"
    __table_args__ = (
        CheckConstraint(
            "partition_kind IN ('DISCOVERY', 'ITERATION_VALIDATION', 'SEALED_HOLDOUT', 'FORWARD_OBSERVATION')",
            name="ck_ai_research_dataset_partition",
        ),
        CheckConstraint(
            "integrity_status IN ('LEGACY_UNVERIFIED', 'VERIFIED', 'FAILED')",
            name="ck_ai_research_dataset_integrity_status",
        ),
        Index("ix_ai_research_dataset_owner_partition", "user_id", "partition_kind", "created_at"),
        Index("ix_ai_research_dataset_content_hash", "content_hash"),
        Index(
            "ix_ai_research_dataset_owner_object_integrity",
            "user_id",
            "object_logical_id",
            "integrity_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    partition_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    instrument_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    split_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    execution_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    point_in_time_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_uri: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    storage_reference_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    object_receipt_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    object_logical_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    object_version: Mapped[str | None] = mapped_column(String(512), nullable=True)
    object_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    object_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    integrity_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="LEGACY_UNVERIFIED"
    )
    integrity_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    integrity_receipt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snapshot_identity_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    license_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchDataPrecheck(Base):
    """Server-generated expiry-bound evidence for one executable research input."""

    __tablename__ = "ai_research_data_prechecks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PASS', 'FAIL', 'BLOCKED')",
            name="ck_ai_research_data_precheck_status",
        ),
        Index(
            "ix_ai_research_data_precheck_owner_expiry",
            "user_id",
            "expires_at",
            "checked_at",
        ),
        Index("ix_ai_research_data_precheck_input", "user_id", "input_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    hypothesis_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_hypothesis_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    dataset_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_dataset_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    experiment_epoch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    profile_id: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_version: Mapped[str] = mapped_column(String(128), nullable=False)
    promotion_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResearchForwardObservationEpoch(Base):
    """A frozen policy window that can receive only post-freeze observations."""

    __tablename__ = "ai_research_forward_observation_epochs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('OPEN', 'READY', 'CLOSED', 'BLOCKED')",
            name="ck_ai_research_forward_epoch_status",
        ),
        CheckConstraint(
            "(freeze_receipt_id IS NULL AND freeze_receipt_fingerprint IS NULL) OR "
            "(freeze_receipt_id IS NOT NULL AND freeze_receipt_fingerprint IS NOT NULL)",
            name="ck_ai_research_forward_epoch_freeze_receipt_pair",
        ),
        UniqueConstraint(
            "candidate_id",
            "policy_version",
            name="uq_ai_research_forward_epoch_candidate_policy",
        ),
        Index("ix_ai_research_forward_epoch_owner_status", "user_id", "status", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"), nullable=False
    )
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    freeze_receipt_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_candidate_freeze_receipts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    freeze_receipt_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchForwardObservationSnapshot(Base):
    """One append-only post-freeze observation and its controlled data snapshot."""

    __tablename__ = "ai_research_forward_observation_snapshots"
    __table_args__ = (
        CheckConstraint(
            "quality_status IN ('PASS', 'FAIL', 'UNKNOWN')",
            name="ck_ai_research_forward_snapshot_quality",
        ),
        UniqueConstraint(
            "observation_epoch_id",
            "idempotency_key",
            name="uq_ai_research_forward_snapshot_idempotency",
        ),
        UniqueConstraint(
            "observation_epoch_id",
            "dataset_snapshot_id",
            name="uq_ai_research_forward_snapshot_dataset",
        ),
        Index("ix_ai_research_forward_snapshot_epoch_event", "observation_epoch_id", "event_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    observation_epoch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_forward_observation_epochs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    dataset_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_dataset_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    candidate_frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    quality_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchConfigProfile(Base):
    """A user/workspace-scoped, secret-free v2 research configuration profile."""

    __tablename__ = "ai_research_config_profiles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUARANTINED', 'ACTIVE', 'RETIRED')",
            name="ck_ai_research_config_profile_status",
        ),
        UniqueConstraint("legacy_source_hash", name="uq_ai_research_config_profile_legacy_hash"),
        Index(
            "ix_ai_research_config_profile_owner_status",
            "owner_user_id",
            "workspace_id",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    legacy_source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    legacy_source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    credential_refs: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUARANTINED")
    quarantine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class ResearchRun(Base):
    """Database authority for one v2 research run and its protocol binding."""

    __tablename__ = "ai_research_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT')",
            name="ck_ai_research_run_status",
        ),
        Index("ix_ai_research_run_owner_status", "user_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    hypothesis_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_hypothesis_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    dataset_snapshot_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_dataset_snapshots.id", ondelete="RESTRICT"),
        nullable=True,
    )
    data_precheck_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    experiment_epoch_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    protocol_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v2")
    workflow_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="generation-v1",
        server_default="generation-v1",
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")
    stage_cursor: Mapped[str] = mapped_column(String(64), nullable=False, default="CLARIFY")
    promotion_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    capability_profile_id: Mapped[str] = mapped_column(String(128), nullable=False)
    capability_profile_version: Mapped[str] = mapped_column(String(128), nullable=False)
    capability_evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchTask(Base):
    """Durable v2 task with an idempotency key and fenced worker lease."""

    __tablename__ = "ai_research_tasks"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_ai_research_task_idempotency"),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT')",
            name="ck_ai_research_task_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_ai_research_task_attempt_count"),
        CheckConstraint("event_sequence >= 0", name="ck_ai_research_task_event_sequence"),
        CheckConstraint(
            "(lease_token IS NULL AND lease_expires_at IS NULL AND lease_heartbeat_at IS NULL) OR "
            "(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND lease_heartbeat_at IS NOT NULL)",
            name="ck_ai_research_task_lease_pair",
        ),
        Index("ix_ai_research_task_owner_status", "user_id", "status", "created_at"),
        Index("ix_ai_research_task_claim", "status", "lease_expires_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")
    stage_cursor: Mapped[str] = mapped_column(String(64), nullable=False)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    retry_of_task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_research_tasks.id", ondelete="RESTRICT"), nullable=True
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchTaskEvent(Base):
    """Append-only safe summary of one durable task state transition."""

    __tablename__ = "ai_research_task_events"
    __table_args__ = (
        UniqueConstraint("task_id", "sequence_no", name="uq_ai_research_task_event_sequence"),
        CheckConstraint("sequence_no > 0", name="ck_ai_research_task_event_sequence_positive"),
        Index("ix_ai_research_task_event_task_sequence", "task_id", "sequence_no"),
        Index("ix_ai_research_task_event_owner_created", "user_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    stage_attempt_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_stage_attempts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchArtifact(Base):
    """Content-addressed artifact metadata; ordinary responses omit storage URI."""

    __tablename__ = "ai_research_artifacts"
    __table_args__ = (
        UniqueConstraint("content_hash", "kind", name="uq_ai_research_artifact_content_kind"),
        Index("ix_ai_research_artifact_producer", "producer_identity", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    producer_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    container_image_digest: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchArtifactContent(Base):
    """Database-backed payload for locally created, verifiable stage outputs."""

    __tablename__ = "ai_research_artifact_contents"

    artifact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchCandidate(Base):
    """A code/data/environment-bound candidate that may become frozen once."""

    __tablename__ = "ai_research_candidates"
    __table_args__ = (
        CheckConstraint(
            "freeze_status IN ('MUTABLE', 'FROZEN')", name="ck_ai_research_candidate_freeze"
        ),
        Index("ix_ai_research_candidate_epoch_status", "experiment_epoch_id", "freeze_status"),
        Index("ix_ai_research_candidate_owner_hash", "user_id", "candidate_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    experiment_epoch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_strategy_research_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    dataset_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_dataset_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code_artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"), nullable=False
    )
    dependency_artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"), nullable=False
    )
    candidate_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    environment_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    cost_model_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    freeze_status: Mapped[str] = mapped_column(String(16), nullable=False, default="MUTABLE")
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    frozen_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchCandidateFreezeReceipt(Base):
    """Append-only strict identity captured when a discovery candidate freezes."""

    __tablename__ = "ai_research_candidate_freeze_receipts"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id",
            name="uq_ai_research_candidate_freeze_receipt_candidate",
        ),
        CheckConstraint(
            "workflow_version = 'discovery-v1'",
            name="ck_ai_research_candidate_freeze_receipt_workflow",
        ),
        CheckConstraint(
            "checker_version = 'candidate-freeze-v1'",
            name="ck_ai_research_candidate_freeze_receipt_checker",
        ),
        CheckConstraint(
            "attempt_count_total > 0 AND market_trial_count > 0",
            name="ck_ai_research_candidate_freeze_receipt_counts",
        ),
        Index(
            "ix_ai_research_candidate_freeze_receipt_owner_run",
            "user_id",
            "run_id",
            "frozen_at",
        ),
        Index(
            "ix_ai_research_candidate_freeze_receipt_epoch",
            "experiment_epoch_id",
            "frozen_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    experiment_epoch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    candidate_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="discovery-v1"
    )
    generation_materialization_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ledger_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_count_total: Mapped[int] = mapped_column(Integer, nullable=False)
    market_trial_count: Mapped[int] = mapped_column(Integer, nullable=False)
    search_budget_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_snapshot_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dependency_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hypothesis_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    environment_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    cost_model_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    checker_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="candidate-freeze-v1"
    )
    frozen_by: Mapped[str] = mapped_column(String(128), nullable=False)
    frozen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchEvidencePackage(Base):
    """Immutable, server-built evidence manifest for one approval binding."""

    __tablename__ = "ai_research_evidence_packages"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id",
            "promotion_policy_version",
            "gate_input_evidence_hash",
            "manifest_hash",
            name="uq_ai_research_evidence_package_manifest",
        ),
        CheckConstraint(
            "(command_id IS NULL AND evaluation_id IS NULL AND "
            "artifact_binding_id IS NULL AND terminal_access_audit_id IS NULL) OR "
            "(command_id IS NOT NULL AND evaluation_id IS NOT NULL AND "
            "artifact_binding_id IS NOT NULL AND terminal_access_audit_id IS NOT NULL)",
            name="ck_ai_research_evidence_package_command_graph",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'WITHDRAWN')",
            name="ck_ai_research_evidence_package_status",
        ),
        Index(
            "ix_ai_research_evidence_package_owner_run",
            "user_id",
            "run_id",
            "created_at",
        ),
        Index(
            "ix_ai_research_evidence_package_command_created",
            "command_id",
            "created_at",
        ),
        Index(
            "ix_ai_research_evidence_package_evaluation",
            "evaluation_id",
        ),
        Index(
            "ix_ai_research_evidence_package_artifact_binding",
            "artifact_binding_id",
        ),
        Index(
            "ix_ai_research_evidence_package_terminal_audit",
            "terminal_access_audit_id",
        ),
        Index(
            "uq_ai_research_evidence_package_command",
            "command_id",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"), nullable=False
    )
    command_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "ai_research_holdout_evaluation_commands.id",
            name="fk_ai_research_evidence_package_command",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    evaluation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "ai_research_evaluations.id",
            name="fk_ai_research_evidence_package_evaluation",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    artifact_binding_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "ai_research_holdout_artifact_bindings.id",
            name="fk_ai_research_evidence_package_artifact_binding",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    terminal_access_audit_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "ai_research_holdout_access_audits.id",
            name="fk_ai_research_evidence_package_terminal_audit",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    promotion_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    gate_input_evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_binding_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchTrial(Base):
    """Append-only record of a market or technical experiment attempt."""

    __tablename__ = "ai_research_trials"
    __table_args__ = (
        UniqueConstraint("run_id", "ordinal", name="uq_ai_research_trial_ordinal"),
        UniqueConstraint("run_id", "idempotency_key", name="uq_ai_research_trial_idempotency"),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT', 'INVALID')",
            name="ck_ai_research_trial_status",
        ),
        Index("ix_ai_research_trial_candidate", "candidate_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    candidate_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"), nullable=True
    )
    parent_trial_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_research_trials.id", ondelete="RESTRICT"), nullable=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    returns_artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"), nullable=True
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    observed_market_performance: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    counts_as_market_trial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    counting_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchModelInvocation(Base):
    """Normalized provenance for every model/generator/repair call."""

    __tablename__ = "ai_research_model_invocations"
    __table_args__ = (Index("ix_ai_research_invocation_run_created", "run_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    trial_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_research_trials.id", ondelete="RESTRICT"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_model: Mapped[str] = mapped_column(String(256), nullable=False)
    resolved_model: Mapped[str] = mapped_column(String(256), nullable=False)
    provider_reported_model: Mapped[str | None] = mapped_column(String(256), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    prompt_template_version: Mapped[str] = mapped_column(String(128), nullable=False)
    system_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sampling_params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    tool_manifest: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    transformation_chain: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    fallback_chain: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    token_usage: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    cost: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchGenerationMaterialization(Base):
    """One server-owned provenance link from GENERATE to a mutable candidate."""

    __tablename__ = "ai_research_generation_materializations"
    __table_args__ = (
        UniqueConstraint(
            "stage_attempt_id",
            name="uq_ai_research_generation_materialization_attempt",
        ),
        UniqueConstraint(
            "candidate_id",
            name="uq_ai_research_generation_materialization_candidate",
        ),
        UniqueConstraint(
            "model_invocation_id",
            name="uq_ai_research_generation_materialization_invocation",
        ),
        UniqueConstraint(
            "manifest_artifact_id",
            name="uq_ai_research_generation_materialization_manifest",
        ),
        Index(
            "ix_ai_research_generation_materialization_owner_run",
            "user_id",
            "run_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    stage_attempt_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_stage_attempts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"), nullable=False
    )
    model_invocation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_model_invocations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    manifest_artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"), nullable=False
    )
    model_output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    materialization_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchDiscoveryExecution(Base):
    """Immutable discovery-runner command plus its later observed receipt."""

    __tablename__ = "ai_research_discovery_executions"
    __table_args__ = (
        UniqueConstraint(
            "stage_attempt_id",
            name="uq_ai_research_discovery_execution_attempt",
        ),
        UniqueConstraint(
            "quota_reservation_id",
            name="uq_ai_research_discovery_execution_reservation",
        ),
        CheckConstraint(
            "status IN ('PREPARED', 'OBSERVED', 'UNKNOWN')",
            name="ck_ai_research_discovery_execution_status",
        ),
        UniqueConstraint("search_epoch_id", "search_ordinal", name="uq_ai_research_search_slot"),
        UniqueConstraint("trial_id", name="uq_ai_research_discovery_trial"),
        CheckConstraint(
            "(search_epoch_id IS NULL AND search_ordinal IS NULL AND search_budget_hash IS NULL) "
            "OR (search_epoch_id IS NOT NULL AND search_ordinal IS NOT NULL "
            "AND search_ordinal > 0 AND search_budget_hash IS NOT NULL)",
            name="ck_ai_research_discovery_search_binding",
        ),
        Index(
            "ix_ai_research_discovery_execution_owner_run",
            "user_id",
            "run_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    operation_id: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    stage_attempt_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_stage_attempts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"), nullable=False
    )
    quota_reservation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_quota_reservations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    command_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # NULL is retained only for pre-allocation migration history, never new dispatches.
    search_epoch_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    search_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    search_budget_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trial_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_research_trials.id", ondelete="RESTRICT"), nullable=True
    )
    command_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PREPARED")
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class ResearchHoldoutEvaluationCommand(Base):
    """Server-authored durable intent to evaluate one frozen candidate.

    This record deliberately contains neither an authorization token nor its
    hash.  A dedicated evaluator claim transaction must issue and consume the
    one-time authorization just in time; that delivery path is not represented
    by an ordinary command row.
    """

    __tablename__ = "ai_research_holdout_evaluation_commands"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_ai_research_holdout_command_idempotency",
        ),
        UniqueConstraint(
            "experiment_epoch_id",
            name="uq_ai_research_holdout_command_epoch",
        ),
        UniqueConstraint(
            "freeze_receipt_id",
            name="uq_ai_research_holdout_command_freeze_receipt",
        ),
        UniqueConstraint(
            "authorization_id",
            name="uq_ai_research_holdout_command_authorization",
        ),
        UniqueConstraint(
            "evaluation_id",
            name="uq_ai_research_holdout_command_evaluation",
        ),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', "
            "'TIMED_OUT', 'RECONCILING')",
            name="ck_ai_research_holdout_command_status",
        ),
        CheckConstraint(
            "stage IN ('REQUEST_HOLDOUT', 'HOLDOUT_PENDING')",
            name="ck_ai_research_holdout_command_stage",
        ),
        CheckConstraint(
            "(authorization_id IS NULL AND evaluation_id IS NULL) OR "
            "(authorization_id IS NOT NULL AND evaluation_id IS NOT NULL)",
            name="ck_ai_research_holdout_command_binding_pair",
        ),
        CheckConstraint(
            "(lease_owner IS NULL AND lease_token_hash IS NULL AND "
            "lease_expires_at IS NULL AND lease_heartbeat_at IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_token_hash IS NOT NULL AND "
            "lease_expires_at IS NOT NULL AND lease_heartbeat_at IS NOT NULL)",
            name="ck_ai_research_holdout_command_lease_group",
        ),
        CheckConstraint(
            "(status = 'QUEUED' AND stage = 'REQUEST_HOLDOUT' AND "
            "authorization_id IS NULL AND evaluation_id IS NULL AND lease_owner IS NULL AND "
            "lease_token_hash IS NULL AND lease_generation = 0 AND lease_expires_at IS NULL "
            "AND lease_heartbeat_at IS NULL AND attempt_count = 0 AND started_at IS NULL) OR "
            "(status = 'RUNNING' AND stage = 'HOLDOUT_PENDING' AND "
            "authorization_id IS NOT NULL AND evaluation_id IS NOT NULL AND "
            "lease_owner IS NOT NULL AND lease_token_hash IS NOT NULL AND "
            "lease_generation >= 1 AND lease_expires_at IS NOT NULL AND "
            "lease_heartbeat_at IS NOT NULL AND attempt_count = lease_generation AND "
            "started_at IS NOT NULL) OR "
            "(status = 'RECONCILING' AND stage = 'REQUEST_HOLDOUT' AND "
            "authorization_id IS NULL AND evaluation_id IS NULL AND lease_owner IS NULL AND "
            "lease_token_hash IS NULL AND lease_generation = 0 AND lease_expires_at IS NULL "
            "AND lease_heartbeat_at IS NULL AND attempt_count = 0 AND started_at IS NULL "
            "AND error_code IS NOT NULL) OR "
            "(status IN ('SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT', 'RECONCILING') "
            "AND stage = 'HOLDOUT_PENDING' AND authorization_id IS NOT NULL AND "
            "evaluation_id IS NOT NULL AND lease_owner IS NULL AND lease_token_hash IS NULL "
            "AND lease_generation >= 1 AND lease_expires_at IS NULL AND "
            "lease_heartbeat_at IS NULL AND attempt_count = lease_generation AND "
            "started_at IS NOT NULL)",
            name="ck_ai_research_holdout_command_state_bindings",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_ai_research_holdout_command_attempt_count",
        ),
        CheckConstraint(
            "lease_generation >= 0",
            name="ck_ai_research_holdout_command_lease_generation",
        ),
        CheckConstraint(
            "expected_candidate_state = 'FROZEN'",
            name="ck_ai_research_holdout_command_candidate_state",
        ),
        Index(
            "ix_ai_research_holdout_command_owner_status",
            "user_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_ai_research_holdout_command_claim",
            "status",
            "stage",
            "lease_expires_at",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    experiment_epoch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"), nullable=False
    )
    candidate_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_candidate_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="FROZEN"
    )
    freeze_receipt_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_candidate_freeze_receipts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    freeze_receipt_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_dataset_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    dataset_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    sealed_dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sealed_dataset_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluator_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    capability_profile_id: Mapped[str] = mapped_column(String(128), nullable=False)
    capability_profile_version: Mapped[str] = mapped_column(String(128), nullable=False)
    capability_evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    authorization_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_holdout_authorizations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    evaluation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_evaluations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="REQUEST_HOLDOUT")
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class ResearchHoldoutExecution(Base):
    """Durable idempotency journal for one external sealed-evaluator operation."""

    __tablename__ = "ai_research_holdout_executions"
    __table_args__ = (
        UniqueConstraint("operation_id", name="uq_ai_research_holdout_execution_operation"),
        UniqueConstraint("command_id", name="uq_ai_research_holdout_execution_command"),
        CheckConstraint(
            "state IN ('PREPARED', 'IN_FLIGHT', 'OBSERVED', 'UNKNOWN', 'SETTLED')",
            name="ck_ai_research_holdout_execution_state",
        ),
        CheckConstraint(
            "lease_generation > 0",
            name="ck_ai_research_holdout_execution_generation",
        ),
        CheckConstraint(
            "(result_hash IS NULL AND result_json IS NULL AND observed_at IS NULL) OR "
            "(result_hash IS NOT NULL AND result_json IS NOT NULL AND observed_at IS NOT NULL)",
            name="ck_ai_research_holdout_execution_result_group",
        ),
        CheckConstraint(
            "(state IN ('OBSERVED', 'SETTLED') AND result_hash IS NOT NULL) OR "
            "(state IN ('PREPARED', 'IN_FLIGHT', 'UNKNOWN') AND result_hash IS NULL)",
            name="ck_ai_research_holdout_execution_result_state",
        ),
        CheckConstraint(
            "(state = 'UNKNOWN' AND error_code IS NOT NULL) OR "
            "(state != 'UNKNOWN' AND error_code IS NULL)",
            name="ck_ai_research_holdout_execution_error_state",
        ),
        CheckConstraint(
            "(state = 'SETTLED' AND settled_at IS NOT NULL) OR "
            "(state != 'SETTLED' AND settled_at IS NULL)",
            name="ck_ai_research_holdout_execution_settlement",
        ),
        Index(
            "ix_ai_research_holdout_execution_state_updated",
            "state",
            "updated_at",
        ),
        Index(
            "ix_ai_research_holdout_execution_owner_command",
            "user_id",
            "command_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    operation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    command_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_holdout_evaluation_commands.id", ondelete="RESTRICT"),
        nullable=False,
    )
    evaluation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_evaluations.id", ondelete="RESTRICT"), nullable=False
    )
    command_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    lease_owner: Mapped[str] = mapped_column(String(128), nullable=False)
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="PREPARED")
    command_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prepared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    not_executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class ResearchHoldoutRequestAudit(Base):
    """Append-only evidence for accepted, rejected, and uncertain requests."""

    __tablename__ = "ai_research_holdout_request_audits"
    __table_args__ = (
        CheckConstraint(
            "purpose = 'HOLDOUT_EVALUATION_REQUEST'",
            name="ck_ai_research_holdout_request_audit_purpose",
        ),
        CheckConstraint(
            "result IN ('ACCEPTED', 'REJECTED', 'UNKNOWN')",
            name="ck_ai_research_holdout_request_audit_result",
        ),
        CheckConstraint(
            "(result = 'ACCEPTED' AND command_id IS NOT NULL AND "
            "resolved_snapshot_id IS NOT NULL) OR "
            "(result IN ('REJECTED', 'UNKNOWN') AND command_id IS NULL AND "
            "resolved_snapshot_id IS NULL)",
            name="ck_ai_research_holdout_request_audit_authority",
        ),
        UniqueConstraint(
            "command_id",
            name="uq_ai_research_holdout_request_audit_command",
        ),
        Index(
            "ix_ai_research_holdout_request_audit_actor_created",
            "actor_user_id",
            "created_at",
        ),
        Index(
            "ix_ai_research_holdout_request_audit_candidate_created",
            "candidate_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    candidate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    expected_candidate_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resolved_snapshot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    purpose: Mapped[str] = mapped_column(
        String(64), nullable=False, default="HOLDOUT_EVALUATION_REQUEST"
    )
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(256), nullable=False)
    command_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_holdout_evaluation_commands.id", ondelete="RESTRICT"),
        nullable=True,
    )
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchHoldoutAuthorization(Base):
    """Opaque, one-time permission for the independent evaluator."""

    __tablename__ = "ai_research_holdout_authorizations"
    __table_args__ = (
        UniqueConstraint(
            "experiment_epoch_id",
            name="uq_ai_research_holdout_authorization_epoch",
        ),
        CheckConstraint(
            "status IN ('ISSUED', 'CONSUMED', 'EXPIRED', 'REVOKED')",
            name="ck_ai_research_holdout_authorization_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    experiment_epoch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    candidate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    candidate_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ISSUED")
    evaluator_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    capability_profile_id: Mapped[str] = mapped_column(String(128), nullable=False)
    capability_profile_version: Mapped[str] = mapped_column(String(128), nullable=False)
    capability_evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    issued_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchEvaluation(Base):
    """Independent evaluation receipt; it never owns candidate mutation."""

    __tablename__ = "ai_research_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "experiment_epoch_id",
            "dataset_snapshot_id",
            "policy_version",
            "evaluation_type",
            name="uq_ai_research_evaluation_budget",
        ),
        UniqueConstraint(
            "authorization_id",
            name="uq_ai_research_evaluation_authorization",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'PASSED', 'REJECTED', 'FAILED', 'EXPIRED')",
            name="ck_ai_research_evaluation_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    experiment_epoch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    candidate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    dataset_snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    evaluation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluator_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    authorization_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_holdout_authorizations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    returns_artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"), nullable=True
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    gate_inputs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchHoldoutAccessAudit(Base):
    """Append-only audit of internal sealed-holdout claim authority changes."""

    __tablename__ = "ai_research_holdout_access_audits"
    __table_args__ = (
        CheckConstraint(
            "action IN ('CLAIM_STARTED', 'CLAIM_REJECTED', 'CLAIM_UNKNOWN', "
            "'LEASE_EXPIRED_RECONCILING', 'EXECUTION_OBSERVED_RECONCILING', "
            "'CHECKPOINT_RECORDED', "
            "'CHECKPOINT_REJECTED', 'CHECKPOINT_UNKNOWN', 'FINALIZE_COMPLETED', "
            "'FINALIZE_REJECTED', 'FINALIZE_UNKNOWN', 'RECONCILE_COMPLETED', "
            "'RECONCILE_REJECTED')",
            name="ck_ai_research_holdout_access_audit_action",
        ),
        CheckConstraint(
            "result IN ('ACCEPTED', 'REJECTED', 'UNKNOWN')",
            name="ck_ai_research_holdout_access_audit_result",
        ),
        CheckConstraint(
            "(action IN ('CLAIM_STARTED', 'LEASE_EXPIRED_RECONCILING', "
            "'EXECUTION_OBSERVED_RECONCILING', 'CHECKPOINT_RECORDED', "
            "'FINALIZE_COMPLETED', 'RECONCILE_COMPLETED') AND "
            "result = 'ACCEPTED') OR (action IN ('CLAIM_REJECTED', "
            "'CHECKPOINT_REJECTED', 'FINALIZE_REJECTED', 'RECONCILE_REJECTED') AND "
            "result = 'REJECTED') OR (action IN ('CLAIM_UNKNOWN', "
            "'CHECKPOINT_UNKNOWN', 'FINALIZE_UNKNOWN') AND result = 'UNKNOWN')",
            name="ck_ai_research_holdout_access_audit_outcome",
        ),
        CheckConstraint(
            "(result = 'ACCEPTED' AND command_id IS NOT NULL AND "
            "authorization_id IS NOT NULL AND evaluation_id IS NOT NULL AND "
            "experiment_epoch_id IS NOT NULL AND candidate_id IS NOT NULL AND "
            "dataset_snapshot_id IS NOT NULL AND lease_generation IS NOT NULL) OR "
            "(result IN ('REJECTED', 'UNKNOWN') AND command_id IS NULL AND "
            "authorization_id IS NULL AND evaluation_id IS NULL AND "
            "experiment_epoch_id IS NULL AND candidate_id IS NULL AND "
            "dataset_snapshot_id IS NULL AND lease_generation IS NULL)",
            name="ck_ai_research_holdout_access_audit_authority",
        ),
        UniqueConstraint(
            "action",
            "command_id",
            "lease_generation",
            name="uq_ai_research_holdout_access_audit_event",
        ),
        Index(
            "ix_ai_research_holdout_access_audit_actor_created",
            "actor_identity",
            "created_at",
        ),
        Index(
            "ix_ai_research_holdout_access_audit_requested_command",
            "requested_command_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_command_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    command_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_holdout_evaluation_commands.id", ondelete="RESTRICT"),
        nullable=True,
    )
    authorization_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_holdout_authorizations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    evaluation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_evaluations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    experiment_epoch_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    candidate_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"),
        nullable=True,
    )
    dataset_snapshot_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_dataset_snapshots.id", ondelete="RESTRICT"),
        nullable=True,
    )
    lease_generation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchHoldoutArtifactBinding(Base):
    """Immutable authority snapshot for one leased holdout evidence artifact."""

    __tablename__ = "ai_research_holdout_artifact_bindings"
    __table_args__ = (
        UniqueConstraint(
            "command_id",
            name="uq_ai_research_holdout_artifact_binding_command",
        ),
        UniqueConstraint(
            "authorization_id",
            name="uq_ai_research_holdout_artifact_binding_authorization",
        ),
        UniqueConstraint(
            "evaluation_id",
            name="uq_ai_research_holdout_artifact_binding_evaluation",
        ),
        UniqueConstraint(
            "artifact_id",
            name="uq_ai_research_holdout_artifact_binding_artifact",
        ),
        UniqueConstraint(
            "claim_access_audit_id",
            name="uq_ai_research_holdout_artifact_binding_claim_audit",
        ),
        UniqueConstraint(
            "authority_binding_hash",
            name="uq_ai_research_holdout_artifact_binding_authority_hash",
        ),
        CheckConstraint(
            "lease_generation > 0",
            name="ck_ai_research_holdout_artifact_binding_generation",
        ),
        CheckConstraint(
            "binding_schema_version = 'holdout-artifact-binding-v1'",
            name="ck_ai_research_holdout_artifact_binding_schema",
        ),
        Index(
            "ix_ai_research_holdout_artifact_binding_owner_run",
            "user_id",
            "run_id",
            "created_at",
        ),
        Index(
            "ix_ai_research_holdout_artifact_binding_epoch_candidate",
            "experiment_epoch_id",
            "candidate_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    command_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_holdout_evaluation_commands.id", ondelete="RESTRICT"),
        nullable=False,
    )
    authorization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_holdout_authorizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    evaluation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_evaluations.id", ondelete="RESTRICT"), nullable=False
    )
    experiment_epoch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_dataset_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"), nullable=False
    )
    claim_access_audit_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_holdout_access_audits.id", ondelete="RESTRICT"),
        nullable=False,
    )
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    lease_owner: Mapped[str] = mapped_column(String(128), nullable=False)
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    binding_schema_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="holdout-artifact-binding-v1"
    )
    authority_binding_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchGateDecision(Base):
    """Immutable service-side hard gate decision and its evidence input hash."""

    __tablename__ = "ai_research_gate_decisions"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_id",
            "policy_version",
            "input_evidence_hash",
            "gate_code",
            name="uq_ai_research_gate_decision_evaluation_input_gate",
        ),
        Index("ix_ai_research_gate_candidate", "candidate_id", "evaluated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    evaluation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_research_evaluations.id", ondelete="RESTRICT"), nullable=True
    )
    gate_code: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    input_evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    executor_version: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchApprovalGrant(Base):
    """Control-plane-issued human approval authority for one exact run scope."""

    __tablename__ = "ai_research_approval_grants"
    __table_args__ = (
        CheckConstraint(
            "subject_kind = 'HUMAN' AND issuer_kind = 'HUMAN'",
            name="ck_ai_research_approval_grant_human_identity",
        ),
        CheckConstraint(
            "permission = 'research:approve'",
            name="ck_ai_research_approval_grant_permission",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= issued_at",
            name="ck_ai_research_approval_grant_revocation_time",
        ),
        CheckConstraint(
            "(revoked_at IS NULL AND revoked_by IS NULL AND revocation_reason IS NULL) OR "
            "(revoked_at IS NOT NULL AND revoked_by IS NOT NULL AND "
            "length(trim(revocation_reason)) > 0)",
            name="ck_ai_research_approval_grant_revocation_group",
        ),
        CheckConstraint(
            "expires_at > issued_at",
            name="ck_ai_research_approval_grant_expiry",
        ),
        UniqueConstraint("grant_hash", name="uq_ai_research_approval_grant_hash"),
        Index(
            "ix_ai_research_approval_grant_scope",
            "actor_id",
            "run_id",
            "workspace_id",
            "permission",
            "expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    permission: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="HUMAN")
    issuer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    issuer_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="HUMAN")
    grant_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchApprovalGrantAudit(Base):
    """Append-only issue/revoke command receipt for approval grants."""

    __tablename__ = "ai_research_approval_grant_audits"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('ISSUED', 'REVOKED')",
            name="ck_ai_research_approval_grant_audit_event",
        ),
        CheckConstraint(
            "(event_type = 'ISSUED' AND reason_hash IS NULL) OR "
            "(event_type = 'REVOKED' AND reason_hash IS NOT NULL)",
            name="ck_ai_research_approval_grant_audit_reason",
        ),
        CheckConstraint(
            "length(policy_material_hash) = 64 AND length(command_material_hash) = 64 "
            "AND (reason_hash IS NULL OR length(reason_hash) = 64)",
            name="ck_ai_research_approval_grant_audit_hash_lengths",
        ),
        UniqueConstraint(
            "actor_id",
            "idempotency_key",
            name="uq_ai_research_approval_grant_audit_idempotency",
        ),
        UniqueConstraint(
            "grant_id",
            "event_type",
            name="uq_ai_research_approval_grant_audit_event",
        ),
        Index(
            "ix_ai_research_approval_grant_audit_scope",
            "run_id",
            "subject_id",
            "event_type",
            "occurred_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    grant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_approval_grants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    subject_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    permission: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_material_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    command_material_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResearchApprovalRequest(Base):
    """Server-issued approval window bound to a policy and evidence package."""

    __tablename__ = "ai_research_approval_requests"
    __table_args__ = (
        CheckConstraint(
            "approval_mode IS NULL OR approval_mode IN ('single_actor', 'multi_actor')",
            name="ck_ai_research_approval_request_mode",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'DECIDED', 'EXPIRED', 'REVOKED')",
            name="ck_ai_research_approval_request_status",
        ),
        UniqueConstraint(
            "candidate_id",
            "idempotency_key",
            name="uq_ai_research_approval_request_idempotency",
        ),
        Index(
            "ix_ai_research_approval_request_run_candidate_status",
            "run_id",
            "candidate_id",
            "status",
            "requested_at",
        ),
        CheckConstraint(
            "(run_id IS NULL AND evidence_package_id IS NULL AND "
            "policy_material_hash IS NULL AND approval_mode IS NULL AND "
            "capability_profile_id IS NULL AND capability_profile_version IS NULL AND "
            "capability_evidence_hash IS NULL AND request_material_hash IS NULL) OR "
            "(run_id IS NOT NULL AND evidence_package_id IS NOT NULL AND "
            "policy_material_hash IS NOT NULL AND approval_mode IS NOT NULL AND "
            "capability_profile_id IS NOT NULL AND capability_profile_version IS NOT NULL AND "
            "capability_evidence_hash IS NOT NULL AND request_material_hash IS NOT NULL)",
            name="ck_ai_research_approval_request_v2_binding",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND decided_at IS NULL) OR "
            "(status != 'PENDING' AND decided_at IS NOT NULL)",
            name="ck_ai_research_approval_request_decided_state",
        ),
        CheckConstraint(
            "eligible_at >= requested_at AND expires_at > requested_at",
            name="ck_ai_research_approval_request_time_order",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    evidence_package_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_evidence_packages.id", ondelete="RESTRICT"),
        nullable=True,
    )
    requested_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_material_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approval_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    capability_profile_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capability_profile_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capability_evidence_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gate_input_evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_package_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_material_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    eligible_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchHumanDecision(Base):
    """Authenticated human approval/rejection; client actor values are ignored."""

    __tablename__ = "ai_research_human_decisions"
    __table_args__ = (
        CheckConstraint(
            "approval_mode IN ('single_actor', 'multi_actor')",
            name="ck_ai_research_human_decision_mode",
        ),
        CheckConstraint(
            "(approval_mode = 'single_actor' AND single_actor = TRUE) OR "
            "(approval_mode = 'multi_actor' AND single_actor = FALSE)",
            name="ck_ai_research_human_decision_actor_mode",
        ),
        UniqueConstraint(
            "candidate_id", "idempotency_key", name="uq_ai_research_human_decision_idempotency"
        ),
        UniqueConstraint(
            "approval_request_id",
            name="uq_ai_research_human_decision_approval_request",
        ),
        Index(
            "ix_ai_research_human_decision_run_candidate_decided",
            "run_id",
            "candidate_id",
            "decided_at",
        ),
        CheckConstraint(
            "decision IN ('APPROVED', 'REJECTED', 'REQUESTED_CHANGES')",
            name="ck_ai_research_human_decision",
        ),
        CheckConstraint(
            "(approval_request_id IS NULL AND run_id IS NULL AND evidence_package_id IS NULL "
            "AND grant_id IS NULL AND grant_hash IS NULL AND policy_material_hash IS NULL "
            "AND capability_profile_id IS NULL AND capability_profile_version IS NULL "
            "AND capability_evidence_hash IS NULL AND challenge_hash IS NULL "
            "AND risk_acknowledgement_hash IS NULL AND reason_hash IS NULL "
            "AND gate_input_evidence_hash IS NULL AND decision_material_hash IS NULL) OR "
            "(approval_request_id IS NOT NULL AND run_id IS NOT NULL "
            "AND evidence_package_id IS NOT NULL AND grant_id IS NOT NULL "
            "AND grant_hash IS NOT NULL AND policy_material_hash IS NOT NULL "
            "AND capability_profile_id IS NOT NULL AND capability_profile_version IS NOT NULL "
            "AND capability_evidence_hash IS NOT NULL AND challenge_hash IS NOT NULL "
            "AND risk_acknowledgement_hash IS NOT NULL AND reason_hash IS NOT NULL "
            "AND gate_input_evidence_hash IS NOT NULL AND decision_material_hash IS NOT NULL "
            "AND requested_at IS NOT NULL AND eligible_at IS NOT NULL "
            "AND expires_at IS NOT NULL AND comment IS NOT NULL "
            "AND length(trim(comment)) > 0)",
            name="ck_ai_research_human_decision_v2_binding",
        ),
        CheckConstraint(
            "approval_request_id IS NULL OR "
            "(eligible_at >= requested_at AND decided_at >= requested_at AND expires_at > decided_at)",
            name="ck_ai_research_human_decision_time_order",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approval_request_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_approval_requests.id", ondelete="RESTRICT"),
        nullable=True,
    )
    evidence_package_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("ai_research_evidence_packages.id", ondelete="RESTRICT"),
        nullable=True,
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    domain_permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_material_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approval_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    capability_profile_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capability_profile_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capability_evidence_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    grant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_research_approval_grants.id", ondelete="RESTRICT"), nullable=True
    )
    grant_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    single_actor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_acknowledgement: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    challenge_records: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    challenge_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    risk_acknowledgement_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gate_input_evidence_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_package_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_material_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    eligible_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchApprovalDenialFence(Base):
    """Immutable rejection fence for one exact approval evidence scope."""

    __tablename__ = "ai_research_approval_denial_fences"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('REJECTED', 'REQUESTED_CHANGES')",
            name="ck_ai_research_approval_denial_fence_decision",
        ),
        CheckConstraint(
            "length(fence_scope_hash) = 64 AND "
            "length(gate_input_evidence_hash) = 64 AND "
            "length(evidence_package_hash) = 64 AND "
            "length(approval_policy_material_hash) = 64 AND "
            "length(approval_binding_hash) = 64",
            name="ck_ai_research_approval_denial_fence_hash_lengths",
        ),
        UniqueConstraint(
            "fence_scope_hash",
            name="uq_ai_research_approval_denial_fence_scope",
        ),
        UniqueConstraint(
            "decision_id",
            name="uq_ai_research_approval_denial_fence_decision",
        ),
        Index(
            "ix_ai_research_approval_denial_fence_run_candidate",
            "run_id",
            "candidate_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    evidence_package_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_evidence_packages.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_human_decisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    promotion_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    approval_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    approval_policy_material_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    gate_input_evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_package_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_binding_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fence_scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchGovernanceDecision(Base):
    """A recorded deviation, never a rewrite of the underlying gate outcome."""

    __tablename__ = "ai_research_governance_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    target_requirement_or_gate: Mapped[str] = mapped_column(String(128), nullable=False)
    original_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    risk: Mapped[str] = mapped_column(Text, nullable=False)
    compensating_controls: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    actor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    scope: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchStageAttempt(Base):
    """Idempotent checkpoint around an external stage side effect."""

    __tablename__ = "ai_research_stage_attempts"
    __table_args__ = (
        UniqueConstraint("task_id", "stage", "attempt_no", name="uq_ai_research_stage_attempt"),
        UniqueConstraint("task_id", "idempotency_key", name="uq_ai_research_stage_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchStageArtifactBinding(Base):
    """One immutable, auditable local-output binding for a stage attempt."""

    __tablename__ = "ai_research_stage_artifact_bindings"
    __table_args__ = (
        UniqueConstraint(
            "stage_attempt_id",
            name="uq_ai_research_stage_output_binding_attempt",
        ),
        Index(
            "ix_ai_research_stage_output_binding_owner_run",
            "user_id",
            "run_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_tasks.id", ondelete="RESTRICT"),
        nullable=False,
    )
    stage_attempt_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_stage_attempts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    artifact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class ResearchQuotaBucket(Base):
    """A fenced, versioned aggregate for one quota resource window."""

    __tablename__ = "ai_research_quota_buckets"
    __table_args__ = (
        UniqueConstraint(
            "scope_type",
            "scope_id",
            "policy_version",
            "resource_type",
            "window_start",
            "window_end",
            name="uq_ai_research_quota_bucket_window",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'BLOCKED_UNKNOWN')", name="ck_ai_research_quota_bucket_status"
        ),
        CheckConstraint(
            "reserved_amount >= 0 AND settled_amount >= 0", name="ck_ai_research_quota_amounts"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hard_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    concurrency_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    settled_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_reservations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    reconcile_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_fencing_token: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class ResearchQuotaReservation(Base):
    """One idempotent reservation; unknown external work is never auto-released."""

    __tablename__ = "ai_research_quota_reservations"
    __table_args__ = (
        UniqueConstraint(
            "bucket_id", "resource_type", "idempotency_key", name="uq_ai_research_quota_reservation"
        ),
        CheckConstraint(
            "status IN ('RESERVED', 'IN_FLIGHT', 'RECONCILING', 'SETTLED', 'RELEASED', 'EXPIRED', 'BLOCKED_UNKNOWN')",
            name="ck_ai_research_quota_reservation_status",
        ),
        CheckConstraint(
            "reserved_amount >= 0 AND settled_amount >= 0",
            name="ck_ai_research_quota_reservation_amounts",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    bucket_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_quota_buckets.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_research_tasks.id", ondelete="RESTRICT"), nullable=False
    )
    stage_attempt_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_research_stage_attempts.id", ondelete="RESTRICT"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reserved_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    settled_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RESERVED")
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fencing_token: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_operation_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reservation_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
