"""Import explicit operator-approved market calendars."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_research import AssetDataSourceRegistry
from app.models.market_data_platform import (
    CALENDAR_SOURCE_GOVERNANCE_STATE_VERIFIED,
    MdCalendarEvent,
    MdCalendarImportLock,
    MdCalendarSnapshot,
)
from app.services.market_data.publication import (
    PUBLICATION_CALENDAR_SNAPSHOT,
    MarketDataPublicationError,
    MarketDataPublicationManager,
)

UTC = timezone.utc
MANIFEST_VERSION = "market-data-calendar-v1"
MAX_CALENDAR_MANIFEST_BYTES = 5 * 1024 * 1024
_CALENDAR_SOURCE_GOVERNANCE_VERSION = "market-data-calendar-source-governance-v1"
_APPROVED_LICENSES = frozenset(
    {
        "APPROVED",
        "LICENSED",
        "MARKET_DATA_APPROVED",
        "PUBLIC",
        "RESEARCH_APPROVED",
    }
)
_READABLE_REDISTRIBUTION_POLICIES = frozenset({"ALLOWED", "INTERNAL_ONLY", "NO_REDISTRIBUTION"})
_PROHIBITED_RETENTION_POLICIES = frozenset({"", "DENIED", "EXPIRED", "PROHIBITED", "UNKNOWN"})


class MarketDataCalendarImportError(ValueError):
    """Stable error code for invalid or conflicting calendar imports."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MarketDataCalendarCoverageManifest(_StrictModel):
    """One exact expected-event grid carried by a trading-session record."""

    data_kind: Literal["bars", "reference_series"]
    frequency: Literal["5min", "30min", "1h", "1d", "1w", "1mo"]

    @model_validator(mode="after")
    def validate_data_kind_frequency(self) -> MarketDataCalendarCoverageManifest:
        """Keep the first reference-series calendar grid to its reviewed daily shape."""
        if self.data_kind == "reference_series" and self.frequency != "1d":
            raise ValueError("reference_series calendar coverage requires frequency 1d")
        return self


class MarketDataCalendarEventManifest(_StrictModel):
    """One explicit event. Coverage sessions name their data kind and frequency."""

    trading_date: date
    event_type: str = Field(min_length=1, max_length=64)
    session_code: str = Field(min_length=1, max_length=128)
    is_trading_day: bool
    event_start: datetime | None = None
    event_end: datetime | None = None
    coverage: MarketDataCalendarCoverageManifest | None = None
    event_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type", "session_code")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("calendar event text must not be blank")
        return normalized

    @field_validator("event_start", "event_end")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("calendar event timestamp must include a timezone")
        return value.astimezone(UTC)

    @field_validator("event_payload")
    @classmethod
    def reject_reserved_coverage_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        if "coverage" in value:
            raise ValueError("event_payload may not override the coverage descriptor")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> MarketDataCalendarEventManifest:
        is_coverage_session = self.is_trading_day and self.event_type == "session"
        if is_coverage_session and self.event_start is None:
            raise ValueError("a trading session requires event_start")
        if is_coverage_session and self.coverage is None:
            raise ValueError("a trading session requires a coverage descriptor")
        if not is_coverage_session and self.coverage is not None:
            raise ValueError("only a trading session may declare coverage")
        if self.event_start is not None and self.event_end is not None:
            if self.event_end < self.event_start:
                raise ValueError("calendar event_end must not precede event_start")
        return self


class MarketDataCalendarManifest(_StrictModel):
    """A static calendar definition with evidence and a half-open coverage window."""

    manifest_version: Literal["market-data-calendar-v1"] = MANIFEST_VERSION
    approval_reference: str = Field(min_length=1, max_length=255)
    evidence_uri: str = Field(min_length=1, max_length=2048)
    evidence_content_hash: str = Field(min_length=64, max_length=64)
    source_registry_id: str = Field(min_length=1, max_length=128)
    calendar_code: str = Field(min_length=1, max_length=128)
    calendar_version: str = Field(min_length=1, max_length=128)
    timezone_name: str = Field(min_length=1, max_length=128)
    coverage_start_at: datetime
    coverage_end_at: datetime
    events: tuple[MarketDataCalendarEventManifest, ...] = ()

    @field_validator(
        "approval_reference",
        "evidence_uri",
        "source_registry_id",
        "calendar_code",
        "calendar_version",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("calendar manifest text must not be blank")
        return normalized

    @field_validator("evidence_content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("evidence_content_hash must be a SHA-256 hex digest")
        return normalized

    @field_validator("timezone_name")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        normalized = value.strip()
        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone_name must be an installed IANA timezone") from exc
        return normalized

    @field_validator("coverage_start_at", "coverage_end_at")
    @classmethod
    def normalize_coverage_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("calendar coverage timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_coverage_and_events(self) -> MarketDataCalendarManifest:
        if self.coverage_end_at <= self.coverage_start_at:
            raise ValueError("calendar coverage must be a non-empty half-open window")
        keys: set[tuple[date, str, str]] = set()
        coverage_event_starts: set[tuple[str, str, datetime]] = set()
        for event in self.events:
            key = (event.trading_date, event.event_type, event.session_code)
            if key in keys:
                raise ValueError("calendar manifest contains duplicate event identity")
            keys.add(key)
            for timestamp in (event.event_start, event.event_end):
                if timestamp is not None and not (
                    self.coverage_start_at <= timestamp < self.coverage_end_at
                ):
                    raise ValueError("calendar event timestamp is outside advertised coverage")
            if event.is_trading_day and event.event_type == "session":
                assert event.event_start is not None
                assert event.coverage is not None
                coverage_key = (
                    event.coverage.data_kind,
                    event.coverage.frequency,
                    event.event_start,
                )
                if coverage_key in coverage_event_starts:
                    raise ValueError("calendar manifest contains duplicate coverage event key")
                coverage_event_starts.add(coverage_key)
        return self


@dataclass(frozen=True, slots=True)
class MarketDataCalendarImportReport:
    """One safe aggregate result for the calendar import command."""

    dry_run: bool
    action: Literal["would_create", "created", "reused"]
    manifest_hash: str
    calendar_code: str
    calendar_version: str
    snapshot_id: str
    event_count: int
    publication_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "dry_run": self.dry_run,
            "action": self.action,
            "manifest_hash": self.manifest_hash,
            "calendar_code": self.calendar_code,
            "calendar_version": self.calendar_version,
            "snapshot_id": self.snapshot_id,
            "event_count": self.event_count,
        }


class MarketDataCalendarImporter:
    """Import a reviewed calendar through a post-commit visibility receipt."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._db = db
        self._clock = clock or _utc_now
        self._publications = MarketDataPublicationManager(db)

    async def import_payload(
        self,
        *,
        payload: Mapping[str, Any],
        dry_run: bool = True,
    ) -> MarketDataCalendarImportReport:
        if not isinstance(payload, Mapping):
            raise MarketDataCalendarImportError("CALENDAR_MANIFEST_INVALID")
        if not isinstance(dry_run, bool):
            raise TypeError("dry_run must be a bool")
        try:
            manifest = MarketDataCalendarManifest.model_validate(payload)
        except ValidationError as exc:
            raise MarketDataCalendarImportError("CALENDAR_MANIFEST_INVALID") from exc
        manifest_hash = _sha256(_canonical_json(manifest.model_dump(mode="json")))

        caller_owned_transaction = self._db.in_transaction()
        if not dry_run and caller_owned_transaction:
            # A visibility receipt can only be trusted if this importer knows
            # exactly when its entity transaction commits.  Reject mixed
            # caller-owned writes rather than publish an ambiguous cutoff.
            raise MarketDataCalendarImportError("CALENDAR_PUBLICATION_REQUIRES_CLEAN_SESSION")
        owns_root_transaction = not caller_owned_transaction
        await self._begin_root_transaction_if_needed()
        try:
            async with self._db.begin_nested():
                report = await self._persist_or_verify(manifest, manifest_hash, dry_run)
        except MarketDataCalendarImportError:
            # This importer opened the root transaction, so leave a semantic
            # rejection with no latent transaction for a later independent
            # import.  Caller-owned dry-run transactions are never rolled
            # back by this component.
            if owns_root_transaction and self._db.in_transaction():
                await self._db.rollback()
            raise
        except IntegrityError as exc:
            if owns_root_transaction and self._db.in_transaction():
                await self._db.rollback()
            raise MarketDataCalendarImportError("CALENDAR_IMPORT_CONFLICT") from exc
        except OperationalError as exc:
            if owns_root_transaction and self._db.in_transaction():
                await self._db.rollback()
            # SQLite's first-writer race can report a database-level lock
            # rather than a unique-constraint conflict.  Keep the condition
            # retryable and typed instead of leaking a driver exception.
            raise MarketDataCalendarImportError("CALENDAR_IMPORT_LOCK_UNAVAILABLE") from exc
        if dry_run:
            return report
        if report.publication_id is None:
            raise MarketDataCalendarImportError("CALENDAR_PUBLICATION_INTEGRITY")
        try:
            await self._db.commit()
            await self._publications.publish_staged((report.publication_id,))
        except (MarketDataPublicationError, IntegrityError) as exc:
            if self._db.in_transaction():
                await self._db.rollback()
            raise MarketDataCalendarImportError("CALENDAR_PUBLICATION_FAILED") from exc
        return report

    async def _begin_root_transaction_if_needed(self) -> None:
        if self._db.in_transaction():
            return
        await self._db.begin()
        connection = await self._db.connection()
        if connection.dialect.name == "sqlite":
            await connection.exec_driver_sql("BEGIN")

    async def _persist_or_verify(
        self,
        manifest: MarketDataCalendarManifest,
        manifest_hash: str,
        dry_run: bool,
    ) -> MarketDataCalendarImportReport:
        await self._lock_calendar_code(manifest.calendar_code)
        source_governance = await self._source_governance_for_manifest(
            manifest,
            manifest_hash=manifest_hash,
        )
        snapshots = list(
            (
                await self._db.execute(
                    select(MdCalendarSnapshot).where(
                        MdCalendarSnapshot.calendar_code == manifest.calendar_code
                    )
                )
            )
            .scalars()
            .all()
        )
        same_version = [
            snapshot
            for snapshot in snapshots
            if snapshot.calendar_version == manifest.calendar_version
        ]
        if len(same_version) > 1:
            raise MarketDataCalendarImportError("CALENDAR_IMPORT_INTEGRITY")
        if same_version:
            snapshot = same_version[0]
            if snapshot.snapshot_sha256 != manifest_hash:
                raise MarketDataCalendarImportError("CALENDAR_VERSION_CONFLICT")
            if (
                snapshot.source_registry_id != manifest.source_registry_id
                or snapshot.source_governance_state != CALENDAR_SOURCE_GOVERNANCE_STATE_VERIFIED
                or snapshot.source_governance_descriptor_sha256
                != source_governance["descriptor_hash"]
            ):
                raise MarketDataCalendarImportError("CALENDAR_SOURCE_GOVERNANCE_CONFLICT")
            try:
                publication = await self._publications.stage(
                    entity_type=PUBLICATION_CALENDAR_SNAPSHOT,
                    entity_id=snapshot.id,
                    entity_sha256=snapshot.snapshot_sha256,
                )
            except MarketDataPublicationError as exc:
                raise MarketDataCalendarImportError("CALENDAR_PUBLICATION_INTEGRITY") from exc
            return MarketDataCalendarImportReport(
                dry_run=dry_run,
                action="reused",
                manifest_hash=manifest_hash,
                calendar_code=manifest.calendar_code,
                calendar_version=manifest.calendar_version,
                snapshot_id=snapshot.id,
                event_count=len(manifest.events),
                publication_id=publication.id,
            )

        for snapshot in snapshots:
            existing_start, existing_end = _existing_window(snapshot)
            if _overlaps(
                manifest.coverage_start_at,
                manifest.coverage_end_at,
                existing_start,
                existing_end,
            ):
                raise MarketDataCalendarImportError("CALENDAR_COVERAGE_OVERLAP")

        snapshot = MdCalendarSnapshot(
            calendar_code=manifest.calendar_code,
            calendar_version=manifest.calendar_version,
            timezone_name=manifest.timezone_name,
            source_registry_id=manifest.source_registry_id,
            source_governance_state=CALENDAR_SOURCE_GOVERNANCE_STATE_VERIFIED,
            source_governance_descriptor_sha256=str(source_governance["descriptor_hash"]),
            snapshot_sha256=manifest_hash,
            definition_json={
                "schema_version": MANIFEST_VERSION,
                "approval_reference": manifest.approval_reference,
                "evidence_uri": manifest.evidence_uri,
                "evidence_content_hash": manifest.evidence_content_hash,
                "manifest_hash": manifest_hash,
                "source_governance": source_governance,
                "coverage_window": {
                    "start_at": manifest.coverage_start_at.isoformat(),
                    "end_at": manifest.coverage_end_at.isoformat(),
                },
                "event_time_contract": (
                    "trading sessions declare exact (data_kind, frequency, UTC event_start) "
                    "coverage keys"
                ),
            },
            effective_from=manifest.coverage_start_at.date(),
            effective_to=(manifest.coverage_end_at - timedelta(microseconds=1)).date(),
        )
        self._db.add(snapshot)
        await self._db.flush()
        try:
            publication = await self._publications.stage(
                entity_type=PUBLICATION_CALENDAR_SNAPSHOT,
                entity_id=snapshot.id,
                entity_sha256=snapshot.snapshot_sha256,
            )
        except MarketDataPublicationError as exc:
            raise MarketDataCalendarImportError("CALENDAR_PUBLICATION_INTEGRITY") from exc
        self._db.add_all(
            [
                MdCalendarEvent(
                    calendar_snapshot_id=snapshot.id,
                    trading_date=event.trading_date,
                    event_type=event.event_type,
                    session_code=event.session_code,
                    is_trading_day=event.is_trading_day,
                    event_start=event.event_start,
                    event_end=event.event_end,
                    event_payload_json={
                        **event.event_payload,
                        **(
                            {"coverage": event.coverage.model_dump()}
                            if event.coverage is not None
                            else {}
                        ),
                    },
                    event_sha256=_event_hash(manifest_hash, event),
                )
                for event in manifest.events
            ]
        )
        await self._db.flush()
        return MarketDataCalendarImportReport(
            dry_run=dry_run,
            action="would_create" if dry_run else "created",
            manifest_hash=manifest_hash,
            calendar_code=manifest.calendar_code,
            calendar_version=manifest.calendar_version,
            snapshot_id=snapshot.id,
            event_count=len(manifest.events),
            publication_id=publication.id,
        )

    async def _source_governance_for_manifest(
        self,
        manifest: MarketDataCalendarManifest,
        *,
        manifest_hash: str,
    ) -> dict[str, object]:
        """Freeze a registry-backed calendar source descriptor for one import.

        The calendar importer is an operator workflow, but it does not get to
        make a registry or licence decision by itself.  It re-reads the exact
        configured source and records a canonical digest of that decision;
        product reads then require the same source to appear in the current
        access grant before the calendar can prove coverage.
        """
        registry = await self._db.scalar(
            select(AssetDataSourceRegistry)
            .where(AssetDataSourceRegistry.source_id == manifest.source_registry_id)
            .execution_options(populate_existing=True)
        )
        if registry is None:
            raise MarketDataCalendarImportError("CALENDAR_SOURCE_REGISTRY_UNREGISTERED")
        try:
            source_id = _required_text(
                registry.source_id,
                field_name="calendar source_registry_id",
                maximum=128,
            )
            if source_id != manifest.source_registry_id:
                raise ValueError("source registry identity mismatch")
            enabled = registry.enabled
            if not isinstance(enabled, bool):
                raise ValueError("calendar source enabled state is invalid")
            asset_types = _registry_tokens(registry.asset_types, field_name="calendar asset_types")
            jurisdictions = _registry_tokens(
                registry.jurisdictions,
                field_name="calendar jurisdictions",
            )
            allowed_uses = _registry_tokens(
                registry.allowed_uses,
                field_name="calendar allowed_uses",
            )
            license_status = _registry_token(
                registry.license_status,
                field_name="calendar license_status",
                maximum=64,
            )
            retention_policy = _registry_token(
                registry.retention_policy,
                field_name="calendar retention_policy",
                maximum=64,
            )
            redistribution_policy = _registry_token(
                registry.redistribution_policy,
                field_name="calendar redistribution_policy",
                maximum=64,
            )
            effective_from = _stored_utc(
                registry.effective_from,
                field_name="calendar source effective_from",
            )
            effective_to = (
                _stored_utc(registry.effective_to, field_name="calendar source effective_to")
                if registry.effective_to is not None
                else None
            )
            retention_expires_at = (
                _stored_utc(
                    registry.retention_expires_at,
                    field_name="calendar source retention_expires_at",
                )
                if registry.retention_expires_at is not None
                else None
            )
            registry_updated_at = _stored_utc(
                registry.updated_at,
                field_name="calendar source registry_updated_at",
            )
            now = _trusted_now(self._clock)
        except (TypeError, ValueError) as exc:
            raise MarketDataCalendarImportError("CALENDAR_SOURCE_REGISTRY_INVALID") from exc
        if (
            not enabled
            or license_status not in _APPROVED_LICENSES
            or retention_policy in _PROHIBITED_RETENTION_POLICIES
            or redistribution_policy not in _READABLE_REDISTRIBUTION_POLICIES
            or not _jurisdiction_allows(jurisdictions, manifest.calendar_code)
            or effective_from > now
            or (effective_to is not None and effective_to < now)
            or (retention_expires_at is not None and retention_expires_at < now)
        ):
            raise MarketDataCalendarImportError("CALENDAR_SOURCE_REGISTRY_DENIED")
        payload: dict[str, object] = {
            "version": _CALENDAR_SOURCE_GOVERNANCE_VERSION,
            "source_registry_id": source_id,
            "registry_updated_at": registry_updated_at.isoformat(),
            "license_status": license_status,
            "asset_types": list(asset_types),
            "jurisdictions": list(jurisdictions),
            "allowed_uses": list(allowed_uses),
            "effective_from": effective_from.isoformat(),
            "effective_to": effective_to.isoformat() if effective_to is not None else None,
            "retention_policy": retention_policy,
            "retention_expires_at": (
                retention_expires_at.isoformat() if retention_expires_at is not None else None
            ),
            "redistribution_policy": redistribution_policy,
            "approval_reference": manifest.approval_reference,
            "evidence_uri": manifest.evidence_uri,
            "evidence_content_hash": manifest.evidence_content_hash,
            "calendar_manifest_hash": manifest_hash,
            "decision": "ALLOW",
        }
        return {**payload, "descriptor_hash": _sha256(_canonical_json(payload))}

    async def _lock_calendar_code(self, calendar_code: str) -> None:
        """Serialize overlap checks per calendar code on every supported database.

        PostgreSQL/MySQL use the row lock. SQLite serializes writers at the
        database level. A nested insert handles the first-writer race before
        the subsequent ``FOR UPDATE`` re-read establishes the shared sentinel.
        """
        try:
            lock = await self._db.scalar(
                select(MdCalendarImportLock)
                .where(MdCalendarImportLock.calendar_code == calendar_code)
                .with_for_update()
            )
            if lock is None:
                try:
                    async with self._db.begin_nested():
                        self._db.add(MdCalendarImportLock(calendar_code=calendar_code))
                        await self._db.flush()
                except IntegrityError:
                    # Another importer made the sentinel. Re-read it under a
                    # row lock before evaluating versions or coverage windows.
                    pass
                lock = await self._db.scalar(
                    select(MdCalendarImportLock)
                    .where(MdCalendarImportLock.calendar_code == calendar_code)
                    .with_for_update()
                )
        except OperationalError as exc:
            raise MarketDataCalendarImportError("CALENDAR_IMPORT_LOCK_UNAVAILABLE") from exc
        if lock is None:
            raise MarketDataCalendarImportError("CALENDAR_IMPORT_LOCK_FAILED")


def load_market_data_calendar_manifest(path: Path) -> dict[str, Any]:
    """Read one bounded JSON calendar manifest without exposing its content in errors."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise MarketDataCalendarImportError("CALENDAR_MANIFEST_UNREADABLE") from exc
    if size < 1 or size > MAX_CALENDAR_MANIFEST_BYTES:
        raise MarketDataCalendarImportError("CALENDAR_MANIFEST_SIZE_INVALID")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise MarketDataCalendarImportError("CALENDAR_MANIFEST_UNREADABLE") from exc
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarketDataCalendarImportError("CALENDAR_MANIFEST_INVALID_JSON") from exc
    if not isinstance(payload, Mapping):
        raise MarketDataCalendarImportError("CALENDAR_MANIFEST_INVALID")
    return dict(payload)


def _existing_window(snapshot: MdCalendarSnapshot) -> tuple[datetime, datetime]:
    definition = snapshot.definition_json
    if not isinstance(definition, Mapping):
        raise MarketDataCalendarImportError("CALENDAR_IMPORT_INTEGRITY")
    raw_window = definition.get("coverage_window")
    if not isinstance(raw_window, Mapping):
        raise MarketDataCalendarImportError("CALENDAR_IMPORT_INTEGRITY")
    try:
        start = _parse_timestamp(raw_window["start_at"])
        end = _parse_timestamp(raw_window["end_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MarketDataCalendarImportError("CALENDAR_IMPORT_INTEGRITY") from exc
    if end <= start:
        raise MarketDataCalendarImportError("CALENDAR_IMPORT_INTEGRITY")
    return start, end


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("calendar timestamp must be an ISO string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("calendar timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _utc_now() -> datetime:
    """Return the import-time clock used for registry validity checks."""
    return datetime.now(UTC)


def _trusted_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime):
        raise ValueError("calendar source clock invalid")
    return _stored_utc(value, field_name="calendar source clock")


def _stored_utc(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _required_text(value: object, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{field_name} is invalid")
    return normalized


def _registry_token(value: object, *, field_name: str, maximum: int) -> str:
    return _required_text(value, field_name=field_name, maximum=maximum).upper()


def _registry_tokens(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list")
    normalized = tuple(
        sorted({_registry_token(item, field_name=field_name, maximum=128) for item in value})
    )
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _jurisdiction_allows(jurisdictions: Sequence[str], market: str) -> bool:
    if "GLOBAL" in jurisdictions:
        return True
    normalized_market = market.upper()
    market_prefix = normalized_market.split("-", maxsplit=1)[0]
    return normalized_market in jurisdictions or market_prefix in jurisdictions


def _overlaps(
    left_start: datetime,
    left_end: datetime,
    right_start: datetime,
    right_end: datetime,
) -> bool:
    return left_start < right_end and right_start < left_end


def _event_hash(manifest_hash: str, event: MarketDataCalendarEventManifest) -> str:
    return _sha256(
        _canonical_json(
            {
                "manifest_hash": manifest_hash,
                "trading_date": event.trading_date.isoformat(),
                "event_type": event.event_type,
                "session_code": event.session_code,
                "is_trading_day": event.is_trading_day,
                "event_start": event.event_start.isoformat() if event.event_start else None,
                "event_end": event.event_end.isoformat() if event.event_end else None,
                "event_payload": event.event_payload,
            }
        )
    )


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise MarketDataCalendarImportError("CALENDAR_MANIFEST_INVALID") from exc


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
