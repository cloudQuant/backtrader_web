"""Database-backed worker for approved multi-asset shadow schedules.

APScheduler only wakes this worker.  The database lease is the source of
truth, so a second application process, a process restart, or a duplicate
trigger cannot turn one scheduled fire into duplicate predictions.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import async_session_maker
from app.middleware.metrics import set_asset_research_queue_depth
from app.models.asset_research import AssetSignalRun, AssetSignalSchedule
from app.services.asset_research.orchestrator import AssetResearchOrchestrator
from app.services.asset_research.schedule_policy import latest_schedule_fire, next_schedule_fire


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ClaimedSchedule:
    """A database lease that must be released by the matching worker token."""

    schedule_id: str
    lease_token: str


OrchestratorFactory = Callable[[AsyncSession], AssetResearchOrchestrator]


class AssetResearchScheduleRunner:
    """Poll due schedules, atomically lease them, and retain retry evidence."""

    def __init__(
        self,
        *,
        session_maker: Any = async_session_maker,
        orchestrator_factory: OrchestratorFactory | None = None,
        lease_seconds: int | None = None,
        max_retries: int | None = None,
        misfire_grace_seconds: int | None = None,
        retry_base_seconds: int | None = None,
        retry_max_seconds: int | None = None,
        max_batch: int | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        settings = get_settings()
        self._session_maker = session_maker
        self._orchestrator_factory = orchestrator_factory or AssetResearchOrchestrator
        self._lease_seconds = (
            lease_seconds
            if lease_seconds is not None
            else settings.ASSET_RESEARCH_SCHEDULE_LEASE_SECONDS
        )
        self._max_retries = (
            max_retries if max_retries is not None else settings.ASSET_RESEARCH_SCHEDULE_MAX_RETRIES
        )
        self._misfire_grace_seconds = (
            misfire_grace_seconds
            if misfire_grace_seconds is not None
            else settings.ASSET_RESEARCH_SCHEDULE_MISFIRE_GRACE_SECONDS
        )
        self._retry_base_seconds = (
            retry_base_seconds
            if retry_base_seconds is not None
            else settings.ASSET_RESEARCH_SCHEDULE_RETRY_BASE_SECONDS
        )
        self._retry_max_seconds = (
            retry_max_seconds
            if retry_max_seconds is not None
            else settings.ASSET_RESEARCH_SCHEDULE_RETRY_MAX_SECONDS
        )
        self._max_batch = (
            max_batch if max_batch is not None else settings.ASSET_RESEARCH_SCHEDULE_MAX_BATCH
        )
        self._max_concurrency = (
            max_concurrency
            if max_concurrency is not None
            else settings.ASSET_RESEARCH_SCHEDULE_WORKER_CONCURRENCY
        )
        if self._max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self.scheduler: Any = None

    @staticmethod
    def _lease_available_clause(now: datetime):
        return or_(
            AssetSignalSchedule.lease_expires_at.is_(None),
            AssetSignalSchedule.lease_expires_at <= now,
        )

    @staticmethod
    def _due_clause(now: datetime):
        return or_(
            and_(
                AssetSignalSchedule.retry_not_before_at.is_not(None),
                AssetSignalSchedule.retry_not_before_at <= now,
            ),
            and_(
                AssetSignalSchedule.retry_not_before_at.is_(None),
                AssetSignalSchedule.next_run_at.is_not(None),
                AssetSignalSchedule.next_run_at <= now,
            ),
        )

    async def claim_due(self, *, now: datetime | None = None) -> list[ClaimedSchedule]:
        """Atomically lease due user or approved system schedules by expiry."""
        claim_time = _as_utc(now or _now())
        lease_expires_at = claim_time + timedelta(seconds=self._lease_seconds)
        claims: list[ClaimedSchedule] = []
        async with self._session_maker() as db:
            queue_rows = (
                await db.execute(
                    select(AssetSignalSchedule.asset_type, func.count())
                    .where(
                        AssetSignalSchedule.enabled.is_(True),
                        self._lease_available_clause(claim_time),
                        self._due_clause(claim_time),
                    )
                    .group_by(AssetSignalSchedule.asset_type)
                )
            ).all()
            for asset_type, count in queue_rows:
                set_asset_research_queue_depth(asset_type=str(asset_type), count=int(count))
            candidates = list(
                (
                    await db.execute(
                        select(AssetSignalSchedule.id)
                        .where(
                            AssetSignalSchedule.enabled.is_(True),
                            or_(
                                and_(
                                    AssetSignalSchedule.owner_scope == "USER",
                                    AssetSignalSchedule.user_id.is_not(None),
                                ),
                                and_(
                                    AssetSignalSchedule.owner_scope.in_(
                                        ["PUBLIC_SHADOW", "ADMIN_EVAL"]
                                    ),
                                    AssetSignalSchedule.user_id.is_(None),
                                ),
                            ),
                            self._lease_available_clause(claim_time),
                            self._due_clause(claim_time),
                        )
                        .order_by(
                            AssetSignalSchedule.retry_not_before_at,
                            AssetSignalSchedule.next_run_at,
                            AssetSignalSchedule.id,
                        )
                        .limit(self._max_batch)
                    )
                ).scalars()
            )
            for schedule_id in candidates:
                lease_token = uuid4().hex
                result = await db.execute(
                    update(AssetSignalSchedule)
                    .where(
                        AssetSignalSchedule.id == schedule_id,
                        AssetSignalSchedule.enabled.is_(True),
                        self._lease_available_clause(claim_time),
                        self._due_clause(claim_time),
                    )
                    .values(
                        lease_token=lease_token,
                        lease_expires_at=lease_expires_at,
                        last_attempt_at=claim_time,
                    )
                )
                if result.rowcount == 1:
                    claims.append(
                        ClaimedSchedule(schedule_id=str(schedule_id), lease_token=lease_token)
                    )
            await db.commit()
        return claims

    async def run_due(self, *, now: datetime | None = None) -> int:
        """Run one bounded claimed batch and return the number of leased rows."""
        claim_time = _as_utc(now or _now())
        claims = await self.claim_due(now=claim_time)
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def run_claim_with_permit(claim: ClaimedSchedule) -> None:
            async with semaphore:
                await self._run_claim(claim, claim_time=claim_time)

        await asyncio.gather(*(run_claim_with_permit(claim) for claim in claims))
        return len(claims)

    async def _run_claim(self, claim: ClaimedSchedule, *, claim_time: datetime) -> None:
        """Consume one lease, preserving frozen failure context before release."""
        try:
            async with self._session_maker() as db:
                schedule = await db.get(AssetSignalSchedule, claim.schedule_id)
                if schedule is None or schedule.lease_token != claim.lease_token:
                    return
                service = self._orchestrator_factory(db)
                if schedule.retry_of_run_id is not None:
                    run = await service.retry_claimed_schedule(
                        schedule_id=schedule.id,
                        failed_run_id=schedule.retry_of_run_id,
                    )
                elif schedule.next_run_at is not None:
                    scheduled_fire_at = _as_utc(schedule.next_run_at)
                    if self._is_misfire(schedule, claim_time):
                        if schedule.misfire_policy == "SKIP":
                            await self._skip_misfire(db, schedule, claim.lease_token, claim_time)
                            await db.commit()
                            return
                        if schedule.misfire_policy == "RUN_ONCE":
                            scheduled_fire_at = latest_schedule_fire(
                                cutoff_policy=schedule.cutoff_policy,
                                at=claim_time,
                            )
                    run = await service.run_claimed_schedule(
                        schedule_id=schedule.id,
                        scheduled_fire_at=scheduled_fire_at,
                        run_type="SCHEDULED",
                    )
                else:
                    await self._release_without_retry(
                        db,
                        schedule,
                        claim.lease_token,
                        error_code="SCHEDULE_FIRE_MISSING",
                    )
                    await db.commit()
                    return

                if run.status == "SUCCEEDED":
                    self._finish_success(schedule, claim.lease_token)
                else:
                    self._finish_failure(
                        schedule,
                        run,
                        claim.lease_token,
                        completed_at=_now(),
                    )
                await db.commit()
        except Exception as exc:
            # A database-level failure may prevent a durable failed run from
            # being written.  Release only the matching lease in a fresh
            # transaction; the unchanged due fire will be safely reclaimed.
            await self._recover_unhandled_claim(
                claim,
                error_code=getattr(exc, "code", type(exc).__name__),
            )

    def _finish_success(self, schedule: AssetSignalSchedule, lease_token: str) -> None:
        if schedule.lease_token != lease_token:
            return
        schedule.last_error_code = None
        self._clear_retry(schedule)
        self._release_lease(schedule)

    def _finish_failure(
        self,
        schedule: AssetSignalSchedule,
        run: AssetSignalRun,
        lease_token: str,
        *,
        completed_at: datetime,
    ) -> None:
        if schedule.lease_token != lease_token:
            return
        error_code = str((run.counts_json or {}).get("error_code") or "SCHEDULE_RUN_FAILED")
        schedule.last_error_code = error_code
        retry_attempt = int(schedule.retry_attempt or 0) + 1
        if retry_attempt <= self._max_retries:
            schedule.retry_of_run_id = run.id
            schedule.retry_not_before_at = completed_at + timedelta(
                seconds=min(
                    self._retry_base_seconds * (2 ** (retry_attempt - 1)),
                    self._retry_max_seconds,
                )
            )
            schedule.retry_scheduled_fire_at = run.as_of_at
            schedule.retry_cutoff_at = run.cutoff_at
            schedule.retry_schedule_version = run.schedule_version
            schedule.retry_cutoff_policy_version = run.cutoff_policy_version
            schedule.retry_schedule_config_json = run.schedule_config_json
            schedule.retry_attempt = retry_attempt
        else:
            # Do not let a poisoned historic fire block all future approved
            # fires.  Advance only from the original scheduled timestamp.
            cutoff_policy = str((run.schedule_config_json or {}).get("cutoff_policy") or "")
            try:
                schedule.next_run_at = next_schedule_fire(
                    cutoff_policy=cutoff_policy,
                    after=_as_utc(run.as_of_at),
                )
            except Exception:
                schedule.next_run_at = None
                schedule.last_error_code = "SCHEDULE_NEXT_FIRE_UNAVAILABLE"
            self._clear_retry(schedule)
        self._release_lease(schedule)

    async def _release_without_retry(
        self,
        db: AsyncSession,
        schedule: AssetSignalSchedule,
        lease_token: str,
        *,
        error_code: str,
    ) -> None:
        if schedule.lease_token != lease_token:
            return
        schedule.last_error_code = error_code
        self._release_lease(schedule)
        await db.flush()

    def _is_misfire(self, schedule: AssetSignalSchedule, claim_time: datetime) -> bool:
        if schedule.next_run_at is None:
            return False
        due_at = _as_utc(schedule.next_run_at)
        return claim_time > due_at + timedelta(seconds=self._misfire_grace_seconds)

    async def _skip_misfire(
        self,
        db: AsyncSession,
        schedule: AssetSignalSchedule,
        lease_token: str,
        claim_time: datetime,
    ) -> None:
        """Advance a stale fire without manufacturing a prediction or run."""
        if schedule.lease_token != lease_token:
            return
        schedule.next_run_at = next_schedule_fire(
            cutoff_policy=schedule.cutoff_policy,
            after=claim_time,
        )
        schedule.last_error_code = "SCHEDULE_MISFIRE_SKIPPED"
        self._release_lease(schedule)
        await db.flush()

    async def _recover_unhandled_claim(self, claim: ClaimedSchedule, *, error_code: str) -> None:
        try:
            async with self._session_maker() as db:
                schedule = await db.get(AssetSignalSchedule, claim.schedule_id)
                if schedule is not None and schedule.lease_token == claim.lease_token:
                    schedule.last_error_code = error_code
                    self._release_lease(schedule)
                    await db.commit()
        except Exception:
            # The lease expiry remains the last safety net when the database
            # itself cannot accept a recovery update.
            return

    @staticmethod
    def _release_lease(schedule: AssetSignalSchedule) -> None:
        schedule.lease_token = None
        schedule.lease_expires_at = None

    @staticmethod
    def _clear_retry(schedule: AssetSignalSchedule) -> None:
        schedule.retry_of_run_id = None
        schedule.retry_not_before_at = None
        schedule.retry_scheduled_fire_at = None
        schedule.retry_cutoff_at = None
        schedule.retry_schedule_version = None
        schedule.retry_cutoff_policy_version = None
        schedule.retry_schedule_config_json = None
        schedule.retry_attempt = 0

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
            trigger=IntervalTrigger(seconds=get_settings().ASSET_RESEARCH_SCHEDULE_POLL_SECONDS),
            id="asset_research_schedule_poll",
            replace_existing=True,
        )
        self.scheduler = scheduler
        return scheduler

    async def start(self) -> bool:
        """Start a disabled-by-default bounded database poller."""
        if not get_settings().ASSET_RESEARCH_SCHEDULE_ENABLED:
            return False
        scheduler = self._ensure_scheduler()
        if not scheduler.running:
            scheduler.start()
        return True

    async def shutdown(self) -> None:
        if self.scheduler is not None and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self.scheduler = None


@lru_cache
def get_asset_research_schedule_runner() -> AssetResearchScheduleRunner:
    """Return the lifecycle-owned runner; tests may instantiate an isolated one."""
    return AssetResearchScheduleRunner()
