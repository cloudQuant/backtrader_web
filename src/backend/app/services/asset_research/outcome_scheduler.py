"""Database-leased worker that advances mature multi-asset outcome heads.

One observed source snapshot can legally score several outcome heads for one
immutable prediction.  The prediction-level lease therefore prevents duplicate
collection across application processes without making a mutable worker state
part of the decision-input hash.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any
from uuid import uuid4

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import async_session_maker
from app.middleware.metrics import set_asset_research_outcome_backlog
from app.models.asset_research import AssetSignalOutcome, AssetSignalPrediction
from app.services.asset_research.orchestrator import AssetResearchOrchestrator


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ClaimedOutcomePrediction:
    """A prediction lease that can only be released by its owner token."""

    prediction_id: str
    lease_token: str


OrchestratorFactory = Callable[[AsyncSession], AssetResearchOrchestrator]


class AssetResearchOutcomeRunner:
    """Poll mature heads and score each prediction at most once per lease."""

    def __init__(
        self,
        *,
        session_maker: Any = async_session_maker,
        orchestrator_factory: OrchestratorFactory | None = None,
        lease_seconds: int | None = None,
        max_batch: int | None = None,
    ) -> None:
        settings = get_settings()
        self._session_maker = session_maker
        self._orchestrator_factory = orchestrator_factory or AssetResearchOrchestrator
        self._lease_seconds = (
            lease_seconds
            if lease_seconds is not None
            else settings.ASSET_RESEARCH_OUTCOME_EVALUATOR_LEASE_SECONDS
        )
        self._max_batch = (
            max_batch
            if max_batch is not None
            else settings.ASSET_RESEARCH_OUTCOME_EVALUATOR_MAX_BATCH
        )
        self.scheduler: Any = None
        self._observed_asset_types: set[str] = set()

    @staticmethod
    def _lease_available_clause(now: datetime):
        return or_(
            AssetSignalPrediction.outcome_lease_expires_at.is_(None),
            AssetSignalPrediction.outcome_lease_expires_at <= now,
        )

    @staticmethod
    def _has_due_outcome_clause(now: datetime):
        return exists(
            select(1)
            .select_from(AssetSignalOutcome)
            .where(
                AssetSignalOutcome.prediction_id == AssetSignalPrediction.id,
                AssetSignalOutcome.status == "PENDING",
                AssetSignalOutcome.maturity_at.is_not(None),
                AssetSignalOutcome.maturity_at <= now,
            )
        ).correlate(AssetSignalPrediction)

    async def claim_due(self, *, now: datetime | None = None) -> list[ClaimedOutcomePrediction]:
        """Atomically lease mature predictions, not individual outcome heads."""
        claim_time = _as_utc(now or _now())
        lease_expires_at = claim_time + timedelta(seconds=self._lease_seconds)
        claims: list[ClaimedOutcomePrediction] = []
        async with self._session_maker() as db:
            candidate_ids = list(
                (
                    await db.execute(
                        select(AssetSignalPrediction.id)
                        .where(
                            self._lease_available_clause(claim_time),
                            self._has_due_outcome_clause(claim_time),
                        )
                        .order_by(
                            AssetSignalPrediction.as_of_at,
                            AssetSignalPrediction.id,
                        )
                        .limit(self._max_batch)
                    )
                ).scalars()
            )
            for prediction_id in candidate_ids:
                lease_token = uuid4().hex
                result = await db.execute(
                    update(AssetSignalPrediction)
                    .where(
                        AssetSignalPrediction.id == prediction_id,
                        self._lease_available_clause(claim_time),
                        self._has_due_outcome_clause(claim_time),
                    )
                    .values(
                        outcome_lease_token=lease_token,
                        outcome_lease_expires_at=lease_expires_at,
                        outcome_last_attempt_at=claim_time,
                    )
                )
                if result.rowcount == 1:
                    claims.append(
                        ClaimedOutcomePrediction(
                            prediction_id=str(prediction_id),
                            lease_token=lease_token,
                        )
                    )
            await db.commit()
        return claims

    async def run_due(self, *, now: datetime | None = None) -> int:
        """Claim and process one bounded set of mature predictions."""
        claim_time = _as_utc(now or _now())
        await self.refresh_backlog(now=claim_time)
        claims = await self.claim_due(now=claim_time)
        for claim in claims:
            await self._run_claim(claim, claim_time=claim_time)
        await self.refresh_backlog(now=claim_time)
        return len(claims)

    async def refresh_backlog(self, *, now: datetime | None = None) -> None:
        """Publish mature pending outcome-head counts without identity-level labels."""
        cutoff = _as_utc(now or _now())
        async with self._session_maker() as db:
            rows = (
                await db.execute(
                    select(AssetSignalPrediction.asset_type, func.count(AssetSignalOutcome.id))
                    .join(
                        AssetSignalPrediction,
                        AssetSignalPrediction.id == AssetSignalOutcome.prediction_id,
                    )
                    .where(
                        AssetSignalOutcome.status == "PENDING",
                        AssetSignalOutcome.maturity_at.is_not(None),
                        AssetSignalOutcome.maturity_at <= cutoff,
                    )
                    .group_by(AssetSignalPrediction.asset_type)
                    .order_by(AssetSignalPrediction.asset_type)
                )
            ).all()
        counts = {str(asset_type): int(count) for asset_type, count in rows}
        self._observed_asset_types.update(counts)
        for asset_type in sorted(self._observed_asset_types):
            set_asset_research_outcome_backlog(
                asset_type=asset_type,
                count=counts.get(asset_type, 0),
            )

    async def _run_claim(self, claim: ClaimedOutcomePrediction, *, claim_time: datetime) -> None:
        """Collect one authorized observed vintage and release its lease safely."""
        try:
            async with self._session_maker() as db:
                prediction = await db.get(AssetSignalPrediction, claim.prediction_id)
                if prediction is None or prediction.outcome_lease_token != claim.lease_token:
                    return
                errors: dict[str, str] = {}
                try:
                    service = self._orchestrator_factory(db)
                    await service.evaluate_due_outcomes(
                        cutoff_at=claim_time,
                        limit=1,
                        prediction_ids=[prediction.id],
                        errors=errors,
                    )
                    prediction.outcome_last_error_code = errors.get(prediction.id)
                except Exception as exc:
                    prediction.outcome_last_error_code = str(
                        getattr(exc, "code", type(exc).__name__)
                    )
                self._release_lease(prediction, claim.lease_token)
                await db.commit()
        except Exception as exc:
            await self._recover_unhandled_claim(
                claim,
                error_code=str(getattr(exc, "code", type(exc).__name__)),
            )

    async def _recover_unhandled_claim(
        self,
        claim: ClaimedOutcomePrediction,
        *,
        error_code: str,
    ) -> None:
        """Make a failed attempt retryable when the original transaction dies."""
        try:
            async with self._session_maker() as db:
                prediction = await db.get(AssetSignalPrediction, claim.prediction_id)
                if prediction is not None and prediction.outcome_lease_token == claim.lease_token:
                    prediction.outcome_last_error_code = error_code
                    self._release_lease(prediction, claim.lease_token)
                    await db.commit()
        except Exception:
            # Lease expiry is the last safety net if the database is unavailable.
            return

    @staticmethod
    def _release_lease(prediction: AssetSignalPrediction, lease_token: str) -> None:
        if prediction.outcome_lease_token != lease_token:
            return
        prediction.outcome_lease_token = None
        prediction.outcome_lease_expires_at = None

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
            trigger=IntervalTrigger(
                seconds=get_settings().ASSET_RESEARCH_OUTCOME_EVALUATOR_POLL_SECONDS
            ),
            id="asset_research_outcome_evaluator_poll",
            replace_existing=True,
        )
        self.scheduler = scheduler
        return scheduler

    async def start(self) -> bool:
        """Start the disabled-by-default evaluator poller."""
        if not get_settings().ASSET_RESEARCH_OUTCOME_EVALUATOR_ENABLED:
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
def get_asset_research_outcome_runner() -> AssetResearchOutcomeRunner:
    """Return the lifecycle-owned evaluator runner."""
    return AssetResearchOutcomeRunner()
