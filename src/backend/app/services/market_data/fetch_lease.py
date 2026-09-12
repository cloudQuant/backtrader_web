"""Durable cross-worker fetch leases for local-first market-data fills.

The API process-level singleflight gate avoids duplicate work inside one
worker.  This module supplies the missing database-backed coordination for
separate workers: a canonical coverage gap maps to one lease row, every
acquisition advances an immutable fencing number, and a conditional renewal
is performed in the same short transaction as a write or publication.

External provider I/O is deliberately outside every database transaction.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_platform import MdFetchLease
from app.services.market_data.coverage import TimeWindow

if TYPE_CHECKING:
    from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext

UTC = timezone.utc
# The reviewed policy permits at most one primary and one fallback request.
# Their request-facing timeouts are 30 seconds, so five minutes leaves four
# minutes after those bounded responses for validation, facts and publication
# fencing. OpenBB terminates its timed-out runner. AkShare's synchronous worker
# thread can outlive its request timeout; this TTL therefore does *not* certify
# zero duplicate AkShare I/O after a timeout. That production claim remains
# blocked until AkShare has a killable runner or a retained-lease heartbeat.
# Any future longer request timeout requires a reviewed TTL or heartbeat.
DEFAULT_FETCH_LEASE_TTL = timedelta(minutes=5)
_LEASE_CONTRACT_VERSION = "market-data-fetch-lease-v2"
_MAX_ACQUIRE_RETRIES = 3


class MarketDataFetchLeaseError(ValueError):
    """Stable failure code for durable local-first fetch coordination."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class MarketDataFetchLeaseHandle:
    """One owner-scoped, monotonic lease fence returned after acquisition."""

    lease_key_sha256: str
    owner_token: str
    fence_token: int
    expires_at: datetime
    lease_ttl: timedelta = DEFAULT_FETCH_LEASE_TTL

    def __post_init__(self) -> None:
        _require_sha256(self.lease_key_sha256, field_name="fetch lease key")
        if not isinstance(self.owner_token, str) or not self.owner_token.strip():
            raise ValueError("fetch lease owner token must be non-empty")
        if len(self.owner_token) > 64:
            raise ValueError("fetch lease owner token is too long")
        if (
            not isinstance(self.fence_token, int)
            or isinstance(self.fence_token, bool)
            or self.fence_token < 1
        ):
            raise ValueError("fetch lease fence token must be positive")
        object.__setattr__(
            self,
            "expires_at",
            _as_utc(self.expires_at, field_name="fetch lease expiry"),
        )
        if not isinstance(self.lease_ttl, timedelta) or self.lease_ttl <= timedelta(0):
            raise ValueError("fetch lease ttl must be positive")


def market_data_fetch_lease_key(
    context: ResolvedMarketDataQueryContext,
    *,
    coverage_gap: TimeWindow,
    mode: str,
    policy_descriptor_hash: str,
    access_grant_descriptor_hash: str,
) -> str:
    """Hash the server-resolved semantic query and one exact coverage gap.

    The key contains no caller-supplied provider name or mutable in-process
    state.  It includes the authoritative policy/access descriptors so a
    changed source authorization cannot accidentally join an older work item.
    """
    # Import here rather than at module import time: identity resolution uses
    # publication receipts, while publication needs the fence assertion below.
    # The key factory is called only after the market-data service graph has
    # been initialized, so this preserves the concrete context boundary
    # without creating an import cycle through identity/publication.
    from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext

    if not isinstance(context, ResolvedMarketDataQueryContext):
        raise TypeError("context must be a ResolvedMarketDataQueryContext")
    if not isinstance(coverage_gap, TimeWindow):
        raise TypeError("coverage_gap must be a TimeWindow")
    if mode not in {"local_first", "refresh"}:
        raise ValueError("fetch lease mode must be local_first or refresh")
    _require_sha256(policy_descriptor_hash, field_name="fetch lease policy descriptor")
    _require_sha256(access_grant_descriptor_hash, field_name="fetch lease access grant")
    query = context.query
    payload = {
        "lease_contract_version": _LEASE_CONTRACT_VERSION,
        "canonical_id": query.canonical_id,
        "dataset_code": query.dataset_code,
        "instrument_metadata_version": query.instrument_metadata_version,
        "asset_type": context.identity.asset_type,
        "market": context.identity.venue,
        "data_kind": query.data_kind,
        "frequency": query.frequency,
        "required_fields": sorted(query.required_fields),
        "adjustment": query.adjustment,
        "price_basis": query.price_basis,
        "currency": query.currency,
        "unit": query.unit,
        # A query family is a public product/contract boundary.  Even when two
        # families presently share bars storage, they must not share one
        # cross-worker fill if a future registry revision differentiates their
        # fields, routes, or publication semantics.
        "family_id": query.family_id,
        "family_contract_version": query.family_contract_version,
        "source_policy_id": query.source_policy_id,
        "mode": mode,
        "coverage_gap": {
            "start": _as_utc(coverage_gap.start_at, field_name="coverage gap start").isoformat(),
            "end": _as_utc(coverage_gap.end_at, field_name="coverage gap end").isoformat(),
        },
        "policy_descriptor_hash": policy_descriptor_hash,
        "access_grant_descriptor_hash": access_grant_descriptor_hash,
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


class MarketDataFetchLeaseManager:
    """Acquire and fence one durable coverage-gap owner through ``md_fetch_leases``.

    Rows are retained after release rather than deleted.  Retaining the row is
    what keeps ``fence_token`` monotonic and prevents an ABA case where a stale
    process observes a newly-created row with the same low generation.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
        lease_ttl: timedelta = DEFAULT_FETCH_LEASE_TTL,
    ) -> None:
        if not isinstance(db, AsyncSession):
            raise TypeError("db must be an AsyncSession")
        if not isinstance(lease_ttl, timedelta) or lease_ttl <= timedelta(0):
            raise ValueError("lease_ttl must be positive")
        if lease_ttl > timedelta(hours=1):
            raise ValueError("lease_ttl must be no more than one hour")
        self._db = db
        # A supplied clock is a deterministic test seam. Production managers
        # deliberately use the database clock so independently deployed web
        # workers cannot steal a lease merely because their host clocks differ.
        self._clock = clock
        self._lease_ttl = lease_ttl

    async def acquire(self, lease_key_sha256: str) -> MarketDataFetchLeaseHandle | None:
        """Acquire a gap owner or return ``None`` while another owner is current.

        The method commits only the small lease mutation.  It never calls a
        provider and it rolls back a read-only loser transaction so a follower
        can immediately re-read local facts on its own request session.
        """
        key = _require_sha256(lease_key_sha256, field_name="fetch lease key")
        await self._start_acquire_transaction()
        for attempt in range(_MAX_ACQUIRE_RETRIES):
            owner_token = str(uuid.uuid4())
            try:
                row = await self._db.scalar(
                    select(MdFetchLease)
                    .where(MdFetchLease.lease_key_sha256 == key)
                    .execution_options(populate_existing=True)
                    .with_for_update()
                )
                # Sample only after the row lock/read completes. A timestamp
                # captured before a long lock wait could otherwise create a
                # lease that is already expired when ownership is decided.
                now = await self._now()
                if row is None:
                    provisional_expires_at = now + self._lease_ttl
                    candidate = MdFetchLease(
                        lease_key_sha256=key,
                        owner_token=owner_token,
                        fence_token=1,
                        expires_at=provisional_expires_at,
                        created_at=now,
                        updated_at=now,
                        released_at=None,
                    )
                    self._db.add(candidate)
                    await self._db.flush()
                    expires_at = await self._renew_claimed_lease(
                        lease_key_sha256=key,
                        owner_token=owner_token,
                        fence_token=1,
                    )
                    await self._db.commit()
                    return MarketDataFetchLeaseHandle(
                        lease_key_sha256=key,
                        owner_token=owner_token,
                        fence_token=1,
                        expires_at=expires_at,
                        lease_ttl=self._lease_ttl,
                    )

                if row.owner_token is not None:
                    if row.expires_at is None:
                        raise MarketDataFetchLeaseError("FETCH_LEASE_STATE_INVALID")
                    existing_expiry = _stored_utc(
                        row.expires_at,
                        field_name="stored fetch lease expiry",
                    )
                    if existing_expiry > now:
                        await self._rollback_if_needed()
                        return None
                elif row.expires_at is not None:
                    raise MarketDataFetchLeaseError("FETCH_LEASE_STATE_INVALID")

                next_fence = int(row.fence_token) + 1
                # The compare-and-swap predicate is required even though
                # PostgreSQL/MySQL take a row lock above: SQLite ignores
                # ``FOR UPDATE`` and concurrent writers must still never both
                # receive the same owner/fence pair.
                claimed = await self._db.execute(
                    update(MdFetchLease)
                    .where(
                        MdFetchLease.lease_key_sha256 == key,
                        MdFetchLease.fence_token == int(row.fence_token),
                        or_(
                            MdFetchLease.owner_token.is_(None),
                            MdFetchLease.expires_at <= now,
                        ),
                    )
                    .values(
                        owner_token=owner_token,
                        fence_token=next_fence,
                        # Preserve an expired predecessor until a post-write
                        # clock sample proves this claim owns the row. A
                        # released row has NULL expiry by invariant, so it
                        # needs a provisional non-NULL value for the same
                        # owner/expiry constraint before that renewal.
                        expires_at=(
                            MdFetchLease.expires_at
                            if row.expires_at is not None
                            else now + self._lease_ttl
                        ),
                        updated_at=now,
                        released_at=None,
                    )
                    .execution_options(synchronize_session=False)
                )
                if claimed.rowcount != 1:
                    await self._rollback_if_needed()
                    continue
                expires_at = await self._renew_claimed_lease(
                    lease_key_sha256=key,
                    owner_token=owner_token,
                    fence_token=next_fence,
                )
                await self._db.commit()
                return MarketDataFetchLeaseHandle(
                    lease_key_sha256=key,
                    owner_token=owner_token,
                    fence_token=next_fence,
                    expires_at=expires_at,
                    lease_ttl=self._lease_ttl,
                )
            except MarketDataFetchLeaseError:
                await self._rollback_if_needed()
                raise
            except IntegrityError as exc:
                # A concurrent first insert won the unique primary key.  A
                # clean retry observes that durable winner without trusting an
                # engine-specific UPSERT extension.
                await self._rollback_if_needed()
                if attempt + 1 == _MAX_ACQUIRE_RETRIES:
                    raise MarketDataFetchLeaseError("FETCH_LEASE_ACQUIRE_CONFLICT") from exc
            except OperationalError as exc:
                await self._rollback_if_needed()
                raise MarketDataFetchLeaseError("FETCH_LEASE_ACQUIRE_CONFLICT") from exc
        raise MarketDataFetchLeaseError("FETCH_LEASE_ACQUIRE_CONFLICT")

    async def _renew_claimed_lease(
        self,
        *,
        lease_key_sha256: str,
        owner_token: str,
        fence_token: int,
    ) -> datetime:
        """Renew immediately after this transaction has claimed the row lock.

        Acquisition samples a fresh database timestamp *after* either the
        insert or compare-and-swap write.  That avoids returning a lease that
        was already old because a prior read or lock wait consumed its TTL.
        The mutation remains in the same tiny transaction as the claim.
        """
        now = await self._now()
        expires_at = now + self._lease_ttl
        try:
            renewed = await self._db.execute(
                update(MdFetchLease)
                .where(
                    MdFetchLease.lease_key_sha256 == lease_key_sha256,
                    MdFetchLease.owner_token == owner_token,
                    MdFetchLease.fence_token == fence_token,
                )
                .values(expires_at=expires_at, updated_at=now)
                .execution_options(synchronize_session=False)
            )
        except OperationalError as exc:
            raise MarketDataFetchLeaseError("FETCH_LEASE_ACQUIRE_CONFLICT") from exc
        if renewed.rowcount != 1:
            raise MarketDataFetchLeaseError("FETCH_LEASE_ACQUIRE_CONFLICT")
        return expires_at

    async def assert_held_in_transaction(
        self,
        handle: MarketDataFetchLeaseHandle,
    ) -> MarketDataFetchLeaseHandle:
        """Conditionally renew an owner in the caller's short write transaction.

        Callers must commit or roll back the surrounding transaction.  A stale
        owner cannot make its data/publication mutation durable because this
        conditional update participates in that same transaction.
        """
        if not isinstance(handle, MarketDataFetchLeaseHandle):
            raise TypeError("handle must be a MarketDataFetchLeaseHandle")
        lock_check_now = await self._now()
        try:
            # The first conditional no-op takes the durable row lock without
            # overwriting its original expiry. If it waited beyond expiry, the
            # second check below sees that fact at the actual ownership point.
            locked = await self._db.execute(
                update(MdFetchLease)
                .where(
                    MdFetchLease.lease_key_sha256 == handle.lease_key_sha256,
                    MdFetchLease.owner_token == handle.owner_token,
                    MdFetchLease.fence_token == handle.fence_token,
                    MdFetchLease.expires_at.is_not(None),
                    MdFetchLease.expires_at > lock_check_now,
                )
                .values(updated_at=MdFetchLease.updated_at)
                .execution_options(synchronize_session=False)
            )
        except OperationalError as exc:
            raise MarketDataFetchLeaseError("FETCH_LEASE_FENCE_UNAVAILABLE") from exc
        if locked.rowcount != 1:
            raise MarketDataFetchLeaseError("FETCH_LEASE_FENCE_LOST")
        now = await self._now()
        expires_at = now + self._lease_ttl
        try:
            renewed = await self._db.execute(
                update(MdFetchLease)
                .where(
                    MdFetchLease.lease_key_sha256 == handle.lease_key_sha256,
                    MdFetchLease.owner_token == handle.owner_token,
                    MdFetchLease.fence_token == handle.fence_token,
                    MdFetchLease.expires_at.is_not(None),
                    MdFetchLease.expires_at > now,
                )
                .values(expires_at=expires_at, updated_at=now)
                .execution_options(synchronize_session=False)
            )
        except OperationalError as exc:
            raise MarketDataFetchLeaseError("FETCH_LEASE_FENCE_UNAVAILABLE") from exc
        if renewed.rowcount != 1:
            raise MarketDataFetchLeaseError("FETCH_LEASE_FENCE_LOST")
        return replace(handle, expires_at=expires_at)

    async def release(self, handle: MarketDataFetchLeaseHandle) -> bool:
        """Release only the exact owner/fence pair, preserving the generation row."""
        if not isinstance(handle, MarketDataFetchLeaseHandle):
            raise TypeError("handle must be a MarketDataFetchLeaseHandle")
        await self._start_release_transaction()
        now = await self._now()
        try:
            released = await self._db.execute(
                update(MdFetchLease)
                .where(
                    MdFetchLease.lease_key_sha256 == handle.lease_key_sha256,
                    MdFetchLease.owner_token == handle.owner_token,
                    MdFetchLease.fence_token == handle.fence_token,
                )
                .values(
                    owner_token=None,
                    expires_at=None,
                    released_at=now,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if released.rowcount != 1:
                await self._rollback_if_needed()
                return False
            await self._db.commit()
            return True
        except OperationalError as exc:
            await self._rollback_if_needed()
            raise MarketDataFetchLeaseError("FETCH_LEASE_RELEASE_CONFLICT") from exc

    async def _rollback_if_needed(self) -> None:
        if self._db.in_transaction():
            await self._db.rollback()

    async def _start_acquire_transaction(self) -> None:
        """Discard only a read-only predecessor before the lease CAS begins.

        A query's local coverage reads can auto-begin a transaction before it
        asks for a lease. Acquiring must not inherit that old transaction
        snapshot or its locks. Like ``release``, acquisition owns its short
        transaction and therefore rejects caller-staged ORM changes instead
        of silently rolling them back.
        """
        if not self._db.in_transaction():
            return
        if self._db.new or self._db.dirty or self._db.deleted:
            raise MarketDataFetchLeaseError("FETCH_LEASE_ACQUIRE_DIRTY_TRANSACTION")
        try:
            await self._db.rollback()
        except OperationalError as exc:
            raise MarketDataFetchLeaseError("FETCH_LEASE_ACQUIRE_CONFLICT") from exc

    async def _start_release_transaction(self) -> None:
        """Give release its own short transaction without committing caller state."""
        if not self._db.in_transaction():
            return
        if self._db.new or self._db.dirty or self._db.deleted:
            raise MarketDataFetchLeaseError("FETCH_LEASE_RELEASE_DIRTY_TRANSACTION")
        try:
            await self._db.rollback()
        except OperationalError as exc:
            raise MarketDataFetchLeaseError("FETCH_LEASE_RELEASE_CONFLICT") from exc

    async def _now(self) -> datetime:
        """Read a shared time source for production lease comparisons.

        The expression is evaluated by SQLite, MySQL, or PostgreSQL in an
        explicitly UTC representation. It is intentionally read in the same
        short transaction as the compare-and-swap that consumes it; no adapter
        call occurs before that transaction commits or rolls back.
        """
        if self._clock is not None:
            return _trusted_now(self._clock)
        try:
            dialect_name = self._db.get_bind().dialect.name
            if dialect_name == "mysql":
                # MySQL's CURRENT_TIMESTAMP follows the connection session
                # time zone. UTC_TIMESTAMP is immune to per-worker/session
                # settings and preserves microseconds for the fence expiry.
                statement = select(func.utc_timestamp(6))
            elif dialect_name == "postgresql":
                # Unlike CURRENT_TIMESTAMP, clock_timestamp() is not fixed at
                # transaction start. That matters when a preceding local read
                # waited before this short acquisition transaction began.
                statement = select(func.timezone("UTC", func.clock_timestamp()))
            else:
                # SQLite CURRENT_TIMESTAMP is documented as UTC.
                statement = select(func.current_timestamp())
            value = await self._db.scalar(statement)
        except OperationalError as exc:
            raise MarketDataFetchLeaseError("FETCH_LEASE_CLOCK_UNAVAILABLE") from exc
        try:
            return _stored_utc(value, field_name="database fetch lease clock")
        except ValueError as exc:
            raise MarketDataFetchLeaseError("FETCH_LEASE_CLOCK_INVALID") from exc


async def assert_fetch_lease_held_in_transaction(
    db: AsyncSession,
    handle: MarketDataFetchLeaseHandle,
    *,
    clock: Callable[[], datetime] | None = None,
    lease_ttl: timedelta | None = None,
) -> MarketDataFetchLeaseHandle:
    """Renew a fence without owning manager lifecycle state.

    ``MarketDataStore`` uses this helper during its fact and publication
    transactions.  It keeps the same conditional update rule as the manager
    while allowing the store to pass a caller-owned handle through both phases.
    """
    return await MarketDataFetchLeaseManager(
        db,
        clock=clock,
        lease_ttl=lease_ttl or handle.lease_ttl,
    ).assert_held_in_transaction(handle)


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MarketDataFetchLeaseError("FETCH_LEASE_KEY_INVALID") from exc


def _require_sha256(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a SHA-256 digest")
    normalized = value.strip()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return normalized


def _trusted_now(clock: Callable[[], datetime]) -> datetime:
    return _as_utc(clock(), field_name="fetch lease clock")


def _as_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _stored_utc(value: datetime, *, field_name: str) -> datetime:
    """Normalize portable database reads that omit SQLite timezone metadata."""
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)
