"""Cross-worker fencing contracts for Iteration 197 local-first fills."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.market_data_platform import MdFetchLease
from app.services.market_data import fetch_lease as fetch_lease_module
from app.services.market_data.fetch_lease import (
    MarketDataFetchLeaseError,
    MarketDataFetchLeaseManager,
)

UTC = timezone.utc


def _at(minute: int) -> datetime:
    return datetime(2026, 9, 9, 9, minute, tzinfo=UTC)


def _key(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_owner_and_independent_session_follower_share_one_durable_lease() -> None:
    """A second worker must become a follower without obtaining a new fence."""
    key = _key("stock-bars-gap-1")

    def clock() -> datetime:
        return _at(0)

    async with async_session_maker() as owner_db, async_session_maker() as follower_db:
        owner = MarketDataFetchLeaseManager(owner_db, clock=clock, lease_ttl=timedelta(minutes=1))
        follower = MarketDataFetchLeaseManager(
            follower_db,
            clock=clock,
            lease_ttl=timedelta(minutes=1),
        )
        owner_handle = await owner.acquire(key)
        follower_handle = await follower.acquire(key)
        stored = await follower_db.scalar(
            select(MdFetchLease).where(MdFetchLease.lease_key_sha256 == key)
        )

    assert owner_handle is not None
    assert follower_handle is None
    assert stored is not None
    assert stored.owner_token == owner_handle.owner_token
    assert stored.fence_token == 1


@pytest.mark.asyncio
async def test_default_managers_use_shared_database_clock_not_worker_wall_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production acquisition remains coordinated even if a worker clock is unusable."""
    key = _key("shared-database-clock")

    def unexpected_worker_clock() -> datetime:
        raise AssertionError("production lease acquisition must not read worker wall time")

    monkeypatch.setattr(fetch_lease_module, "_utc_now", unexpected_worker_clock)
    async with async_session_maker() as owner_db, async_session_maker() as follower_db:
        owner = MarketDataFetchLeaseManager(owner_db, lease_ttl=timedelta(minutes=1))
        follower = MarketDataFetchLeaseManager(follower_db, lease_ttl=timedelta(minutes=1))
        owner_handle = await owner.acquire(key)
        follower_handle = await follower.acquire(key)

    assert owner_handle is not None
    assert follower_handle is None


@pytest.mark.asyncio
async def test_same_manager_reacquire_refreshes_a_released_row_before_claiming_it() -> None:
    """expire_on_commit=False identity maps cannot retain a stale owner image."""
    key = _key("same-manager-reacquire")

    async with async_session_maker() as db:
        manager = MarketDataFetchLeaseManager(
            db,
            clock=lambda: _at(0),
            lease_ttl=timedelta(minutes=1),
        )
        first = await manager.acquire(key)
        assert first is not None
        assert await manager.release(first)
        second = await manager.acquire(key)

    assert second is not None
    assert second.owner_token != first.owner_token
    assert second.fence_token == first.fence_token + 1


@pytest.mark.asyncio
async def test_release_refuses_to_commit_caller_staged_orm_changes() -> None:
    """Lease cleanup never commits or rolls back unrelated pending state."""
    key = _key("release-dirty-transaction")

    async with async_session_maker() as db:
        manager = MarketDataFetchLeaseManager(
            db,
            clock=lambda: _at(0),
            lease_ttl=timedelta(minutes=1),
        )
        handle = await manager.acquire(key)
        assert handle is not None
        pending = MdFetchLease(
            lease_key_sha256=_key("unrelated-pending-lease"),
            owner_token="other-owner",
            fence_token=1,
            expires_at=_at(1),
            created_at=_at(0),
            updated_at=_at(0),
        )
        db.add(pending)

        with pytest.raises(MarketDataFetchLeaseError) as rejected:
            await manager.release(handle)

        assert rejected.value.code == "FETCH_LEASE_RELEASE_DIRTY_TRANSACTION"
        assert pending in db.new
        await db.rollback()


@pytest.mark.asyncio
async def test_expired_owner_is_taken_over_with_a_higher_fence_in_another_session() -> None:
    """Expiry is an explicit handoff, never a reuse of an old owner generation."""
    key = _key("stock-bars-gap-2")

    async with async_session_maker() as first_db, async_session_maker() as second_db:
        first = MarketDataFetchLeaseManager(
            first_db,
            clock=lambda: _at(0),
            lease_ttl=timedelta(minutes=1),
        )
        second = MarketDataFetchLeaseManager(
            second_db,
            clock=lambda: _at(2),
            lease_ttl=timedelta(minutes=1),
        )
        first_handle = await first.acquire(key)
        second_handle = await second.acquire(key)
        stored = await second_db.scalar(
            select(MdFetchLease).where(MdFetchLease.lease_key_sha256 == key)
        )

    assert first_handle is not None
    assert second_handle is not None
    assert second_handle.owner_token != first_handle.owner_token
    assert second_handle.fence_token == first_handle.fence_token + 1
    assert stored is not None
    assert stored.owner_token == second_handle.owner_token
    assert stored.fence_token == second_handle.fence_token


@pytest.mark.asyncio
async def test_stale_owner_cannot_renew_or_release_a_newer_owner_fence() -> None:
    """A stale process cannot mutate a takeover row after its old lease expires."""
    key = _key("stock-bars-gap-3")

    async with async_session_maker() as stale_db, async_session_maker() as current_db:
        stale = MarketDataFetchLeaseManager(
            stale_db,
            clock=lambda: _at(0),
            lease_ttl=timedelta(minutes=1),
        )
        current = MarketDataFetchLeaseManager(
            current_db,
            clock=lambda: _at(2),
            lease_ttl=timedelta(minutes=1),
        )
        stale_handle = await stale.acquire(key)
        current_handle = await current.acquire(key)
        assert stale_handle is not None
        assert current_handle is not None

        with pytest.raises(MarketDataFetchLeaseError) as lost:
            await stale.assert_held_in_transaction(stale_handle)
        await stale_db.rollback()
        released = await stale.release(stale_handle)
        stored = await current_db.scalar(
            select(MdFetchLease).where(MdFetchLease.lease_key_sha256 == key)
        )

    assert lost.value.code == "FETCH_LEASE_FENCE_LOST"
    assert released is False
    assert stored is not None
    assert stored.owner_token == current_handle.owner_token
    assert stored.fence_token == current_handle.fence_token
