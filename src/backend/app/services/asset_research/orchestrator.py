"""Transactional orchestration for asset-research tasks and immutable predictions."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError
from sqlalchemy import and_, desc, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import async_session_maker
from app.middleware.metrics import (
    record_asset_research_outcome,
    record_asset_research_prediction_reuse,
    record_asset_research_schedule_run,
    record_asset_research_source,
    record_asset_research_task,
)
from app.models.asset_research import (
    AssetAnalysisReport,
    AssetAnalysisTask,
    AssetInstrument,
    AssetModelRegistry,
    AssetPositionContextSnapshot,
    AssetScheduleManifest,
    AssetSignalOutcome,
    AssetSignalPrediction,
    AssetSignalRun,
    AssetSignalSchedule,
    AssetSourceSnapshot,
)
from app.schemas.asset_research import (
    ApprovedScheduleManifestCreateRequest,
    ApprovedScheduleManifestResponse,
    AssetAnalysisCreateRequest,
    AssetAnalysisResultResponse,
    AssetAnalysisTaskResponse,
    AssetSignalHistoryItem,
    AssetSignalHistoryResponse,
    AssetSignalOutcomeResponse,
    AssetSignalRunResponse,
    AssetSignalScheduleCreateRequest,
    AssetSignalScheduleResponse,
    AssetSignalScheduleUpdateRequest,
    CryptoProductIdentityDetails,
    FxIdentityDetails,
    InstrumentIdentity,
    PositionContext,
    PositionContextCreateRequest,
    PositionContextSnapshotResponse,
    RawAssetSnapshot,
    SignalSummaryResponse,
)
from app.services.asset_research.compliance import AssetResearchCompliancePolicy
from app.services.asset_research.concurrency import (
    AssetResearchSourceConcurrencyLimiter,
    get_asset_research_source_concurrency_limiter,
)
from app.services.asset_research.data import (
    DEFAULT_ASSET_RESEARCH_SOURCE_ID,
    StrictMarketDataAdapter,
    canonical_json_hash,
    sanitize_raw_snapshot,
)
from app.services.asset_research.decision import apply_publication_gate
from app.services.asset_research.outcomes import AssetOutcomeEvaluator
from app.services.asset_research.plugins.option.costs import parse_option_cost_snapshot
from app.services.asset_research.promotion import (
    has_complete_t2_metrics,
    has_matching_promotion_event,
    has_required_model_approvals,
    verified_promotion_scope,
)
from app.services.asset_research.redaction import redact_sensitive_data
from app.services.asset_research.registry import DEFAULT_ASSET_RESEARCH_REGISTRY
from app.services.asset_research.reports import build_report_payload, render_markdown
from app.services.asset_research.schedule_policy import (
    AssetSchedulePolicyError,
    next_schedule_fire,
    resolve_schedule_cutoff,
    validate_schedule_contract,
)
from app.services.asset_research.source_registry import AssetSourceRegistryPolicy
from app.services.asset_research.types import AssetResearchPluginRegistry
from app.services.market_instrument import MarketInstrumentService


class AssetResearchOrchestrationError(ValueError):
    """Stable task-creation error which API handlers map without leaking internals."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_SYSTEM_SCHEDULE_OWNER_SCOPES = frozenset({"PUBLIC_SHADOW", "ADMIN_EVAL"})


class AssetDataAdapter(Protocol):
    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot: ...


class AssetSourcePolicy(Protocol):
    """Freezes a server-owned source permission decision into a raw snapshot."""

    async def authorize(self, snapshot: RawAssetSnapshot) -> RawAssetSnapshot: ...


@dataclass(frozen=True, slots=True)
class _FrozenScheduleRun:
    """The immutable schedule contract consumed by one run or retry."""

    scheduled_fire_at: datetime
    cutoff_at: datetime
    schedule_version: int
    cutoff_policy_version: str
    schedule_config: dict[str, Any]
    horizon_code: str
    horizon_spec: dict[str, Any]
    cutoff_policy: str
    retry_of_run_id: str | None = None
    attempt_number: int = 1


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's naive DATETIME reads and aware production reads."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _task_payload(
    task: AssetAnalysisTask, report: AssetAnalysisReport | None = None
) -> AssetAnalysisTaskResponse:
    message_map = {
        "QUEUED": "多资产研究任务已创建",
        "RUNNING": "正在生成多资产研究报告",
        "SUCCEEDED": "多资产研究已完成",
        "FAILED": "多资产研究失败",
        "CANCELLED": "多资产研究已取消",
    }
    return AssetAnalysisTaskResponse(
        task_id=task.id,
        status=task.status,
        asset_type=task.asset_type,
        canonical_id=task.canonical_id,
        progress=task.progress,
        message=message_map.get(task.status),
        error_code=task.error_code,
        report_id=report.id if report else None,
        prediction_id=report.prediction_id if report else None,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


class AssetResearchOrchestrator:
    """Coordinates facts, policy, reports and audit rows without execution side effects."""

    # v2 freezes the first asset-specific feature/decision policy.  It must
    # not reuse v1 predictions, whose generic price rule and weekday-derived
    # horizons had different semantics.
    POLICY_VERSION = "asset-research-policy-v2"
    FEATURE_VERSION = "asset-research-features-v2"
    MODEL_VERSION = "asset-research-shadow-v2"
    CALIBRATION_VERSION = "not-promoted-v2"
    CAPABILITY_VERSION = "asset-research-capabilities-v1"
    COMPLIANCE_POLICY_VERSION = "asset-research-compliance-v1"
    CUTOFF_POLICY_VERSION = "asset-research-cutoff-v1"

    def __init__(
        self,
        db: AsyncSession,
        *,
        data_adapter: AssetDataAdapter | None = None,
        source_policy: AssetSourcePolicy | None = None,
        source_limiter: AssetResearchSourceConcurrencyLimiter | None = None,
        compliance_policy: AssetResearchCompliancePolicy | None = None,
        registry: AssetResearchPluginRegistry = DEFAULT_ASSET_RESEARCH_REGISTRY,
    ) -> None:
        self.db = db
        self.registry = registry
        if data_adapter is None:
            if get_settings().ASSET_RESEARCH_AKSHARE_PROVIDER_ENABLED:
                from app.services.asset_research.providers.akshare import (
                    AkShareCompositeProvider,
                )

                data_adapter = AkShareCompositeProvider()
            else:
                data_adapter = StrictMarketDataAdapter(
                    MarketInstrumentService(),
                    declared_source_id=DEFAULT_ASSET_RESEARCH_SOURCE_ID,
                )
        self.data_adapter = data_adapter
        self.source_policy = source_policy or AssetSourceRegistryPolicy(db)
        self.source_limiter = source_limiter or get_asset_research_source_concurrency_limiter()
        self.compliance_policy = (
            compliance_policy or AssetResearchCompliancePolicy.from_runtime_settings()
        )

    def _declared_adapter_source_ids(self) -> tuple[str, ...] | None:
        """Return a production adapter's pre-authorized sources, if declared."""
        source_ids = getattr(self.data_adapter, "declared_source_ids", None)
        if source_ids is None:
            return None
        if isinstance(source_ids, str):
            source_ids = (source_ids,)
        try:
            normalized = tuple(
                str(source_id).strip() for source_id in source_ids if str(source_id).strip()
            )
        except TypeError:
            return None
        return normalized

    def _collection_source_bucket(self) -> str | None:
        """Select a server-declared source key for the in-process limiter.

        A source-specific adapter with exactly one declaration receives that
        provider's own bucket.  Adapters with no declaration or a dynamic
        collection path share the conservative undeclared bucket; a provider
        response must never choose its own concurrency key.
        """
        source_ids = self._declared_adapter_source_ids()
        if source_ids is None:
            return None
        unique_source_ids = tuple(dict.fromkeys(source_ids))
        return unique_source_ids[0] if len(unique_source_ids) == 1 else None

    async def require_research_capability(self, asset_type: str) -> None:
        """Fail closed unless the server registry currently permits this asset type.

        This deliberately reads the registry rather than trusting an injected
        data adapter or a client-supplied provider manifest.  It protects every
        task/schedule creation path before it can enqueue collection work.
        Snapshot authorization still runs later to freeze the exact source and
        effective-time decision used by a completed research run.
        """
        enabled_asset_types = await AssetSourceRegistryPolicy(self.db).enabled_asset_types(
            source_ids=self._declared_adapter_source_ids()
        )
        if asset_type not in enabled_asset_types:
            raise AssetResearchOrchestrationError("SOURCE_CAPABILITY_UNAVAILABLE")

    async def _collect_authorized_snapshot(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        """Collect and authorize one source snapshot with safe source observability."""
        started_at = perf_counter()
        requested_cutoff_at = _as_utc(cutoff_at)
        try:
            async with self.source_limiter.acquire(self._collection_source_bucket()):
                snapshot = await self.data_adapter.collect(identity, cutoff_at=cutoff_at)
            if not identity.matches_frozen_identity(snapshot.identity):
                raise AssetResearchOrchestrationError("SNAPSHOT_IDENTITY_MISMATCH")
            if _as_utc(snapshot.cutoff_at) != requested_cutoff_at:
                raise AssetResearchOrchestrationError("SNAPSHOT_CUTOFF_MISMATCH")
            snapshot = await self.source_policy.authorize(snapshot)
            if not identity.matches_frozen_identity(snapshot.identity):
                raise AssetResearchOrchestrationError("SNAPSHOT_IDENTITY_MISMATCH")
            if _as_utc(snapshot.cutoff_at) != requested_cutoff_at:
                raise AssetResearchOrchestrationError("SNAPSHOT_CUTOFF_MISMATCH")
            snapshot = sanitize_raw_snapshot(snapshot)
        except Exception:
            record_asset_research_source(
                source_id="UNREGISTERED",
                result="FAILED",
                duration_seconds=perf_counter() - started_at,
            )
            raise
        registry_status = str(snapshot.source_manifest.get("source_registry_status") or "")
        result = "AUTHORIZED" if registry_status == "ACTIVE" else registry_status
        source_id = (
            str(snapshot.source_manifest.get("source_id") or "UNREGISTERED")
            if registry_status in {"ACTIVE", "BLOCKED"}
            else "UNREGISTERED"
        )
        record_asset_research_source(
            source_id=source_id,
            result=result,
            duration_seconds=perf_counter() - started_at,
            registered=registry_status in {"ACTIVE", "BLOCKED"},
        )
        return snapshot

    @staticmethod
    def _task_duration_seconds(task: AssetAnalysisTask) -> float | None:
        """Return a non-negative completed task duration across SQLite and production dates."""
        if task.started_at is None or task.completed_at is None:
            return None
        return max(0.0, (_as_utc(task.completed_at) - _as_utc(task.started_at)).total_seconds())

    async def persist_identity(
        self,
        identity: InstrumentIdentity,
        *,
        valid_from: datetime | None = None,
    ) -> AssetInstrument:
        """Persist one immutable identity version and reuse an existing exact version.

        ``valid_from`` is a test-only hook for historical point-in-time
        fixtures.  Production callers should let the orchestrator stamp the
        current UTC time so the identity cannot be backdated accidentally.
        """
        existing = (
            await self.db.execute(
                select(AssetInstrument).where(
                    AssetInstrument.canonical_id == identity.canonical_id,
                    AssetInstrument.metadata_version == identity.metadata_version,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        record = AssetInstrument(
            canonical_id=identity.canonical_id,
            asset_type=identity.asset_type,
            identity_level=identity.identity_level,
            venue=identity.venue,
            currency=identity.currency,
            product_type=identity.product_type,
            identity_json=identity.model_dump(mode="json"),
            metadata_version=identity.metadata_version,
            lifecycle_status="ACTIVE",
            valid_from=_as_utc(valid_from) if valid_from is not None else _now(),
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def create_position_context(
        self,
        *,
        user_id: str,
        request: PositionContextCreateRequest,
        idempotency_key: str | None = None,
    ) -> AssetPositionContextSnapshot:
        """Persist an immutable, explicitly user-declared research context.

        This is deliberately not an account connection or a broker-position
        assertion.  It only makes a user's declared context reproducible for a
        later research decision, subject to owner, identity and expiry checks.
        """
        instrument = await self._instrument_for_canonical_id(request.canonical_id)
        self._validate_position_context_request(request)
        request_hash = canonical_json_hash(request.model_dump(mode="json"))
        normalized_key = self._normalized_idempotency_key(idempotency_key)
        if normalized_key is not None:
            existing = await self._position_context_by_idempotency_key(
                user_id=user_id,
                idempotency_key=normalized_key,
            )
            if existing is not None:
                if existing.idempotency_request_hash != request_hash:
                    raise AssetResearchOrchestrationError("IDEMPOTENCY_CONFLICT")
                return existing

        available_at = _now()
        source_manifest = {"account_connected": False, "source": "USER_DECLARED"}
        content = {
            "owner_scope": "USER",
            "instrument_id": instrument.id,
            "canonical_id": instrument.canonical_id,
            "identity_version": instrument.metadata_version,
            "position_context": request.position_context,
            "long_quantity": request.long_quantity,
            "short_quantity": request.short_quantity,
            "as_of_at": request.as_of_at,
            "expires_at": request.expires_at,
            "source_manifest": source_manifest,
        }
        snapshot = AssetPositionContextSnapshot(
            owner_scope="USER",
            user_id=user_id,
            instrument_id=instrument.id,
            asset_type=instrument.asset_type,
            canonical_id=instrument.canonical_id,
            identity_version=instrument.metadata_version,
            position_context=request.position_context,
            long_quantity=request.long_quantity,
            short_quantity=request.short_quantity,
            as_of_at=request.as_of_at,
            available_at=available_at,
            expires_at=request.expires_at,
            source_type="USER_DECLARED",
            source_manifest_json=source_manifest,
            content_hash=canonical_json_hash(content),
            idempotency_key=normalized_key,
            idempotency_request_hash=request_hash if normalized_key is not None else None,
        )
        self.db.add(snapshot)
        await self.db.flush()
        return snapshot

    async def get_position_context(
        self, *, user_id: str, snapshot_id: str
    ) -> PositionContextSnapshotResponse | None:
        """Return only metadata for the caller's own declared context."""
        snapshot = (
            await self.db.execute(
                select(AssetPositionContextSnapshot).where(
                    AssetPositionContextSnapshot.id == snapshot_id,
                    AssetPositionContextSnapshot.owner_scope == "USER",
                    AssetPositionContextSnapshot.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if snapshot is None:
            return None
        return PositionContextSnapshotResponse(
            snapshot_id=snapshot.id,
            asset_type=snapshot.asset_type,
            canonical_id=snapshot.canonical_id,
            identity_version=snapshot.identity_version,
            position_context=snapshot.position_context,
            long_quantity=snapshot.long_quantity,
            short_quantity=snapshot.short_quantity,
            as_of_at=snapshot.as_of_at,
            available_at=snapshot.available_at,
            expires_at=snapshot.expires_at,
            source_type=snapshot.source_type,
            account_connected=False,
            content_hash=snapshot.content_hash,
        )

    async def create_schedule(
        self,
        *,
        user_id: str,
        request: AssetSignalScheduleCreateRequest,
        idempotency_key: str | None = None,
    ) -> AssetSignalSchedule:
        """Create one single-asset, research-only shadow schedule."""
        self._validate_schedule_request(request)
        normalized_key = self._normalized_idempotency_key(idempotency_key)
        request_hash = canonical_json_hash(request.model_dump(mode="json"))
        if normalized_key is not None:
            existing = await self._schedule_by_idempotency_key(
                user_id=user_id,
                idempotency_key=normalized_key,
            )
            if existing is not None:
                if existing.idempotency_request_hash != request_hash:
                    raise AssetResearchOrchestrationError("IDEMPOTENCY_CONFLICT")
                return existing
        await self.require_research_capability(request.asset_type)
        instrument = await self._current_instrument(
            canonical_id=request.canonical_id,
            asset_type=request.asset_type,
        )
        schedule = AssetSignalSchedule(
            owner_scope="USER",
            user_id=user_id,
            instrument_id=instrument.id,
            asset_type=request.asset_type,
            canonical_id=instrument.canonical_id,
            identity_version=instrument.metadata_version,
            horizon_code=request.horizon_code,
            horizon_spec_json=request.horizon_spec.model_dump(mode="json"),
            position_context="UNKNOWN",
            position_context_snapshot_id=None,
            cron_expression=request.cron_expression,
            timezone=request.timezone,
            cutoff_policy=request.cutoff_policy,
            cutoff_policy_version=self.CUTOFF_POLICY_VERSION,
            misfire_policy=request.misfire_policy,
            schedule_version=1,
            enabled=True,
            next_run_at=next_schedule_fire(cutoff_policy=request.cutoff_policy, after=_now()),
            idempotency_key=normalized_key,
            idempotency_request_hash=request_hash if normalized_key is not None else None,
        )
        self.db.add(schedule)
        await self.db.flush()
        return schedule

    async def create_approved_schedule_manifest(
        self,
        *,
        actor_id: str,
        request: ApprovedScheduleManifestCreateRequest,
        idempotency_key: str | None = None,
    ) -> AssetScheduleManifest:
        """Expand an approved static set into exact system-owned schedules.

        This is deliberately a configuration-time operation.  Every entry is
        individually validated against the currently approved source
        capability and exact master-data identity before any manifest or
        schedule row is written.  It never discovers a universe at runtime.
        """
        request_hash = canonical_json_hash(request.model_dump(mode="json"))
        normalized_key = self._normalized_idempotency_key(idempotency_key)
        if normalized_key is not None:
            existing_for_key = (
                await self.db.execute(
                    select(AssetScheduleManifest).where(
                        AssetScheduleManifest.approved_by == actor_id,
                        AssetScheduleManifest.idempotency_key == normalized_key,
                    )
                )
            ).scalar_one_or_none()
            if existing_for_key is not None:
                if existing_for_key.idempotency_request_hash != request_hash:
                    raise AssetResearchOrchestrationError("IDEMPOTENCY_CONFLICT")
                return existing_for_key
        existing = (
            await self.db.execute(
                select(AssetScheduleManifest).where(
                    AssetScheduleManifest.manifest_key == request.manifest_key,
                    AssetScheduleManifest.manifest_version == request.manifest_version,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.content_hash != request_hash:
                raise AssetResearchOrchestrationError("SCHEDULE_MANIFEST_VERSION_CONFLICT")
            return existing

        active_manifest = (
            await self.db.execute(
                select(AssetScheduleManifest).where(
                    AssetScheduleManifest.manifest_key == request.manifest_key,
                    AssetScheduleManifest.status == "ACTIVE",
                )
            )
        ).scalar_one_or_none()
        if active_manifest is not None:
            raise AssetResearchOrchestrationError("SCHEDULE_MANIFEST_ACTIVE_EXISTS")

        resolved_entries: list[
            tuple[str, AssetSignalScheduleCreateRequest, AssetInstrument, str]
        ] = []
        target_keys: set[str] = set()
        for entry in request.entries:
            self._validate_schedule_request(entry.schedule)
            await self.require_research_capability(entry.schedule.asset_type)
            instrument = await self._current_instrument(
                canonical_id=entry.schedule.canonical_id,
                asset_type=entry.schedule.asset_type,
            )
            target_key = self._system_schedule_target_key(
                owner_scope=request.owner_scope,
                request=entry.schedule,
                instrument=instrument,
            )
            if target_key in target_keys:
                raise AssetResearchOrchestrationError("SCHEDULE_MANIFEST_TARGET_DUPLICATE")
            target_keys.add(target_key)
            resolved_entries.append((entry.entry_key, entry.schedule, instrument, target_key))

        existing_target = (
            await self.db.execute(
                select(AssetSignalSchedule.id).where(
                    AssetSignalSchedule.system_target_key.in_(target_keys)
                )
            )
        ).first()
        if existing_target is not None:
            raise AssetResearchOrchestrationError("SCHEDULE_MANIFEST_TARGET_ACTIVE")

        manifest = AssetScheduleManifest(
            manifest_key=request.manifest_key,
            manifest_version=request.manifest_version,
            owner_scope=request.owner_scope,
            approval_reference=request.approval_reference,
            evidence_uri=request.evidence_uri,
            evidence_content_hash=request.evidence_content_hash,
            content_hash=request_hash,
            approved_by=actor_id,
            approved_at=_now(),
            status="ACTIVE",
            idempotency_key=normalized_key,
            idempotency_request_hash=request_hash if normalized_key is not None else None,
            retirement_reason_codes_json=[],
        )
        self.db.add(manifest)
        await self.db.flush()
        for entry_key, schedule_request, instrument, target_key in resolved_entries:
            self.db.add(
                AssetSignalSchedule(
                    owner_scope=request.owner_scope,
                    user_id=None,
                    approved_manifest_id=manifest.id,
                    manifest_entry_key=entry_key,
                    manifest_content_hash=manifest.content_hash,
                    system_target_key=target_key,
                    instrument_id=instrument.id,
                    asset_type=schedule_request.asset_type,
                    canonical_id=instrument.canonical_id,
                    identity_version=instrument.metadata_version,
                    horizon_code=schedule_request.horizon_code,
                    horizon_spec_json=schedule_request.horizon_spec.model_dump(mode="json"),
                    position_context="UNKNOWN",
                    position_context_snapshot_id=None,
                    cron_expression=schedule_request.cron_expression,
                    timezone=schedule_request.timezone,
                    cutoff_policy=schedule_request.cutoff_policy,
                    cutoff_policy_version=self.CUTOFF_POLICY_VERSION,
                    misfire_policy=schedule_request.misfire_policy,
                    schedule_version=1,
                    enabled=True,
                    next_run_at=next_schedule_fire(
                        cutoff_policy=schedule_request.cutoff_policy,
                        after=_now(),
                    ),
                )
            )
        await self.db.flush()
        return manifest

    async def retire_approved_schedule_manifest(
        self,
        *,
        actor_id: str,
        manifest_id: str,
        reason_codes: list[str],
    ) -> AssetScheduleManifest:
        """Retire a manifest without rewriting its historical schedules or runs."""
        manifest = await self.db.get(AssetScheduleManifest, manifest_id)
        if manifest is None:
            raise AssetResearchOrchestrationError("SCHEDULE_MANIFEST_NOT_FOUND")
        if manifest.status == "RETIRED":
            return manifest
        schedules = list(
            (
                await self.db.execute(
                    select(AssetSignalSchedule).where(
                        AssetSignalSchedule.approved_manifest_id == manifest.id
                    )
                )
            ).scalars()
        )
        if any(schedule.lease_token is not None for schedule in schedules):
            raise AssetResearchOrchestrationError("SCHEDULE_MANIFEST_LEASE_ACTIVE")
        if any(schedule.retry_of_run_id is not None for schedule in schedules):
            raise AssetResearchOrchestrationError("SCHEDULE_MANIFEST_RETRY_PENDING")

        retired_at = _now()
        for schedule in schedules:
            schedule.enabled = False
            schedule.next_run_at = None
            schedule.system_target_key = None
            schedule.schedule_version += 1
        manifest.status = "RETIRED"
        manifest.retired_by = actor_id
        manifest.retired_at = retired_at
        manifest.retirement_reason_codes_json = list(reason_codes)
        await self.db.flush()
        return manifest

    async def get_approved_schedule_manifest(
        self, *, manifest_id: str
    ) -> AssetScheduleManifest | None:
        """Load one immutable control-plane record for an admin-only endpoint."""
        return await self.db.get(AssetScheduleManifest, manifest_id)

    async def list_approved_schedule_manifests(
        self, *, limit: int = 100
    ) -> list[AssetScheduleManifest]:
        """List auditable manifest versions, never reconstructing a universe."""
        return list(
            (
                await self.db.execute(
                    select(AssetScheduleManifest)
                    .order_by(
                        desc(AssetScheduleManifest.approved_at),
                        desc(AssetScheduleManifest.id),
                    )
                    .limit(max(1, min(limit, 100)))
                )
            ).scalars()
        )

    async def schedule_manifest_payload(
        self, manifest: AssetScheduleManifest
    ) -> ApprovedScheduleManifestResponse:
        """Serialize control-plane metadata and its explicitly persisted schedules."""
        schedules = list(
            (
                await self.db.execute(
                    select(AssetSignalSchedule)
                    .where(AssetSignalSchedule.approved_manifest_id == manifest.id)
                    .order_by(AssetSignalSchedule.manifest_entry_key, AssetSignalSchedule.id)
                )
            ).scalars()
        )
        return ApprovedScheduleManifestResponse(
            manifest_id=manifest.id,
            manifest_key=manifest.manifest_key,
            manifest_version=manifest.manifest_version,
            owner_scope=manifest.owner_scope,
            approval_reference=manifest.approval_reference,
            evidence_uri=manifest.evidence_uri,
            evidence_content_hash=manifest.evidence_content_hash,
            content_hash=manifest.content_hash,
            approved_by=manifest.approved_by,
            approved_at=manifest.approved_at,
            status=manifest.status,
            retired_by=manifest.retired_by,
            retired_at=manifest.retired_at,
            retirement_reason_codes=list(manifest.retirement_reason_codes_json or []),
            schedules=[self.schedule_payload(schedule) for schedule in schedules],
        )

    async def update_schedule(
        self,
        *,
        user_id: str,
        schedule_id: str,
        request: AssetSignalScheduleUpdateRequest,
    ) -> AssetSignalSchedule:
        """Version a future schedule config without rewriting any existing run."""
        schedule = await self._owned_schedule(user_id=user_id, schedule_id=schedule_id)
        if schedule is None:
            raise AssetResearchOrchestrationError("SCHEDULE_NOT_FOUND")
        if schedule.lease_expires_at is not None and _as_utc(schedule.lease_expires_at) > _now():
            raise AssetResearchOrchestrationError("SCHEDULE_LEASE_ACTIVE")
        if schedule.retry_of_run_id is not None:
            raise AssetResearchOrchestrationError("SCHEDULE_RETRY_PENDING")
        changes = request.model_dump(exclude_none=True, mode="json")
        if "cron_expression" in changes:
            self._validate_cron(str(changes["cron_expression"]))
        if "timezone" in changes:
            self._validate_timezone(str(changes["timezone"]))
        if {"cron_expression", "timezone", "cutoff_policy"} & changes.keys():
            self._validate_schedule_contract_values(
                asset_type=schedule.asset_type,
                cron_expression=str(changes.get("cron_expression", schedule.cron_expression)),
                timezone_name=str(changes.get("timezone", schedule.timezone)),
                cutoff_policy=str(changes.get("cutoff_policy", schedule.cutoff_policy)),
            )
        if changes.get("enabled") is True:
            await self.require_research_capability(schedule.asset_type)
            current_instrument = await self._current_instrument(
                canonical_id=schedule.canonical_id,
                asset_type=schedule.asset_type,
            )
            if (
                current_instrument.id != schedule.instrument_id
                or current_instrument.metadata_version != schedule.identity_version
            ):
                raise AssetResearchOrchestrationError("INSTRUMENT_VERSION_STALE")
        for name, value in changes.items():
            if name == "horizon_spec":
                schedule.horizon_spec_json = value
            else:
                setattr(schedule, name, value)
        schedule.schedule_version += 1
        schedule.cutoff_policy_version = self.CUTOFF_POLICY_VERSION
        schedule.next_run_at = (
            next_schedule_fire(cutoff_policy=schedule.cutoff_policy, after=_now())
            if schedule.enabled
            else None
        )
        await self.db.flush()
        return schedule

    async def list_schedules(self, *, user_id: str, limit: int = 100) -> list[AssetSignalSchedule]:
        """List only schedules owned by the authenticated user."""
        return list(
            (
                await self.db.execute(
                    select(AssetSignalSchedule)
                    .where(
                        AssetSignalSchedule.owner_scope == "USER",
                        AssetSignalSchedule.user_id == user_id,
                    )
                    .order_by(desc(AssetSignalSchedule.updated_at), desc(AssetSignalSchedule.id))
                    .limit(max(1, min(limit, 100)))
                )
            ).scalars()
        )

    @staticmethod
    def schedule_payload(schedule: AssetSignalSchedule) -> AssetSignalScheduleResponse:
        """Serialize a frozen single-asset schedule without an account context."""
        return AssetSignalScheduleResponse(
            schedule_id=schedule.id,
            asset_type=schedule.asset_type,
            canonical_id=schedule.canonical_id,
            identity_version=schedule.identity_version,
            horizon_code=schedule.horizon_code,
            horizon_spec=schedule.horizon_spec_json,
            position_context="UNKNOWN",
            cron_expression=schedule.cron_expression,
            timezone=schedule.timezone,
            cutoff_policy=schedule.cutoff_policy,
            cutoff_policy_version=schedule.cutoff_policy_version,
            misfire_policy=schedule.misfire_policy,
            schedule_version=schedule.schedule_version,
            enabled=schedule.enabled,
            next_run_at=schedule.next_run_at,
            created_at=schedule.created_at,
            updated_at=schedule.updated_at,
        )

    @staticmethod
    def run_payload(run: AssetSignalRun) -> AssetSignalRunResponse:
        """Serialize a task- or schedule-sourced audit run without candidate data."""
        return AssetSignalRunResponse(
            run_id=run.id,
            status=run.status,
            schedule_id=run.schedule_id,
            task_id=run.task_id,
            asset_type=run.asset_type,
            as_of_at=run.as_of_at,
            cutoff_at=run.cutoff_at,
            counts=run.counts_json or {},
            created_at=run.created_at,
            completed_at=run.completed_at,
        )

    async def run_schedule(
        self,
        *,
        user_id: str,
        schedule_id: str,
        scheduled_fire_at: datetime | None = None,
        run_type: str = "MANUAL_SCHEDULE",
    ) -> AssetSignalRun:
        """Run one frozen schedule in shadow mode without creating a task/report."""
        schedule = await self._owned_schedule(user_id=user_id, schedule_id=schedule_id)
        if schedule is None:
            raise AssetResearchOrchestrationError("SCHEDULE_NOT_FOUND")
        return await self._run_schedule_record(
            schedule=schedule,
            scheduled_fire_at=scheduled_fire_at,
            run_type=run_type,
        )

    async def run_claimed_schedule(
        self,
        *,
        schedule_id: str,
        scheduled_fire_at: datetime | None = None,
        run_type: str = "SCHEDULED",
    ) -> AssetSignalRun:
        """Run a database-leased schedule without impersonating a user.

        This is intentionally an internal worker entry point.  Public HTTP
        callers remain restricted to their own ``USER`` schedules through
        :meth:`run_schedule`; a worker can also consume a pre-approved
        ``PUBLIC_SHADOW`` or ``ADMIN_EVAL`` static schedule with a null user.
        """
        schedule = await self.db.get(AssetSignalSchedule, schedule_id)
        if schedule is None:
            raise AssetResearchOrchestrationError("SCHEDULE_NOT_FOUND")
        self._validate_schedule_owner(schedule)
        await self._validate_system_schedule_manifest(schedule)
        return await self._run_schedule_record(
            schedule=schedule,
            scheduled_fire_at=scheduled_fire_at,
            run_type=run_type,
        )

    async def _run_schedule_record(
        self,
        *,
        schedule: AssetSignalSchedule,
        scheduled_fire_at: datetime | None,
        run_type: str,
    ) -> AssetSignalRun:
        """Run an already-authorized schedule record with its own owner scope."""
        await self.require_research_capability(schedule.asset_type)
        frozen = self._freeze_schedule_run(schedule, scheduled_fire_at=scheduled_fire_at)
        return await self._run_frozen_schedule(
            schedule=schedule,
            frozen=frozen,
            run_type=run_type,
        )

    async def retry_schedule_run(
        self,
        *,
        user_id: str,
        schedule_id: str,
        failed_run_id: str,
    ) -> AssetSignalRun:
        """Create a new auditable retry from a failed run's frozen facts only.

        This is intentionally a worker-only operation.  It does not recompute
        the cutoff from the current time and it never overwrites the failed
        audit row that caused the retry.
        """
        schedule = await self._owned_schedule(user_id=user_id, schedule_id=schedule_id)
        if schedule is None:
            raise AssetResearchOrchestrationError("SCHEDULE_NOT_FOUND")
        return await self._retry_schedule_record(
            schedule=schedule,
            failed_run_id=failed_run_id,
        )

    async def retry_claimed_schedule(
        self,
        *,
        schedule_id: str,
        failed_run_id: str,
    ) -> AssetSignalRun:
        """Replay a leased schedule's frozen failed run under the original owner scope."""
        schedule = await self.db.get(AssetSignalSchedule, schedule_id)
        if schedule is None:
            raise AssetResearchOrchestrationError("SCHEDULE_NOT_FOUND")
        self._validate_schedule_owner(schedule)
        await self._validate_system_schedule_manifest(schedule)
        return await self._retry_schedule_record(
            schedule=schedule,
            failed_run_id=failed_run_id,
        )

    async def _retry_schedule_record(
        self,
        *,
        schedule: AssetSignalSchedule,
        failed_run_id: str,
    ) -> AssetSignalRun:
        """Replay only an immutable failure record already bound to this schedule."""
        await self.require_research_capability(schedule.asset_type)
        failed_run = await self.db.get(AssetSignalRun, failed_run_id)
        if (
            failed_run is None
            or failed_run.schedule_id != schedule.id
            or failed_run.owner_scope != schedule.owner_scope
            or failed_run.user_id != schedule.user_id
            or failed_run.status != "FAILED"
        ):
            raise AssetResearchOrchestrationError("SCHEDULE_RETRY_INVALID")
        frozen = self._frozen_schedule_retry(failed_run)
        self._validate_frozen_system_manifest(schedule=schedule, frozen=frozen)
        return await self._run_frozen_schedule(
            schedule=schedule,
            frozen=frozen,
            run_type="SCHEDULE_RETRY",
        )

    def _freeze_schedule_run(
        self,
        schedule: AssetSignalSchedule,
        *,
        scheduled_fire_at: datetime | None,
    ) -> _FrozenScheduleRun:
        """Freeze current schedule fields before any collection begins."""
        fire_at = scheduled_fire_at or _now()
        if fire_at.tzinfo is None:
            raise AssetResearchOrchestrationError("SCHEDULE_TIME_INVALID")
        fire_at = _as_utc(fire_at)
        try:
            cutoff_at = resolve_schedule_cutoff(
                schedule.asset_type, schedule.cutoff_policy, fire_at
            )
        except AssetSchedulePolicyError as exc:
            raise AssetResearchOrchestrationError(exc.code) from exc
        schedule_config = {
            "canonical_id": schedule.canonical_id,
            "identity_version": schedule.identity_version,
            "horizon_code": schedule.horizon_code,
            "horizon_spec": schedule.horizon_spec_json,
            "cron_expression": schedule.cron_expression,
            "timezone": schedule.timezone,
            "cutoff_policy": schedule.cutoff_policy,
            "scheduled_fire_at": fire_at.isoformat(),
            "cutoff_at": cutoff_at.isoformat(),
            "misfire_policy": schedule.misfire_policy,
        }
        if schedule.owner_scope in _SYSTEM_SCHEDULE_OWNER_SCOPES:
            schedule_config.update(
                {
                    "approved_manifest_id": schedule.approved_manifest_id,
                    "manifest_entry_key": schedule.manifest_entry_key,
                    "manifest_content_hash": schedule.manifest_content_hash,
                }
            )
        return _FrozenScheduleRun(
            scheduled_fire_at=fire_at,
            cutoff_at=cutoff_at,
            schedule_version=schedule.schedule_version,
            cutoff_policy_version=schedule.cutoff_policy_version,
            schedule_config=schedule_config,
            horizon_code=schedule.horizon_code,
            horizon_spec=dict(schedule.horizon_spec_json or {}),
            cutoff_policy=schedule.cutoff_policy,
        )

    @staticmethod
    def _frozen_schedule_retry(failed_run: AssetSignalRun) -> _FrozenScheduleRun:
        """Validate and reconstruct the immutable replay payload from a failure."""
        config = dict(failed_run.schedule_config_json or {})
        required = {
            "canonical_id",
            "identity_version",
            "horizon_code",
            "horizon_spec",
            "cron_expression",
            "timezone",
            "cutoff_policy",
            "scheduled_fire_at",
            "cutoff_at",
            "misfire_policy",
        }
        if not required <= set(config):
            raise AssetResearchOrchestrationError("SCHEDULE_RETRY_INVALID")
        horizon_spec = config["horizon_spec"]
        if not isinstance(horizon_spec, dict):
            raise AssetResearchOrchestrationError("SCHEDULE_RETRY_INVALID")
        schedule_version = failed_run.schedule_version
        if schedule_version is None:
            raise AssetResearchOrchestrationError("SCHEDULE_RETRY_INVALID")
        return _FrozenScheduleRun(
            scheduled_fire_at=_as_utc(failed_run.as_of_at),
            cutoff_at=_as_utc(failed_run.cutoff_at),
            schedule_version=schedule_version,
            cutoff_policy_version=failed_run.cutoff_policy_version,
            schedule_config=config,
            horizon_code=str(config["horizon_code"]),
            horizon_spec=horizon_spec,
            cutoff_policy=str(config["cutoff_policy"]),
            retry_of_run_id=failed_run.id,
            attempt_number=failed_run.attempt_number + 1,
        )

    async def _run_frozen_schedule(
        self,
        *,
        schedule: AssetSignalSchedule,
        frozen: _FrozenScheduleRun,
        run_type: str,
    ) -> AssetSignalRun:
        """Execute the supplied frozen schedule contract without mutable inputs."""
        run_key_material = (
            f"{schedule.owner_scope}:{schedule.user_id or 'SYSTEM'}|schedule:{schedule.id}|"
            f"{frozen.schedule_version}|{frozen.scheduled_fire_at.isoformat()}|"
            f"{frozen.cutoff_at.isoformat()}|{frozen.cutoff_policy_version}|{self.POLICY_VERSION}"
        )
        if frozen.retry_of_run_id is not None:
            run_key_material = f"{run_key_material}|retry:{frozen.retry_of_run_id}"
        run_key = hashlib.sha256(run_key_material.encode()).hexdigest()
        existing = (
            await self.db.execute(select(AssetSignalRun).where(AssetSignalRun.run_key == run_key))
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        run = AssetSignalRun(
            run_key=run_key,
            schedule_id=schedule.id,
            task_id=None,
            retry_of_run_id=frozen.retry_of_run_id,
            attempt_number=frozen.attempt_number,
            schedule_version=frozen.schedule_version,
            schedule_config_json=frozen.schedule_config,
            cutoff_policy_version=frozen.cutoff_policy_version,
            owner_scope=schedule.owner_scope,
            user_id=schedule.user_id,
            run_type=run_type,
            asset_type=schedule.asset_type,
            as_of_at=frozen.scheduled_fire_at,
            cutoff_at=frozen.cutoff_at,
            policy_version=self.POLICY_VERSION,
            status="RUNNING",
            counts_json={},
        )
        try:
            async with self.db.begin_nested():
                self.db.add(run)
                await self.db.flush()
        except IntegrityError:
            existing = (
                await self.db.execute(
                    select(AssetSignalRun).where(AssetSignalRun.run_key == run_key)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing
            raise
        try:
            instrument = await self.db.get(AssetInstrument, schedule.instrument_id)
            current_instrument = await self._current_instrument(
                canonical_id=schedule.canonical_id,
                asset_type=schedule.asset_type,
                effective_at=frozen.cutoff_at,
            )
            if (
                instrument is None
                or not self._instrument_is_current_at(instrument, frozen.cutoff_at)
                or current_instrument.id != schedule.instrument_id
                or current_instrument.metadata_version != schedule.identity_version
            ):
                raise AssetResearchOrchestrationError("INSTRUMENT_VERSION_STALE")
            identity = InstrumentIdentity.model_validate(instrument.identity_json)
            plugin = self.registry.get(schedule.asset_type)
            raw_snapshot = await self._collect_authorized_snapshot(
                identity, cutoff_at=frozen.cutoff_at
            )
            snapshot_record = await self._persist_raw_snapshot(instrument, raw_snapshot)
            quality = plugin.assess_quality(raw_snapshot)
            eligible = plugin.promote_snapshot(raw_snapshot, quality)
            features = plugin.compute_features(eligible) if eligible is not None else None
            candidate = plugin.make_decision(
                features,
                quality,
                position_context="UNKNOWN",
                horizon_code=frozen.horizon_code,
                snapshot=raw_snapshot,
            )
            published = apply_publication_gate(
                candidate,
                promoted=await self._is_promoted(
                    asset_type=schedule.asset_type,
                    horizon_code=frozen.horizon_code,
                    as_of_at=frozen.cutoff_at,
                    identity=identity,
                    candidate=candidate,
                ),
                region_restricted=self.compliance_policy.is_region_restricted(
                    asset_type=schedule.asset_type,
                    source_manifest=raw_snapshot.source_manifest,
                ),
            )
            prediction, link_role = await self._persist_or_reuse_schedule_prediction(
                schedule=schedule,
                instrument=instrument,
                snapshot=snapshot_record,
                raw_snapshot=raw_snapshot,
                quality_json=quality.model_dump(mode="json"),
                candidate_json=candidate.model_dump(mode="json"),
                published_json=published.model_dump(mode="json"),
                features=features.model_dump(mode="json") if features is not None else {},
                frozen=frozen,
            )
            if link_role == "CREATED":
                for outcome in plugin.score_outcome(
                    decision=candidate,
                    horizon_code=frozen.horizon_code,
                    as_of=frozen.cutoff_at,
                    snapshot=raw_snapshot,
                ):
                    self.db.add(
                        AssetSignalOutcome(
                            prediction_id=prediction.id,
                            outcome_kind=outcome.outcome_kind,
                            head_spec_hash=outcome.head_spec_hash,
                            horizon_code=outcome.horizon_code,
                            evaluator_version=outcome.evaluator_version,
                            status=outcome.status,
                            maturity_reason=outcome.maturity_reason,
                            maturity_at=outcome.maturity_at,
                            metrics_json=outcome.metrics,
                            reason_codes_json=outcome.reason_codes,
                        )
                    )
            # Keep the relation and terminal status in one SQL row update.
            # The database CHECK then enforces both directions of the
            # cardinality invariant without relying on a MySQL trigger.
            run.prediction_id = prediction.id
            run.prediction_link_role = link_role
            run.status = "SUCCEEDED"
            run.counts_json = {
                "created": 1 if link_role == "CREATED" else 0,
                "reused": 1 if link_role == "REUSED" else 0,
            }
            run.completed_at = _now()
            schedule.next_run_at = (
                next_schedule_fire(
                    cutoff_policy=frozen.cutoff_policy,
                    after=frozen.scheduled_fire_at,
                )
                if schedule.enabled
                else None
            )
        except Exception as exc:
            run.prediction_id = None
            run.prediction_link_role = None
            run.status = "FAILED"
            run.counts_json = {"error_code": str(getattr(exc, "code", None) or type(exc).__name__)}
            run.completed_at = _now()
        await self.db.flush()
        record_asset_research_schedule_run(
            asset_type=run.asset_type,
            status=run.status,
            lateness_seconds=max(
                0.0,
                (_as_utc(run.completed_at) - frozen.scheduled_fire_at).total_seconds(),
            )
            if run.completed_at is not None
            else None,
        )
        if run.counts_json.get("reused"):
            record_asset_research_prediction_reuse(asset_type=run.asset_type)
        return run

    async def get_signal_history(
        self,
        *,
        user_id: str,
        asset_type: str,
        canonical_id: str,
        limit: int = 30,
    ) -> AssetSignalHistoryResponse:
        """Read published predictions only; candidates remain a restricted audit field."""
        records = list(
            (
                await self.db.execute(
                    select(AssetSignalPrediction)
                    .where(
                        AssetSignalPrediction.asset_type == asset_type,
                        AssetSignalPrediction.canonical_id == canonical_id,
                        or_(
                            and_(
                                AssetSignalPrediction.owner_scope == "USER",
                                AssetSignalPrediction.user_id == user_id,
                            ),
                            and_(
                                AssetSignalPrediction.owner_scope == "PUBLIC_SHADOW",
                                AssetSignalPrediction.user_id.is_(None),
                            ),
                        ),
                    )
                    .order_by(desc(AssetSignalPrediction.as_of_at), desc(AssetSignalPrediction.id))
                    .limit(max(1, min(limit, 100)))
                )
            ).scalars()
        )
        return AssetSignalHistoryResponse(
            items=[self._public_prediction_payload(record) for record in records],
            next_cursor=None,
        )

    async def get_signal_summary(
        self,
        *,
        user_id: str,
        asset_type: str,
        canonical_id: str,
        head_spec_hash: str | None = None,
    ) -> SignalSummaryResponse:
        """Compute one versioned scorecard cohort without mixing target definitions."""
        predictions = list(
            (
                await self.db.execute(
                    select(AssetSignalPrediction)
                    .where(
                        AssetSignalPrediction.owner_scope == "USER",
                        AssetSignalPrediction.user_id == user_id,
                        AssetSignalPrediction.asset_type == asset_type,
                        AssetSignalPrediction.canonical_id == canonical_id,
                    )
                    .order_by(desc(AssetSignalPrediction.as_of_at), desc(AssetSignalPrediction.id))
                )
            ).scalars()
        )
        prediction_ids = [prediction.id for prediction in predictions]
        outcomes = (
            list(
                (
                    await self.db.execute(
                        select(AssetSignalOutcome).where(
                            AssetSignalOutcome.prediction_id.in_(prediction_ids)
                        )
                    )
                ).scalars()
            )
            if prediction_ids
            else []
        )
        outcomes_by_prediction: dict[str, list[AssetSignalOutcome]] = {}
        for outcome in outcomes:
            outcomes_by_prediction.setdefault(outcome.prediction_id, []).append(outcome)

        # Candidate direction is intentionally consumed only inside this
        # aggregate.  It is necessary for empirical validation while SHADOW is
        # active, but no individual candidate action/probability escapes this
        # service through a public response.
        primary_outcomes: dict[str, AssetSignalOutcome] = {}
        candidate_by_prediction: dict[str, dict[str, Any]] = {}
        head_by_prediction: dict[str, dict[str, Any]] = {}
        for prediction in predictions:
            candidate = dict(prediction.candidate_decision_json or {})
            candidate_by_prediction[prediction.id] = candidate
            primary_code = str(candidate.get("primary_head_code") or "")
            head = next(
                (
                    item
                    for item in candidate.get("prediction_heads") or []
                    if isinstance(item, dict) and item.get("head_code") == primary_code
                ),
                {},
            )
            if isinstance(head, dict):
                head_by_prediction[prediction.id] = head
            primary = next(
                (
                    outcome
                    for outcome in outcomes_by_prediction.get(prediction.id, [])
                    if outcome.status == "SCORED"
                    and outcome.outcome_kind == primary_code
                    and (not head or outcome.head_spec_hash == head.get("head_spec_hash"))
                ),
                None,
            )
            if primary is not None:
                primary_outcomes[prediction.id] = primary

        available_head_spec_hashes: list[str] = []
        for prediction in predictions:
            head_hash = head_by_prediction.get(prediction.id, {}).get("head_spec_hash")
            if (
                isinstance(head_hash, str)
                and len(head_hash) == 64
                and head_hash not in available_head_spec_hashes
            ):
                available_head_spec_hashes.append(head_hash)
        if head_spec_hash is not None and head_spec_hash not in available_head_spec_hashes:
            raise AssetResearchOrchestrationError("SCORECARD_COHORT_NOT_FOUND")
        cohort_selection_required = head_spec_hash is None and len(available_head_spec_hashes) > 1
        selected_head_spec_hash = (
            head_spec_hash
            if head_spec_hash is not None
            else (available_head_spec_hashes[0] if len(available_head_spec_hashes) == 1 else None)
        )
        cohort_predictions = [
            prediction
            for prediction in predictions
            if selected_head_spec_hash is not None
            and head_by_prediction.get(prediction.id, {}).get("head_spec_hash")
            == selected_head_spec_hash
        ]

        actioned: list[AssetSignalPrediction] = []
        breakdown: dict[str, dict[str, int]] = {}
        for prediction in cohort_predictions:
            published = prediction.published_decision_json or {}
            recommendation = str(published.get("recommendation") or "HOLD")
            bucket = breakdown.setdefault(
                recommendation, {"generated_count": 0, "scorable_count": 0}
            )
            bucket["generated_count"] += 1
            if prediction.id in primary_outcomes:
                bucket["scorable_count"] += 1
            candidate_direction = str(
                candidate_by_prediction[prediction.id].get("normalized_direction")
                or "INDETERMINATE"
            )
            if candidate_direction in {"LONG", "SHORT"}:
                actioned.append(prediction)

        actioned_scorable = [
            prediction for prediction in actioned if prediction.id in primary_outcomes
        ]
        actioned_success = sum(
            primary_outcomes[prediction.id].success_label is True
            for prediction in actioned_scorable
        )
        scored_primary = [
            primary_outcomes[prediction.id]
            for prediction in cohort_predictions
            if prediction.id in primary_outcomes
        ]

        brier_values: list[float] = []
        baseline_brier_values: list[float] = []
        calibration: dict[int, dict[str, float]] = {}
        for prediction in actioned_scorable:
            outcome = primary_outcomes[prediction.id]
            metrics = dict(outcome.metrics_json or {})
            probabilities = metrics.get("probabilities")
            observed_label = metrics.get("observed_label")
            head = head_by_prediction.get(prediction.id, {})
            labels = head.get("labels") if isinstance(head, dict) else None
            if not isinstance(probabilities, dict) or not isinstance(observed_label, str):
                continue
            if not isinstance(labels, list) or not labels:
                labels = list(probabilities)
            if not labels or not all(isinstance(label, str) for label in labels):
                continue
            label_names = [label for label in labels if isinstance(label, str)]
            if any(label not in probabilities for label in label_names):
                continue
            numeric_probabilities: dict[str, float] = {}
            invalid_probability = False
            for label in label_names:
                raw_probability = probabilities[label]
                if isinstance(raw_probability, bool):
                    invalid_probability = True
                    break
                try:
                    probability = float(raw_probability)
                except (TypeError, ValueError):
                    invalid_probability = True
                    break
                if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
                    invalid_probability = True
                    break
                numeric_probabilities[label] = probability
            if invalid_probability or not numeric_probabilities:
                continue
            brier_values.append(
                sum(
                    (numeric_probabilities[label] - float(label == observed_label)) ** 2
                    for label in label_names
                )
                / len(label_names)
            )
            baseline_probability = 1.0 / len(label_names)
            baseline_brier_values.append(
                sum(
                    (baseline_probability - float(label == observed_label)) ** 2
                    for label in label_names
                )
                / len(label_names)
            )
            predicted_label = max(
                numeric_probabilities, key=lambda label: numeric_probabilities[label]
            )
            confidence = numeric_probabilities[predicted_label]
            bucket_index = min(int(confidence * 5), 4)
            calibration_bucket = calibration.setdefault(
                bucket_index, {"count": 0.0, "confidence": 0.0, "correct": 0.0}
            )
            calibration_bucket["count"] += 1.0
            calibration_bucket["confidence"] += confidence
            calibration_bucket["correct"] += float(predicted_label == observed_label)

        action_returns: list[float] = []
        for prediction in actioned_scorable:
            net_return = primary_outcomes[prediction.id].net_return
            if net_return is not None:
                action_returns.append(float(net_return))
        wealth = 1.0
        peak = 1.0
        max_drawdown = 0.0
        for prediction in sorted(actioned_scorable, key=lambda item: item.as_of_at):
            net_return = primary_outcomes[prediction.id].net_return
            if net_return is None:
                continue
            wealth *= 1.0 + float(net_return)
            peak = max(peak, wealth)
            max_drawdown = min(max_drawdown, wealth / peak - 1.0)

        generated_count = len(cohort_predictions)
        scorable_count = len(scored_primary)
        mean_brier = sum(brier_values) / len(brier_values) if brier_values else None
        mean_baseline_brier = (
            sum(baseline_brier_values) / len(baseline_brier_values)
            if baseline_brier_values
            else None
        )
        return SignalSummaryResponse(
            asset_type=asset_type,
            canonical_id=canonical_id,
            head_spec_hash=selected_head_spec_hash,
            available_head_spec_hashes=available_head_spec_hashes,
            cohort_selection_required=cohort_selection_required,
            total_generated_count=len(predictions),
            excluded_prediction_count=len(predictions) - generated_count,
            generated_count=generated_count,
            scorable_count=scorable_count,
            actioned_generated_count=len(actioned),
            actioned_scorable_count=len(actioned_scorable),
            actioned_success_count=actioned_success,
            actioned_success_rate=(
                actioned_success / len(actioned_scorable) if actioned_scorable else None
            ),
            coverage_rate=len(actioned) / generated_count if generated_count else None,
            maturity_rate=scorable_count / generated_count if generated_count else None,
            brier_score=mean_brier,
            brier_skill_score=(
                1.0 - mean_brier / mean_baseline_brier
                if mean_brier is not None
                and mean_baseline_brier is not None
                and mean_baseline_brier != 0.0
                else None
            ),
            average_net_return=(
                sum(action_returns) / len(action_returns) if action_returns else None
            ),
            max_drawdown=max_drawdown if action_returns else None,
            calibration_bins=[
                {
                    "lower_bound": index / 5,
                    "upper_bound": (index + 1) / 5,
                    "sample_count": int(values["count"]),
                    "mean_confidence": values["confidence"] / values["count"],
                    "observed_frequency": values["correct"] / values["count"],
                }
                for index, values in sorted(calibration.items())
                if values["count"]
            ],
            action_breakdown=[
                {"recommendation": recommendation, **counts}
                for recommendation, counts in sorted(breakdown.items())
            ],
        )

    async def get_signal_evidence(
        self, *, user_id: str, prediction_id: str
    ) -> dict[str, Any] | None:
        """Return a safe evidence manifest, never raw provider payloads or candidates."""
        prediction = await self._owned_prediction(user_id=user_id, prediction_id=prediction_id)
        if prediction is None:
            return None
        snapshot = await self.db.get(AssetSourceSnapshot, prediction.snapshot_id)
        manifest = dict(snapshot.source_manifest_json or {}) if snapshot is not None else {}
        decision = prediction.published_decision_json or {}
        allowed_source_fields = {
            key: manifest.get(key)
            for key in (
                "source_id",
                "provider",
                "license_status",
                "source_registry_status",
                "observed_at",
                "available_at",
                "retrieved_at",
                "capabilities",
                "allowed_uses",
            )
            if manifest.get(key) is not None
        }
        return {
            "prediction_id": prediction.id,
            "canonical_id": prediction.canonical_id,
            "asset_type": prediction.asset_type,
            "source": allowed_source_fields,
            "source_snapshot_hash": snapshot.content_hash if snapshot is not None else None,
            "license_tags": list(snapshot.license_tags_json or []) if snapshot is not None else [],
            "versions": {
                "feature_version": prediction.feature_version,
                "policy_version": prediction.policy_version,
                "model_version": prediction.model_version,
                "calibration_version": prediction.calibration_version,
                "capability_version": prediction.capability_version,
                "compliance_policy_version": prediction.compliance_policy_version,
                "cutoff_policy_version": prediction.cutoff_policy_version,
                "head_spec_set_hash": prediction.head_spec_set_hash,
            },
            "reason_codes": list(decision.get("reason_codes") or []),
        }

    async def get_signal_outcomes(
        self, *, user_id: str, prediction_id: str
    ) -> list[AssetSignalOutcomeResponse] | None:
        """Read all outcome heads for an owned prediction without re-evaluating it."""
        prediction = await self._owned_prediction(user_id=user_id, prediction_id=prediction_id)
        if prediction is None:
            return None
        outcomes = list(
            (
                await self.db.execute(
                    select(AssetSignalOutcome)
                    .where(AssetSignalOutcome.prediction_id == prediction.id)
                    .order_by(AssetSignalOutcome.outcome_kind, AssetSignalOutcome.evaluator_version)
                )
            ).scalars()
        )
        return [
            AssetSignalOutcomeResponse(
                outcome_id=outcome.id,
                prediction_id=outcome.prediction_id,
                outcome_kind=outcome.outcome_kind,
                head_spec_hash=outcome.head_spec_hash,
                horizon_code=outcome.horizon_code,
                evaluator_version=outcome.evaluator_version,
                status=outcome.status,
                maturity_reason=outcome.maturity_reason,
                maturity_at=outcome.maturity_at,
                gross_return=outcome.gross_return,
                net_return=outcome.net_return,
                benchmark_return=outcome.benchmark_return,
                success_label=outcome.success_label,
                reason_codes=list(outcome.reason_codes_json or []),
                metrics=outcome.metrics_json or {},
                scored_at=outcome.scored_at,
            )
            for outcome in outcomes
        ]

    async def evaluate_due_outcomes(
        self,
        *,
        cutoff_at: datetime | None = None,
        limit: int = 100,
        prediction_ids: Collection[str] | None = None,
        errors: dict[str, str] | None = None,
    ) -> int:
        """Collect and score due predictions once per immutable prediction.

        This worker boundary is deliberately independent of the user-facing
        task queue.  It groups pending heads by prediction, records the later
        licensed raw snapshot exactly once, and then lets the evaluator update
        each head idempotently.  A provider failure leaves the pending row in
        place rather than inventing a neutral result.
        """
        evaluation_cutoff = _as_utc(cutoff_at or _now())
        requested_prediction_ids = list(dict.fromkeys(prediction_ids or []))
        if prediction_ids is not None and not requested_prediction_ids:
            return 0
        due_query = (
            select(AssetSignalOutcome.prediction_id)
            .where(
                AssetSignalOutcome.status == "PENDING",
                AssetSignalOutcome.maturity_at.is_not(None),
                AssetSignalOutcome.maturity_at <= evaluation_cutoff,
            )
            .distinct()
            .limit(max(1, min(limit, 1000)))
        )
        if prediction_ids is not None:
            due_query = due_query.where(
                AssetSignalOutcome.prediction_id.in_(requested_prediction_ids)
            )
        due_prediction_ids = list((await self.db.execute(due_query)).scalars())
        scorer = AssetOutcomeEvaluator(self.db)
        scored_count = 0
        for prediction_id in due_prediction_ids:
            prediction = await self.db.get(AssetSignalPrediction, prediction_id)
            if prediction is None:
                continue
            instrument = await self.db.get(AssetInstrument, prediction.instrument_id)
            if instrument is None:
                continue
            try:
                entry_snapshot = await self.db.get(AssetSourceSnapshot, prediction.snapshot_id)
                source_manifest = (
                    dict(entry_snapshot.source_manifest_json or {})
                    if entry_snapshot is not None
                    else {}
                )
                source_id = str(
                    source_manifest.get("source_id") or source_manifest.get("provider") or ""
                ).strip()
                declared_source_ids = self._declared_adapter_source_ids()
                source_is_bound = declared_source_ids is None or source_id in declared_source_ids
                source_is_authorized = source_is_bound and await AssetSourceRegistryPolicy(
                    self.db
                ).is_research_authorized(
                    source_id=source_id,
                    asset_type=prediction.asset_type,
                    at=evaluation_cutoff,
                )
                if not source_is_authorized:
                    blocked_outcomes = await scorer.mark_due_source_license_blocked(
                        prediction_id=prediction.id,
                        evaluated_at=evaluation_cutoff,
                    )
                    for outcome in blocked_outcomes:
                        record_asset_research_outcome(
                            asset_type=prediction.asset_type,
                            status=outcome.status,
                        )
                    if errors is not None:
                        errors[str(prediction_id)] = "SOURCE_LICENSE_BLOCKED"
                    continue
                identity = InstrumentIdentity.model_validate(instrument.identity_json)
                observed_snapshot = await self._collect_authorized_snapshot(
                    identity, cutoff_at=evaluation_cutoff
                )
                await self._persist_raw_snapshot(instrument, observed_snapshot)
                before = {
                    outcome.id: outcome.status
                    for outcome in (
                        await self.db.execute(
                            select(AssetSignalOutcome).where(
                                AssetSignalOutcome.prediction_id == prediction.id
                            )
                        )
                    ).scalars()
                }
                outcomes = await scorer.score_prediction(
                    prediction_id=prediction.id,
                    observed_snapshot=observed_snapshot,
                )
                scored_count += sum(
                    before.get(outcome.id) != "SCORED" and outcome.status == "SCORED"
                    for outcome in outcomes
                )
                for outcome in outcomes:
                    if before.get(outcome.id) != outcome.status:
                        record_asset_research_outcome(
                            asset_type=prediction.asset_type,
                            status=outcome.status,
                        )
            except Exception as exc:
                # The original prediction and PENDING outcome evidence remain
                # queryable; a subsequent scheduled retry will use the same
                # horizon and only newly legal point-in-time observations.
                if errors is not None:
                    errors[str(prediction_id)] = str(getattr(exc, "code", type(exc).__name__))
                continue
        await self.db.flush()
        return scored_count

    async def create_and_run(
        self,
        *,
        user_id: str,
        request: AssetAnalysisCreateRequest,
        cutoff_at: datetime | None = None,
        retry_of_task_id: str | None = None,
    ) -> AssetAnalysisTask:
        """Create one task and run it in the caller's transaction/session."""
        task = await self.create_pending(
            user_id=user_id,
            request=request,
            retry_of_task_id=retry_of_task_id,
        )
        instrument = await self.db.get(AssetInstrument, task.instrument_id)
        if instrument is None:
            raise AssetResearchOrchestrationError("INSTRUMENT_VERSION_STALE")
        return await self._run_task(task, instrument, cutoff_at=cutoff_at or _now())

    async def create_pending(
        self,
        *,
        user_id: str,
        request: AssetAnalysisCreateRequest,
        retry_of_task_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> AssetAnalysisTask:
        """Persist a queued task so request handlers can return before research runs."""
        normalized_key = self._normalized_idempotency_key(idempotency_key)
        request_hash = canonical_json_hash(request.model_dump(mode="json"))
        if normalized_key is not None:
            existing = await self._task_by_idempotency_key(
                user_id=user_id,
                idempotency_key=normalized_key,
            )
            if existing is not None:
                if existing.idempotency_request_hash != request_hash:
                    raise AssetResearchOrchestrationError("IDEMPOTENCY_CONFLICT")
                return existing
        await self.require_research_capability(request.asset_type)
        instrument = await self._current_instrument(
            canonical_id=request.canonical_id,
            asset_type=request.asset_type,
        )
        position_snapshot_id, position_context = await self._validate_position_context(
            user_id=user_id,
            instrument=instrument,
            requested_position_context=request.position_context,
            snapshot_id=request.position_context_snapshot_id,
        )
        task = AssetAnalysisTask(
            user_id=user_id,
            owner_scope="USER",
            instrument_id=instrument.id,
            asset_type=request.asset_type,
            canonical_id=instrument.canonical_id,
            identity_version=instrument.metadata_version,
            request_json=request.model_dump(mode="json"),
            position_context=position_context,
            position_context_snapshot_id=position_snapshot_id,
            horizon_code=request.horizon_code,
            status="QUEUED",
            progress=0,
            retry_of_task_id=retry_of_task_id,
            idempotency_key=normalized_key,
            idempotency_request_hash=request_hash if normalized_key is not None else None,
        )
        self.db.add(task)
        await self.db.flush()
        record_asset_research_task(asset_type=task.asset_type, status="QUEUED")
        return task

    @classmethod
    async def run_pending_task(cls, *, task_id: str, user_id: str) -> None:
        """Compatibility entrypoint that claims one queued task with a durable lease."""
        claim_time = _now()
        lease_token = uuid4().hex
        terminal_metric: tuple[str, str, float | None] | None = None
        async with async_session_maker() as session:
            service = cls(session)
            claim = await session.execute(
                update(AssetAnalysisTask)
                .where(
                    AssetAnalysisTask.id == task_id,
                    AssetAnalysisTask.owner_scope == "USER",
                    AssetAnalysisTask.user_id == user_id,
                    AssetAnalysisTask.status == "QUEUED",
                    AssetAnalysisTask.lease_token.is_(None),
                )
                .values(
                    status="RUNNING",
                    progress=10,
                    started_at=claim_time,
                    lease_token=lease_token,
                    lease_expires_at=claim_time + timedelta(seconds=900),
                    lease_heartbeat_at=claim_time,
                    attempt_count=AssetAnalysisTask.attempt_count + 1,
                )
            )
            if claim.rowcount != 1:
                return
            await session.commit()
            task = await session.get(AssetAnalysisTask, task_id)
            if task is not None:
                record_asset_research_task(asset_type=task.asset_type, status="RUNNING")
            try:
                await service.run_claimed_task(task_id=task_id, lease_token=lease_token)
            except Exception as exc:
                task = await session.get(AssetAnalysisTask, task_id)
                if task is not None and task.lease_token == lease_token:
                    service._fail_task(
                        task,
                        error_code=str(getattr(exc, "code", type(exc).__name__)),
                        record_metric=False,
                    )
            finally:
                task = await session.get(AssetAnalysisTask, task_id)
                if task is not None:
                    if task.status not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                        service._fail_task(
                            task,
                            error_code="TASK_RUNNER_NONTERMINAL",
                            record_metric=False,
                        )
                    service._release_task_lease(task, lease_token=lease_token)
                    if task.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                        terminal_metric = (
                            task.asset_type,
                            task.status,
                            service._task_duration_seconds(task),
                        )
                await session.commit()
        if terminal_metric is not None:
            asset_type, status, duration_seconds = terminal_metric
            record_asset_research_task(
                asset_type=asset_type,
                status=status,
                duration_seconds=duration_seconds,
            )

    async def run_claimed_task(
        self,
        *,
        task_id: str,
        lease_token: str,
    ) -> AssetAnalysisTask | None:
        """Run a matching durable task lease without allowing a second worker to take it."""
        task = await self.db.get(AssetAnalysisTask, task_id)
        if task is None or task.status != "RUNNING" or task.lease_token != lease_token:
            return None
        try:
            await self.require_research_capability(task.asset_type)
        except AssetResearchOrchestrationError as exc:
            self._fail_task(task, error_code=exc.code, record_metric=False)
            return task

        analysis_at = _now()
        instrument = await self.db.get(AssetInstrument, task.instrument_id)
        try:
            current_instrument = await self._current_instrument(
                canonical_id=task.canonical_id,
                asset_type=task.asset_type,
                effective_at=analysis_at,
            )
        except AssetResearchOrchestrationError:
            current_instrument = None
        if (
            instrument is None
            or not self._instrument_is_current_at(instrument, analysis_at)
            or current_instrument is None
            or current_instrument.id != task.instrument_id
            or current_instrument.metadata_version != task.identity_version
        ):
            self._fail_task(
                task,
                error_code="INSTRUMENT_VERSION_STALE",
                record_metric=False,
            )
            return task
        return await self._run_task(
            task,
            instrument,
            cutoff_at=analysis_at,
            defer_terminal_transition=True,
        )

    def _fail_task(
        self,
        task: AssetAnalysisTask,
        *,
        error_code: str,
        record_metric: bool = True,
    ) -> None:
        """Record a terminal task failure without mutating immutable run evidence."""
        task.status = "FAILED"
        task.progress = 100
        task.error_code = error_code
        task.completed_at = _now()
        if record_metric:
            record_asset_research_task(
                asset_type=task.asset_type,
                status="FAILED",
                duration_seconds=self._task_duration_seconds(task),
            )

    @staticmethod
    def _release_task_lease(task: AssetAnalysisTask, *, lease_token: str) -> None:
        """Release only the lease owned by the caller's worker token."""
        if task.lease_token != lease_token:
            return
        task.lease_token = None
        task.lease_expires_at = None
        task.lease_heartbeat_at = None

    async def get_task(self, *, user_id: str, task_id: str) -> AssetAnalysisTaskResponse | None:
        task = await self._owned_task(user_id=user_id, task_id=task_id)
        if task is None:
            return None
        report = await self._report_for_task(task.id)
        return _task_payload(task, report)

    async def get_result(self, *, user_id: str, task_id: str) -> AssetAnalysisResultResponse | None:
        """Return the public result, explicitly leaving candidate fields server-only."""
        task = await self._owned_task(user_id=user_id, task_id=task_id)
        if task is None:
            return None
        report = await self._report_for_task(task.id)
        prediction = None
        if report and report.prediction_id:
            prediction = await self.db.get(AssetSignalPrediction, report.prediction_id)
        if prediction is None:
            prediction = (
                (
                    await self.db.execute(
                        select(AssetSignalPrediction)
                        .join(
                            AssetSignalRun, AssetSignalRun.prediction_id == AssetSignalPrediction.id
                        )
                        .where(
                            AssetSignalRun.task_id == task.id,
                            AssetSignalRun.status == "SUCCEEDED",
                            AssetSignalPrediction.owner_scope == "USER",
                            AssetSignalPrediction.user_id == user_id,
                        )
                        .order_by(
                            desc(AssetSignalRun.completed_at),
                            desc(AssetSignalPrediction.created_at),
                        )
                    )
                )
                .scalars()
                .first()
            )
        return AssetAnalysisResultResponse(
            task_id=task.id,
            status=task.status,
            report_id=report.id if report else None,
            prediction_id=prediction.id if prediction else None,
            published_decision=(
                prediction.published_decision_json if prediction is not None else None
            ),
            report=self._public_report_payload(report.sections_json)
            if report is not None
            else None,
        )

    async def cancel_task(self, *, user_id: str, task_id: str) -> AssetAnalysisTaskResponse | None:
        task = await self._owned_task(user_id=user_id, task_id=task_id)
        if task is None:
            return None
        if task.status in {"QUEUED", "RUNNING"}:
            task.status = "CANCELLED"
            task.progress = 100
            task.completed_at = _now()
            await self.db.flush()
            record_asset_research_task(
                asset_type=task.asset_type,
                status="CANCELLED",
                duration_seconds=self._task_duration_seconds(task),
            )
        return _task_payload(task, await self._report_for_task(task.id))

    async def retry_task(self, *, user_id: str, task_id: str) -> AssetAnalysisTask:
        task = await self._owned_task(user_id=user_id, task_id=task_id)
        if task is None:
            raise AssetResearchOrchestrationError("TASK_NOT_FOUND")
        if task.status not in {"FAILED", "CANCELLED"}:
            raise AssetResearchOrchestrationError("TASK_NOT_RETRYABLE")
        request = AssetAnalysisCreateRequest.model_validate(task.request_json)
        return await self.create_pending(user_id=user_id, request=request, retry_of_task_id=task.id)

    async def _run_task(
        self,
        task: AssetAnalysisTask,
        instrument: AssetInstrument,
        *,
        cutoff_at: datetime,
        defer_terminal_transition: bool = False,
    ) -> AssetAnalysisTask:
        """Run deterministic research before attempting the secondary report resource.

        A report renderer may be unavailable while the identity, snapshot and
        published decision have already been persisted correctly.  Keep that
        failure from rewriting the run's factual lifecycle or discarding the
        prediction; the public result endpoint can still expose the structured
        published decision and the task carries a stable report error code.
        """
        if not defer_terminal_transition:
            task.status = "RUNNING"
            task.progress = 10
            task.started_at = task.started_at or _now()
        if not defer_terminal_transition:
            record_asset_research_task(asset_type=task.asset_type, status="RUNNING")
        run: AssetSignalRun | None = None
        try:
            identity = InstrumentIdentity.model_validate(instrument.identity_json)
            plugin = self.registry.get(task.asset_type)
            option_close_context_authorized = (
                await self._normalize_task_position_context_for_cutoff(
                    task=task,
                    instrument=instrument,
                    identity=identity,
                    cutoff_at=cutoff_at,
                )
            )
            raw_snapshot = await self._collect_authorized_snapshot(identity, cutoff_at=cutoff_at)
            await self.db.refresh(task)
            if task.status == "CANCELLED":
                return task
            snapshot_record = await self._persist_raw_snapshot(instrument, raw_snapshot)
            if not defer_terminal_transition:
                task.progress = 35

            quality = plugin.assess_quality(raw_snapshot)
            eligible = plugin.promote_snapshot(raw_snapshot, quality)
            features = plugin.compute_features(eligible) if eligible is not None else None
            candidate = plugin.make_decision(
                features,
                quality,
                position_context=task.position_context,
                horizon_code=task.horizon_code,
                snapshot=raw_snapshot,
            )
            published = apply_publication_gate(
                candidate,
                promoted=await self._is_promoted(
                    asset_type=task.asset_type,
                    horizon_code=task.horizon_code,
                    as_of_at=cutoff_at,
                    identity=identity,
                    candidate=candidate,
                ),
                region_restricted=self.compliance_policy.is_region_restricted(
                    asset_type=task.asset_type,
                    source_manifest=raw_snapshot.source_manifest,
                ),
                option_close_context_authorized=option_close_context_authorized,
            )
            if not defer_terminal_transition:
                task.progress = 60

            prediction, link_role = await self._persist_or_reuse_prediction(
                task=task,
                instrument=instrument,
                snapshot=snapshot_record,
                raw_snapshot=raw_snapshot,
                quality_json=quality.model_dump(mode="json"),
                candidate_json=candidate.model_dump(mode="json"),
                published_json=published.model_dump(mode="json"),
                features=features.model_dump(mode="json") if features is not None else {},
                cutoff_at=cutoff_at,
            )
            run = await self._create_run(task, cutoff_at)
            if link_role == "CREATED":
                for outcome in plugin.score_outcome(
                    decision=candidate,
                    horizon_code=task.horizon_code,
                    as_of=cutoff_at,
                    snapshot=raw_snapshot,
                ):
                    self.db.add(
                        AssetSignalOutcome(
                            prediction_id=prediction.id,
                            outcome_kind=outcome.outcome_kind,
                            head_spec_hash=outcome.head_spec_hash,
                            horizon_code=outcome.horizon_code,
                            evaluator_version=outcome.evaluator_version,
                            status=outcome.status,
                            maturity_reason=outcome.maturity_reason,
                            maturity_at=outcome.maturity_at,
                            metrics_json=outcome.metrics,
                            reason_codes_json=outcome.reason_codes,
                        )
                    )

            # Assign the immutable prediction in the same flush as the
            # terminal transition; failed and running rows must stay null.
            run.prediction_id = prediction.id
            run.prediction_link_role = link_role
            run.status = "SUCCEEDED"
            run.counts_json = {
                "created": 1 if link_role == "CREATED" else 0,
                "reused": 1 if link_role == "REUSED" else 0,
            }
            run.completed_at = _now()
            if defer_terminal_transition:
                # Leave the task itself untouched until the durable runner
                # performs its lease-token compare-and-set.  This flush keeps
                # immutable prediction/run facts in the same transaction but
                # cannot overwrite a cancellation committed by another
                # session while collection or rendering was in progress.
                await self.db.flush()
            else:
                task.status = "SUCCEEDED"
                task.progress = 100
                task.completed_at = _now()
                await self.db.flush()
                record_asset_research_task(
                    asset_type=task.asset_type,
                    status="SUCCEEDED",
                    duration_seconds=self._task_duration_seconds(task),
                )
            if link_role == "REUSED":
                record_asset_research_prediction_reuse(asset_type=task.asset_type)
        except Exception as exc:
            if run is not None:
                run.prediction_id = None
                run.prediction_link_role = None
                run.status = "FAILED"
                run.counts_json = {
                    "error_code": str(getattr(exc, "code", None) or type(exc).__name__)
                }
                run.completed_at = _now()
            if defer_terminal_transition:
                await self.db.flush()
            task.status = "FAILED"
            task.progress = 100
            task.error_code = str(getattr(exc, "code", None) or type(exc).__name__)
            task.completed_at = _now()
            if not defer_terminal_transition:
                await self.db.flush()
            if not defer_terminal_transition:
                record_asset_research_task(
                    asset_type=task.asset_type,
                    status="FAILED",
                    duration_seconds=self._task_duration_seconds(task),
                )
            return task

        try:
            sections = plugin.build_report_sections(raw_snapshot, published)
            report_payload = build_report_payload(
                identity=identity, published_decision=published, sections=sections
            )
            rendered_markdown = render_markdown(report_payload)
            report = AssetAnalysisReport(
                task_id=task.id,
                prediction_id=prediction.id,
                report_version="v1",
                sections_json=report_payload,
                rendered_markdown=rendered_markdown,
                content_hash=canonical_json_hash(report_payload),
            )
            self.db.add(report)
            await self.db.flush()
        except Exception:
            # The task and run are intentionally already SUCCEEDED.  The
            # missing report is observable and can be regenerated without
            # mutating the decision or its outcome heads.
            task.error_code = "REPORT_RENDER_FAILED"
            if not defer_terminal_transition:
                await self.db.flush()
        if defer_terminal_transition:
            task.status = "SUCCEEDED"
            task.progress = 100
            task.completed_at = _now()
        return task

    async def _persist_raw_snapshot(
        self, instrument: AssetInstrument, raw: RawAssetSnapshot
    ) -> AssetSourceSnapshot:
        record = AssetSourceSnapshot(
            instrument_id=instrument.id,
            asset_type=instrument.asset_type,
            canonical_id=instrument.canonical_id,
            identity_version=instrument.metadata_version,
            cutoff_at=raw.cutoff_at,
            raw_schema_version=raw.raw_schema_version,
            raw_fields_json={
                "fields": raw.raw_fields,
                "history_rows": raw.history_rows,
                "observations": {
                    field_name: observation.model_dump(mode="json")
                    for field_name, observation in raw.observations.items()
                },
                "retrieved_at": raw.retrieved_at.isoformat(),
            },
            source_manifest_json=raw.source_manifest,
            content_hash=raw.content_hash,
            license_tags_json=raw.license_tags,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    @staticmethod
    def _frozen_cost_snapshot(raw_snapshot: RawAssetSnapshot) -> dict[str, float | str]:
        """Persist only a validated server-collected executable-cost envelope.

        User request options never become costs.  An absent or malformed option
        cost source stays an empty payload and is already rejected by the
        option quality gate. Other asset types need an explicit total cost rate
        and version for outcome scoring; an empty payload is retained as a
        missing fact, never reinterpreted as a free transaction.
        """
        asset_type = raw_snapshot.identity.asset_type
        asset_fields = raw_snapshot.raw_fields.get(asset_type)
        if not isinstance(asset_fields, Mapping):
            return {}
        if asset_type == "option":
            costs, _ = parse_option_cost_snapshot(asset_fields.get("cost_snapshot"))
            return costs.to_payload() if costs is not None else {}

        raw_cost_snapshot = asset_fields.get("cost_snapshot")
        if not isinstance(raw_cost_snapshot, Mapping):
            return {}
        version = raw_cost_snapshot.get("cost_model_version")
        if not isinstance(version, str) or not version.strip():
            return {}
        for field_name in ("total_cost_rate", "cost_rate", "transaction_cost_rate"):
            raw_rate = raw_cost_snapshot.get(field_name)
            if raw_rate is None or isinstance(raw_rate, bool):
                continue
            try:
                rate = float(raw_rate)
            except (TypeError, ValueError):
                continue
            if math.isfinite(rate) and rate >= 0:
                return {"cost_model_version": version.strip(), "total_cost_rate": rate}
        return {}

    async def _persist_or_reuse_prediction(
        self,
        *,
        task: AssetAnalysisTask,
        instrument: AssetInstrument,
        snapshot: AssetSourceSnapshot,
        raw_snapshot: RawAssetSnapshot,
        quality_json: dict[str, Any],
        candidate_json: dict[str, Any],
        published_json: dict[str, Any],
        features: dict[str, Any],
        cutoff_at: datetime,
    ) -> tuple[AssetSignalPrediction, str]:
        cost_snapshot = self._frozen_cost_snapshot(raw_snapshot)
        position_snapshot: AssetPositionContextSnapshot | None = None
        position_snapshot_hash: str | None = None
        if task.position_context_snapshot_id is not None:
            position_snapshot = await self.db.get(
                AssetPositionContextSnapshot,
                task.position_context_snapshot_id,
            )
            if position_snapshot is not None:
                position_snapshot_hash = position_snapshot.content_hash
        input_payload = {
            "identity": instrument.identity_json,
            "cutoff_at": cutoff_at.isoformat(),
            "horizon_code": task.horizon_code,
            "position_context": task.position_context,
            "position_context_snapshot_id": task.position_context_snapshot_id,
            "position_context_snapshot_hash": position_snapshot_hash,
            "position_context_snapshot_as_of_at": (
                position_snapshot.as_of_at.isoformat() if position_snapshot is not None else None
            ),
            "position_context_snapshot_available_at": (
                position_snapshot.available_at.isoformat()
                if position_snapshot is not None
                else None
            ),
            "position_context_snapshot_expires_at": (
                position_snapshot.expires_at.isoformat()
                if position_snapshot is not None and position_snapshot.expires_at is not None
                else None
            ),
            "request_options": (task.request_json or {}).get("request_options", {}),
            "source_snapshot_hash": raw_snapshot.content_hash,
            "prediction_heads": candidate_json.get("prediction_heads", []),
            "cost_snapshot": cost_snapshot,
            "feature_version": self.FEATURE_VERSION,
            "policy_version": self.POLICY_VERSION,
            "model_version": self.MODEL_VERSION,
            "calibration_version": self.CALIBRATION_VERSION,
            "capability_version": self.CAPABILITY_VERSION,
            "compliance_policy_version": self.COMPLIANCE_POLICY_VERSION,
            "compliance_context": self.compliance_policy.frozen_context(
                source_manifest=raw_snapshot.source_manifest
            ),
            "cutoff_policy_version": self.CUTOFF_POLICY_VERSION,
        }
        decision_input_hash = canonical_json_hash(input_payload)
        prediction_key = hashlib.sha256(
            f"USER:{task.user_id}|{decision_input_hash}".encode()
        ).hexdigest()
        existing = (
            await self.db.execute(
                select(AssetSignalPrediction).where(
                    AssetSignalPrediction.prediction_key == prediction_key
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, "REUSED"
        prediction = AssetSignalPrediction(
            prediction_key=prediction_key,
            decision_input_hash=decision_input_hash,
            owner_scope="USER",
            user_id=task.user_id,
            instrument_id=instrument.id,
            asset_type=task.asset_type,
            canonical_id=task.canonical_id,
            identity_version=instrument.metadata_version,
            as_of_at=cutoff_at,
            horizon_code=task.horizon_code,
            horizon_spec_json=(published_json.get("horizon_spec") or {}),
            position_context=task.position_context,
            position_context_snapshot_id=task.position_context_snapshot_id,
            position_context_snapshot_as_of_at=(
                position_snapshot.as_of_at if position_snapshot is not None else None
            ),
            position_context_snapshot_available_at=(
                position_snapshot.available_at if position_snapshot is not None else None
            ),
            position_context_snapshot_expires_at=(
                position_snapshot.expires_at if position_snapshot is not None else None
            ),
            candidate_decision_json=candidate_json,
            published_decision_json=published_json,
            actionability=published_json["actionability"],
            quality_status=quality_json["status"],
            quality_json={**quality_json, "features": features},
            snapshot_id=snapshot.id,
            mapped_contract_id=None,
            head_spec_set_hash=canonical_json_hash(
                [head["head_spec_hash"] for head in candidate_json.get("prediction_heads", [])]
            ),
            feature_version=self.FEATURE_VERSION,
            policy_version=self.POLICY_VERSION,
            model_version=self.MODEL_VERSION,
            calibration_version=self.CALIBRATION_VERSION,
            capability_version=self.CAPABILITY_VERSION,
            compliance_policy_version=self.COMPLIANCE_POLICY_VERSION,
            cutoff_policy_version=self.CUTOFF_POLICY_VERSION,
            cost_snapshot_json=cost_snapshot,
        )
        return await self._insert_or_reuse_prediction_record(prediction)

    async def _persist_or_reuse_schedule_prediction(
        self,
        *,
        schedule: AssetSignalSchedule,
        instrument: AssetInstrument,
        snapshot: AssetSourceSnapshot,
        raw_snapshot: RawAssetSnapshot,
        quality_json: dict[str, Any],
        candidate_json: dict[str, Any],
        published_json: dict[str, Any],
        features: dict[str, Any],
        frozen: _FrozenScheduleRun,
    ) -> tuple[AssetSignalPrediction, str]:
        """Persist a schedule-owned prediction without creating a task-backed run."""
        cost_snapshot = self._frozen_cost_snapshot(raw_snapshot)
        input_payload = {
            "identity": instrument.identity_json,
            "schedule_id": schedule.id,
            "schedule_version": frozen.schedule_version,
            "cutoff_at": frozen.cutoff_at.isoformat(),
            "horizon_code": frozen.horizon_code,
            "horizon_spec": frozen.horizon_spec,
            "position_context": "UNKNOWN",
            "source_snapshot_hash": raw_snapshot.content_hash,
            "prediction_heads": candidate_json.get("prediction_heads", []),
            "cost_snapshot": cost_snapshot,
            "feature_version": self.FEATURE_VERSION,
            "policy_version": self.POLICY_VERSION,
            "model_version": self.MODEL_VERSION,
            "calibration_version": self.CALIBRATION_VERSION,
            "capability_version": self.CAPABILITY_VERSION,
            "compliance_policy_version": self.COMPLIANCE_POLICY_VERSION,
            "compliance_context": self.compliance_policy.frozen_context(
                source_manifest=raw_snapshot.source_manifest
            ),
            "cutoff_policy_version": frozen.cutoff_policy_version,
        }
        decision_input_hash = canonical_json_hash(input_payload)
        access_principal = f"{schedule.owner_scope}:{schedule.user_id or 'SYSTEM'}"
        prediction_key = hashlib.sha256(
            f"{access_principal}|{decision_input_hash}".encode()
        ).hexdigest()
        existing = (
            await self.db.execute(
                select(AssetSignalPrediction).where(
                    AssetSignalPrediction.prediction_key == prediction_key
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, "REUSED"
        prediction = AssetSignalPrediction(
            prediction_key=prediction_key,
            decision_input_hash=decision_input_hash,
            owner_scope=schedule.owner_scope,
            user_id=schedule.user_id,
            instrument_id=instrument.id,
            asset_type=schedule.asset_type,
            canonical_id=schedule.canonical_id,
            identity_version=instrument.metadata_version,
            as_of_at=frozen.cutoff_at,
            horizon_code=frozen.horizon_code,
            horizon_spec_json=(published_json.get("horizon_spec") or frozen.horizon_spec),
            position_context="UNKNOWN",
            position_context_snapshot_id=None,
            candidate_decision_json=candidate_json,
            published_decision_json=published_json,
            actionability=published_json["actionability"],
            quality_status=quality_json["status"],
            quality_json={**quality_json, "features": features},
            snapshot_id=snapshot.id,
            mapped_contract_id=None,
            head_spec_set_hash=canonical_json_hash(
                [head["head_spec_hash"] for head in candidate_json.get("prediction_heads", [])]
            ),
            feature_version=self.FEATURE_VERSION,
            policy_version=self.POLICY_VERSION,
            model_version=self.MODEL_VERSION,
            calibration_version=self.CALIBRATION_VERSION,
            capability_version=self.CAPABILITY_VERSION,
            compliance_policy_version=self.COMPLIANCE_POLICY_VERSION,
            cutoff_policy_version=frozen.cutoff_policy_version,
            cost_snapshot_json=cost_snapshot,
        )
        return await self._insert_or_reuse_prediction_record(prediction)

    async def _insert_or_reuse_prediction_record(
        self, prediction: AssetSignalPrediction
    ) -> tuple[AssetSignalPrediction, str]:
        """Let the unique prediction key close a concurrent-worker race safely.

        The initial lookup above keeps the common path inexpensive.  A lookup
        cannot, however, serialize two workers that read before either one
        writes.  The nested transaction makes a duplicate-key conflict local
        to this insert; the losing worker then links its independently valid
        run to the already committed immutable prediction.
        """
        try:
            async with self.db.begin_nested():
                self.db.add(prediction)
                await self.db.flush()
        except IntegrityError:
            existing = (
                await self.db.execute(
                    select(AssetSignalPrediction).where(
                        AssetSignalPrediction.prediction_key == prediction.prediction_key
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing, "REUSED"
            raise
        return prediction, "CREATED"

    async def _create_run(self, task: AssetAnalysisTask, cutoff_at: datetime) -> AssetSignalRun:
        run_key = hashlib.sha256(
            f"task:{task.id}|{cutoff_at.isoformat()}|{self.CUTOFF_POLICY_VERSION}|{self.POLICY_VERSION}".encode()
        ).hexdigest()
        run = AssetSignalRun(
            run_key=run_key,
            task_id=task.id,
            cutoff_policy_version=self.CUTOFF_POLICY_VERSION,
            owner_scope="USER",
            user_id=task.user_id,
            run_type="MANUAL",
            asset_type=task.asset_type,
            as_of_at=cutoff_at,
            cutoff_at=cutoff_at,
            policy_version=self.POLICY_VERSION,
            status="RUNNING",
            counts_json={},
        )
        self.db.add(run)
        await self.db.flush()
        return run

    async def _is_promoted(
        self,
        *,
        asset_type: str,
        horizon_code: str,
        as_of_at: datetime,
        identity: InstrumentIdentity,
        candidate: Any,
    ) -> bool:
        """Require an exact effective model scope rather than any asset-wide row."""
        primary_head = next(
            (
                head
                for head in candidate.prediction_heads
                if head.head_code == candidate.primary_head_code
            ),
            None,
        )
        if primary_head is None:
            return False
        query = select(AssetModelRegistry).where(
            AssetModelRegistry.asset_type == asset_type,
            AssetModelRegistry.horizon_code == horizon_code,
            AssetModelRegistry.status == "PROMOTED",
            AssetModelRegistry.signal_head == primary_head.head_code,
            AssetModelRegistry.head_spec_hash == primary_head.head_spec_hash,
            AssetModelRegistry.target_spec_version == primary_head.target_spec_version,
            AssetModelRegistry.scoreability_rule_version == primary_head.scoreability_rule_version,
            AssetModelRegistry.baseline_version == primary_head.baseline_version,
            AssetModelRegistry.policy_version == self.POLICY_VERSION,
            AssetModelRegistry.model_version == self.MODEL_VERSION,
            AssetModelRegistry.calibration_version == self.CALIBRATION_VERSION,
        )
        records = list((await self.db.execute(query)).scalars())
        for record in records:
            if not self._model_scope_matches(record, identity=identity, as_of_at=as_of_at):
                continue
            if not has_required_model_approvals(record):
                continue
            if record.approved_at is None or record.effective_from is None:
                continue
            if _as_utc(record.approved_at) > _as_utc(as_of_at):
                continue
            if _as_utc(record.training_cutoff_at) > _as_utc(as_of_at):
                continue
            if not has_complete_t2_metrics(record):
                continue
            if await has_matching_promotion_event(self.db, record=record, as_of_at=as_of_at):
                return True
        return False

    @staticmethod
    def _model_scope_matches(
        record: AssetModelRegistry, *, identity: InstrumentIdentity, as_of_at: datetime
    ) -> bool:
        scope = verified_promotion_scope(record)
        if scope is None:
            return False
        effective_from = (
            _as_utc(record.effective_from) if record.effective_from is not None else None
        )
        effective_to = _as_utc(record.effective_to) if record.effective_to is not None else None
        if (effective_from is not None and effective_from > _as_utc(as_of_at)) or (
            effective_to is not None and effective_to < _as_utc(as_of_at)
        ):
            return False
        if scope.asset_type != identity.asset_type:
            return False
        identity_product_type = (identity.product_type or "").strip().upper()
        identity_venue = (identity.venue or "").strip().upper()
        if scope.instrument_class not in {"*", identity_product_type}:
            return False
        if scope.canonical_id and scope.canonical_id != identity.canonical_id:
            return False
        if scope.venue and scope.venue != identity_venue:
            return False
        if scope.product_type and scope.product_type != identity_product_type:
            return False
        if scope.scope_type == "INSTRUMENT_SPECIFIC":
            return scope.canonical_id == identity.canonical_id
        if scope.scope_type == "VENUE_PRODUCT":
            quote_or_settlement_asset = (
                AssetResearchOrchestrator._identity_quote_or_settlement_asset(identity)
            )
            return bool(
                scope.venue
                and scope.product_type
                and scope.quote_or_settlement_asset
                and quote_or_settlement_asset
                and scope.quote_or_settlement_asset == quote_or_settlement_asset
            )
        return scope.scope_type == "POOLED"

    @staticmethod
    def _identity_quote_or_settlement_asset(identity: InstrumentIdentity) -> str | None:
        """Return the P&L currency that a venue/product scope must freeze."""
        details = identity.details
        if isinstance(details, CryptoProductIdentityDetails):
            value = details.settlement_asset_id or details.quote_asset_id
        elif isinstance(details, FxIdentityDetails):
            value = details.settlement_currency or details.quote_currency
        else:
            return None
        return value.strip().upper() if isinstance(value, str) and value.strip() else None

    async def _current_instrument(
        self,
        *,
        canonical_id: str,
        asset_type: str,
        effective_at: datetime | None = None,
    ) -> AssetInstrument:
        effective_at = _as_utc(effective_at or _now())
        records = list(
            (
                await self.db.execute(
                    select(AssetInstrument)
                    .where(
                        AssetInstrument.canonical_id == canonical_id,
                        AssetInstrument.asset_type == asset_type,
                        AssetInstrument.lifecycle_status == "ACTIVE",
                        AssetInstrument.valid_from <= effective_at,
                        or_(
                            AssetInstrument.valid_to.is_(None),
                            AssetInstrument.valid_to >= effective_at,
                        ),
                    )
                    .order_by(desc(AssetInstrument.valid_from))
                )
            )
            .scalars()
            .all()
        )
        return self._latest_unambiguous_instrument(records)

    @staticmethod
    def _instrument_is_current_at(instrument: AssetInstrument, effective_at: datetime) -> bool:
        """Return whether an identity version may be used at this exact cutoff."""
        valid_from = _as_utc(instrument.valid_from)
        valid_to = _as_utc(instrument.valid_to) if instrument.valid_to is not None else None
        effective_at = _as_utc(effective_at)
        return (
            instrument.lifecycle_status == "ACTIVE"
            and valid_from <= effective_at
            and (valid_to is None or valid_to >= effective_at)
        )

    @staticmethod
    def _latest_unambiguous_instrument(records: list[AssetInstrument]) -> AssetInstrument:
        """Return the newest version or fail closed when its authority is tied."""
        if not records:
            raise AssetResearchOrchestrationError("INSTRUMENT_VERSION_STALE")
        newest_valid_from = _as_utc(records[0].valid_from)
        if sum(_as_utc(record.valid_from) == newest_valid_from for record in records) != 1:
            raise AssetResearchOrchestrationError("INSTRUMENT_VERSION_STALE")
        record = records[0]
        try:
            identity = InstrumentIdentity.model_validate(record.identity_json)
        except ValidationError as exc:
            raise AssetResearchOrchestrationError("INSTRUMENT_VERSION_STALE") from exc
        if (
            identity.asset_type != record.asset_type
            or identity.canonical_id != record.canonical_id
            or identity.identity_level != record.identity_level
            or identity.metadata_version != record.metadata_version
            or identity.venue != record.venue
            or identity.currency != record.currency
            or identity.product_type != record.product_type
        ):
            raise AssetResearchOrchestrationError("INSTRUMENT_VERSION_STALE")
        return record

    async def _instrument_for_canonical_id(self, canonical_id: str) -> AssetInstrument:
        effective_at = _now()
        records = list(
            (
                await self.db.execute(
                    select(AssetInstrument)
                    .where(
                        AssetInstrument.canonical_id == canonical_id,
                        AssetInstrument.lifecycle_status == "ACTIVE",
                        AssetInstrument.valid_from <= effective_at,
                        or_(
                            AssetInstrument.valid_to.is_(None),
                            AssetInstrument.valid_to >= effective_at,
                        ),
                    )
                    .order_by(desc(AssetInstrument.valid_from))
                )
            )
            .scalars()
            .all()
        )
        return self._latest_unambiguous_instrument(records)

    @staticmethod
    def _normalized_idempotency_key(idempotency_key: str | None) -> str | None:
        if idempotency_key is None:
            return None
        normalized = idempotency_key.strip()
        if not normalized or len(normalized) > 128:
            raise AssetResearchOrchestrationError("IDEMPOTENCY_KEY_INVALID")
        return normalized

    @staticmethod
    def _validate_position_context_request(request: PositionContextCreateRequest) -> None:
        if request.as_of_at.tzinfo is None:
            raise AssetResearchOrchestrationError("POSITION_CONTEXT_INVALID")
        if request.expires_at is not None:
            if request.expires_at.tzinfo is None or request.expires_at <= request.as_of_at:
                raise AssetResearchOrchestrationError("POSITION_CONTEXT_INVALID")
        long_quantity = request.long_quantity
        short_quantity = request.short_quantity
        valid = {
            "FLAT": long_quantity == 0 and short_quantity == 0,
            "LONG": long_quantity > 0 and short_quantity == 0,
            "SHORT": short_quantity > 0 and long_quantity == 0,
            "UNKNOWN": long_quantity == 0 and short_quantity == 0,
        }
        if not valid[request.position_context]:
            raise AssetResearchOrchestrationError("POSITION_CONTEXT_INVALID")

    async def _position_context_by_idempotency_key(
        self, *, user_id: str, idempotency_key: str
    ) -> AssetPositionContextSnapshot | None:
        return (
            await self.db.execute(
                select(AssetPositionContextSnapshot).where(
                    AssetPositionContextSnapshot.owner_scope == "USER",
                    AssetPositionContextSnapshot.user_id == user_id,
                    AssetPositionContextSnapshot.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()

    async def _task_by_idempotency_key(
        self, *, user_id: str, idempotency_key: str
    ) -> AssetAnalysisTask | None:
        return (
            await self.db.execute(
                select(AssetAnalysisTask).where(
                    AssetAnalysisTask.owner_scope == "USER",
                    AssetAnalysisTask.user_id == user_id,
                    AssetAnalysisTask.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()

    async def _schedule_by_idempotency_key(
        self, *, user_id: str, idempotency_key: str
    ) -> AssetSignalSchedule | None:
        return (
            await self.db.execute(
                select(AssetSignalSchedule).where(
                    AssetSignalSchedule.owner_scope == "USER",
                    AssetSignalSchedule.user_id == user_id,
                    AssetSignalSchedule.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()

    async def _owned_schedule(
        self, *, user_id: str, schedule_id: str
    ) -> AssetSignalSchedule | None:
        return (
            await self.db.execute(
                select(AssetSignalSchedule).where(
                    AssetSignalSchedule.id == schedule_id,
                    AssetSignalSchedule.owner_scope == "USER",
                    AssetSignalSchedule.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    def _validate_schedule_owner(schedule: AssetSignalSchedule) -> None:
        """Defend the worker path if an invalid legacy row bypassed DB checks."""
        if schedule.owner_scope == "USER" and schedule.user_id is not None:
            return
        if schedule.owner_scope in _SYSTEM_SCHEDULE_OWNER_SCOPES and schedule.user_id is None:
            return
        raise AssetResearchOrchestrationError("SCHEDULE_OWNER_INVALID")

    async def _validate_system_schedule_manifest(self, schedule: AssetSignalSchedule) -> None:
        """Reject an orphaned, retired, or changed system schedule before collection."""
        if schedule.owner_scope == "USER":
            return
        if (
            schedule.approved_manifest_id is None
            or schedule.manifest_entry_key is None
            or schedule.manifest_content_hash is None
            or schedule.system_target_key is None
        ):
            raise AssetResearchOrchestrationError("SCHEDULE_MANIFEST_STALE")
        manifest = await self.db.get(AssetScheduleManifest, schedule.approved_manifest_id)
        if (
            manifest is None
            or manifest.status != "ACTIVE"
            or manifest.owner_scope != schedule.owner_scope
            or manifest.content_hash != schedule.manifest_content_hash
        ):
            raise AssetResearchOrchestrationError("SCHEDULE_MANIFEST_STALE")

    @staticmethod
    def _validate_frozen_system_manifest(
        *, schedule: AssetSignalSchedule, frozen: _FrozenScheduleRun
    ) -> None:
        """Keep a retry bound to the exact manifest facts that produced its run."""
        if schedule.owner_scope == "USER":
            return
        config = frozen.schedule_config
        if (
            config.get("approved_manifest_id") != schedule.approved_manifest_id
            or config.get("manifest_entry_key") != schedule.manifest_entry_key
            or config.get("manifest_content_hash") != schedule.manifest_content_hash
        ):
            raise AssetResearchOrchestrationError("SCHEDULE_RETRY_INVALID")

    @staticmethod
    def _system_schedule_target_key(
        *,
        owner_scope: str,
        request: AssetSignalScheduleCreateRequest,
        instrument: AssetInstrument,
    ) -> str:
        """Make duplicate active targets impossible without doing market scans."""
        return canonical_json_hash(
            {
                "owner_scope": owner_scope,
                "asset_type": request.asset_type,
                "canonical_id": instrument.canonical_id,
                "identity_version": instrument.metadata_version,
                "horizon_code": request.horizon_code,
                "horizon_spec": request.horizon_spec.model_dump(mode="json"),
                "cron_expression": request.cron_expression,
                "timezone": request.timezone,
                "cutoff_policy": request.cutoff_policy,
            }
        )

    @staticmethod
    def _validate_cron(cron_expression: str) -> None:
        fields = cron_expression.split()
        if len(fields) != 5 or any(not field.strip() for field in fields):
            raise AssetResearchOrchestrationError("SCHEDULE_CRON_INVALID")

    @staticmethod
    def _validate_timezone(timezone_name: str) -> None:
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise AssetResearchOrchestrationError("SCHEDULE_TIMEZONE_INVALID") from exc

    @classmethod
    def _validate_schedule_request(cls, request: AssetSignalScheduleCreateRequest) -> None:
        cls._validate_cron(request.cron_expression)
        cls._validate_timezone(request.timezone)
        cls._validate_schedule_contract_values(
            asset_type=request.asset_type,
            cron_expression=request.cron_expression,
            timezone_name=request.timezone,
            cutoff_policy=request.cutoff_policy,
        )

    @staticmethod
    def _validate_schedule_contract_values(
        *,
        asset_type: str,
        cron_expression: str,
        timezone_name: str,
        cutoff_policy: str,
    ) -> None:
        try:
            validate_schedule_contract(
                asset_type=asset_type,  # type: ignore[arg-type]
                cron_expression=cron_expression,
                timezone_name=timezone_name,
                cutoff_policy=cutoff_policy,
            )
        except AssetSchedulePolicyError as exc:
            raise AssetResearchOrchestrationError(exc.code) from exc

    async def _validate_position_context(
        self,
        *,
        user_id: str,
        instrument: AssetInstrument,
        requested_position_context: PositionContext,
        snapshot_id: str | None,
    ) -> tuple[str | None, PositionContext]:
        if snapshot_id is None:
            if requested_position_context != "UNKNOWN":
                raise AssetResearchOrchestrationError("POSITION_CONTEXT_INVALID")
            return None, "UNKNOWN"
        snapshot = await self.db.get(AssetPositionContextSnapshot, snapshot_id)
        if snapshot is None:
            raise AssetResearchOrchestrationError("POSITION_CONTEXT_INVALID")
        expired = snapshot.expires_at is not None and snapshot.expires_at <= _now()
        if (
            expired
            or snapshot.owner_scope != "USER"
            or snapshot.user_id != user_id
            or snapshot.instrument_id != instrument.id
            or snapshot.canonical_id != instrument.canonical_id
            or snapshot.identity_version != instrument.metadata_version
        ):
            raise AssetResearchOrchestrationError("POSITION_CONTEXT_INVALID")
        if snapshot.position_context == "FLAT":
            position_context: PositionContext = "FLAT"
        elif snapshot.position_context == "LONG":
            position_context = "LONG"
        elif snapshot.position_context == "SHORT":
            position_context = "SHORT"
        elif snapshot.position_context == "UNKNOWN":
            position_context = "UNKNOWN"
        else:
            raise AssetResearchOrchestrationError("POSITION_CONTEXT_INVALID")
        return snapshot.id, position_context

    async def _normalize_task_position_context_for_cutoff(
        self,
        *,
        task: AssetAnalysisTask,
        instrument: AssetInstrument,
        identity: InstrumentIdentity,
        cutoff_at: datetime,
    ) -> bool:
        """Normalize an immutable context using only facts legal at ``cutoff_at``.

        The task stores the effective research context, not an assertion that a
        brokerage position exists.  In particular, an option close can only be
        authorized from an exact, available, unexpired pure-LONG contract
        snapshot owned by the same user.
        """
        snapshot_id = task.position_context_snapshot_id
        if snapshot_id is None:
            task.position_context = "UNKNOWN"
            return False

        snapshot = await self.db.get(AssetPositionContextSnapshot, snapshot_id)
        cutoff = _as_utc(cutoff_at)
        expires_at = _as_utc(snapshot.expires_at) if snapshot and snapshot.expires_at else None
        valid_snapshot = snapshot is not None and (
            snapshot.owner_scope == "USER"
            and snapshot.user_id == task.user_id
            and snapshot.instrument_id == instrument.id
            and snapshot.asset_type == instrument.asset_type
            and snapshot.canonical_id == instrument.canonical_id
            and snapshot.identity_version == instrument.metadata_version
            and _as_utc(snapshot.as_of_at) <= cutoff
            and _as_utc(snapshot.available_at) <= cutoff
            and (expires_at is None or cutoff < expires_at)
        )
        if not valid_snapshot or snapshot is None:
            task.position_context = "UNKNOWN"
            task.position_context_snapshot_id = None
            return False

        if snapshot.long_quantity > 0 and snapshot.short_quantity == 0:
            normalized_context: PositionContext = "LONG"
        elif snapshot.short_quantity > 0 and snapshot.long_quantity == 0:
            normalized_context = "SHORT"
        elif snapshot.long_quantity == 0 and snapshot.short_quantity == 0:
            normalized_context = "FLAT"
        else:
            normalized_context = "UNKNOWN"

        task.position_context = normalized_context
        if identity.asset_type != "option":
            return False

        # Option v1 needs a finite exact-contract observation for every
        # position-aware action.  An unsupported short or a non-contract
        # identity must not survive as an actionable context.
        if (
            identity.identity_level != "CONTRACT"
            or snapshot.expires_at is None
            or normalized_context == "SHORT"
        ):
            task.position_context = "UNKNOWN"
            task.position_context_snapshot_id = None
            return False
        return normalized_context == "LONG"

    async def _owned_task(self, *, user_id: str, task_id: str) -> AssetAnalysisTask | None:
        return (
            await self.db.execute(
                select(AssetAnalysisTask).where(
                    AssetAnalysisTask.id == task_id,
                    AssetAnalysisTask.owner_scope == "USER",
                    AssetAnalysisTask.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def _owned_prediction(
        self, *, user_id: str, prediction_id: str
    ) -> AssetSignalPrediction | None:
        return (
            await self.db.execute(
                select(AssetSignalPrediction).where(
                    AssetSignalPrediction.id == prediction_id,
                    AssetSignalPrediction.owner_scope == "USER",
                    AssetSignalPrediction.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def _report_for_task(self, task_id: str) -> AssetAnalysisReport | None:
        return (
            (
                await self.db.execute(
                    select(AssetAnalysisReport)
                    .where(AssetAnalysisReport.task_id == task_id)
                    .order_by(desc(AssetAnalysisReport.created_at))
                )
            )
            .scalars()
            .first()
        )

    @staticmethod
    def _public_report_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """Defensively redact candidate and credential fields from legacy report rows."""
        safe_payload = redact_sensitive_data(payload or {})
        if not isinstance(safe_payload, dict):
            return {}
        safe_payload.pop("candidate_decision", None)
        safe_payload.pop("candidate_decision_json", None)
        return safe_payload

    @staticmethod
    def _public_prediction_payload(prediction: AssetSignalPrediction) -> AssetSignalHistoryItem:
        """Create a public DTO that structurally has no candidate field to leak."""
        return AssetSignalHistoryItem(
            prediction_id=prediction.id,
            owner_scope=prediction.owner_scope,
            asset_type=prediction.asset_type,
            canonical_id=prediction.canonical_id,
            as_of_at=prediction.as_of_at,
            horizon_code=prediction.horizon_code,
            position_context=prediction.position_context,
            actionability=prediction.actionability,
            quality_status=prediction.quality_status,
            published_decision=prediction.published_decision_json,
            created_at=prediction.created_at,
        )
