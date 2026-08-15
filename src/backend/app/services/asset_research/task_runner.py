"""Durable, bounded claiming for interactive multi-asset research tasks."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any
from uuid import uuid4
from weakref import WeakKeyDictionary

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import async_session_maker
from app.middleware.metrics import record_asset_research_task, set_asset_research_queue_depth
from app.models.asset_research import AssetAnalysisTask
from app.services.asset_research.orchestrator import AssetResearchOrchestrator
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ClaimedAnalysisTask:
    """One interactive task leased by a uniquely identifying worker token."""

    task_id: str
    lease_token: str


@dataclass(frozen=True, slots=True)
class _TerminalTaskUpdate:
    """Terminal fields submitted only by the lease-owning compare-and-set."""

    status: str
    progress: int
    error_code: str | None
    completed_at: datetime


OrchestratorFactory = Callable[[AsyncSession], Any]
_TERMINAL_TASK_STATUSES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED"})


class AssetResearchTaskRunner:
    """Claim queued tasks and make interrupted work explicitly retryable."""

    def __init__(
        self,
        *,
        session_maker: Any = async_session_maker,
        orchestrator_factory: OrchestratorFactory | None = None,
        lease_seconds: int | None = None,
        max_batch: int | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        settings = get_settings()
        resolved_lease_seconds = (
            lease_seconds
            if lease_seconds is not None
            else settings.ASSET_RESEARCH_TASK_LEASE_SECONDS
        )
        resolved_max_batch = (
            max_batch if max_batch is not None else settings.ASSET_RESEARCH_TASK_MAX_BATCH
        )
        resolved_max_concurrency = (
            max_concurrency
            if max_concurrency is not None
            else settings.ASSET_RESEARCH_TASK_WORKER_CONCURRENCY
        )
        if resolved_lease_seconds < 1:
            raise ValueError("lease_seconds must be at least 1")
        if resolved_max_batch < 1:
            raise ValueError("max_batch must be at least 1")
        if resolved_max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self._session_maker = session_maker
        self._orchestrator_factory = orchestrator_factory or AssetResearchOrchestrator
        self._lease_seconds = resolved_lease_seconds
        self._max_batch = resolved_max_batch
        self._max_concurrency = resolved_max_concurrency
        self.scheduler: Any = None
        self._run_locks: WeakKeyDictionary[Any, asyncio.Lock] = WeakKeyDictionary()
        self._wake_tasks: WeakKeyDictionary[Any, asyncio.Task[int]] = WeakKeyDictionary()

    async def claim_due(self, *, now: datetime | None = None) -> list[ClaimedAnalysisTask]:
        """Atomically lease a bounded set of queued user tasks."""
        claim_time = _as_utc(now or _now())
        lease_expires_at = claim_time + timedelta(seconds=self._lease_seconds)
        claims: list[ClaimedAnalysisTask] = []
        async with self._session_maker() as db:
            queue_rows = (
                await db.execute(
                    select(AssetAnalysisTask.asset_type, func.count())
                    .where(
                        AssetAnalysisTask.status == "QUEUED",
                        AssetAnalysisTask.lease_token.is_(None),
                    )
                    .group_by(AssetAnalysisTask.asset_type)
                )
            ).all()
            for asset_type, count in queue_rows:
                set_asset_research_queue_depth(asset_type=str(asset_type), count=int(count))
            candidate_ids = list(
                (
                    await db.execute(
                        select(AssetAnalysisTask.id)
                        .where(
                            AssetAnalysisTask.status == "QUEUED",
                            AssetAnalysisTask.lease_token.is_(None),
                        )
                        .order_by(AssetAnalysisTask.created_at, AssetAnalysisTask.id)
                        .limit(self._max_batch)
                    )
                ).scalars()
            )
            for task_id in candidate_ids:
                lease_token = uuid4().hex
                claimed = await db.execute(
                    update(AssetAnalysisTask)
                    .where(
                        AssetAnalysisTask.id == task_id,
                        AssetAnalysisTask.status == "QUEUED",
                        AssetAnalysisTask.lease_token.is_(None),
                    )
                    .values(
                        status="RUNNING",
                        progress=10,
                        started_at=claim_time,
                        lease_token=lease_token,
                        lease_expires_at=lease_expires_at,
                        lease_heartbeat_at=claim_time,
                        attempt_count=AssetAnalysisTask.attempt_count + 1,
                    )
                )
                if claimed.rowcount == 1:
                    claims.append(
                        ClaimedAnalysisTask(task_id=str(task_id), lease_token=lease_token)
                    )
            await db.commit()
        return claims

    async def recover_expired_leases(self, *, now: datetime | None = None) -> int:
        """Fail only expired matching leases so the user can create an auditable retry."""
        recovery_time = _as_utc(now or _now())
        async with self._session_maker() as db:
            result = await db.execute(
                update(AssetAnalysisTask)
                .where(
                    AssetAnalysisTask.status == "RUNNING",
                    AssetAnalysisTask.lease_token.is_not(None),
                    AssetAnalysisTask.lease_expires_at.is_not(None),
                    AssetAnalysisTask.lease_expires_at <= recovery_time,
                )
                .values(
                    status="FAILED",
                    progress=100,
                    error_code="TASK_LEASE_EXPIRED",
                    completed_at=recovery_time,
                    lease_token=None,
                    lease_expires_at=None,
                    lease_heartbeat_at=None,
                )
            )
            await db.commit()
        return int(result.rowcount or 0)

    async def run_due(self, *, now: datetime | None = None) -> int:
        """Recover stale leases and execute one globally bounded claimed batch."""
        async with self._run_lock_for_current_loop():
            return await self._run_due_once(now=now)

    async def _run_due_once(self, *, now: datetime | None = None) -> int:
        """Run one serialized claim cycle inside this application process."""
        run_time = _as_utc(now or _now())
        await self.recover_expired_leases(now=run_time)
        claims = await self.claim_due(now=run_time)
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def run_claim_with_permit(claim: ClaimedAnalysisTask) -> None:
            async with semaphore:
                await self._run_claim(claim)

        await asyncio.gather(*(run_claim_with_permit(claim) for claim in claims))
        return len(claims)

    def wake(self) -> bool:
        """Schedule one immediate coalesced poll after a task is queued or retried."""
        if not get_settings().ASSET_RESEARCH_TASK_RUNNER_ENABLED:
            return False
        loop = asyncio.get_running_loop()
        existing = self._wake_tasks.get(loop)
        if existing is not None and not existing.done():
            return False
        task = loop.create_task(self.run_due(), name="asset-research-task-wake")
        self._wake_tasks[loop] = task
        task.add_done_callback(lambda completed: self._finish_wake_task(loop, completed))
        return True

    def _run_lock_for_current_loop(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        lock = self._run_locks.get(loop)
        if lock is None:
            lock = asyncio.Lock()
            self._run_locks[loop] = lock
        return lock

    def _finish_wake_task(self, loop: Any, completed: asyncio.Task[int]) -> None:
        if self._wake_tasks.get(loop) is completed:
            self._wake_tasks.pop(loop, None)
        if completed.cancelled():
            return
        try:
            completed.result()
        except Exception as exc:
            logger.error("Interactive asset-research task wake failed: {}", exc)

    async def _run_claim(self, claim: ClaimedAnalysisTask) -> None:
        """Run one matching lease and atomically commit its terminal transition.

        The worker's session may have an old in-memory task object while an
        authenticated user cancels the task through another transaction.  Do
        not let that stale object overwrite the cancellation during commit:
        the final state update compares both ``RUNNING`` and the lease token.
        Whichever transaction wins that compare owns the terminal transition.
        """
        heartbeat_stop = asyncio.Event()
        heartbeat_task: asyncio.Task[None] | None = None
        error_code: str | None = None
        lost_claim = False
        try:
            async with self._session_maker() as db:
                task = await db.get(AssetAnalysisTask, claim.task_id)
                if task is None or task.lease_token != claim.lease_token:
                    return
                record_asset_research_task(asset_type=task.asset_type, status="RUNNING")
                heartbeat_task = asyncio.create_task(
                    self._maintain_lease_heartbeat(claim, heartbeat_stop),
                    name=f"asset-research-task-heartbeat:{claim.task_id}",
                )
                service = self._orchestrator_factory(db)
                await service.run_claimed_task(
                    task_id=claim.task_id,
                    lease_token=claim.lease_token,
                )
                with db.no_autoflush:
                    task = await db.get(AssetAnalysisTask, claim.task_id)
                if task is None:
                    await db.rollback()
                    return
                asset_type = task.asset_type
                started_at = task.started_at
                terminal_update = await self._finalize_claimed_task(db, claim=claim, task=task)
                if terminal_update is not None:
                    await db.commit()
                    duration_seconds = (
                        max(
                            0.0,
                            (terminal_update.completed_at - _as_utc(started_at)).total_seconds(),
                        )
                        if started_at is not None
                        else None
                    )
                    record_asset_research_task(
                        asset_type=asset_type,
                        status=terminal_update.status,
                        duration_seconds=duration_seconds,
                    )
                else:
                    # A cancellation or another terminal transition won the
                    # compare-and-set.  Discard all in-flight snapshots,
                    # predictions, runs and reports from this worker.
                    await db.rollback()
                    lost_claim = True
        except Exception as exc:
            error_code = str(getattr(exc, "code", type(exc).__name__))
        finally:
            if heartbeat_task is not None:
                heartbeat_stop.set()
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
        if error_code is not None:
            await self._recover_unhandled_claim(claim, error_code=error_code)
        elif lost_claim:
            await self._release_lost_terminal_lease(claim)

    async def _finalize_claimed_task(
        self,
        db: AsyncSession,
        *,
        claim: ClaimedAnalysisTask,
        task: AssetAnalysisTask,
    ) -> _TerminalTaskUpdate | None:
        """Compare-and-set one claimed task's desired terminal state.

        ``task`` is deliberately expunged before the statement executes.  A
        service is allowed to prepare a terminal state on that ORM instance,
        but SQLAlchemy must not autoflush stale task fields before the guarded
        update has checked whether a concurrent cancellation already won.
        Other in-flight immutable facts remain in the same transaction and
        are committed only if this state transition succeeds.
        """
        terminal_update = self._terminal_update_for(task)

        db.expunge(task)
        result = await db.execute(
            update(AssetAnalysisTask)
            .where(
                AssetAnalysisTask.id == claim.task_id,
                AssetAnalysisTask.status == "RUNNING",
                AssetAnalysisTask.lease_token == claim.lease_token,
            )
            .values(
                status=terminal_update.status,
                progress=terminal_update.progress,
                error_code=terminal_update.error_code,
                completed_at=terminal_update.completed_at,
                lease_token=None,
                lease_expires_at=None,
                lease_heartbeat_at=None,
            )
            .execution_options(synchronize_session=False)
        )
        return terminal_update if int(getattr(result, "rowcount", 0) or 0) == 1 else None

    @staticmethod
    def _terminal_update_for(task: AssetAnalysisTask) -> _TerminalTaskUpdate:
        """Normalize a service's desired terminal state before it can be committed."""
        if task.status not in _TERMINAL_TASK_STATUSES:
            return _TerminalTaskUpdate(
                status="FAILED",
                progress=100,
                error_code="TASK_RUNNER_NONTERMINAL",
                completed_at=_now(),
            )
        return _TerminalTaskUpdate(
            status=task.status,
            progress=task.progress,
            error_code=task.error_code,
            completed_at=task.completed_at or _now(),
        )

    async def _release_lost_terminal_lease(self, claim: ClaimedAnalysisTask) -> None:
        """Clear only the stale lease left by a winning terminal transition."""
        async with self._session_maker() as db:
            await db.execute(
                update(AssetAnalysisTask)
                .where(
                    AssetAnalysisTask.id == claim.task_id,
                    AssetAnalysisTask.lease_token == claim.lease_token,
                    AssetAnalysisTask.status.in_(_TERMINAL_TASK_STATUSES),
                )
                .values(
                    lease_token=None,
                    lease_expires_at=None,
                    lease_heartbeat_at=None,
                )
            )
            await db.commit()

    async def _maintain_lease_heartbeat(
        self,
        claim: ClaimedAnalysisTask,
        stop: asyncio.Event,
    ) -> None:
        """Renew only this worker's active lease until terminal cleanup begins."""
        interval_seconds = max(1, min(self._lease_seconds // 3, 60))
        try:
            while True:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
                    return
                except asyncio.TimeoutError:
                    # asyncio.TimeoutError (not the builtin TimeoutError): on
                    # Python 3.10 they are distinct classes, and catching the
                    # builtin here killed the heartbeat after the first tick.
                    if not await self._renew_lease(claim):
                        return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Lease expiry remains the fallback if a separate heartbeat
            # transaction cannot reach MySQL while the worker is running.
            logger.warning("Interactive asset-research task lease heartbeat failed: {}", exc)

    async def _renew_lease(self, claim: ClaimedAnalysisTask) -> bool:
        heartbeat_at = _now()
        async with self._session_maker() as db:
            result = await db.execute(
                update(AssetAnalysisTask)
                .where(
                    AssetAnalysisTask.id == claim.task_id,
                    AssetAnalysisTask.status == "RUNNING",
                    AssetAnalysisTask.lease_token == claim.lease_token,
                )
                .values(
                    lease_expires_at=heartbeat_at + timedelta(seconds=self._lease_seconds),
                    lease_heartbeat_at=heartbeat_at,
                )
            )
            await db.commit()
        return result.rowcount == 1

    async def _recover_unhandled_claim(
        self,
        claim: ClaimedAnalysisTask,
        *,
        error_code: str,
    ) -> None:
        """Persist a retryable terminal state when execution fails before cleanup."""
        try:
            async with self._session_maker() as db:
                await db.execute(
                    update(AssetAnalysisTask)
                    .where(
                        AssetAnalysisTask.id == claim.task_id,
                        AssetAnalysisTask.status == "RUNNING",
                        AssetAnalysisTask.lease_token == claim.lease_token,
                    )
                    .values(
                        status="FAILED",
                        progress=100,
                        error_code=error_code,
                        completed_at=_now(),
                        lease_token=None,
                        lease_expires_at=None,
                        lease_heartbeat_at=None,
                    )
                )
                await db.commit()
        except Exception:
            # If the database itself is unavailable, expiry remains the durable
            # fallback and the next poll turns the task into a retryable failure.
            return

    def _ensure_scheduler(self) -> Any:
        if self.scheduler is not None:
            return self.scheduler
        try:
            from apscheduler.executors.asyncio import AsyncIOExecutor
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.interval import IntervalTrigger
        except ImportError as exc:
            raise RuntimeError("APScheduler is not installed") from exc
        scheduler = AsyncIOScheduler(
            executors={"default": AsyncIOExecutor()},
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
            timezone="UTC",
        )
        scheduler.add_job(
            self.run_due,
            trigger=IntervalTrigger(seconds=get_settings().ASSET_RESEARCH_TASK_POLL_SECONDS),
            id="asset_research_task_poll",
            replace_existing=True,
        )
        self.scheduler = scheduler
        return scheduler

    async def start(self) -> bool:
        """Start the durable interactive task poller; API writes explicitly wake it."""
        if not get_settings().ASSET_RESEARCH_TASK_RUNNER_ENABLED:
            return False
        scheduler = self._ensure_scheduler()
        if not scheduler.running:
            scheduler.start()
        return True

    async def shutdown(self) -> None:
        """Stop triggers; any unfinished database lease remains recoverable by expiry."""
        if self.scheduler is not None and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self.scheduler = None
        wake_tasks = list(self._wake_tasks.values())
        for task in wake_tasks:
            if not task.done():
                task.cancel()
        if wake_tasks:
            await asyncio.gather(*wake_tasks, return_exceptions=True)
        self._wake_tasks.clear()
        self._run_locks.clear()


@lru_cache
def get_asset_research_task_runner() -> AssetResearchTaskRunner:
    """Return the lifecycle-owned interactive task runner."""
    return AssetResearchTaskRunner()
