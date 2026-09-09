"""Normalized, append-only market-data persistence models for Iteration 197.

These models hold canonical market-data facts independently of an AkShare
warehouse table, CSV file, or provider SDK type.  They intentionally contain
no asset-specific columns: a data series is defined by a catalog dataset and a
server-computed semantic hash, while each observation carries its own source,
quality, and revision provenance.
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
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import relationship, synonym

from app.db.database import Base
from app.models.identifier_types import exact_identifier_string

_SHA256_LENGTH = 64
_CALENDAR_COVERAGE_PAYLOAD_KEY = "coverage"
# These states are intentionally stored in relational columns rather than
# inferred from a caller-controlled JSON blob.  A current v2 source grant can
# therefore exclude compatibility/legacy receipts before they participate in
# a local response or coverage decision.
SOURCE_AUTHORIZATION_STATE_VERIFIED = "VERIFIED"
SOURCE_AUTHORIZATION_STATE_UNVERIFIED_COMPATIBILITY = "UNVERIFIED_COMPATIBILITY"
CALENDAR_SOURCE_GOVERNANCE_STATE_VERIFIED = "VERIFIED"
CALENDAR_SOURCE_GOVERNANCE_STATE_UNVERIFIED_COMPATIBILITY = "UNVERIFIED_COMPATIBILITY"
# MySQL defaults DATETIME columns to whole seconds.  Point-in-time publication
# makes an explicit one-microsecond ordering guarantee, so all Iteration 197
# evidence timestamps must retain microseconds on that dialect as well.
PITDateTime = DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")


def _uuid() -> str:
    """Generate a portable UUID primary-key value."""
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp for immutable evidence records."""
    return datetime.now(timezone.utc)


class ImmutableMarketDataRecordError(RuntimeError):
    """Raised when ORM code attempts to mutate an append-only evidence record."""


class MdPublication(Base):
    """A post-commit visibility receipt for one immutable market-data entity.

    The entity and this row are inserted in the same business transaction with
    ``published_at`` unset.  A separate transaction sets ``published_at`` only
    after the first commit succeeds.  Consumers join this receipt rather than
    infer point-in-time visibility from an ORM ``created_at`` timestamp.
    """

    __tablename__ = "md_publications"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            name="uq_md_publication_entity",
        ),
        CheckConstraint(
            f"length(entity_sha256) = {_SHA256_LENGTH}",
            name="ck_md_publication_entity_sha256_length",
        ),
        CheckConstraint(
            "visibility_sequence IS NULL OR visibility_sequence >= 1",
            name="ck_md_publication_visibility_sequence_positive",
        ),
        CheckConstraint(
            "(published_at IS NULL AND visibility_sequence IS NULL) OR "
            "(published_at IS NOT NULL AND visibility_sequence >= 1)",
            name="ck_md_publication_visibility_state",
        ),
        UniqueConstraint(
            "visibility_sequence",
            name="uq_md_publication_visibility_sequence",
        ),
        Index(
            "ix_md_publication_entity_visible",
            "entity_type",
            "entity_id",
            "published_at",
        ),
        Index(
            "ix_md_publication_visible_anchor",
            "published_at",
            "visibility_sequence",
        ),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(36), nullable=False)
    entity_sha256 = Column(String(_SHA256_LENGTH), nullable=False)
    published_at = Column(PITDateTime, nullable=True)
    # ``published_at`` is the historical physical column name.  ``visible_at``
    # is the public semantic name used by Iteration 197's complete visibility
    # anchor.  Keeping the synonym avoids a destructive table rewrite while
    # preventing callers from treating an ORM ``created_at`` as a seal time.
    visible_at = synonym("published_at")
    # Pending receipts have no sequence.  Every sealed receipt receives one
    # unique, globally monotonic value in the post-commit transaction.
    visibility_sequence = Column(BigInteger, nullable=True)
    created_at = Column(PITDateTime, default=_utcnow, nullable=False)


class MdVisibilitySequenceAllocator(Base):
    """The locked singleton that allocates globally ordered visibility receipts.

    It is mutable control-plane state, rather than immutable evidence.  The
    publication manager locks this row in the same transaction that seals
    receipts, so sequence allocation remains portable across PostgreSQL,
    MySQL, and SQLite without trusting process-local counters.
    """

    __tablename__ = "md_visibility_sequence_allocator"
    __table_args__ = (
        CheckConstraint(
            "singleton_id = 1",
            name="ck_md_visibility_sequence_allocator_singleton",
        ),
        CheckConstraint(
            "next_visibility_sequence >= 1",
            name="ck_md_visibility_sequence_allocator_next_positive",
        ),
    )

    singleton_id = Column(Integer, primary_key=True)
    next_visibility_sequence = Column(BigInteger, nullable=False)
    last_visible_at = Column(PITDateTime, nullable=True)
    created_at = Column(PITDateTime, default=_utcnow, nullable=False)


class MdInstrumentIdentityRevision(Base):
    """Immutable v2 projection of an authoritative instrument identity version.

    ``asset_instruments`` remains the source of truth for the broader research
    system.  This table preserves the exact identity and validity facts that
    were published for a market-data request, so a later update to the source
    row cannot rewrite an earlier strict point-in-time replay.
    """

    __tablename__ = "md_instrument_identity_revisions"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "revision_number",
            name="uq_md_instrument_identity_revision_number",
        ),
        UniqueConstraint(
            "revision_sha256",
            name="uq_md_instrument_identity_revision_sha256",
        ),
        CheckConstraint(
            f"length(revision_sha256) = {_SHA256_LENGTH}",
            name="ck_md_instrument_identity_revision_sha256_length",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_md_instrument_identity_revision_valid_window",
        ),
        CheckConstraint(
            "revision_number >= 1",
            name="ck_md_instrument_identity_revision_number_positive",
        ),
        Index(
            "ix_md_instrument_identity_revision_canonical",
            "canonical_id",
            "valid_from",
        ),
        Index(
            "ix_md_instrument_identity_revision_exact",
            "asset_type",
            "market",
            "symbol",
            "valid_from",
        ),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    instrument_id = Column(
        String(36),
        ForeignKey(
            "asset_instruments.id",
            name="fk_md_identity_revision_instrument",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    canonical_id = Column(exact_identifier_string(512), nullable=False)
    asset_type = Column(exact_identifier_string(16), nullable=False)
    market = Column(exact_identifier_string(128), nullable=True)
    symbol = Column(exact_identifier_string(128), nullable=False)
    metadata_version = Column(String(64), nullable=False)
    identity_json = Column(JSON, default=dict, nullable=False)
    valid_from = Column(PITDateTime, nullable=False)
    valid_to = Column(PITDateTime, nullable=True)
    revision_number = Column(Integer, nullable=False)
    revision_sha256 = Column(String(_SHA256_LENGTH), nullable=False)
    created_at = Column(PITDateTime, default=_utcnow, nullable=False)

    instrument = relationship("AssetInstrument")


class MdCalendarImportLock(Base):
    """One durable lock sentinel per calendar code for portable import serialization."""

    __tablename__ = "md_calendar_import_locks"

    calendar_code = Column(String(128), primary_key=True)
    created_at = Column(PITDateTime, default=_utcnow, nullable=False)


class MdFetchLease(Base):
    """Durable owner/fence state for one normalized market-data fetch gap.

    The row remains after release so its monotonically increasing fence token
    cannot be reset by a delete/reinsert ABA race.  It is mutable control-plane
    state rather than evidence; source facts still carry their own immutable
    receipt and publication provenance.
    """

    __tablename__ = "md_fetch_leases"
    __table_args__ = (
        CheckConstraint(
            f"length(lease_key_sha256) = {_SHA256_LENGTH}",
            name="ck_md_fetch_lease_key_sha256_length",
        ),
        CheckConstraint(
            "fence_token >= 1",
            name="ck_md_fetch_lease_fence_token_positive",
        ),
        CheckConstraint(
            "(owner_token IS NULL AND expires_at IS NULL) OR "
            "(owner_token IS NOT NULL AND expires_at IS NOT NULL)",
            name="ck_md_fetch_lease_owner_expiry_state",
        ),
        Index("ix_md_fetch_lease_expires_at", "expires_at"),
    )

    lease_key_sha256 = Column(String(_SHA256_LENGTH), primary_key=True)
    owner_token = Column(String(64), nullable=True)
    fence_token = Column(BigInteger, nullable=False)
    expires_at = Column(PITDateTime, nullable=True)
    created_at = Column(PITDateTime, default=_utcnow, nullable=False)
    updated_at = Column(PITDateTime, default=_utcnow, nullable=False)
    released_at = Column(PITDateTime, nullable=True)


class MdInstrumentLookupKey(Base):
    """Materialized exact master-data key for bounded triple identity resolution.

    ``symbol`` is stored exactly as registered.  This table does not lowercase,
    trim, tokenize, or otherwise guess an identifier; callers must supply the
    same exact asset type, market, and symbol to use its covering lookup index.
    ``active_lookup_scope`` makes a single active mapping portable across
    SQLite, MySQL, and PostgreSQL while retaining inactive historical versions.
    """

    __tablename__ = "md_instrument_lookup_keys"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            name="uq_md_instrument_lookup_key_instrument",
        ),
        UniqueConstraint(
            "asset_type",
            "market",
            "symbol",
            "active_lookup_scope",
            name="uq_md_instrument_lookup_key_active",
        ),
        CheckConstraint(
            "(is_active = true AND active_lookup_scope IS NOT NULL AND active_lookup_scope = 'ACTIVE') "
            "OR (is_active = false AND active_lookup_scope IS NULL)",
            name="ck_md_instrument_lookup_key_active_scope",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_md_instrument_lookup_key_valid_window",
        ),
        Index(
            "ix_md_instrument_lookup_active_exact",
            "asset_type",
            "market",
            "symbol",
            "is_active",
            "metadata_version",
        ),
        Index(
            "ix_md_instrument_lookup_instrument_version",
            "instrument_id",
            "metadata_version",
        ),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    asset_type = Column(exact_identifier_string(16), nullable=False)
    market = Column(exact_identifier_string(128), nullable=False)
    symbol = Column(exact_identifier_string(128), nullable=False)
    instrument_id = Column(
        String(36),
        ForeignKey(
            "asset_instruments.id",
            name="fk_md_instrument_lookup_key_instrument_id_asset_instruments",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    canonical_id = Column(exact_identifier_string(512), nullable=False)
    metadata_version = Column(String(64), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    # NULL for inactive history allows multiple historical versions on every
    # supported SQL engine; ACTIVE gives each exact triple one active row.
    active_lookup_scope = Column(String(16), nullable=True)
    valid_from = Column(PITDateTime, default=_utcnow, nullable=False)
    valid_to = Column(PITDateTime, nullable=True)
    created_at = Column(PITDateTime, default=_utcnow, nullable=False)

    instrument = relationship("AssetInstrument")


@event.listens_for(MdInstrumentLookupKey, "before_insert")
@event.listens_for(MdInstrumentLookupKey, "before_update")
def _sync_active_lookup_scope(
    _mapper: Any,
    _connection: Any,
    target: MdInstrumentLookupKey,
) -> None:
    """Keep the portable active-row uniqueness slot consistent with ``is_active``."""
    target.active_lookup_scope = "ACTIVE" if target.is_active else None


class MdDataSeries(Base):
    """One exact semantic series, independent of source and physical storage.

    ``semantic_key_sha256`` is calculated by the service from every
    content-affecting identity and policy field.  The original structured
    identity is retained in JSON to make an accidental or malicious hash
    collision detectable before a reader treats two series as equivalent.
    """

    __tablename__ = "md_data_series"
    __table_args__ = (
        UniqueConstraint("semantic_key_sha256", name="uq_md_data_series_semantic_key_sha256"),
        CheckConstraint(
            f"length(semantic_key_sha256) = {_SHA256_LENGTH}",
            name="ck_md_data_series_semantic_key_sha256_length",
        ),
        Index(
            "ix_md_data_series_dataset_canonical_kind",
            "dataset_id",
            "canonical_id",
            "data_kind",
        ),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    dataset_id = Column(
        String(36),
        ForeignKey(
            "dg_datasets.id",
            name="fk_md_data_series_dataset_id_dg_datasets",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    canonical_id = Column(String(512), nullable=False)
    data_kind = Column(String(64), nullable=False)
    frequency = Column(String(16), nullable=True)
    semantic_key_sha256 = Column(String(_SHA256_LENGTH), nullable=False)
    semantic_identity_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(PITDateTime, default=_utcnow, nullable=False)

    dataset = relationship("DgDataset")
    observation_revisions = relationship(
        "MdObservationRevision",
        back_populates="series",
        passive_deletes=True,
    )


class MdSourceSnapshot(Base):
    """Immutable raw-source receipt with query, provider-call, and payload evidence.

    ``request_fingerprint_sha256`` predates the provider-call receipt fields and
    keeps its public-query semantic meaning for historical compatibility.  New
    snapshots additionally carry the one-time provider request ID, the digest
    of the complete outbound provider DTO, and an explicit query digest.  The
    three new fields remain nullable only so receipts written before Iteration
    197's expanded evidence contract continue to be readable.
    """

    __tablename__ = "md_source_snapshots"
    __table_args__ = (
        CheckConstraint(
            f"length(request_fingerprint_sha256) = {_SHA256_LENGTH}",
            name="ck_md_source_snapshot_request_fingerprint_sha256_length",
        ),
        CheckConstraint(
            "provider_request_id IS NULL OR "
            "(length(provider_request_id) >= 32 AND length(provider_request_id) <= 128)",
            name="ck_md_source_snapshot_provider_request_id_length",
        ),
        CheckConstraint(
            "provider_request_fingerprint_sha256 IS NULL OR "
            f"length(provider_request_fingerprint_sha256) = {_SHA256_LENGTH}",
            name="ck_md_srcsnap_provider_req_fp_sha256_len",
        ),
        CheckConstraint(
            "query_fingerprint_sha256 IS NULL OR "
            f"length(query_fingerprint_sha256) = {_SHA256_LENGTH}",
            name="ck_md_source_snapshot_query_fingerprint_sha256_length",
        ),
        CheckConstraint(
            "(provider_request_id IS NULL AND "
            "provider_request_fingerprint_sha256 IS NULL AND "
            "query_fingerprint_sha256 IS NULL) OR "
            "(provider_request_id IS NOT NULL AND "
            "provider_request_fingerprint_sha256 IS NOT NULL AND "
            "query_fingerprint_sha256 IS NOT NULL)",
            name="ck_md_source_snapshot_provider_request_evidence_state",
        ),
        CheckConstraint(
            "source_authorization_state IS NULL OR "
            "source_authorization_state IN ('VERIFIED', 'UNVERIFIED_COMPATIBILITY')",
            name="ck_md_source_snapshot_source_authorization_state",
        ),
        CheckConstraint(
            "source_authorization_descriptor_sha256 IS NULL OR "
            f"length(source_authorization_descriptor_sha256) = {_SHA256_LENGTH}",
            name="ck_md_srcsnap_src_auth_desc_sha256_len",
        ),
        CheckConstraint(
            "(source_authorization_state IS NULL AND "
            "source_authorization_descriptor_sha256 IS NULL) OR "
            "(source_authorization_state = 'VERIFIED' AND "
            "source_authorization_descriptor_sha256 IS NOT NULL) OR "
            "(source_authorization_state = 'UNVERIFIED_COMPATIBILITY' AND "
            "source_authorization_descriptor_sha256 IS NULL)",
            name="ck_md_source_snapshot_source_authorization_evidence_state",
        ),
        CheckConstraint(
            "(fetch_lease_key_sha256 IS NULL AND fetch_lease_fence_token IS NULL) OR "
            f"(fetch_lease_key_sha256 IS NOT NULL AND fetch_lease_fence_token IS NOT NULL AND "
            f"length(fetch_lease_key_sha256) = {_SHA256_LENGTH} AND "
            "fetch_lease_fence_token >= 1)",
            name="ck_md_source_snapshot_fetch_lease_generation_state",
        ),
        CheckConstraint(
            f"length(payload_sha256) = {_SHA256_LENGTH}",
            name="ck_md_source_snapshot_payload_sha256_length",
        ),
        Index(
            "ix_md_source_snapshot_provider_request",
            "provider_id",
            "request_fingerprint_sha256",
        ),
        Index(
            "ix_md_source_snapshot_provider_request_id",
            "provider_id",
            "provider_request_id",
            # A regular SQL unique index allows multiple NULL values, so
            # receipts written before the provider-call evidence contract keep
            # their legitimate legacy shape while one provider cannot record
            # the same non-NULL external attempt twice.
            unique=True,
        ),
        Index("ix_md_source_snapshot_payload_sha256", "payload_sha256"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    provider_id = Column(
        String(36),
        ForeignKey(
            "dg_providers.id",
            name="fk_md_source_snapshot_provider_id_dg_providers",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    platform = Column(String(64), nullable=False)
    source_id = Column(String(255), nullable=False)
    adapter_id = Column(String(128), nullable=False)
    endpoint_version = Column(String(128), nullable=False)
    # Legacy name retained because existing rows and downstream reports use it
    # as the public query fingerprint.  Do not repurpose it as provider-call
    # identity: a query can legitimately produce multiple external attempts.
    request_fingerprint_sha256 = Column(String(_SHA256_LENGTH), nullable=False)
    provider_request_id = Column(String(128), nullable=True)
    provider_request_fingerprint_sha256 = Column(String(_SHA256_LENGTH), nullable=True)
    query_fingerprint_sha256 = Column(String(_SHA256_LENGTH), nullable=True)
    source_authorization_state = Column(String(32), nullable=True)
    source_authorization_descriptor_sha256 = Column(String(_SHA256_LENGTH), nullable=True)
    # A local-first provider fetch binds immutable evidence to the exact durable
    # lease generation that staged it. The owner token is intentionally omitted:
    # a monotonically increasing fence is enough to prove that a later takeover
    # superseded this receipt without persisting a process-local secret.
    fetch_lease_key_sha256 = Column(String(_SHA256_LENGTH), nullable=True)
    fetch_lease_fence_token = Column(BigInteger, nullable=True)
    payload_sha256 = Column(String(_SHA256_LENGTH), nullable=False)
    request_json = Column(JSON, default=dict, nullable=False)
    payload_manifest_json = Column(JSON, default=dict, nullable=False)
    payload_uri = Column(Text, nullable=True)
    provenance_json = Column(JSON, default=dict, nullable=False)
    source_observed_at = Column(PITDateTime, nullable=True)
    source_published_at = Column(PITDateTime, nullable=True)
    retrieved_at = Column(PITDateTime, nullable=False)
    created_at = Column(PITDateTime, default=_utcnow, nullable=False)

    provider = relationship("DgProvider")
    observation_revisions = relationship(
        "MdObservationRevision",
        back_populates="source_snapshot",
        passive_deletes=True,
    )


class MdObservationRevision(Base):
    """One immutable normalized observation revision and its full provenance.

    This table is deliberately generic: ``fields_json`` can represent a bar,
    quote, option-chain record, position report, or reference-series value.
    The data kind belongs to the referenced series, avoiding a family of
    partially overlapping fact tables.
    """

    __tablename__ = "md_observation_revisions"
    __table_args__ = (
        UniqueConstraint(
            "revision_key_sha256",
            name="uq_md_observation_revision_key_sha256",
        ),
        UniqueConstraint(
            "series_id",
            "event_time",
            "revision_number",
            name="uq_md_observation_revision_series_event_number",
        ),
        CheckConstraint(
            f"length(fields_sha256) = {_SHA256_LENGTH}",
            name="ck_md_observation_revision_fields_sha256_length",
        ),
        CheckConstraint(
            f"length(revision_key_sha256) = {_SHA256_LENGTH}",
            name="ck_md_observation_revision_key_sha256_length",
        ),
        CheckConstraint(
            "revision_number >= 1",
            name="ck_md_observation_revision_number_positive",
        ),
        Index(
            "ix_md_observation_revision_series_event",
            "series_id",
            "event_time",
            "available_at",
        ),
        Index("ix_md_observation_revision_source", "source_snapshot_id"),
        Index("ix_md_observation_revision_available", "available_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    series_id = Column(
        String(36),
        ForeignKey(
            "md_data_series.id",
            name="fk_md_observation_revision_series_id_md_data_series",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    event_time = Column(PITDateTime, nullable=False)
    event_end = Column(PITDateTime, nullable=True)
    available_at = Column(PITDateTime, nullable=False)
    source_snapshot_id = Column(
        String(36),
        ForeignKey(
            "md_source_snapshots.id",
            name="fk_md_observation_revision_source_snapshot",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    quality_status = Column(String(32), nullable=False)
    quality_policy_version = Column(String(128), nullable=False)
    quality_details_json = Column(JSON, default=dict, nullable=False)
    fields_json = Column(JSON, default=dict, nullable=False)
    fields_sha256 = Column(String(_SHA256_LENGTH), nullable=False)
    revision_number = Column(Integer, nullable=False)
    revision_key_sha256 = Column(String(_SHA256_LENGTH), nullable=False)
    normalization_version = Column(String(128), nullable=False)
    source_record_key = Column(String(512), nullable=True)
    provenance_json = Column(JSON, default=dict, nullable=False)
    committed_at = Column(PITDateTime, nullable=False)
    created_at = Column(PITDateTime, default=_utcnow, nullable=False)

    series = relationship("MdDataSeries", back_populates="observation_revisions")
    source_snapshot = relationship("MdSourceSnapshot", back_populates="observation_revisions")


class MdCalendarSnapshot(Base):
    """One immutable version of a market calendar and its source evidence."""

    __tablename__ = "md_calendar_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "calendar_code",
            "calendar_version",
            name="uq_md_calendar_snapshot_code_version",
        ),
        UniqueConstraint("snapshot_sha256", name="uq_md_calendar_snapshot_sha256"),
        CheckConstraint(
            f"length(snapshot_sha256) = {_SHA256_LENGTH}",
            name="ck_md_calendar_snapshot_sha256_length",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_md_calendar_snapshot_effective_window",
        ),
        CheckConstraint(
            "source_registry_id IS NULL OR "
            "(length(source_registry_id) >= 1 AND length(source_registry_id) <= 128)",
            name="ck_md_calendar_snapshot_source_registry_id_length",
        ),
        CheckConstraint(
            "source_governance_state IS NULL OR "
            "source_governance_state IN ('VERIFIED', 'UNVERIFIED_COMPATIBILITY')",
            name="ck_md_calendar_snapshot_source_governance_state",
        ),
        CheckConstraint(
            "source_governance_descriptor_sha256 IS NULL OR "
            f"length(source_governance_descriptor_sha256) = {_SHA256_LENGTH}",
            name="ck_md_calsnap_src_gov_desc_sha256_len",
        ),
        CheckConstraint(
            "(source_registry_id IS NULL AND source_governance_state IS NULL AND "
            "source_governance_descriptor_sha256 IS NULL) OR "
            "(source_registry_id IS NOT NULL AND source_governance_state = 'VERIFIED' AND "
            "source_governance_descriptor_sha256 IS NOT NULL) OR "
            "(source_registry_id IS NOT NULL AND "
            "source_governance_state = 'UNVERIFIED_COMPATIBILITY' AND "
            "source_governance_descriptor_sha256 IS NULL)",
            name="ck_md_calendar_snapshot_source_governance_evidence_state",
        ),
        Index("ix_md_calendar_snapshot_code_version", "calendar_code", "calendar_version"),
        Index(
            "ix_md_calendar_snapshot_source_registry",
            "source_registry_id",
            "calendar_code",
            "calendar_version",
        ),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    calendar_code = Column(String(128), nullable=False)
    calendar_version = Column(String(128), nullable=False)
    timezone_name = Column(String(128), nullable=False)
    source_registry_id = Column(String(128), nullable=True)
    source_governance_state = Column(String(32), nullable=True)
    source_governance_descriptor_sha256 = Column(String(_SHA256_LENGTH), nullable=True)
    source_snapshot_id = Column(
        String(36),
        ForeignKey(
            "md_source_snapshots.id",
            name="fk_md_calendar_snapshot_source_snapshot_id_md_source_snapshots",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    snapshot_sha256 = Column(String(_SHA256_LENGTH), nullable=False)
    definition_json = Column(JSON, default=dict, nullable=False)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    created_at = Column(PITDateTime, default=_utcnow, nullable=False)

    source_snapshot = relationship("MdSourceSnapshot")
    events = relationship(
        "MdCalendarEvent", back_populates="calendar_snapshot", passive_deletes=True
    )


class MdCalendarEvent(Base):
    """One session/holiday/break fact inside an immutable calendar version."""

    __tablename__ = "md_calendar_events"
    __table_args__ = (
        UniqueConstraint("event_sha256", name="uq_md_calendar_event_sha256"),
        UniqueConstraint(
            "calendar_snapshot_id",
            "trading_date",
            "event_type",
            "session_code",
            name="uq_md_calendar_event_snapshot_date_type_session",
        ),
        UniqueConstraint(
            "calendar_snapshot_id",
            "coverage_event_key",
            name="uq_md_calendar_event_snapshot_coverage_key",
        ),
        CheckConstraint(
            f"length(event_sha256) = {_SHA256_LENGTH}",
            name="ck_md_calendar_event_sha256_length",
        ),
        CheckConstraint(
            "event_end IS NULL OR event_start IS NULL OR event_end >= event_start",
            name="ck_md_calendar_event_time_window",
        ),
        CheckConstraint(
            "coverage_event_key IS NULL OR "
            "(is_trading_day = true AND event_type = 'session' AND event_start IS NOT NULL)",
            name="ck_md_calendar_event_coverage_key",
        ),
        Index(
            "ix_md_calendar_event_snapshot_trading_date",
            "calendar_snapshot_id",
            "trading_date",
        ),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    calendar_snapshot_id = Column(
        String(36),
        ForeignKey(
            "md_calendar_snapshots.id",
            name="fk_md_calendar_event_snapshot_id_md_calendar_snapshots",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    trading_date = Column(Date, nullable=False)
    event_type = Column(String(64), nullable=False)
    session_code = Column(String(128), nullable=False)
    is_trading_day = Column(Boolean, nullable=False, default=False)
    event_start = Column(PITDateTime, nullable=True)
    event_end = Column(PITDateTime, nullable=True)
    coverage_event_key = Column(String(128), nullable=True)
    event_payload_json = Column(JSON, default=dict, nullable=False)
    event_sha256 = Column(String(_SHA256_LENGTH), nullable=False)
    created_at = Column(PITDateTime, default=_utcnow, nullable=False)

    calendar_snapshot = relationship("MdCalendarSnapshot", back_populates="events")


@event.listens_for(MdCalendarEvent, "before_insert")
def _sync_calendar_coverage_event_key(
    _mapper: Any,
    _connection: Any,
    target: MdCalendarEvent,
) -> None:
    """Materialize one portable unique slot for an explicit frequency grid event."""
    if not target.is_trading_day or target.event_type != "session":
        if _calendar_coverage_descriptor(target.event_payload_json) is not None:
            raise ValueError("only trading session events may declare calendar coverage")
        target.coverage_event_key = None
        return
    event_start = target.event_start
    if not isinstance(event_start, datetime) or event_start.tzinfo is None:
        raise ValueError("trading session event_start must be timezone-aware")
    descriptor = _calendar_coverage_descriptor(target.event_payload_json)
    if descriptor is None:
        raise ValueError("trading session events require an explicit coverage descriptor")
    target.coverage_event_key = calendar_coverage_event_key(
        event_start=event_start,
        data_kind=descriptor[0],
        frequency=descriptor[1],
    )


def _calendar_coverage_descriptor(payload: object) -> tuple[str, str] | None:
    """Read a strict optional coverage descriptor from persisted event payload."""
    if not isinstance(payload, dict):
        raise ValueError("calendar event payload must be an object")
    raw = payload.get(_CALENDAR_COVERAGE_PAYLOAD_KEY)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("calendar coverage descriptor must be an object")
    if set(raw) != {"data_kind", "frequency"}:
        raise ValueError("calendar coverage descriptor fields are invalid")
    data_kind = raw["data_kind"]
    frequency = raw["frequency"]
    if not isinstance(data_kind, str) or not data_kind.strip():
        raise ValueError("calendar coverage data_kind is invalid")
    if not isinstance(frequency, str) or not frequency.strip():
        raise ValueError("calendar coverage frequency is invalid")
    return data_kind.strip(), frequency.strip()


def calendar_coverage_event_key(
    *,
    event_start: datetime,
    data_kind: str,
    frequency: str,
) -> str:
    """Build the stable unique key for one explicitly declared coverage slot."""
    if event_start.tzinfo is None or event_start.utcoffset() is None:
        raise ValueError("calendar coverage event_start must be timezone-aware")
    if not data_kind or not frequency:
        raise ValueError("calendar coverage identity must not be blank")
    return f"{data_kind}:{frequency}@{event_start.astimezone(timezone.utc).isoformat()}"


def calendar_coverage_descriptor(payload: object) -> tuple[str, str] | None:
    """Expose strict descriptor parsing to readers that verify persisted calendar facts."""
    return _calendar_coverage_descriptor(payload)


class MdResearchDataBinding(Base):
    """Server-issued immutable market-data artifact binding for one research intent.

    The relational receipt is the authority for a backtest input artifact.  A
    caller may carry its opaque identifier and HMAC envelope through a
    workspace request, but it never supplies a filesystem path, provider, or
    canonical identity.  The artifact itself is retained outside the database;
    its relative path and content digest are therefore stored with the exact
    local-first/PIT evidence that produced it.
    """

    __tablename__ = "md_research_data_bindings"
    __table_args__ = (
        UniqueConstraint("binding_hash", name="uq_md_rdb_binding_hash"),
        CheckConstraint(
            f"length(binding_hash) = {_SHA256_LENGTH}",
            name="ck_md_rdb_binding_hash_len",
        ),
        CheckConstraint(
            f"length(manifest_sha256) = {_SHA256_LENGTH}",
            name="ck_md_rdb_manifest_hash_len",
        ),
        CheckConstraint(
            f"length(artifact_sha256) = {_SHA256_LENGTH}",
            name="ck_md_rdb_artifact_hash_len",
        ),
        CheckConstraint(
            "artifact_size_bytes > 0",
            name="ck_md_rdb_artifact_size_pos",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'REVOKED', 'INVALID')",
            name="ck_md_rdb_status",
        ),
        CheckConstraint(
            "visibility_sequence >= 0 AND identity_visibility_sequence >= 0",
            name="ck_md_rdb_visibility_seq",
        ),
        Index("ix_md_rdb_owner_intent", "user_id", "intent_id", "created_at"),
        Index("ix_md_rdb_status_created", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(
        String(36),
        ForeignKey("users.id", name="fk_md_rdb_user", ondelete="RESTRICT"),
        nullable=False,
    )
    intent_id = Column(String(128), nullable=False)
    binding_hash = Column(String(_SHA256_LENGTH), nullable=False)
    binding_schema_version = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="ACTIVE")
    artifact_relative_path = Column(String(512), nullable=False)
    artifact_sha256 = Column(String(_SHA256_LENGTH), nullable=False)
    artifact_size_bytes = Column(BigInteger, nullable=False)
    manifest_json = Column(JSON, default=dict, nullable=False)
    manifest_sha256 = Column(String(_SHA256_LENGTH), nullable=False)
    canonical_id = Column(exact_identifier_string(512), nullable=False)
    instrument_metadata_version = Column(String(128), nullable=False)
    dataset_code = Column(String(255), nullable=False)
    family_id = Column(String(128), nullable=False)
    family_contract_version = Column(String(64), nullable=False)
    data_kind = Column(String(64), nullable=False)
    frequency = Column(String(32), nullable=False)
    source_policy_id = Column(String(128), nullable=False)
    query_fingerprint = Column(String(_SHA256_LENGTH), nullable=False)
    knowledge_cutoff = Column(PITDateTime, nullable=False)
    identity_knowledge_cutoff = Column(PITDateTime, nullable=False)
    visibility_at = Column(PITDateTime, nullable=False)
    visibility_sequence = Column(BigInteger, nullable=False)
    identity_visibility_at = Column(PITDateTime, nullable=False)
    identity_visibility_sequence = Column(BigInteger, nullable=False)
    created_at = Column(PITDateTime, default=_utcnow, nullable=False)


class MdResearchDataBindingScope(Base):
    """The one research workspace that may consume a sealed binding.

    A binding is issued before the AI-research pipeline has created its first
    strategy unit.  This immutable server-side scope is therefore established
    by that trusted pipeline immediately after the first unit exists.  It
    prevents an owner from copying an otherwise valid token into a different
    workspace through the generic workspace API.
    """

    __tablename__ = "md_research_data_binding_scopes"
    __table_args__ = (
        CheckConstraint("length(intent_id) > 0", name="ck_md_rdb_scope_intent_nonempty"),
        Index("ix_md_rdb_scope_workspace", "workspace_id", "created_at"),
    )

    binding_id = Column(
        String(36),
        ForeignKey(
            "md_research_data_bindings.id",
            name="fk_md_rdb_scope_binding",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    user_id = Column(String(36), nullable=False)
    intent_id = Column(String(128), nullable=False)
    workspace_id = Column(String(36), nullable=False)
    created_at = Column(PITDateTime, default=_utcnow, nullable=False)


class MdResearchDataBindingConsumer(Base):
    """One server-attested research unit allowed to consume a binding.

    The row is not derived from browser ``data_config``.  Runtime resolution
    requires this exact binding/workspace/unit/intent tuple in addition to the
    HMAC token, so copying the token to another user-created unit fails
    closed.
    """

    __tablename__ = "md_research_data_binding_consumers"
    __table_args__ = (
        UniqueConstraint("binding_id", "unit_id", name="uq_md_rdb_consumer_binding_unit"),
        UniqueConstraint("unit_id", name="uq_md_rdb_consumer_unit"),
        CheckConstraint("length(intent_id) > 0", name="ck_md_rdb_consumer_intent_nonempty"),
        Index("ix_md_rdb_consumer_lookup", "binding_id", "workspace_id", "intent_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    binding_id = Column(
        String(36),
        ForeignKey(
            "md_research_data_bindings.id",
            name="fk_md_rdb_consumer_binding",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    user_id = Column(String(36), nullable=False)
    intent_id = Column(String(128), nullable=False)
    workspace_id = Column(String(36), nullable=False)
    unit_id = Column(String(36), nullable=False)
    created_at = Column(PITDateTime, default=_utcnow, nullable=False)


class MdResearchDataBindingRevocation(Base):
    """Append-only emergency invalidation for a sealed binding artifact."""

    __tablename__ = "md_research_data_binding_revocations"
    __table_args__ = (
        UniqueConstraint("binding_id", name="uq_md_rdb_revocation_binding"),
        CheckConstraint(
            "status IN ('REVOKED', 'INVALID')",
            name="ck_md_rdb_revocation_status",
        ),
        CheckConstraint("length(reason_code) > 0", name="ck_md_rdb_revocation_reason_nonempty"),
        Index("ix_md_rdb_revocation_created", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    binding_id = Column(
        String(36),
        ForeignKey(
            "md_research_data_bindings.id",
            name="fk_md_rdb_revocation_binding",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    actor_user_id = Column(String(36), nullable=True)
    status = Column(String(16), nullable=False)
    reason_code = Column(String(128), nullable=False)
    revoked_at = Column(PITDateTime, default=_utcnow, nullable=False)
    created_at = Column(PITDateTime, default=_utcnow, nullable=False)


def _deny_immutable_mutation(_mapper: Any, _connection: Any, target: Any) -> None:
    """Keep evidence entities append-only when accessed through the ORM."""
    raise ImmutableMarketDataRecordError(
        f"{target.__class__.__name__} records are immutable; append a new version instead"
    )


def _deny_research_binding_mutation(
    _mapper: Any,
    _connection: Any,
    target: MdResearchDataBinding,
) -> None:
    """Keep the binding receipt immutable; revocations use their own receipt."""
    state = inspect(target)
    changed = [attribute.key for attribute in state.attrs if attribute.history.has_changes()]
    if changed:
        _deny_immutable_mutation(_mapper, _connection, target)


for _immutable_model in (
    MdDataSeries,
    MdSourceSnapshot,
    MdObservationRevision,
    MdCalendarSnapshot,
    MdCalendarEvent,
    MdInstrumentIdentityRevision,
    MdPublication,
    MdResearchDataBindingScope,
    MdResearchDataBindingConsumer,
    MdResearchDataBindingRevocation,
):
    event.listen(_immutable_model, "before_update", _deny_immutable_mutation)
    event.listen(_immutable_model, "before_delete", _deny_immutable_mutation)

event.listen(MdResearchDataBinding, "before_update", _deny_research_binding_mutation)
event.listen(MdResearchDataBinding, "before_delete", _deny_immutable_mutation)
