"""Run the opt-in Iteration 197 PostgreSQL acceptance harness.

This command never accepts an application database URL.  It requires an
explicit ``postgresql+asyncpg`` administrative URL whose database is exactly
``postgres``; when ``--apply`` is supplied it creates only UUID-named temporary
databases, upgrades them with Alembic, exercises the real normalized market-data
services and the stamped-legacy constraint portability path, then drops those
same databases in ``finally``.

The default is a dry run: it validates the administrative connection shape but
does not open a connection, create a database, migrate, or fetch any data.
The command emits structured output without a connection URL, username,
password, host, or query values.

Run from ``src/backend``:

    conda run -n base python scripts/verify_iteration197_postgres_acceptance.py \\
      --postgres-admin-url "$ITER197_POSTGRES_ADMIN_URL"

    conda run -n base python scripts/verify_iteration197_postgres_acceptance.py \\
      --apply --postgres-admin-url "$ITER197_POSTGRES_ADMIN_URL"

The URL is intentionally read only from the command line.  A caller must pass
it explicitly for each run; the harness does not fall back to ``DATABASE_URL``
or any environment variable.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import multiprocessing
import os
import queue
import re
import signal
import sys
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from alembic import command

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.asset_research import AssetDataSourceRegistry
from app.models.data_governance import DgProvider
from app.models.market_data_platform import (
    MdCalendarSnapshot,
    MdFetchLease,
    MdObservationRevision,
    MdSourceSnapshot,
)
from app.models.permission import Role, user_roles
from app.models.user import User
from app.schemas.asset_research import InstrumentIdentity
from app.schemas.market_data_platform import MarketDataQueryRequest
from app.services.market_data.access import MarketDataAccessAuthorizer, MarketDataQueryAccess
from app.services.market_data.bootstrap import (
    CanonicalStorageSpec,
    MarketDataBootstrapSpec,
    MarketDataPlatformBootstrapper,
)
from app.services.market_data.calendar_importer import MANIFEST_VERSION, MarketDataCalendarImporter
from app.services.market_data.catalog import DataCatalogResolver
from app.services.market_data.fetch_lease import MarketDataFetchLeaseManager
from app.services.market_data.identity import MarketDataIdentityResolver
from app.services.market_data.master_data import MarketDataIdentityWriter
from app.services.market_data.providers import (
    MarketDataProviderRequest,
    ProviderFetchResult,
    ProviderMarketObservation,
)
from app.services.market_data.query_resolution import MarketDataQueryResolver
from app.services.market_data.query_service import MarketDataQueryService
from app.services.market_data.source_policy import (
    MarketDataProviderRoute,
    MarketDataSourcePolicy,
    MarketDataSourcePolicyRegistry,
)
from app.services.market_data.store import MarketDataStore

UTC = timezone.utc
TEMPORARY_DATABASE_PREFIX = "iter197_pg_acceptance_"
_TEMPORARY_DATABASE_PATTERN = re.compile(rf"^{re.escape(TEMPORARY_DATABASE_PREFIX)}[0-9a-f]{{32}}$")
_ADMIN_DATABASE = "postgres"
_BACKEND_DIRECTORY = Path(__file__).resolve().parent.parent

_REQUIRED_TABLES = frozenset(
    {
        "alembic_version",
        "asset_instruments",
        "dg_datasets",
        "dg_dataset_storages",
        "dg_providers",
        "dg_storage_targets",
        "md_calendar_events",
        "md_calendar_import_locks",
        "md_calendar_snapshots",
        "md_data_series",
        "md_fetch_leases",
        "md_instrument_identity_revisions",
        "md_instrument_lookup_keys",
        "md_observation_revisions",
        "md_publications",
        "md_source_snapshots",
        "md_visibility_sequence_allocator",
        "users",
        "user_roles",
    }
)
_UTC_TIMESTAMP_COLUMNS: Mapping[str, frozenset[str]] = {
    "md_publications": frozenset({"published_at", "created_at"}),
    "md_source_snapshots": frozenset({"retrieved_at", "created_at"}),
    "md_observation_revisions": frozenset(
        {"event_time", "available_at", "committed_at", "created_at"}
    ),
    "md_calendar_snapshots": frozenset({"created_at"}),
    "md_calendar_events": frozenset({"event_start", "event_end", "created_at"}),
    "md_fetch_leases": frozenset({"expires_at", "created_at", "updated_at", "released_at"}),
}

CANONICAL_ID = "instrument:stock:CN-SSE:600000"
WINDOW_START = datetime(2026, 9, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 9, 3, tzinfo=UTC)
RECEIPT_AT = datetime(2026, 9, 3, 7, tzinfo=UTC)
_PROCESS_EVENT_TIMEOUT_SECONDS = 20.0
_PROCESS_RESULT_TIMEOUT_SECONDS = 30.0
_FAULT_LEASE_TTL = timedelta(seconds=4)
_FAULT_TAKEOVER_TIMEOUT_SECONDS = 12.0
_FAULT_TERMINATED_LEADER_BLOCK_TIMEOUT_SECONDS = (
    _PROCESS_EVENT_TIMEOUT_SECONDS
    + _PROCESS_RESULT_TIMEOUT_SECONDS
    + _FAULT_TAKEOVER_TIMEOUT_SECONDS
)
_PORTABILITY_PREDECESSOR_REVISION = "20260909_market_data_exact_identity_collation"
_POSTGRES_IDENTIFIER_LIMIT = 63

_FAULT_PHASE_RUNNER_STARTED = "runner_started"
_FAULT_PHASE_RUNNER_RECEIPT_READY = "runner_receipt_ready"
_FAULT_PHASE_STORE_BEFORE_PERSIST = "store_before_persist"
_FAULT_PHASE_STORE_AFTER_PERSIST = "store_after_persist"
_FAULT_PHASE_LEASE_RELEASE_STARTED = "lease_release_started"


class PostgresAcceptanceHarnessError(RuntimeError):
    """Stable, non-secret failure emitted by the disposable acceptance command."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class _LegacyConstraintCase:
    """One renamed CHECK whose old PostgreSQL identifier was truncated."""

    table_name: str
    portable_name: str
    legacy_name: str

    @property
    def postgres_truncated_legacy_name(self) -> str:
        """Return PostgreSQL's deterministic 63-byte result for this ASCII identifier."""
        return self.legacy_name[:_POSTGRES_IDENTIFIER_LIMIT]


_LEGACY_CONSTRAINT_CASES = (
    _LegacyConstraintCase(
        table_name="md_source_snapshots",
        portable_name="ck_md_srcsnap_provider_req_fp_sha256_len",
        legacy_name="ck_md_source_snapshot_provider_request_fingerprint_sha256_length",
    ),
    _LegacyConstraintCase(
        table_name="md_source_snapshots",
        portable_name="ck_md_srcsnap_src_auth_desc_sha256_len",
        legacy_name="ck_md_source_snapshot_source_authorization_descriptor_sha256_length",
    ),
    _LegacyConstraintCase(
        table_name="md_calendar_snapshots",
        portable_name="ck_md_calsnap_src_gov_desc_sha256_len",
        legacy_name="ck_md_calendar_snapshot_source_governance_descriptor_sha256_length",
    ),
)


@dataclass(frozen=True, slots=True)
class _LegacyConstraintFixture:
    """Identifiers and content digests needed to prove an upgrade preserves sentinels."""

    source_snapshot_id: str
    calendar_snapshot_id: str
    provider_request_fingerprint_sha256: str
    source_authorization_descriptor_sha256: str
    source_payload_sha256: str
    calendar_governance_descriptor_sha256: str
    calendar_snapshot_sha256: str


@dataclass(frozen=True, slots=True)
class _LegacyConstraintPortabilityEvidence:
    """Safe facts emitted after a stamped predecessor PostgreSQL upgrade."""

    predecessor_revision: str
    current_head: str
    legacy_truncated_constraint_count: int
    portable_constraint_count: int
    source_snapshot_count: int
    calendar_snapshot_count: int
    sentinels_preserved: bool
    short_digest_rejected: bool
    truncated_legacy_to_portable: Mapping[str, str]

    def as_dict(self) -> dict[str, object]:
        return {
            "predecessor_revision": self.predecessor_revision,
            "current_head": self.current_head,
            "legacy_truncated_constraint_count": self.legacy_truncated_constraint_count,
            "portable_constraint_count": self.portable_constraint_count,
            "source_snapshot_count": self.source_snapshot_count,
            "calendar_snapshot_count": self.calendar_snapshot_count,
            "sentinels_preserved": self.sentinels_preserved,
            "short_digest_rejected": self.short_digest_rejected,
            "truncated_legacy_to_portable": dict(self.truncated_legacy_to_portable),
        }


@dataclass(frozen=True, slots=True)
class _TwoProcessExactGapEvidence:
    """Evidence from two separate OS processes against one empty exact gap."""

    process_count: int
    distinct_process_count: int
    provider_call_count: int
    follower_provider_call_count: int
    follower_initial_lease_held: bool
    follower_local_only_fetch_count: int
    follower_local_only_complete: bool
    follower_local_only_observation_count: int
    source_snapshot_count: int
    observation_revision_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "process_count": self.process_count,
            "distinct_process_count": self.distinct_process_count,
            "provider_call_count": self.provider_call_count,
            "follower_provider_call_count": self.follower_provider_call_count,
            "follower_initial_lease_held": self.follower_initial_lease_held,
            "follower_separate_session_local_only": {
                "coverage_complete": self.follower_local_only_complete,
                "fetch_count": self.follower_local_only_fetch_count,
                "observation_count": self.follower_local_only_observation_count,
            },
            "source_snapshot_count": self.source_snapshot_count,
            "observation_revision_count": self.observation_revision_count,
        }


@dataclass(frozen=True, slots=True)
class _FaultPhaseSpec:
    """One deterministic interruption boundary for a fresh logical coverage gap.

    ``receipt_durable_before_fault`` describes the source receipt rather than
    the fake runner's in-memory response: the runner response is never called
    durable until ``MarketDataStore.persist_provider_result`` has returned.
    """

    phase: str
    canonical_id: str
    receipt_durable_before_fault: bool
    release_expected_after_cancellation: bool


_FAULT_PHASE_SPECS = (
    _FaultPhaseSpec(
        phase=_FAULT_PHASE_RUNNER_STARTED,
        canonical_id="instrument:stock:CN-SSE:600001",
        receipt_durable_before_fault=False,
        release_expected_after_cancellation=True,
    ),
    _FaultPhaseSpec(
        phase=_FAULT_PHASE_RUNNER_RECEIPT_READY,
        canonical_id="instrument:stock:CN-SSE:600002",
        receipt_durable_before_fault=False,
        release_expected_after_cancellation=True,
    ),
    _FaultPhaseSpec(
        phase=_FAULT_PHASE_STORE_BEFORE_PERSIST,
        canonical_id="instrument:stock:CN-SSE:600003",
        receipt_durable_before_fault=False,
        release_expected_after_cancellation=True,
    ),
    _FaultPhaseSpec(
        phase=_FAULT_PHASE_STORE_AFTER_PERSIST,
        canonical_id="instrument:stock:CN-SSE:600004",
        receipt_durable_before_fault=True,
        release_expected_after_cancellation=True,
    ),
    _FaultPhaseSpec(
        phase=_FAULT_PHASE_LEASE_RELEASE_STARTED,
        canonical_id="instrument:stock:CN-SSE:600005",
        receipt_durable_before_fault=True,
        release_expected_after_cancellation=False,
    ),
)
_TERMINATED_RUNNER_CANONICAL_ID = "instrument:stock:CN-SSE:600006"
_STALE_RUNNER_CANONICAL_ID = "instrument:stock:CN-SSE:600007"
_FAULT_PHASE_ORDER = tuple(spec.phase for spec in _FAULT_PHASE_SPECS)
_ALL_HARNESS_CANONICAL_IDS = (
    CANONICAL_ID,
    *(spec.canonical_id for spec in _FAULT_PHASE_SPECS),
    _TERMINATED_RUNNER_CANONICAL_ID,
    _STALE_RUNNER_CANONICAL_ID,
)


@dataclass(frozen=True, slots=True)
class _CancelledFaultPhaseEvidence:
    """One cancellation observation and its separate-process recovery facts."""

    phase: str
    leader_process_id: int
    leader_provider_call_count: int
    release_completed_after_cancellation: bool
    follower_process_id: int
    follower_provider_call_count: int
    follower_local_only_complete: bool
    source_snapshot_delta: int
    observation_revision_delta: int
    expired_lease_takeover_fence_token: int | None

    def as_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "leader_process_id": self.leader_process_id,
            "leader_provider_call_count": self.leader_provider_call_count,
            "lease_release_completed_after_cancellation": self.release_completed_after_cancellation,
            "follower_process_id": self.follower_process_id,
            "follower_provider_call_count": self.follower_provider_call_count,
            "follower_local_only_complete": self.follower_local_only_complete,
            "source_snapshot_delta": self.source_snapshot_delta,
            "observation_revision_delta": self.observation_revision_delta,
            "expired_lease_takeover_fence_token": self.expired_lease_takeover_fence_token,
        }


@dataclass(frozen=True, slots=True)
class _TerminatedRunnerTakeoverEvidence:
    """A killed owner after runner start, its blocked follower, and expiry takeover."""

    leader_process_id: int
    blocked_follower_process_id: int
    takeover_process_id: int
    provider_attempt_count: int
    blocked_follower_provider_call_count: int
    takeover_provider_call_count: int
    source_snapshot_delta: int
    observation_revision_delta: int

    def as_dict(self) -> dict[str, object]:
        return {
            "leader_process_id": self.leader_process_id,
            "blocked_follower_process_id": self.blocked_follower_process_id,
            "takeover_process_id": self.takeover_process_id,
            "provider_attempt_count": self.provider_attempt_count,
            "blocked_follower_provider_call_count": self.blocked_follower_provider_call_count,
            "takeover_provider_call_count": self.takeover_provider_call_count,
            "source_snapshot_delta": self.source_snapshot_delta,
            "observation_revision_delta": self.observation_revision_delta,
        }


@dataclass(frozen=True, slots=True)
class _StaleRunnerTakeoverEvidence:
    """A resumed stale owner whose fenced write is rejected after takeover."""

    leader_process_id: int
    blocked_follower_process_id: int
    takeover_process_id: int
    provider_attempt_count: int
    stale_leader_warning_codes: tuple[str, ...]
    source_snapshot_delta: int
    observation_revision_delta: int

    def as_dict(self) -> dict[str, object]:
        return {
            "leader_process_id": self.leader_process_id,
            "blocked_follower_process_id": self.blocked_follower_process_id,
            "takeover_process_id": self.takeover_process_id,
            "provider_attempt_count": self.provider_attempt_count,
            "stale_leader_warning_codes": list(self.stale_leader_warning_codes),
            "source_snapshot_delta": self.source_snapshot_delta,
            "observation_revision_delta": self.observation_revision_delta,
        }


@dataclass(frozen=True, slots=True)
class _FaultTakeoverEvidence:
    """Bounded fixture-only proof of cancellation and owner-death recovery."""

    cancelled_phases: tuple[_CancelledFaultPhaseEvidence, ...]
    stale_runner_start: _StaleRunnerTakeoverEvidence
    terminated_runner_start: _TerminatedRunnerTakeoverEvidence

    def as_dict(self) -> dict[str, object]:
        return {
            "fixture": "deterministic_fake_runner_no_network",
            "cancelled_phases": [item.as_dict() for item in self.cancelled_phases],
            "stale_runner_start": self.stale_runner_start.as_dict(),
            "terminated_runner_start": self.terminated_runner_start.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class _HarnessResult:
    """Safe operator evidence produced after an accepted temporary-db run."""

    alembic_head: str
    first_session_timezone: str
    second_session_timezone: str
    provider_calls: int
    source_snapshot_count: int
    observation_revision_count: int
    local_only_fetch_count: int
    lease_successful_contender_count: int
    lease_fence_token: int
    two_process_exact_gap: _TwoProcessExactGapEvidence
    fault_takeover: _FaultTakeoverEvidence

    def as_dict(self) -> dict[str, object]:
        return {
            "alembic_head": self.alembic_head,
            "session_time_zones": [self.first_session_timezone, self.second_session_timezone],
            "provider_calls": self.provider_calls,
            "source_snapshot_count": self.source_snapshot_count,
            "observation_revision_count": self.observation_revision_count,
            "local_only_fetch_count": self.local_only_fetch_count,
            "independent_connection_lease": {
                "successful_contender_count": self.lease_successful_contender_count,
                "winner_fence_token": self.lease_fence_token,
            },
            "two_process_exact_gap": self.two_process_exact_gap.as_dict(),
            "fault_takeover": self.fault_takeover.as_dict(),
        }


class _FaultCheckpointController:
    """Inject one harness-only cancellation or wait point without provider I/O.

    This object is instantiated only inside spawned acceptance workers.  It is
    deliberately not a production adapter seam: the application providers and
    runtime configuration cannot construct or receive it.
    """

    def __init__(
        self,
        *,
        cancellation_phase: str | None = None,
        blocked_phase: str | None = None,
        reached_event: Any | None = None,
        unblock_event: Any | None = None,
        continue_after_unblock: bool = False,
        event_wait_timeout_seconds: float = _PROCESS_EVENT_TIMEOUT_SECONDS,
    ) -> None:
        if (cancellation_phase is None) == (blocked_phase is None):
            raise ValueError("exactly one fault checkpoint action is required")
        if cancellation_phase is not None:
            _fault_phase_spec(cancellation_phase)
        if blocked_phase is not None:
            _fault_phase_spec(blocked_phase)
        self._cancellation_phase = cancellation_phase
        self._blocked_phase = blocked_phase
        self._reached_event = reached_event
        self._unblock_event = unblock_event
        self._continue_after_unblock = continue_after_unblock
        self._event_wait_timeout_seconds = event_wait_timeout_seconds
        self.reached_phases: list[str] = []

    async def checkpoint(self, phase: str) -> None:
        """Record one boundary, then inject only the reviewed selected fault."""
        self.reached_phases.append(phase)
        if phase == self._cancellation_phase:
            raise asyncio.CancelledError
        if phase != self._blocked_phase:
            return
        if self._reached_event is not None:
            self._reached_event.set()
        if self._unblock_event is None:
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_FAULT_BLOCK_CONFIGURATION_INVALID"
            )
        unblocked = await asyncio.to_thread(
            self._unblock_event.wait,
            self._event_wait_timeout_seconds,
        )
        if not unblocked:
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_BLOCK_TIMEOUT")
        if self._continue_after_unblock:
            return
        # The parent only sets this event while cleaning up an unhappy child.
        # Never let that cleanup accidentally continue to receipt persistence.
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_BLOCK_UNEXPECTED_UNBLOCK")


class _CheckpointingMarketDataStore(MarketDataStore):
    """Real store behavior with two explicit fixture-only interruption points."""

    def __init__(self, db: AsyncSession, *, checkpoints: _FaultCheckpointController) -> None:
        super().__init__(db)
        self._checkpoints = checkpoints

    async def persist_provider_result(self, *args: Any, **kwargs: Any) -> Any:
        """Expose before/after durable receipt boundaries without replacing storage."""
        await self._checkpoints.checkpoint(_FAULT_PHASE_STORE_BEFORE_PERSIST)
        persisted = await super().persist_provider_result(*args, **kwargs)
        await self._checkpoints.checkpoint(_FAULT_PHASE_STORE_AFTER_PERSIST)
        return persisted


class _CheckpointingFetchLeases:
    """Delegate real PostgreSQL leases while exposing only harness release timing."""

    def __init__(
        self,
        leases: MarketDataFetchLeaseManager,
        *,
        checkpoints: _FaultCheckpointController,
    ) -> None:
        self._leases = leases
        self._checkpoints = checkpoints
        self.lease_key_sha256: str | None = None
        self.fence_token: int | None = None
        self.release_started = False
        self.release_completed = False

    async def acquire(self, lease_key_sha256: str) -> Any:
        """Delegate exact durable acquisition and retain non-secret evidence fields."""
        handle = await self._leases.acquire(lease_key_sha256)
        if handle is not None:
            self.lease_key_sha256 = handle.lease_key_sha256
            self.fence_token = handle.fence_token
        return handle

    async def release(self, handle: Any) -> bool:
        """Reach the release boundary before delegating the real release mutation."""
        self.release_started = True
        await self._checkpoints.checkpoint(_FAULT_PHASE_LEASE_RELEASE_STARTED)
        released = await self._leases.release(handle)
        self.release_completed = True
        return released


class _DeterministicProvider:
    """A bounded adapter used only by this acceptance harness; it never does I/O."""

    def __init__(
        self,
        *,
        provider_started_event: Any | None = None,
        provider_release_event: Any | None = None,
        checkpoints: _FaultCheckpointController | None = None,
        provider_attempt_counter: Any | None = None,
        event_wait_timeout_seconds: float = _PROCESS_EVENT_TIMEOUT_SECONDS,
    ) -> None:
        self.calls: list[MarketDataProviderRequest] = []
        self._provider_started_event = provider_started_event
        self._provider_release_event = provider_release_event
        self._checkpoints = checkpoints
        self._provider_attempt_counter = provider_attempt_counter
        self._event_wait_timeout_seconds = event_wait_timeout_seconds

    async def fetch(self, request: MarketDataProviderRequest) -> ProviderFetchResult:
        self.calls.append(request)
        if self._provider_attempt_counter is not None:
            with self._provider_attempt_counter.get_lock():
                self._provider_attempt_counter.value += 1
        if self._provider_started_event is not None:
            self._provider_started_event.set()
        if self._checkpoints is not None:
            await self._checkpoints.checkpoint(_FAULT_PHASE_RUNNER_STARTED)
        if self._provider_release_event is not None:
            released = await asyncio.to_thread(
                self._provider_release_event.wait,
                self._event_wait_timeout_seconds,
            )
            if not released:
                raise PostgresAcceptanceHarnessError(
                    "POSTGRES_ACCEPTANCE_TWO_PROCESS_PROVIDER_RELEASE_TIMEOUT"
                )
        if self._checkpoints is not None:
            # This is a bounded in-memory fixture result. It is intentionally
            # not called a durable receipt until the real Store returns below.
            await self._checkpoints.checkpoint(_FAULT_PHASE_RUNNER_RECEIPT_READY)
        observations = tuple(
            ProviderMarketObservation(
                event_at=event_at,
                available_at=event_at + timedelta(hours=6),
                fields={
                    field_name: (10.0 if field_name == "close" else 1000)
                    for field_name in request.required_fields
                },
            )
            for event_at in (WINDOW_START, WINDOW_START + timedelta(days=1))
        )
        return ProviderFetchResult(
            provider_id="akshare",
            source_revision=f"postgres-acceptance-{len(self.calls)}",
            retrieved_at=RECEIPT_AT,
            observations=observations,
            raw_payload={
                "fixture": "iteration197-postgres-acceptance",
                "request_number": len(self.calls),
                "records": [
                    {"event_at": row.event_at.isoformat(), "fields": dict(row.fields)}
                    for row in observations
                ],
            },
            request=request,
        )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--postgres-admin-url",
        required=True,
        help=(
            "Explicit postgresql+asyncpg administrative URL ending in /postgres. "
            "It is never read from DATABASE_URL or an environment variable."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Create, migrate, verify, and delete UUID-named temporary databases; "
            "includes one stamped legacy-constraint portability upgrade."
        ),
    )
    return parser.parse_args()


def _parse_admin_url(value: object) -> URL:
    """Accept only a PostgreSQL async admin connection, never an app database."""
    if not isinstance(value, str) or not value.strip():
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_ADMIN_URL_REQUIRED")
    try:
        parsed = make_url(value.strip())
    except Exception as exc:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_ADMIN_URL_INVALID") from exc
    if parsed.get_backend_name().lower() not in {"postgresql", "postgres"}:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_POSTGRES_REQUIRED")
    if parsed.get_driver_name().lower() != "asyncpg":
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_ASYNCPG_REQUIRED")
    if parsed.database != _ADMIN_DATABASE:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_ADMIN_DATABASE_UNSAFE")
    return parsed


def _temporary_database_name() -> str:
    """Return the only database name this command may create or delete."""
    return f"{TEMPORARY_DATABASE_PREFIX}{uuid.uuid4().hex}"


def _require_own_temporary_database(database_name: object) -> str:
    """Reject every name except one generated by this harness's strict protocol."""
    if not isinstance(database_name, str) or not _TEMPORARY_DATABASE_PATTERN.fullmatch(
        database_name
    ):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_DATABASE_NAME_UNSAFE")
    return database_name


def _quoted_temporary_database(database_name: object) -> str:
    """Return a quoted identifier after strict whitelist validation, never raw input."""
    return f'"{_require_own_temporary_database(database_name)}"'


def _target_url(admin_url: URL, database_name: str) -> URL:
    """Build a target URL only after it has passed the temporary-name gate."""
    _require_own_temporary_database(database_name)
    return admin_url.set(database=database_name)


def _safe_connection_descriptor(admin_url: URL) -> dict[str, object]:
    """Expose connection shape without exposing any URL component with identity/secrets."""
    return {
        "backend": admin_url.get_backend_name().lower(),
        "driver": admin_url.get_driver_name().lower(),
        "admin_database": _ADMIN_DATABASE,
        "uses_host_or_socket": bool(admin_url.host or admin_url.query.get("host")),
    }


def _url_text(url: URL) -> str:
    """Keep full URL conversion in one internal-only function that never prints it."""
    return url.render_as_string(hide_password=False)


def _alembic_url_text(url: URL) -> str:
    """Escape ConfigParser interpolation while retaining the internal URL value."""
    return _url_text(url).replace("%", "%%")


def _admin_engine(admin_url: URL) -> AsyncEngine:
    """Create a non-pooled autocommit engine for CREATE/DROP DATABASE commands."""
    return create_async_engine(
        _url_text(admin_url),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )


def _target_engine(target_url: URL) -> AsyncEngine:
    """Use a fresh UTC-configured connection for every acceptance session."""
    return create_async_engine(
        _url_text(target_url),
        connect_args={"server_settings": {"timezone": "UTC"}},
        poolclass=NullPool,
    )


async def _create_temporary_database(
    admin_url: URL,
    database_name: str,
    *,
    on_created: Callable[[str], None] | None = None,
) -> None:
    """Create one generated database and register cleanup immediately after CREATE."""
    quoted_name = _quoted_temporary_database(database_name)
    engine = _admin_engine(admin_url)
    try:
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
                {"database_name": database_name},
            )
            if exists is not None:
                raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_DATABASE_COLLISION")
            await connection.execute(text(f"CREATE DATABASE {quoted_name}"))
            # Register the owned cleanup obligation before the connection
            # context or engine disposal can fail.  The callback only runs
            # after PostgreSQL accepted CREATE, so a collision can never
            # cause cleanup to target a database this harness did not create.
            if on_created is not None:
                on_created(database_name)
    except PostgresAcceptanceHarnessError:
        raise
    except Exception as exc:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_DATABASE_CREATE_FAILED") from exc
    finally:
        await engine.dispose()


async def _drop_temporary_database(admin_url: URL, database_name: str) -> None:
    """Terminate only temporary-db sessions, then drop only the generated database."""
    quoted_name = _quoted_temporary_database(database_name)
    engine = _admin_engine(admin_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            await connection.execute(text(f"DROP DATABASE {quoted_name}"))
    except Exception as exc:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_DATABASE_CLEANUP_FAILED") from exc
    finally:
        await engine.dispose()


def _alembic_config(target_url: URL) -> Config:
    """Build an Alembic configuration whose only target is the generated database."""
    config = Config(str(_BACKEND_DIRECTORY / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_DIRECTORY / "alembic"))
    config.set_main_option("sqlalchemy.url", _alembic_url_text(target_url))
    return config


def _run_alembic_upgrade_to_revision(target_url: URL, revision: str) -> None:
    """Run Alembic only against a generated temporary database at one revision."""
    try:
        command.upgrade(_alembic_config(target_url), revision)
    except Exception as exc:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_ALEMBIC_UPGRADE_FAILED") from exc


def _run_alembic_upgrade(target_url: URL) -> str:
    """Run the project's normal Alembic head path against the disposable target."""
    config = _alembic_config(target_url)
    _run_alembic_upgrade_to_revision(target_url, "head")
    try:
        head = ScriptDirectory.from_config(config).get_current_head()
    except Exception as exc:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_ALEMBIC_HEAD_INVALID") from exc
    if not isinstance(head, str) or not head:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_ALEMBIC_HEAD_INVALID")
    return head


def _missing_tables(sync_connection: Any) -> tuple[str, ...]:
    inspector = sa.inspect(sync_connection)
    available = set(inspector.get_table_names())
    return tuple(sorted(_REQUIRED_TABLES - available))


async def _assert_schema_and_timezone(
    session: AsyncSession,
    *,
    expected_alembic_head: str,
) -> str:
    """Verify one fresh connection is UTC and all required 197 structures exist."""
    timezone_name = await _assert_utc_session_timezone(session)
    connection = await session.connection()
    missing_tables = await connection.run_sync(_missing_tables)
    if missing_tables:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_REQUIRED_TABLE_MISSING")
    revision_rows = (
        (await session.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
    )
    if revision_rows != [expected_alembic_head]:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_ALEMBIC_VERSION_MISMATCH")
    timestamp_rows = await session.execute(
        text(
            "SELECT table_name, column_name, data_type "
            "FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = ANY(:table_names)"
        ),
        {"table_names": list(_UTC_TIMESTAMP_COLUMNS)},
    )
    observed_types = {
        (str(table_name), str(column_name)): str(data_type).lower()
        for table_name, column_name, data_type in timestamp_rows
    }
    for table_name, column_names in _UTC_TIMESTAMP_COLUMNS.items():
        for column_name in column_names:
            if observed_types.get((table_name, column_name)) != "timestamp with time zone":
                raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_TIMESTAMP_NOT_UTC")
    return timezone_name


async def _assert_utc_session_timezone(session: AsyncSession) -> str:
    """Verify the UTC session invariant on one fresh PostgreSQL connection."""
    timezone_name = str(await session.scalar(text("SHOW TIME ZONE")) or "")
    if timezone_name.upper() not in {"UTC", "ETC/UTC"}:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_SESSION_TIMEZONE_NOT_UTC")
    return timezone_name


async def _assert_alembic_revision(session: AsyncSession, expected_revision: str) -> None:
    """Fail closed unless the disposable database has exactly one expected revision."""
    revision_rows = (
        (await session.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
    )
    if revision_rows != [expected_revision]:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_ALEMBIC_VERSION_MISMATCH")


def _check_constraint_names(sync_connection: Any, table_name: str) -> frozenset[str]:
    """Return named checks reflected by PostgreSQL from one known table."""
    return frozenset(
        str(check["name"])
        for check in sa.inspect(sync_connection).get_check_constraints(table_name)
        if check.get("name")
    )


async def _reflected_check_constraint_names(
    session: AsyncSession,
    table_name: str,
) -> frozenset[str]:
    """Reflect current PostgreSQL CHECK names through this session's connection."""
    connection = await session.connection()
    return await connection.run_sync(_check_constraint_names, table_name)


def _fixture_digest(label: str) -> str:
    """Generate a deterministic non-secret SHA-256 value for the legacy fixture."""
    return hashlib.sha256(f"iteration197-postgres-legacy:{label}".encode()).hexdigest()


async def _seed_stamped_legacy_constraint_fixture(
    target_url: URL,
) -> _LegacyConstraintFixture:
    """Seed sentinels and let PostgreSQL truncate the simulated old CHECK names."""
    engine = _target_engine(target_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    source_snapshot_id = str(uuid.uuid4())
    calendar_snapshot_id = str(uuid.uuid4())
    fixture = _LegacyConstraintFixture(
        source_snapshot_id=source_snapshot_id,
        calendar_snapshot_id=calendar_snapshot_id,
        provider_request_fingerprint_sha256=_fixture_digest("provider-request"),
        source_authorization_descriptor_sha256=_fixture_digest("source-authorization"),
        source_payload_sha256=_fixture_digest("source-payload"),
        calendar_governance_descriptor_sha256=_fixture_digest("calendar-governance"),
        calendar_snapshot_sha256=_fixture_digest("calendar-snapshot"),
    )
    try:
        async with session_factory() as session:
            await _assert_utc_session_timezone(session)
            await _assert_alembic_revision(session, _PORTABILITY_PREDECESSOR_REVISION)
            provider = DgProvider(
                id=str(uuid.uuid4()),
                provider_id="iteration197-legacy-portability",
                name="Iteration 197 legacy portability fixture",
                category="market_data",
                auth_type="none",
                rate_limit=1,
                is_active=True,
            )
            source_snapshot = MdSourceSnapshot(
                id=fixture.source_snapshot_id,
                provider_id=provider.id,
                platform="iteration197-postgres-acceptance",
                source_id="legacy-constraint-portability-fixture",
                adapter_id="iteration197.legacy.fixture",
                endpoint_version="v1",
                request_fingerprint_sha256=_fixture_digest("query-request"),
                provider_request_id="iteration197-legacy-portability-request-0001",
                provider_request_fingerprint_sha256=(fixture.provider_request_fingerprint_sha256),
                query_fingerprint_sha256=_fixture_digest("query-fingerprint"),
                source_authorization_state="VERIFIED",
                source_authorization_descriptor_sha256=(
                    fixture.source_authorization_descriptor_sha256
                ),
                payload_sha256=fixture.source_payload_sha256,
                request_json={"fixture": "legacy_constraint_portability"},
                payload_manifest_json={"fixture": "legacy_constraint_portability"},
                provenance_json={"fixture": "legacy_constraint_portability"},
                source_observed_at=RECEIPT_AT,
                source_published_at=RECEIPT_AT,
                retrieved_at=RECEIPT_AT,
                created_at=RECEIPT_AT,
            )
            calendar_snapshot = MdCalendarSnapshot(
                id=fixture.calendar_snapshot_id,
                calendar_code="ITER197-LEGACY-PORTABILITY",
                calendar_version="v1",
                timezone_name="UTC",
                source_registry_id="iteration197-legacy-fixture",
                source_governance_state="VERIFIED",
                source_governance_descriptor_sha256=(fixture.calendar_governance_descriptor_sha256),
                source_snapshot_id=fixture.source_snapshot_id,
                snapshot_sha256=fixture.calendar_snapshot_sha256,
                definition_json={"fixture": "legacy_constraint_portability"},
                effective_from=date(2026, 9, 1),
                effective_to=date(2026, 9, 3),
                created_at=RECEIPT_AT,
            )
            session.add_all((provider, source_snapshot, calendar_snapshot))
            await session.commit()

        # These values are internal constants, never operator input. PostgreSQL
        # performs the historical 63-byte truncation when it receives each old
        # long name; the following reflection verifies the actual result.
        async with engine.begin() as connection:
            for case in _LEGACY_CONSTRAINT_CASES:
                await connection.execute(
                    text(
                        f'ALTER TABLE "{case.table_name}" '
                        f'RENAME CONSTRAINT "{case.portable_name}" '
                        f'TO "{case.legacy_name}"'
                    )
                )

        async with session_factory() as session:
            await _assert_utc_session_timezone(session)
            await _assert_alembic_revision(session, _PORTABILITY_PREDECESSOR_REVISION)
            for case in _LEGACY_CONSTRAINT_CASES:
                names = await _reflected_check_constraint_names(session, case.table_name)
                if case.postgres_truncated_legacy_name not in names or case.portable_name in names:
                    raise PostgresAcceptanceHarnessError(
                        "POSTGRES_ACCEPTANCE_LEGACY_TRUNCATION_NOT_OBSERVED"
                    )
        return fixture
    finally:
        await engine.dispose()


async def _verify_stamped_legacy_constraint_upgrade(
    target_url: URL,
    *,
    fixture: _LegacyConstraintFixture,
    current_head: str,
) -> _LegacyConstraintPortabilityEvidence:
    """Verify the portable rename, sentinel preservation, and enforced CHECK."""
    engine = _target_engine(target_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            await _assert_schema_and_timezone(session, expected_alembic_head=current_head)
            for case in _LEGACY_CONSTRAINT_CASES:
                names = await _reflected_check_constraint_names(session, case.table_name)
                if case.portable_name not in names or case.postgres_truncated_legacy_name in names:
                    raise PostgresAcceptanceHarnessError(
                        "POSTGRES_ACCEPTANCE_PORTABLE_CONSTRAINT_NOT_OBSERVED"
                    )
            source_snapshot = await session.get(MdSourceSnapshot, fixture.source_snapshot_id)
            calendar_snapshot = await session.get(MdCalendarSnapshot, fixture.calendar_snapshot_id)
            if (
                source_snapshot is None
                or calendar_snapshot is None
                or source_snapshot.provider_request_fingerprint_sha256
                != fixture.provider_request_fingerprint_sha256
                or source_snapshot.source_authorization_descriptor_sha256
                != fixture.source_authorization_descriptor_sha256
                or source_snapshot.payload_sha256 != fixture.source_payload_sha256
                or calendar_snapshot.source_snapshot_id != fixture.source_snapshot_id
                or calendar_snapshot.source_governance_descriptor_sha256
                != fixture.calendar_governance_descriptor_sha256
                or calendar_snapshot.snapshot_sha256 != fixture.calendar_snapshot_sha256
            ):
                raise PostgresAcceptanceHarnessError(
                    "POSTGRES_ACCEPTANCE_LEGACY_SENTINEL_NOT_PRESERVED"
                )
            source_snapshot_count = int(
                await session.scalar(select(func.count()).select_from(MdSourceSnapshot)) or 0
            )
            calendar_snapshot_count = int(
                await session.scalar(select(func.count()).select_from(MdCalendarSnapshot)) or 0
            )
            if source_snapshot_count != 1 or calendar_snapshot_count != 1:
                raise PostgresAcceptanceHarnessError(
                    "POSTGRES_ACCEPTANCE_LEGACY_SENTINEL_COUNT_INVALID"
                )

        short_digest_rejected = False
        async with session_factory() as session:
            try:
                await session.execute(
                    text(
                        "UPDATE md_source_snapshots "
                        "SET provider_request_fingerprint_sha256 = :invalid_digest "
                        "WHERE id = :snapshot_id"
                    ),
                    {"invalid_digest": "short", "snapshot_id": fixture.source_snapshot_id},
                )
                await session.commit()
            except sa.exc.IntegrityError:
                short_digest_rejected = True
                await session.rollback()
        if not short_digest_rejected:
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_PORTABLE_CHECK_NOT_ENFORCED")

        async with session_factory() as session:
            source_snapshot = await session.get(MdSourceSnapshot, fixture.source_snapshot_id)
            if (
                source_snapshot is None
                or source_snapshot.provider_request_fingerprint_sha256
                != fixture.provider_request_fingerprint_sha256
            ):
                raise PostgresAcceptanceHarnessError(
                    "POSTGRES_ACCEPTANCE_LEGACY_SENTINEL_NOT_PRESERVED"
                )
        return _LegacyConstraintPortabilityEvidence(
            predecessor_revision=_PORTABILITY_PREDECESSOR_REVISION,
            current_head=current_head,
            legacy_truncated_constraint_count=len(_LEGACY_CONSTRAINT_CASES),
            portable_constraint_count=len(_LEGACY_CONSTRAINT_CASES),
            source_snapshot_count=source_snapshot_count,
            calendar_snapshot_count=calendar_snapshot_count,
            sentinels_preserved=True,
            short_digest_rejected=short_digest_rejected,
            truncated_legacy_to_portable={
                case.postgres_truncated_legacy_name: case.portable_name
                for case in _LEGACY_CONSTRAINT_CASES
            },
        )
    finally:
        await engine.dispose()


def _run_legacy_constraint_portability_stage(
    target_url: URL,
) -> _LegacyConstraintPortabilityEvidence:
    """Simulate a stamped old PostgreSQL candidate before upgrading it to head."""
    try:
        _run_alembic_upgrade_to_revision(target_url, _PORTABILITY_PREDECESSOR_REVISION)
        fixture = asyncio.run(_seed_stamped_legacy_constraint_fixture(target_url))
        current_head = _run_alembic_upgrade(target_url)
        return asyncio.run(
            _verify_stamped_legacy_constraint_upgrade(
                target_url,
                fixture=fixture,
                current_head=current_head,
            )
        )
    except PostgresAcceptanceHarnessError:
        raise
    except Exception as exc:
        raise PostgresAcceptanceHarnessError(
            "POSTGRES_ACCEPTANCE_LEGACY_PORTABILITY_STAGE_FAILED"
        ) from exc


def _request(*, mode: str, canonical_id: str = CANONICAL_ID) -> MarketDataQueryRequest:
    """Build a deterministic bars request accepted by the real internal resolver."""
    if canonical_id not in _ALL_HARNESS_CANONICAL_IDS:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_IDENTITY_INVALID")
    return MarketDataQueryRequest.model_validate(
        {
            "identity": {"canonical_id": canonical_id},
            "dataset_code": "market.bars",
            "data_kind": "bars",
            "frequency": "1d",
            "start": WINDOW_START.isoformat(),
            "end": WINDOW_END.isoformat(),
            "required_fields": ["close", "volume"],
            "adjustment": "qfq",
            "price_basis": "close",
            "currency": "CNY",
            "unit": "share",
            "source_policy_id": "market-default-v1",
            "mode": mode,
        }
    )


def _policy(provider: _DeterministicProvider) -> MarketDataSourcePolicyRegistry:
    """Keep provider behavior deterministic while exercising the real route policy path."""
    route = MarketDataProviderRoute(
        route_id="postgres-acceptance-akshare-stock-v1",
        request_provider="akshare",
        expected_result_provider_ids=frozenset({"akshare"}),
        asset_types=frozenset({"stock"}),
        data_kinds=frozenset({"bars"}),
        frequencies=frozenset({"1d"}),
        markets=frozenset({"CN-SSE"}),
        adjustments=frozenset({"qfq"}),
        price_bases=frozenset({"close"}),
        currencies=frozenset({"CNY"}),
        units=frozenset({"share"}),
        adapter=provider,
    )
    return MarketDataSourcePolicyRegistry(
        (
            MarketDataSourcePolicy(
                policy_id="market-default-v1",
                allowed_purposes=frozenset({"display"}),
                routes=(route,),
            ),
        )
    )


def _service(
    session: AsyncSession,
    provider: _DeterministicProvider,
    *,
    now: datetime,
    allow_online_fetch: bool,
    fetch_leases: Any | None = None,
    store: MarketDataStore | None = None,
) -> MarketDataQueryService:
    """Construct the production service graph around a disposable session."""
    return MarketDataQueryService(
        resolver=MarketDataQueryResolver(
            catalog=DataCatalogResolver(session),
            identities=MarketDataIdentityResolver(session),
            # The harness calls the service layer directly to isolate database
            # semantics. Public HTTP requests retain the v2 family-binding gate.
            allow_unbound_internal_requests=True,
        ),
        store=store if store is not None else MarketDataStore(session, clock=lambda: now),
        source_policies=_policy(provider),
        allow_online_fetch=allow_online_fetch,
        clock=lambda: now,
        cursor_signing_key="iteration197-postgres-acceptance-cursor-key-material-0000000000000001",
        fetch_leases=fetch_leases,
    )


async def _seed_prerequisites(
    session: AsyncSession,
    *,
    target_url: URL,
    canonical_ids: tuple[str, ...] = (CANONICAL_ID,),
) -> str:
    """Seed reviewed control-plane prerequisites before any local-first request."""
    if (
        not canonical_ids
        or len(set(canonical_ids)) != len(canonical_ids)
        or any(canonical_id not in _ALL_HARNESS_CANONICAL_IDS for canonical_id in canonical_ids)
    ):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_IDENTITY_INVALID")
    spec = MarketDataBootstrapSpec(
        storage=CanonicalStorageSpec.from_database_url(_url_text(target_url)),
    )
    await MarketDataPlatformBootstrapper(session).bootstrap(spec)
    await session.commit()

    user = User(
        username="iteration197-postgres-acceptance",
        email="iteration197-postgres-acceptance@example.test",
        hashed_password="not-used",
        is_active=True,
    )
    session.add(user)
    session.add(
        AssetDataSourceRegistry(
            source_id="akshare",
            asset_types=["stock"],
            jurisdictions=["CN"],
            license_status="APPROVED",
            allowed_uses=["DISPLAY"],
            redistribution_policy="NO_REDISTRIBUTION",
            derived_data_policy="ALLOWED",
            retention_policy="market-data-v1",
            effective_from=datetime(2020, 1, 1, tzinfo=UTC),
            enabled=True,
            updated_at=RECEIPT_AT,
        )
    )
    await session.flush()
    await session.execute(user_roles.insert().values(user_id=user.id, role=Role.USER.value))
    user_id = str(user.id)
    await session.commit()

    writer = MarketDataIdentityWriter(session)
    for canonical_id in canonical_ids:
        display_symbol = canonical_id.rsplit(":", maxsplit=1)[-1]
        identity = InstrumentIdentity.model_validate(
            {
                "asset_type": "stock",
                "identity_level": "ASSET",
                "canonical_id": canonical_id,
                "display_symbol": display_symbol,
                "name": "PostgreSQL验收股票",
                "venue": "CN-SSE",
                "currency": "CNY",
                "timezone": "Asia/Shanghai",
                "identifier_type": "EXCHANGE_SYMBOL",
                "identifier_value": f"{display_symbol}.SH",
                "product_type": "EQUITY",
                "metadata_version": "market-v1",
                "details": {
                    "kind": "STOCK",
                    "exchange_symbol": f"{display_symbol}.SH",
                },
            }
        )
        await writer.persist_identity(identity, valid_from=datetime(2026, 8, 1, tzinfo=UTC))
        await session.commit()
    await writer.publish_staged()
    await MarketDataCalendarImporter(session).import_payload(
        payload={
            "manifest_version": MANIFEST_VERSION,
            "approval_reference": "CAB-197-POSTGRES-ACCEPTANCE",
            "evidence_uri": "file:///approved/calendars/CN-SSE-2026-09.json",
            "evidence_content_hash": "a" * 64,
            "source_registry_id": "akshare",
            "calendar_code": "CN-SSE",
            "calendar_version": "2026.09",
            "timezone_name": "Asia/Shanghai",
            "coverage_start_at": WINDOW_START.isoformat(),
            "coverage_end_at": WINDOW_END.isoformat(),
            "events": [
                {
                    "trading_date": "2026-09-01",
                    "event_type": "session",
                    "session_code": "bars-daily-close",
                    "is_trading_day": True,
                    "event_start": WINDOW_START.isoformat(),
                    "event_end": (WINDOW_START + timedelta(hours=6)).isoformat(),
                    "coverage": {"data_kind": "bars", "frequency": "1d"},
                    "event_payload": {"provider_observation_key": "daily-close"},
                },
                {
                    "trading_date": "2026-09-02",
                    "event_type": "session",
                    "session_code": "bars-daily-close",
                    "is_trading_day": True,
                    "event_start": (WINDOW_START + timedelta(days=1)).isoformat(),
                    "event_end": (WINDOW_START + timedelta(days=1, hours=6)).isoformat(),
                    "coverage": {"data_kind": "bars", "frequency": "1d"},
                    "event_payload": {"provider_observation_key": "daily-close"},
                },
            ],
        },
        dry_run=False,
    )
    await session.commit()
    return user_id


async def _access_for_session(
    session: AsyncSession,
    *,
    user_id: str,
    now: datetime,
) -> MarketDataQueryAccess:
    """Build a fresh current-principal grant from the temporary database."""
    user = await session.get(User, user_id)
    if user is None:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_USER_MISSING")
    authorizer = MarketDataAccessAuthorizer(session, clock=lambda: now)
    principal = await authorizer.principal_for_user(user)
    return MarketDataQueryAccess(principal=principal, authorizer=authorizer)


def _fault_phase_spec(phase: object) -> _FaultPhaseSpec:
    """Return one reviewed fixture boundary; arbitrary phase injection is forbidden."""
    if not isinstance(phase, str):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_PHASE_INVALID")
    for spec in _FAULT_PHASE_SPECS:
        if spec.phase == phase:
            return spec
    raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_PHASE_INVALID")


def _fault_reached_phases(spec: _FaultPhaseSpec) -> tuple[str, ...]:
    """Return the exact checkpoints the real service must pass before one fault."""
    phase_index = _FAULT_PHASE_ORDER.index(spec.phase)
    return _FAULT_PHASE_ORDER[: phase_index + 1]


async def _fault_persistence_counts(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[int, int]:
    """Read only aggregate counts needed to prove one scenario's durable delta."""
    async with session_factory() as session:
        source_snapshot_count = int(
            await session.scalar(select(func.count()).select_from(MdSourceSnapshot)) or 0
        )
        observation_revision_count = int(
            await session.scalar(select(func.count()).select_from(MdObservationRevision)) or 0
        )
    return source_snapshot_count, observation_revision_count


def _fault_count_delta(
    before: tuple[int, int],
    after: tuple[int, int],
) -> tuple[int, int]:
    """Compute a small monotonic persistence delta and reject impossible removals."""
    source_snapshot_delta = after[0] - before[0]
    observation_revision_delta = after[1] - before[1]
    if source_snapshot_delta < 0 or observation_revision_delta < 0:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_PERSISTENCE_REGRESSED")
    return source_snapshot_delta, observation_revision_delta


def _fault_report_bool(report: Mapping[str, object], field_name: str) -> bool:
    """Read one exact boolean from internal IPC without truthiness coercion."""
    value = report.get(field_name)
    if type(value) is not bool:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_REPORT_INVALID")
    return value


def _fault_report_texts(report: Mapping[str, object], field_name: str) -> tuple[str, ...]:
    """Read a bounded list of checkpoint names from an internal worker report."""
    value = report.get(field_name)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_REPORT_INVALID")
    return tuple(value)


def _validate_cancelled_fault_report(
    report: Mapping[str, object],
    *,
    spec: _FaultPhaseSpec,
) -> tuple[str, int]:
    """Reject any cancellation report that overstates release or receipt state."""
    if (
        _process_report_text(report, "kind") != "fault_cancellation"
        or _process_report_text(report, "status") != "cancelled"
        or _process_report_text(report, "phase") != spec.phase
    ):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_REPORT_INVALID")
    process_id = _process_report_int(report, "pid")
    provider_call_count = _process_report_int(report, "provider_call_count")
    fence_token = _process_report_int(report, "fence_token")
    lease_key_sha256 = _process_report_text(report, "lease_key_sha256")
    if (
        process_id <= 0
        or provider_call_count != 1
        or fence_token < 1
        or not re.fullmatch(r"[0-9a-f]{64}", lease_key_sha256)
        or _fault_report_texts(report, "reached_phases") != _fault_reached_phases(spec)
        or not _fault_report_bool(report, "release_started")
        or _fault_report_bool(report, "release_completed")
        != spec.release_expected_after_cancellation
    ):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_REPORT_INVALID")
    return lease_key_sha256, fence_token


def _validate_fault_follower_report(
    report: Mapping[str, object],
    *,
    mode: str,
    provider_call_count: int,
    coverage_status: str,
    lease_held: bool = False,
) -> int:
    """Validate one independent follower without treating its report as trusted input."""
    if (
        _process_report_text(report, "kind") != "fault_follower"
        or _process_report_text(report, "status") != "ok"
        or _process_report_text(report, "mode") != mode
        or _process_report_int(report, "provider_call_count") != provider_call_count
        or _process_report_int(report, "fetch_count") != provider_call_count
        or _process_report_text(report, "coverage_status") != coverage_status
        or _process_report_text(report, "session_timezone").upper() not in {"UTC", "ETC/UTC"}
    ):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_FOLLOWER_INVALID")
    warning_codes = _fault_report_texts(report, "warning_codes")
    if ("FETCH_LEASE_HELD" in warning_codes) != lease_held:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_FOLLOWER_INVALID")
    process_id = _process_report_int(report, "pid")
    if process_id <= 0:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_FOLLOWER_INVALID")
    if mode == "local_only" and _process_report_int(report, "observation_count") != 2:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_FOLLOWER_INVALID")
    return process_id


async def _wait_for_process_event(event: Any, *, code: str) -> None:
    """Wait for one bounded cross-process checkpoint without blocking the loop."""
    reached = await asyncio.to_thread(event.wait, _PROCESS_EVENT_TIMEOUT_SECONDS)
    if not reached:
        raise PostgresAcceptanceHarnessError(code)


async def _receive_process_message(
    channel: Any,
    *,
    timeout_seconds: float,
    timeout_code: str,
) -> dict[str, object]:
    """Receive one small IPC report and reject malformed or delayed messages."""
    try:
        message = await asyncio.to_thread(channel.get, True, timeout_seconds)
    except queue.Empty as exc:
        raise PostgresAcceptanceHarnessError(timeout_code) from exc
    if not isinstance(message, Mapping):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_TWO_PROCESS_MESSAGE_INVALID")
    return dict(message)


def _process_report_int(report: Mapping[str, object], field_name: str) -> int:
    """Read one intentionally small numeric IPC field without coercion."""
    value = report.get(field_name)
    if type(value) is not int:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_TWO_PROCESS_MESSAGE_INVALID")
    return value


def _process_report_text(report: Mapping[str, object], field_name: str) -> str:
    """Read one intentionally small textual IPC field without coercion."""
    value = report.get(field_name)
    if not isinstance(value, str):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_TWO_PROCESS_MESSAGE_INVALID")
    return value


def _process_report_warning_codes(report: Mapping[str, object]) -> tuple[str, ...]:
    """Validate provider-free follower diagnostics transported over IPC."""
    raw_codes = report.get("initial_warning_codes")
    if not isinstance(raw_codes, list) or not all(isinstance(code, str) for code in raw_codes):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_TWO_PROCESS_MESSAGE_INVALID")
    return tuple(raw_codes)


def _validate_two_process_worker_reports(
    reports: tuple[Mapping[str, object], ...],
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    """Validate leader/follower facts before treating the IPC run as evidence."""
    if len(reports) != 2:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_TWO_PROCESS_REPORT_COUNT_INVALID")
    if any(
        _process_report_text(report, "kind") != "result"
        or _process_report_text(report, "status") != "ok"
        for report in reports
    ):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_TWO_PROCESS_WORKER_FAILED")

    process_ids = tuple(_process_report_int(report, "pid") for report in reports)
    if any(process_id <= 0 for process_id in process_ids) or len(set(process_ids)) != 2:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_TWO_PROCESS_IDENTITY_INVALID")

    provider_call_counts = tuple(
        _process_report_int(report, "provider_call_count") for report in reports
    )
    if sorted(provider_call_counts) != [0, 1]:
        raise PostgresAcceptanceHarnessError(
            "POSTGRES_ACCEPTANCE_TWO_PROCESS_PROVIDER_COUNT_INVALID"
        )
    leader = next(
        report for report in reports if _process_report_int(report, "provider_call_count") == 1
    )
    follower = next(
        report for report in reports if _process_report_int(report, "provider_call_count") == 0
    )

    if (
        _process_report_text(leader, "initial_coverage_status") != "complete"
        or _process_report_int(leader, "initial_fetch_count") != 1
    ):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_TWO_PROCESS_LEADER_FETCH_FAILED")
    if _process_report_int(
        follower, "initial_fetch_count"
    ) != 0 or "FETCH_LEASE_HELD" not in _process_report_warning_codes(follower):
        raise PostgresAcceptanceHarnessError(
            "POSTGRES_ACCEPTANCE_TWO_PROCESS_FOLLOWER_LEASE_NOT_OBSERVED"
        )
    for report in reports:
        if _process_report_text(report, "initial_session_timezone").upper() not in {
            "UTC",
            "ETC/UTC",
        } or _process_report_text(report, "local_only_session_timezone").upper() not in {
            "UTC",
            "ETC/UTC",
        }:
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_SESSION_TIMEZONE_NOT_UTC")
    if (
        _process_report_text(follower, "local_only_coverage_status") != "complete"
        or _process_report_int(follower, "local_only_fetch_count") != 0
        or _process_report_int(follower, "local_only_observation_count") != 2
    ):
        raise PostgresAcceptanceHarnessError(
            "POSTGRES_ACCEPTANCE_TWO_PROCESS_FOLLOWER_REREAD_FAILED"
        )
    return leader, follower


async def _run_two_process_worker(
    target_url_text: str,
    user_id: str,
    query_now_text: str,
    start_event: Any,
    provider_started_event: Any,
    provider_release_event: Any,
    follower_initial_finished_event: Any,
    leader_completed_event: Any,
    ready_queue: Any,
    result_queue: Any,
) -> None:
    """Run one real service worker; all coordination is through process-safe IPC."""
    target_url = make_url(target_url_text)
    _require_own_temporary_database(target_url.database)
    query_now = datetime.fromisoformat(query_now_text)
    if query_now.tzinfo is None:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_TWO_PROCESS_TIME_INVALID")
    query_now = query_now.astimezone(UTC)
    engine = _target_engine(target_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        ready_queue.put({"kind": "ready", "pid": os.getpid()})
        await _wait_for_process_event(
            start_event,
            code="POSTGRES_ACCEPTANCE_TWO_PROCESS_START_TIMEOUT",
        )
        provider = _DeterministicProvider(
            provider_started_event=provider_started_event,
            provider_release_event=provider_release_event,
        )
        async with session_factory() as initial_session:
            initial_timezone = await _assert_utc_session_timezone(initial_session)
            initial = await _service(
                initial_session,
                provider,
                now=query_now,
                allow_online_fetch=True,
                fetch_leases=MarketDataFetchLeaseManager(
                    initial_session,
                    lease_ttl=timedelta(minutes=1),
                ),
            ).execute(
                _request(mode="local_first"),
                access=await _access_for_session(
                    initial_session,
                    user_id=user_id,
                    now=query_now,
                ),
            )
            await initial_session.commit()

        provider_call_count = len(provider.calls)
        if provider_call_count == 0:
            follower_initial_finished_event.set()
        elif provider_call_count == 1:
            # Signal only after the persistence path has committed and the
            # initial session is closed, so followers reread a durable source.
            leader_completed_event.set()
        else:
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_TWO_PROCESS_PROVIDER_COUNT_INVALID"
            )
        if provider_call_count == 0:
            await _wait_for_process_event(
                leader_completed_event,
                code="POSTGRES_ACCEPTANCE_TWO_PROCESS_LEADER_COMPLETION_TIMEOUT",
            )

        async with session_factory() as local_only_session:
            local_only_timezone = await _assert_utc_session_timezone(local_only_session)
            local_only = await _service(
                local_only_session,
                provider,
                now=query_now + timedelta(microseconds=2),
                allow_online_fetch=False,
            ).execute(
                _request(mode="local_only"),
                access=await _access_for_session(
                    local_only_session,
                    user_id=user_id,
                    now=query_now + timedelta(microseconds=2),
                ),
            )

        result_queue.put(
            {
                "kind": "result",
                "status": "ok",
                "pid": os.getpid(),
                "provider_call_count": provider_call_count,
                "initial_coverage_status": initial.coverage.status.value,
                "initial_fetch_count": len(initial.fetches),
                "initial_warning_codes": [warning.code for warning in initial.warnings],
                "initial_session_timezone": initial_timezone,
                "local_only_coverage_status": local_only.coverage.status.value,
                "local_only_fetch_count": len(local_only.fetches),
                "local_only_observation_count": len(local_only.observations),
                "local_only_session_timezone": local_only_timezone,
            }
        )
    finally:
        await engine.dispose()


def _two_process_worker(
    target_url_text: str,
    user_id: str,
    query_now_text: str,
    start_event: Any,
    provider_started_event: Any,
    provider_release_event: Any,
    follower_initial_finished_event: Any,
    leader_completed_event: Any,
    ready_queue: Any,
    result_queue: Any,
) -> None:
    """Report only a stable non-secret failure code from a spawned process."""
    try:
        asyncio.run(
            _run_two_process_worker(
                target_url_text,
                user_id,
                query_now_text,
                start_event,
                provider_started_event,
                provider_release_event,
                follower_initial_finished_event,
                leader_completed_event,
                ready_queue,
                result_queue,
            )
        )
    except Exception:
        result_queue.put(
            {
                "kind": "result",
                "status": "error",
                "pid": os.getpid(),
                "code": "POSTGRES_ACCEPTANCE_TWO_PROCESS_WORKER_FAILED",
            }
        )


async def _join_two_process_workers(processes: tuple[Any, ...]) -> None:
    """Require clean worker exits before the owner drops the temporary database."""
    for process in processes:
        if process.pid is not None:
            await asyncio.to_thread(process.join, _PROCESS_RESULT_TIMEOUT_SECONDS)
    if any(
        process.pid is None or process.is_alive() or process.exitcode != 0 for process in processes
    ):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_TWO_PROCESS_EXIT_FAILED")


async def _stop_two_process_workers(processes: tuple[Any, ...]) -> None:
    """Reap every harness-owned worker before any generated database is dropped.

    A finite ``join`` alone is not cleanup evidence: a process can ignore
    SIGTERM and retain a database connection after this helper returns.  This
    harness owns every supplied child, so it may escalate exactly those live
    processes to ``kill``.  If they still survive, fail closed instead of
    reporting an acceptance result or attempting to hide the leak with a DB
    drop.
    """
    try:
        for process in processes:
            if process.pid is not None and process.is_alive():
                process.terminate()
        for process in processes:
            if process.pid is not None:
                await asyncio.to_thread(process.join, _PROCESS_EVENT_TIMEOUT_SECONDS)

        survivors = [
            process for process in processes if process.pid is not None and process.is_alive()
        ]
        for process in survivors:
            kill = getattr(process, "kill", None)
            if not callable(kill):
                raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_TWO_PROCESS_EXIT_FAILED")
            kill()
        for process in survivors:
            await asyncio.to_thread(process.join, _PROCESS_EVENT_TIMEOUT_SECONDS)
    except PostgresAcceptanceHarnessError:
        raise
    except Exception as exc:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_TWO_PROCESS_EXIT_FAILED") from exc

    if any(process.pid is not None and process.is_alive() for process in processes):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_TWO_PROCESS_EXIT_FAILED")


def _close_process_queue(channel: Any) -> None:
    """Release parent queue threads after every completed or failed IPC run."""
    try:
        channel.close()
        channel.join_thread()
    except (AttributeError, OSError, ValueError):
        return


async def _run_fault_cancellation_worker(
    target_url_text: str,
    user_id: str,
    canonical_id: str,
    phase: str,
    result_queue: Any,
) -> None:
    """Cancel one owned request at a reviewed boundary and report only safe facts."""
    target_url = make_url(target_url_text)
    _require_own_temporary_database(target_url.database)
    spec = _fault_phase_spec(phase)
    if canonical_id != spec.canonical_id:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_IDENTITY_INVALID")
    engine = _target_engine(target_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    checkpoints = _FaultCheckpointController(cancellation_phase=phase)
    try:
        async with session_factory() as session:
            query_now = datetime.now(UTC) + timedelta(minutes=10)
            provider = _DeterministicProvider(checkpoints=checkpoints)
            leases = _CheckpointingFetchLeases(
                MarketDataFetchLeaseManager(session, lease_ttl=_FAULT_LEASE_TTL),
                checkpoints=checkpoints,
            )
            try:
                await _service(
                    session,
                    provider,
                    now=query_now,
                    allow_online_fetch=True,
                    # The fault stage intentionally uses a production-clock
                    # Store. A tiny lease TTL must not be compared to the
                    # synthetic query cutoff used by the legacy harness path.
                    store=_CheckpointingMarketDataStore(session, checkpoints=checkpoints),
                    fetch_leases=leases,
                ).execute(
                    _request(mode="local_first", canonical_id=canonical_id),
                    access=await _access_for_session(
                        session,
                        user_id=user_id,
                        now=query_now,
                    ),
                )
            except asyncio.CancelledError:
                if session.in_transaction():
                    await session.rollback()
            else:
                raise PostgresAcceptanceHarnessError(
                    "POSTGRES_ACCEPTANCE_FAULT_CANCELLATION_NOT_DELIVERED"
                )
            if leases.lease_key_sha256 is None or leases.fence_token is None:
                raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_LEASE_MISSING")
            result_queue.put(
                {
                    "kind": "fault_cancellation",
                    "status": "cancelled",
                    "phase": phase,
                    "pid": os.getpid(),
                    "provider_call_count": len(provider.calls),
                    "reached_phases": list(checkpoints.reached_phases),
                    "lease_key_sha256": leases.lease_key_sha256,
                    "fence_token": leases.fence_token,
                    "release_started": leases.release_started,
                    "release_completed": leases.release_completed,
                }
            )
    finally:
        await engine.dispose()


def _fault_cancellation_worker(
    target_url_text: str,
    user_id: str,
    canonical_id: str,
    phase: str,
    result_queue: Any,
) -> None:
    """Keep spawned failure output stable and free from connection details."""
    try:
        asyncio.run(
            _run_fault_cancellation_worker(
                target_url_text,
                user_id,
                canonical_id,
                phase,
                result_queue,
            )
        )
    except BaseException:
        result_queue.put(
            {
                "kind": "fault_cancellation",
                "status": "error",
                "pid": os.getpid(),
                "code": "POSTGRES_ACCEPTANCE_FAULT_CANCELLATION_WORKER_FAILED",
            }
        )


async def _run_fault_follower_worker(
    target_url_text: str,
    user_id: str,
    canonical_id: str,
    mode: str,
    result_queue: Any,
    provider_attempt_counter: Any | None = None,
) -> None:
    """Use a fresh process/session for one follower or post-expiry takeover read."""
    if mode not in {"local_first", "local_only"}:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_MODE_INVALID")
    if canonical_id not in _ALL_HARNESS_CANONICAL_IDS:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_IDENTITY_INVALID")
    target_url = make_url(target_url_text)
    _require_own_temporary_database(target_url.database)
    engine = _target_engine(target_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            query_now = datetime.now(UTC) + timedelta(minutes=10)
            provider = _DeterministicProvider(provider_attempt_counter=provider_attempt_counter)
            execution = await _service(
                session,
                provider,
                now=query_now,
                allow_online_fetch=mode == "local_first",
                # This is a real Store and real lease manager against the
                # generated database; the only fixture is the no-I/O provider.
                store=MarketDataStore(session),
                fetch_leases=(
                    MarketDataFetchLeaseManager(session, lease_ttl=_FAULT_LEASE_TTL)
                    if mode == "local_first"
                    else None
                ),
            ).execute(
                _request(mode=mode, canonical_id=canonical_id),
                access=await _access_for_session(
                    session,
                    user_id=user_id,
                    now=query_now,
                ),
            )
            await session.commit()
            result_queue.put(
                {
                    "kind": "fault_follower",
                    "status": "ok",
                    "mode": mode,
                    "pid": os.getpid(),
                    "provider_call_count": len(provider.calls),
                    "fetch_count": len(execution.fetches),
                    "coverage_status": execution.coverage.status.value,
                    "warning_codes": [warning.code for warning in execution.warnings],
                    "observation_count": len(execution.observations),
                    "session_timezone": await _assert_utc_session_timezone(session),
                }
            )
    finally:
        await engine.dispose()


def _fault_follower_worker(
    target_url_text: str,
    user_id: str,
    canonical_id: str,
    mode: str,
    result_queue: Any,
    provider_attempt_counter: Any | None = None,
) -> None:
    """Return one compact follower result rather than a child traceback."""
    try:
        asyncio.run(
            _run_fault_follower_worker(
                target_url_text,
                user_id,
                canonical_id,
                mode,
                result_queue,
                provider_attempt_counter,
            )
        )
    except BaseException:
        result_queue.put(
            {
                "kind": "fault_follower",
                "status": "error",
                "pid": os.getpid(),
                "code": "POSTGRES_ACCEPTANCE_FAULT_FOLLOWER_WORKER_FAILED",
            }
        )


async def _run_fault_worker_for_report(
    context: Any,
    *,
    target: Any,
    args: tuple[Any, ...],
    timeout_code: str,
) -> Mapping[str, object]:
    """Start, reap, and drain one short-lived fault worker before returning its IPC fact."""
    result_queue = context.Queue()
    process = context.Process(target=target, args=(*args, result_queue))
    try:
        process.start()
        report = await _receive_process_message(
            result_queue,
            timeout_seconds=_PROCESS_RESULT_TIMEOUT_SECONDS,
            timeout_code=timeout_code,
        )
        await _join_two_process_workers((process,))
        return report
    finally:
        await _stop_two_process_workers((process,))
        _close_process_queue(result_queue)


async def _verify_two_process_exact_gap(
    target_url: URL,
    *,
    user_id: str,
    query_now: datetime,
    session_factory: async_sessionmaker[AsyncSession],
) -> _TwoProcessExactGapEvidence:
    """Prove one exact local-first gap uses one durable source across two OS processes."""
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    provider_started_event = context.Event()
    provider_release_event = context.Event()
    follower_initial_finished_event = context.Event()
    leader_completed_event = context.Event()
    ready_queue = context.Queue()
    result_queue = context.Queue()
    worker_args = (
        _url_text(target_url),
        user_id,
        query_now.isoformat(),
        start_event,
        provider_started_event,
        provider_release_event,
        follower_initial_finished_event,
        leader_completed_event,
        ready_queue,
        result_queue,
    )
    processes = tuple(
        context.Process(target=_two_process_worker, args=worker_args) for _ in range(2)
    )
    try:
        for process in processes:
            process.start()
        ready_reports_list: list[Mapping[str, object]] = []
        for _ in processes:
            ready_reports_list.append(
                await _receive_process_message(
                    ready_queue,
                    timeout_seconds=_PROCESS_EVENT_TIMEOUT_SECONDS,
                    timeout_code="POSTGRES_ACCEPTANCE_TWO_PROCESS_READY_TIMEOUT",
                )
            )
        ready_reports = tuple(ready_reports_list)
        ready_process_ids = tuple(_process_report_int(report, "pid") for report in ready_reports)
        if (
            any(_process_report_text(report, "kind") != "ready" for report in ready_reports)
            or len(set(ready_process_ids)) != 2
        ):
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_TWO_PROCESS_IDENTITY_INVALID")

        start_event.set()
        await _wait_for_process_event(
            provider_started_event,
            code="POSTGRES_ACCEPTANCE_TWO_PROCESS_PROVIDER_START_TIMEOUT",
        )
        await _wait_for_process_event(
            follower_initial_finished_event,
            code="POSTGRES_ACCEPTANCE_TWO_PROCESS_FOLLOWER_TIMEOUT",
        )
        # Keep the leader blocked until the other process has finished its
        # initial local-first path. This makes the follower's zero-I/O result
        # a real exact-gap contention observation rather than a warm-cache hit.
        provider_release_event.set()

        reports_list: list[Mapping[str, object]] = []
        for _ in processes:
            reports_list.append(
                await _receive_process_message(
                    result_queue,
                    timeout_seconds=_PROCESS_RESULT_TIMEOUT_SECONDS,
                    timeout_code="POSTGRES_ACCEPTANCE_TWO_PROCESS_RESULT_TIMEOUT",
                )
            )
        reports = tuple(reports_list)
        await _join_two_process_workers(processes)
        _leader, follower = _validate_two_process_worker_reports(reports)

        async with session_factory() as inspector_session:
            source_snapshot_count = int(
                await inspector_session.scalar(select(func.count()).select_from(MdSourceSnapshot))
                or 0
            )
            observation_revision_count = int(
                await inspector_session.scalar(
                    select(func.count()).select_from(MdObservationRevision)
                )
                or 0
            )
        if source_snapshot_count != 1 or observation_revision_count != 2:
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_TWO_PROCESS_PERSISTENCE_COUNT_INVALID"
            )
        return _TwoProcessExactGapEvidence(
            process_count=len(reports),
            distinct_process_count=len({_process_report_int(report, "pid") for report in reports}),
            provider_call_count=sum(
                _process_report_int(report, "provider_call_count") for report in reports
            ),
            follower_provider_call_count=_process_report_int(follower, "provider_call_count"),
            follower_initial_lease_held=True,
            follower_local_only_fetch_count=_process_report_int(follower, "local_only_fetch_count"),
            follower_local_only_complete=True,
            follower_local_only_observation_count=_process_report_int(
                follower,
                "local_only_observation_count",
            ),
            source_snapshot_count=source_snapshot_count,
            observation_revision_count=observation_revision_count,
        )
    finally:
        # Unblock an unhappy child first, then terminate it if it still has not
        # exited. This happens before the caller can drop the generated DB.
        start_event.set()
        provider_release_event.set()
        leader_completed_event.set()
        await _stop_two_process_workers(processes)
        _close_process_queue(ready_queue)
        _close_process_queue(result_queue)


async def _fault_lease_state(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    lease_key_sha256: str,
) -> tuple[bool, int]:
    """Return whether one exact fault lease is released and its current fence."""
    async with session_factory() as session:
        stored = await session.scalar(
            select(MdFetchLease).where(MdFetchLease.lease_key_sha256 == lease_key_sha256)
        )
    if stored is None or int(stored.fence_token) < 1:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_LEASE_STATE_INVALID")
    released = (
        stored.owner_token is None and stored.expires_at is None and stored.released_at is not None
    )
    active = (
        stored.owner_token is not None
        and stored.expires_at is not None
        and stored.released_at is None
    )
    if not released and not active:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_LEASE_STATE_INVALID")
    return released, int(stored.fence_token)


async def _take_over_expired_fault_lease(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    lease_key_sha256: str,
    prior_fence_token: int,
) -> int:
    """Require a fresh session to advance an unreleased fixture lease only after expiry."""
    deadline = asyncio.get_running_loop().time() + _FAULT_TAKEOVER_TIMEOUT_SECONDS
    while True:
        async with session_factory() as session:
            manager = MarketDataFetchLeaseManager(session, lease_ttl=_FAULT_LEASE_TTL)
            handle = await manager.acquire(lease_key_sha256)
            if handle is not None:
                if handle.fence_token <= prior_fence_token:
                    raise PostgresAcceptanceHarnessError(
                        "POSTGRES_ACCEPTANCE_FAULT_LEASE_FENCE_NOT_ADVANCED"
                    )
                if not await manager.release(handle):
                    raise PostgresAcceptanceHarnessError(
                        "POSTGRES_ACCEPTANCE_FAULT_LEASE_TAKEOVER_RELEASE_FAILED"
                    )
                return handle.fence_token
        if asyncio.get_running_loop().time() >= deadline:
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_LEASE_TAKEOVER_TIMEOUT")
        await asyncio.sleep(0.1)


async def _verify_cancelled_fault_phase(
    target_url: URL,
    *,
    user_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    spec: _FaultPhaseSpec,
) -> _CancelledFaultPhaseEvidence:
    """Cancel a leader at one point, then prove the proper follower recovery path."""
    context = multiprocessing.get_context("spawn")
    before = await _fault_persistence_counts(session_factory)
    leader_report = await _run_fault_worker_for_report(
        context,
        target=_fault_cancellation_worker,
        args=(_url_text(target_url), user_id, spec.canonical_id, spec.phase),
        timeout_code="POSTGRES_ACCEPTANCE_FAULT_CANCELLATION_RESULT_TIMEOUT",
    )
    lease_key_sha256, leader_fence_token = _validate_cancelled_fault_report(
        leader_report,
        spec=spec,
    )
    after_leader = await _fault_persistence_counts(session_factory)
    leader_delta = _fault_count_delta(before, after_leader)
    expected_leader_delta = (1, 2) if spec.receipt_durable_before_fault else (0, 0)
    if leader_delta != expected_leader_delta:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_LEADER_DURABILITY_INVALID")

    released, observed_fence_token = await _fault_lease_state(
        session_factory,
        lease_key_sha256=lease_key_sha256,
    )
    if (
        observed_fence_token != leader_fence_token
        or released != spec.release_expected_after_cancellation
    ):
        raise PostgresAcceptanceHarnessError(
            "POSTGRES_ACCEPTANCE_FAULT_LEASE_RELEASE_STATE_INVALID"
        )

    follower_mode = "local_only" if spec.receipt_durable_before_fault else "local_first"
    follower_report = await _run_fault_worker_for_report(
        context,
        target=_fault_follower_worker,
        args=(_url_text(target_url), user_id, spec.canonical_id, follower_mode),
        timeout_code="POSTGRES_ACCEPTANCE_FAULT_FOLLOWER_RESULT_TIMEOUT",
    )
    follower_process_id = _validate_fault_follower_report(
        follower_report,
        mode=follower_mode,
        provider_call_count=0 if spec.receipt_durable_before_fault else 1,
        coverage_status="complete",
    )
    if follower_process_id == _process_report_int(leader_report, "pid"):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_PROCESS_IDENTITY_INVALID")

    after_follower = await _fault_persistence_counts(session_factory)
    source_snapshot_delta, observation_revision_delta = _fault_count_delta(before, after_follower)
    if (source_snapshot_delta, observation_revision_delta) != (1, 2):
        raise PostgresAcceptanceHarnessError(
            "POSTGRES_ACCEPTANCE_FAULT_RECOVERY_PERSISTENCE_INVALID"
        )

    expired_lease_takeover_fence_token: int | None = None
    if not spec.release_expected_after_cancellation:
        expired_lease_takeover_fence_token = await _take_over_expired_fault_lease(
            session_factory,
            lease_key_sha256=lease_key_sha256,
            prior_fence_token=leader_fence_token,
        )
    return _CancelledFaultPhaseEvidence(
        phase=spec.phase,
        leader_process_id=_process_report_int(leader_report, "pid"),
        leader_provider_call_count=_process_report_int(leader_report, "provider_call_count"),
        release_completed_after_cancellation=_fault_report_bool(leader_report, "release_completed"),
        follower_process_id=follower_process_id,
        follower_provider_call_count=_process_report_int(follower_report, "provider_call_count"),
        follower_local_only_complete=(
            _process_report_text(follower_report, "coverage_status") == "complete"
            if follower_mode == "local_only"
            else False
        ),
        source_snapshot_delta=source_snapshot_delta,
        observation_revision_delta=observation_revision_delta,
        expired_lease_takeover_fence_token=expired_lease_takeover_fence_token,
    )


async def _verify_cancelled_fault_takeovers(
    target_url: URL,
    *,
    user_id: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[_CancelledFaultPhaseEvidence, ...]:
    """Execute all cancellation boundaries on separate seeded logical identities."""
    evidence: list[_CancelledFaultPhaseEvidence] = []
    for spec in _FAULT_PHASE_SPECS:
        evidence.append(
            await _verify_cancelled_fault_phase(
                target_url,
                user_id=user_id,
                session_factory=session_factory,
                spec=spec,
            )
        )
    return tuple(evidence)


async def _run_stale_runner_leader(
    target_url_text: str,
    user_id: str,
    canonical_id: str,
    runner_started_event: Any,
    resume_event: Any,
    ready_queue: Any,
    result_queue: Any,
    provider_attempt_counter: Any,
) -> None:
    """Resume a stale fake-runner owner only after another process takes its fence."""
    if canonical_id != _STALE_RUNNER_CANONICAL_ID:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_IDENTITY_INVALID")
    target_url = make_url(target_url_text)
    _require_own_temporary_database(target_url.database)
    engine = _target_engine(target_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    checkpoints = _FaultCheckpointController(
        blocked_phase=_FAULT_PHASE_RUNNER_STARTED,
        reached_event=runner_started_event,
        unblock_event=resume_event,
        continue_after_unblock=True,
    )
    try:
        ready_queue.put({"kind": "ready", "pid": os.getpid()})
        async with session_factory() as session:
            query_now = datetime.now(UTC) + timedelta(minutes=10)
            provider = _DeterministicProvider(
                checkpoints=checkpoints,
                provider_attempt_counter=provider_attempt_counter,
            )
            execution = await _service(
                session,
                provider,
                now=query_now,
                allow_online_fetch=True,
                store=_CheckpointingMarketDataStore(session, checkpoints=checkpoints),
                fetch_leases=_CheckpointingFetchLeases(
                    MarketDataFetchLeaseManager(session, lease_ttl=_FAULT_LEASE_TTL),
                    checkpoints=checkpoints,
                ),
            ).execute(
                _request(mode="local_first", canonical_id=canonical_id),
                access=await _access_for_session(session, user_id=user_id, now=query_now),
            )
            await session.commit()
            result_queue.put(
                {
                    "kind": "stale_runner_leader",
                    "status": "ok",
                    "pid": os.getpid(),
                    "provider_call_count": len(provider.calls),
                    "fetch_count": len(execution.fetches),
                    "warning_codes": [warning.code for warning in execution.warnings],
                    "session_timezone": await _assert_utc_session_timezone(session),
                }
            )
    finally:
        await engine.dispose()


def _stale_runner_leader(
    target_url_text: str,
    user_id: str,
    canonical_id: str,
    runner_started_event: Any,
    resume_event: Any,
    ready_queue: Any,
    result_queue: Any,
    provider_attempt_counter: Any,
) -> None:
    """Return only a stable child failure code if the stale-owner proof cannot run."""
    try:
        asyncio.run(
            _run_stale_runner_leader(
                target_url_text,
                user_id,
                canonical_id,
                runner_started_event,
                resume_event,
                ready_queue,
                result_queue,
                provider_attempt_counter,
            )
        )
    except BaseException:
        result_queue.put(
            {
                "kind": "stale_runner_leader",
                "status": "error",
                "pid": os.getpid(),
                "code": "POSTGRES_ACCEPTANCE_FAULT_STALE_LEADER_FAILED",
            }
        )


def _validate_stale_runner_leader_report(
    report: Mapping[str, object],
) -> tuple[int, tuple[str, ...]]:
    """Require the original owner to return but fail its stale fenced persistence."""
    if (
        _process_report_text(report, "kind") != "stale_runner_leader"
        or _process_report_text(report, "status") != "ok"
        or _process_report_int(report, "provider_call_count") != 1
        or _process_report_int(report, "fetch_count") != 0
        or _process_report_text(report, "session_timezone").upper() not in {"UTC", "ETC/UTC"}
    ):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_STALE_LEADER_INVALID")
    warning_codes = _fault_report_texts(report, "warning_codes")
    if "FETCH_LEASE_FENCE_LOST" not in warning_codes:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_STALE_LEADER_INVALID")
    process_id = _process_report_int(report, "pid")
    if process_id <= 0:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_PROCESS_IDENTITY_INVALID")
    return process_id, warning_codes


async def _verify_stale_runner_start_takeover(
    target_url: URL,
    *,
    user_id: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> _StaleRunnerTakeoverEvidence:
    """Let a timed-out owner return after takeover and prove its fence rejects it."""
    context = multiprocessing.get_context("spawn")
    runner_started_event = context.Event()
    resume_event = context.Event()
    ready_queue = context.Queue()
    result_queue = context.Queue()
    provider_attempt_counter = context.Value("i", 0)
    leader = context.Process(
        target=_stale_runner_leader,
        args=(
            _url_text(target_url),
            user_id,
            _STALE_RUNNER_CANONICAL_ID,
            runner_started_event,
            resume_event,
            ready_queue,
            result_queue,
            provider_attempt_counter,
        ),
    )
    before = await _fault_persistence_counts(session_factory)
    try:
        leader.start()
        ready_report = await _receive_process_message(
            ready_queue,
            timeout_seconds=_PROCESS_EVENT_TIMEOUT_SECONDS,
            timeout_code="POSTGRES_ACCEPTANCE_FAULT_STALE_LEADER_READY_TIMEOUT",
        )
        leader_process_id = _process_report_int(ready_report, "pid")
        if _process_report_text(ready_report, "kind") != "ready" or leader_process_id <= 0:
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_FAULT_PROCESS_IDENTITY_INVALID"
            )
        await _wait_for_process_event(
            runner_started_event,
            code="POSTGRES_ACCEPTANCE_FAULT_STALE_RUNNER_START_TIMEOUT",
        )

        blocked_follower_report = await _run_fault_worker_for_report(
            context,
            target=_fault_follower_worker,
            args=(
                _url_text(target_url),
                user_id,
                _STALE_RUNNER_CANONICAL_ID,
                "local_first",
            ),
            timeout_code="POSTGRES_ACCEPTANCE_FAULT_STALE_BLOCKED_FOLLOWER_TIMEOUT",
        )
        blocked_follower_process_id = _validate_fault_follower_report(
            blocked_follower_report,
            mode="local_first",
            provider_call_count=0,
            coverage_status="incomplete",
            lease_held=True,
        )
        if blocked_follower_process_id == leader_process_id:
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_FAULT_PROCESS_IDENTITY_INVALID"
            )

        takeover_report = await _run_follower_until_expiry_takeover(
            context,
            target_url=target_url,
            user_id=user_id,
            canonical_id=_STALE_RUNNER_CANONICAL_ID,
            provider_attempt_counter=provider_attempt_counter,
        )
        takeover_process_id = _validate_fault_follower_report(
            takeover_report,
            mode="local_first",
            provider_call_count=1,
            coverage_status="complete",
        )
        if takeover_process_id in {leader_process_id, blocked_follower_process_id}:
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_FAULT_PROCESS_IDENTITY_INVALID"
            )

        resume_event.set()
        stale_report = await _receive_process_message(
            result_queue,
            timeout_seconds=_PROCESS_RESULT_TIMEOUT_SECONDS,
            timeout_code="POSTGRES_ACCEPTANCE_FAULT_STALE_LEADER_RESULT_TIMEOUT",
        )
        await _join_two_process_workers((leader,))
        stale_process_id, warning_codes = _validate_stale_runner_leader_report(stale_report)
        if stale_process_id != leader_process_id:
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_FAULT_PROCESS_IDENTITY_INVALID"
            )
        source_snapshot_delta, observation_revision_delta = _fault_count_delta(
            before,
            await _fault_persistence_counts(session_factory),
        )
        if (source_snapshot_delta, observation_revision_delta) != (1, 2):
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_FAULT_RECOVERY_PERSISTENCE_INVALID"
            )
        with provider_attempt_counter.get_lock():
            provider_attempt_count = int(provider_attempt_counter.value)
        if provider_attempt_count != 2:
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_FAULT_PROVIDER_ATTEMPTS_INVALID"
            )
        return _StaleRunnerTakeoverEvidence(
            leader_process_id=leader_process_id,
            blocked_follower_process_id=blocked_follower_process_id,
            takeover_process_id=takeover_process_id,
            provider_attempt_count=provider_attempt_count,
            stale_leader_warning_codes=warning_codes,
            source_snapshot_delta=source_snapshot_delta,
            observation_revision_delta=observation_revision_delta,
        )
    finally:
        await _stop_two_process_workers((leader,))
        _close_process_queue(ready_queue)
        _close_process_queue(result_queue)


async def _run_terminated_runner_leader(
    target_url_text: str,
    user_id: str,
    canonical_id: str,
    runner_started_event: Any,
    cleanup_unblock_event: Any,
    ready_queue: Any,
    provider_attempt_counter: Any,
) -> None:
    """Own a real lease and block exactly after fake-runner start until parent termination."""
    if canonical_id != _TERMINATED_RUNNER_CANONICAL_ID:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_IDENTITY_INVALID")
    target_url = make_url(target_url_text)
    _require_own_temporary_database(target_url.database)
    engine = _target_engine(target_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    checkpoints = _FaultCheckpointController(
        blocked_phase=_FAULT_PHASE_RUNNER_STARTED,
        reached_event=runner_started_event,
        unblock_event=cleanup_unblock_event,
        # The parent intentionally terminates this worker after exercising a
        # separate blocked follower.  Its local checkpoint must not time out
        # first and turn an ordinary worker error into a false proof of
        # parent-initiated termination.
        event_wait_timeout_seconds=_FAULT_TERMINATED_LEADER_BLOCK_TIMEOUT_SECONDS,
    )
    try:
        ready_queue.put({"kind": "ready", "pid": os.getpid()})
        async with session_factory() as session:
            query_now = datetime.now(UTC) + timedelta(minutes=10)
            provider = _DeterministicProvider(
                checkpoints=checkpoints,
                provider_attempt_counter=provider_attempt_counter,
            )
            await _service(
                session,
                provider,
                now=query_now,
                allow_online_fetch=True,
                store=_CheckpointingMarketDataStore(session, checkpoints=checkpoints),
                fetch_leases=_CheckpointingFetchLeases(
                    MarketDataFetchLeaseManager(session, lease_ttl=_FAULT_LEASE_TTL),
                    checkpoints=checkpoints,
                ),
            ).execute(
                _request(mode="local_first", canonical_id=canonical_id),
                access=await _access_for_session(session, user_id=user_id, now=query_now),
            )
    finally:
        await engine.dispose()


def _terminated_runner_leader(
    target_url_text: str,
    user_id: str,
    canonical_id: str,
    runner_started_event: Any,
    cleanup_unblock_event: Any,
    ready_queue: Any,
    provider_attempt_counter: Any,
) -> None:
    """Run the intentionally killable leader without a production-provider fallback."""
    asyncio.run(
        _run_terminated_runner_leader(
            target_url_text,
            user_id,
            canonical_id,
            runner_started_event,
            cleanup_unblock_event,
            ready_queue,
            provider_attempt_counter,
        )
    )


async def _join_terminated_fault_leader(process: Any) -> None:
    """Require a parent-terminated leader to be reaped before expiry takeover starts."""
    if os.name != "posix" or not hasattr(signal, "SIGKILL"):
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_LEADER_TERMINATION_FAILED")
    if process.pid is None or not process.is_alive():
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_LEADER_TERMINATION_FAILED")
    try:
        process.terminate()
        expected_exitcode = -signal.SIGTERM
        await asyncio.to_thread(process.join, _PROCESS_EVENT_TIMEOUT_SECONDS)
        if process.is_alive():
            kill = getattr(process, "kill", None)
            if not callable(kill):
                raise PostgresAcceptanceHarnessError(
                    "POSTGRES_ACCEPTANCE_FAULT_LEADER_TERMINATION_FAILED"
                )
            kill()
            expected_exitcode = -signal.SIGKILL
            await asyncio.to_thread(process.join, _PROCESS_EVENT_TIMEOUT_SECONDS)
    except PostgresAcceptanceHarnessError:
        raise
    except Exception as exc:
        raise PostgresAcceptanceHarnessError(
            "POSTGRES_ACCEPTANCE_FAULT_LEADER_TERMINATION_FAILED"
        ) from exc
    # A generic nonzero exit is not evidence that the parent terminated this
    # process: it could be a checkpoint timeout or another worker failure in
    # the race between is_alive() and terminate().  On POSIX multiprocessing
    # reports the signal that ended a child as the matching negative signal
    # number, which makes the parent-issued termination auditable.
    if process.is_alive() or process.exitcode != expected_exitcode:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_LEADER_TERMINATION_FAILED")


async def _run_follower_until_expiry_takeover(
    context: Any,
    *,
    target_url: URL,
    user_id: str,
    canonical_id: str,
    provider_attempt_counter: Any,
) -> Mapping[str, object]:
    """Retry only provider-free held responses until the dead owner's lease expires."""
    deadline = asyncio.get_running_loop().time() + _FAULT_TAKEOVER_TIMEOUT_SECONDS
    while True:
        result_queue = context.Queue()
        process = context.Process(
            target=_fault_follower_worker,
            args=(
                _url_text(target_url),
                user_id,
                canonical_id,
                "local_first",
                result_queue,
                provider_attempt_counter,
            ),
        )
        try:
            process.start()
            report = await _receive_process_message(
                result_queue,
                timeout_seconds=_PROCESS_RESULT_TIMEOUT_SECONDS,
                timeout_code="POSTGRES_ACCEPTANCE_FAULT_TAKEOVER_RESULT_TIMEOUT",
            )
            await _join_two_process_workers((process,))
        finally:
            await _stop_two_process_workers((process,))
            _close_process_queue(result_queue)
        if (
            _process_report_text(report, "kind") == "fault_follower"
            and _process_report_text(report, "status") == "ok"
            and _process_report_int(report, "provider_call_count") == 1
        ):
            return report
        if (
            _process_report_text(report, "kind") != "fault_follower"
            or _process_report_text(report, "status") != "ok"
            or _process_report_int(report, "provider_call_count") != 0
            or "FETCH_LEASE_HELD" not in _fault_report_texts(report, "warning_codes")
        ):
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_TAKEOVER_INVALID")
        if asyncio.get_running_loop().time() >= deadline:
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAULT_TAKEOVER_TIMEOUT")
        await asyncio.sleep(0.1)


async def _verify_terminated_runner_start_takeover(
    target_url: URL,
    *,
    user_id: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> _TerminatedRunnerTakeoverEvidence:
    """Prove owner death after runner start blocks a follower until lease expiry takeover."""
    context = multiprocessing.get_context("spawn")
    runner_started_event = context.Event()
    cleanup_unblock_event = context.Event()
    ready_queue = context.Queue()
    provider_attempt_counter = context.Value("i", 0)
    leader = context.Process(
        target=_terminated_runner_leader,
        args=(
            _url_text(target_url),
            user_id,
            _TERMINATED_RUNNER_CANONICAL_ID,
            runner_started_event,
            cleanup_unblock_event,
            ready_queue,
            provider_attempt_counter,
        ),
    )
    before = await _fault_persistence_counts(session_factory)
    try:
        leader.start()
        ready_report = await _receive_process_message(
            ready_queue,
            timeout_seconds=_PROCESS_EVENT_TIMEOUT_SECONDS,
            timeout_code="POSTGRES_ACCEPTANCE_FAULT_TERMINATED_LEADER_READY_TIMEOUT",
        )
        leader_process_id = _process_report_int(ready_report, "pid")
        if _process_report_text(ready_report, "kind") != "ready" or leader_process_id <= 0:
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_FAULT_PROCESS_IDENTITY_INVALID"
            )
        await _wait_for_process_event(
            runner_started_event,
            code="POSTGRES_ACCEPTANCE_FAULT_TERMINATED_RUNNER_START_TIMEOUT",
        )

        blocked_follower_report = await _run_fault_worker_for_report(
            context,
            target=_fault_follower_worker,
            args=(
                _url_text(target_url),
                user_id,
                _TERMINATED_RUNNER_CANONICAL_ID,
                "local_first",
            ),
            timeout_code="POSTGRES_ACCEPTANCE_FAULT_BLOCKED_FOLLOWER_RESULT_TIMEOUT",
        )
        blocked_follower_process_id = _validate_fault_follower_report(
            blocked_follower_report,
            mode="local_first",
            provider_call_count=0,
            coverage_status="incomplete",
            lease_held=True,
        )
        if blocked_follower_process_id == leader_process_id:
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_FAULT_PROCESS_IDENTITY_INVALID"
            )
        if _fault_count_delta(before, await _fault_persistence_counts(session_factory)) != (0, 0):
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_FAULT_LEADER_DURABILITY_INVALID"
            )

        await _join_terminated_fault_leader(leader)
        takeover_report = await _run_follower_until_expiry_takeover(
            context,
            target_url=target_url,
            user_id=user_id,
            canonical_id=_TERMINATED_RUNNER_CANONICAL_ID,
            provider_attempt_counter=provider_attempt_counter,
        )
        takeover_process_id = _validate_fault_follower_report(
            takeover_report,
            mode="local_first",
            provider_call_count=1,
            coverage_status="complete",
        )
        if takeover_process_id in {leader_process_id, blocked_follower_process_id}:
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_FAULT_PROCESS_IDENTITY_INVALID"
            )
        source_snapshot_delta, observation_revision_delta = _fault_count_delta(
            before,
            await _fault_persistence_counts(session_factory),
        )
        if (source_snapshot_delta, observation_revision_delta) != (1, 2):
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_FAULT_RECOVERY_PERSISTENCE_INVALID"
            )
        with provider_attempt_counter.get_lock():
            provider_attempt_count = int(provider_attempt_counter.value)
        if provider_attempt_count != 2:
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_FAULT_PROVIDER_ATTEMPTS_INVALID"
            )
        return _TerminatedRunnerTakeoverEvidence(
            leader_process_id=leader_process_id,
            blocked_follower_process_id=blocked_follower_process_id,
            takeover_process_id=takeover_process_id,
            provider_attempt_count=provider_attempt_count,
            blocked_follower_provider_call_count=_process_report_int(
                blocked_follower_report,
                "provider_call_count",
            ),
            takeover_provider_call_count=_process_report_int(
                takeover_report,
                "provider_call_count",
            ),
            source_snapshot_delta=source_snapshot_delta,
            observation_revision_delta=observation_revision_delta,
        )
    finally:
        cleanup_unblock_event.set()
        await _stop_two_process_workers((leader,))
        _close_process_queue(ready_queue)


async def _verify_fault_takeover_protocol(
    target_url: URL,
    *,
    user_id: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> _FaultTakeoverEvidence:
    """Run fixture-only cancellation and termination recovery without any network route."""
    cancelled_phases = await _verify_cancelled_fault_takeovers(
        target_url,
        user_id=user_id,
        session_factory=session_factory,
    )
    stale_runner_start = await _verify_stale_runner_start_takeover(
        target_url,
        user_id=user_id,
        session_factory=session_factory,
    )
    terminated_runner_start = await _verify_terminated_runner_start_takeover(
        target_url,
        user_id=user_id,
        session_factory=session_factory,
    )
    return _FaultTakeoverEvidence(
        cancelled_phases=cancelled_phases,
        stale_runner_start=stale_runner_start,
        terminated_runner_start=terminated_runner_start,
    )


async def _verify_independent_connection_lease(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[int, int]:
    """Prove a second PostgreSQL connection follows a current durable lease.

    This intentionally tests only the database-backed coordination primitive.
    It does not claim a real multi-worker HTTP deployment or real provider I/O.
    """
    lease_key = hashlib.sha256(b"iteration197-postgres-acceptance-lease").hexdigest()
    async with (
        session_factory() as owner_session,
        session_factory() as follower_session,
        session_factory() as inspector_session,
    ):
        owner = MarketDataFetchLeaseManager(owner_session, lease_ttl=timedelta(minutes=1))
        follower = MarketDataFetchLeaseManager(follower_session, lease_ttl=timedelta(minutes=1))
        # Run both independent PostgreSQL sessions simultaneously. One contender
        # may win the initial insert while the other retries after the unique-key
        # collision; exactly one may receive a durable owner fence.
        owner_handle, follower_handle = await asyncio.gather(
            owner.acquire(lease_key),
            follower.acquire(lease_key),
        )
        handles = tuple(handle for handle in (owner_handle, follower_handle) if handle is not None)
        if len(handles) != 1:
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_LEASE_CONTENTION_INVALID")
        winner = owner if owner_handle is not None else follower
        winner_handle = handles[0]
        stored = await inspector_session.scalar(
            select(MdFetchLease).where(MdFetchLease.lease_key_sha256 == lease_key)
        )
        if stored is None or stored.fence_token != winner_handle.fence_token:
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_LEASE_STATE_INVALID")
        if not await winner.release(winner_handle):
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_LEASE_RELEASE_FAILED")
    return len(handles), winner_handle.fence_token


async def _verify_temporary_database(target_url: URL, *, alembic_head: str) -> _HarnessResult:
    """Exercise UTC/session, catalog, provider persistence, and local-only reread."""
    engine = _target_engine(target_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # Identity and calendar publication receipts deliberately use the real
    # database transaction time. Keep interactive query cutoffs just after
    # that point rather than pretending a historical receipt was visible
    # before its post-commit publication transaction occurred.
    query_now = datetime.now(UTC) + timedelta(minutes=1)
    try:
        async with session_factory() as seed_session:
            first_timezone = await _assert_schema_and_timezone(
                seed_session,
                expected_alembic_head=alembic_head,
            )
            user_id = await _seed_prerequisites(
                seed_session,
                target_url=target_url,
                canonical_ids=_ALL_HARNESS_CANONICAL_IDS,
            )

        two_process_exact_gap = await _verify_two_process_exact_gap(
            target_url,
            user_id=user_id,
            query_now=query_now,
            session_factory=session_factory,
        )
        fault_takeover = await _verify_fault_takeover_protocol(
            target_url,
            user_id=user_id,
            session_factory=session_factory,
        )

        reread_provider = _DeterministicProvider()
        async with session_factory() as reread_session:
            second_timezone = await _assert_schema_and_timezone(
                reread_session,
                expected_alembic_head=alembic_head,
            )
            reread = await _service(
                reread_session,
                reread_provider,
                now=query_now + timedelta(microseconds=2),
                allow_online_fetch=False,
            ).execute(
                _request(mode="local_only"),
                access=await _access_for_session(
                    reread_session,
                    user_id=user_id,
                    now=query_now + timedelta(microseconds=2),
                ),
            )
            source_snapshot_count = int(
                await reread_session.scalar(select(func.count()).select_from(MdSourceSnapshot)) or 0
            )
            observation_revision_count = int(
                await reread_session.scalar(select(func.count()).select_from(MdObservationRevision))
                or 0
            )
        if reread.coverage.status.value != "complete" or reread.fetches:
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_LOCAL_ONLY_REREAD_FAILED")
        if reread_provider.calls:
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_LOCAL_ONLY_PROVIDER_CALLED")
        expected_source_snapshot_count = len(_ALL_HARNESS_CANONICAL_IDS)
        expected_observation_revision_count = expected_source_snapshot_count * 2
        if (
            source_snapshot_count != expected_source_snapshot_count
            or observation_revision_count != expected_observation_revision_count
        ):
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_PERSISTENCE_COUNT_INVALID")
        if len(reread.observations) != 2:
            raise PostgresAcceptanceHarnessError(
                "POSTGRES_ACCEPTANCE_LOCAL_ONLY_OBSERVATIONS_MISSING"
            )

        (
            lease_successful_contender_count,
            lease_fence_token,
        ) = await _verify_independent_connection_lease(session_factory)
        return _HarnessResult(
            alembic_head=alembic_head,
            first_session_timezone=first_timezone,
            second_session_timezone=second_timezone,
            provider_calls=two_process_exact_gap.provider_call_count,
            source_snapshot_count=source_snapshot_count,
            observation_revision_count=observation_revision_count,
            local_only_fetch_count=len(reread.fetches),
            lease_successful_contender_count=lease_successful_contender_count,
            lease_fence_token=lease_fence_token,
            two_process_exact_gap=two_process_exact_gap,
            fault_takeover=fault_takeover,
        )
    except PostgresAcceptanceHarnessError:
        raise
    except Exception as exc:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_VERIFICATION_FAILED") from exc
    finally:
        await engine.dispose()


def _dry_run_output(admin_url: URL) -> dict[str, object]:
    """Describe the command's destructive boundary without contacting PostgreSQL."""
    return {
        "status": "ok",
        "mode": "dry_run",
        "connection": _safe_connection_descriptor(admin_url),
        "temporary_database_prefix": TEMPORARY_DATABASE_PREFIX,
        "apply_required": True,
    }


def _apply(admin_url: URL) -> tuple[int, dict[str, object]]:
    """Run the full disposable acceptance flow and always attempt safe cleanup."""
    legacy_database_name = _temporary_database_name()
    acceptance_database_name = _temporary_database_name()
    database_names = (legacy_database_name, acceptance_database_name)
    created_database_names: list[str] = []
    cleanup = "not_needed"
    result: _HarnessResult | None = None
    legacy_portability_result: _LegacyConstraintPortabilityEvidence | None = None
    failure: PostgresAcceptanceHarnessError | None = None
    try:
        if len(set(database_names)) != len(database_names):
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_DATABASE_COLLISION")

        asyncio.run(
            _create_temporary_database(
                admin_url,
                legacy_database_name,
                on_created=created_database_names.append,
            )
        )
        legacy_target_url = _target_url(admin_url, legacy_database_name)
        legacy_portability_result = _run_legacy_constraint_portability_stage(legacy_target_url)

        asyncio.run(
            _create_temporary_database(
                admin_url,
                acceptance_database_name,
                on_created=created_database_names.append,
            )
        )
        target_url = _target_url(admin_url, acceptance_database_name)
        alembic_head = _run_alembic_upgrade(target_url)
        result = asyncio.run(_verify_temporary_database(target_url, alembic_head=alembic_head))
    except PostgresAcceptanceHarnessError as exc:
        failure = exc
    except Exception:
        failure = PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAILED")
    finally:
        if created_database_names:
            cleanup_errors: list[PostgresAcceptanceHarnessError] = []
            for database_name in reversed(created_database_names):
                try:
                    asyncio.run(_drop_temporary_database(admin_url, database_name))
                except PostgresAcceptanceHarnessError as cleanup_error:
                    cleanup_errors.append(cleanup_error)
            if cleanup_errors:
                # Cleanup failure is always the terminal result: generated
                # temporary databases may remain and need explicit operator
                # action, while no existing database was ever targeted.
                cleanup = "failed"
                failure = cleanup_errors[0]
            else:
                cleanup = "complete"

    output: dict[str, object] = {
        "connection": _safe_connection_descriptor(admin_url),
        "temporary_database_prefix": TEMPORARY_DATABASE_PREFIX,
        "cleanup": cleanup,
        "scope": {
            "provider": "deterministic_fixture_only",
            "lease": (
                "two_os_process_exact_gap_plus_fixture_cancellation_stale_fence_and_terminated_owner_takeover"
            ),
            "fault_runner": "deterministic_fixture_only_no_network_or_runtime_flag_change",
            "legacy_constraint_portability": (
                "stamped_predecessor_postgresql_truncated_check_names"
            ),
            "not_proven": [
                "real_akshare_or_openbb_io",
                "http_server_or_deployment_worker_topology",
            ],
        },
    }
    if failure is not None:
        output.update({"status": "error", "code": failure.code})
        return 2, output
    if result is None or legacy_portability_result is None:
        output.update({"status": "error", "code": "POSTGRES_ACCEPTANCE_RESULT_MISSING"})
        return 2, output
    evidence = result.as_dict()
    evidence["legacy_constraint_portability"] = legacy_portability_result.as_dict()
    output.update({"status": "ok", "mode": "applied", "evidence": evidence})
    return 0, output


def main() -> int:
    """Parse explicit opt-in arguments and print safe JSON only."""
    try:
        args = _arguments()
        admin_url = _parse_admin_url(args.postgres_admin_url)
        if not args.apply:
            output = _dry_run_output(admin_url)
            code = 0
        else:
            code, output = _apply(admin_url)
    except PostgresAcceptanceHarnessError as exc:
        code = 2
        output = {"status": "error", "code": exc.code}
    except Exception:
        code = 1
        output = {"status": "error", "code": "POSTGRES_ACCEPTANCE_UNEXPECTED_FAILURE"}
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
