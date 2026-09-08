"""Run the opt-in Iteration 197 PostgreSQL acceptance harness.

This command never accepts an application database URL.  It requires an
explicit ``postgresql+asyncpg`` administrative URL whose database is exactly
``postgres``; when ``--apply`` is supplied it creates one UUID-named temporary
database, upgrades it with Alembic, exercises the real normalized market-data
services, and drops that same database in ``finally``.

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
import re
import sys
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
from app.models.market_data_platform import MdFetchLease, MdObservationRevision, MdSourceSnapshot
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


class PostgresAcceptanceHarnessError(RuntimeError):
    """Stable, non-secret failure emitted by the disposable acceptance command."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


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
        }


class _DeterministicProvider:
    """A bounded adapter used only by this acceptance harness; it never does I/O."""

    def __init__(self) -> None:
        self.calls: list[MarketDataProviderRequest] = []

    async def fetch(self, request: MarketDataProviderRequest) -> ProviderFetchResult:
        self.calls.append(request)
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
        help="Create, migrate, verify, and delete one UUID-named temporary database.",
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


async def _create_temporary_database(admin_url: URL, database_name: str) -> None:
    """Create one generated database only after proving the name is safe."""
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


def _run_alembic_upgrade(target_url: URL) -> str:
    """Run the project's normal Alembic path against the disposable target only."""
    try:
        config = Config(str(_BACKEND_DIRECTORY / "alembic.ini"))
        config.set_main_option("script_location", str(_BACKEND_DIRECTORY / "alembic"))
        config.set_main_option("sqlalchemy.url", _alembic_url_text(target_url))
        command.upgrade(config, "head")
        head = ScriptDirectory.from_config(config).get_current_head()
    except Exception as exc:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_ALEMBIC_UPGRADE_FAILED") from exc
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
    timezone_name = str(await session.scalar(text("SHOW TIME ZONE")) or "")
    if timezone_name.upper() not in {"UTC", "ETC/UTC"}:
        raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_SESSION_TIMEZONE_NOT_UTC")
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


def _request(*, mode: str) -> MarketDataQueryRequest:
    """Build a deterministic bars request accepted by the real internal resolver."""
    return MarketDataQueryRequest.model_validate(
        {
            "identity": {"canonical_id": CANONICAL_ID},
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
        store=MarketDataStore(session, clock=lambda: now),
        source_policies=_policy(provider),
        allow_online_fetch=allow_online_fetch,
        clock=lambda: now,
        cursor_signing_key="iteration197-postgres-acceptance-cursor-key-material-0000000000000001",
    )


async def _seed_prerequisites(
    session: AsyncSession,
    *,
    target_url: URL,
) -> str:
    """Seed reviewed control-plane prerequisites before any local-first request."""
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

    identity = InstrumentIdentity.model_validate(
        {
            "asset_type": "stock",
            "identity_level": "ASSET",
            "canonical_id": CANONICAL_ID,
            "display_symbol": "600000",
            "name": "PostgreSQL验收股票",
            "venue": "CN-SSE",
            "currency": "CNY",
            "timezone": "Asia/Shanghai",
            "identifier_type": "EXCHANGE_SYMBOL",
            "identifier_value": "600000.SH",
            "product_type": "EQUITY",
            "metadata_version": "market-v1",
            "details": {"kind": "STOCK", "exchange_symbol": "600000.SH"},
        }
    )
    writer = MarketDataIdentityWriter(session)
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
    provider = _DeterministicProvider()
    # Identity and calendar publication receipts deliberately use the real
    # database transaction time. Keep interactive query cutoffs just after
    # that point rather than pretending a historical receipt was visible
    # before its post-commit publication transaction occurred.
    query_now = datetime.now(UTC) + timedelta(minutes=1)
    try:
        async with session_factory() as seed_session:
            await _assert_schema_and_timezone(
                seed_session,
                expected_alembic_head=alembic_head,
            )
            user_id = await _seed_prerequisites(seed_session, target_url=target_url)

        async with session_factory() as first_session:
            first_timezone = await _assert_schema_and_timezone(
                first_session,
                expected_alembic_head=alembic_head,
            )
            first = await _service(
                first_session,
                provider,
                now=query_now,
                allow_online_fetch=True,
            ).execute(
                _request(mode="local_first"),
                access=await _access_for_session(
                    first_session,
                    user_id=user_id,
                    now=query_now,
                ),
            )
            await first_session.commit()
        if first.coverage.status.value != "complete" or len(first.fetches) != 1:
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FIRST_FETCH_INCOMPLETE")

        async with session_factory() as reread_session:
            second_timezone = await _assert_schema_and_timezone(
                reread_session,
                expected_alembic_head=alembic_head,
            )
            reread = await _service(
                reread_session,
                provider,
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
        if len(provider.calls) != 1:
            raise PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_PROVIDER_CALL_COUNT_INVALID")
        if source_snapshot_count != 1 or observation_revision_count != 2:
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
            provider_calls=len(provider.calls),
            source_snapshot_count=source_snapshot_count,
            observation_revision_count=observation_revision_count,
            local_only_fetch_count=len(reread.fetches),
            lease_successful_contender_count=lease_successful_contender_count,
            lease_fence_token=lease_fence_token,
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
    database_name = _temporary_database_name()
    created = False
    cleanup = "not_needed"
    result: _HarnessResult | None = None
    failure: PostgresAcceptanceHarnessError | None = None
    try:
        asyncio.run(_create_temporary_database(admin_url, database_name))
        created = True
        target_url = _target_url(admin_url, database_name)
        alembic_head = _run_alembic_upgrade(target_url)
        result = asyncio.run(_verify_temporary_database(target_url, alembic_head=alembic_head))
    except PostgresAcceptanceHarnessError as exc:
        failure = exc
    except Exception:
        failure = PostgresAcceptanceHarnessError("POSTGRES_ACCEPTANCE_FAILED")
    finally:
        if created:
            try:
                asyncio.run(_drop_temporary_database(admin_url, database_name))
                cleanup = "complete"
            except PostgresAcceptanceHarnessError as cleanup_error:
                # Cleanup failure is always the terminal result: a generated
                # temporary database may remain and needs explicit operator
                # action, while no existing database was ever targeted.
                cleanup = "failed"
                failure = cleanup_error

    output: dict[str, object] = {
        "connection": _safe_connection_descriptor(admin_url),
        "temporary_database_prefix": TEMPORARY_DATABASE_PREFIX,
        "cleanup": cleanup,
        "scope": {
            "provider": "deterministic_fixture_only",
            "lease": "independent_database_connections_only",
            "not_proven": ["real_akshare_or_openbb_io", "multi_process_http_workers"],
        },
    }
    if failure is not None:
        output.update({"status": "error", "code": failure.code})
        return 2, output
    if result is None:
        output.update({"status": "error", "code": "POSTGRES_ACCEPTANCE_RESULT_MISSING"})
        return 2, output
    output.update({"status": "ok", "mode": "applied", "evidence": result.as_dict()})
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
