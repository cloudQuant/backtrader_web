"""Append-only experiment ledger used by trusted research statistical gates."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import ResearchCandidate, ResearchRun, ResearchTrial
from app.services.research.discovery_search_budget import lock_search_epoch

_TRIAL_STATUSES = frozenset(
    {"PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT", "INVALID"}
)


class ExperimentLedger:
    """Write every experiment outcome once and expose auditable trial counts."""

    async def record_trial(
        self,
        *,
        user_id: str,
        run_id: str,
        candidate_id: str | None,
        idempotency_key: str,
        stage: str,
        status: str,
        input_hash: str,
        metrics: dict[str, Any],
        observed_market_performance: bool,
        counts_as_market_trial: bool,
        counting_reason: str,
        error_code: str | None = None,
        returns_artifact_id: str | None = None,
        parent_trial_id: str | None = None,
    ) -> ResearchTrial:
        """Persist a success, failure, cancel, timeout, or invalid attempt.

        An idempotent repeat returns the original append-only row.  A caller
        cannot turn an unrelated payload into an apparently identical trial by
        reusing the same key.
        """

        async with database.async_session_maker() as session:
            trial = await self.record_trial_in_session(
                session,
                user_id=user_id,
                run_id=run_id,
                candidate_id=candidate_id,
                idempotency_key=idempotency_key,
                stage=stage,
                status=status,
                input_hash=input_hash,
                metrics=metrics,
                observed_market_performance=observed_market_performance,
                counts_as_market_trial=counts_as_market_trial,
                counting_reason=counting_reason,
                error_code=error_code,
                returns_artifact_id=returns_artifact_id,
                parent_trial_id=parent_trial_id,
            )
            await session.commit()
            await session.refresh(trial)
            return trial

    async def record_trial_in_session(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        run_id: str,
        candidate_id: str | None,
        idempotency_key: str,
        stage: str,
        status: str,
        input_hash: str,
        metrics: dict[str, Any],
        observed_market_performance: bool,
        counts_as_market_trial: bool,
        counting_reason: str,
        error_code: str | None = None,
        returns_artifact_id: str | None = None,
        parent_trial_id: str | None = None,
    ) -> ResearchTrial:
        """Append one trial within the caller-owned transaction.

        Epoch-backed runs take the epoch's database write lock before the run
        lock so ordinal allocation is serialized across independent SQLite
        connections as well as databases that honor ``FOR UPDATE``.  Legacy
        runs with no epoch retain their original per-run ledger behavior.
        """

        if status not in _TRIAL_STATUSES:
            raise ValueError("RESEARCH_TRIAL_STATUS_INVALID")
        if counts_as_market_trial and not observed_market_performance:
            raise ValueError("MARKET_TRIAL_REQUIRES_OBSERVED_PERFORMANCE")
        if counts_as_market_trial and not counting_reason.strip():
            raise ValueError("MARKET_TRIAL_COUNTING_REASON_REQUIRED")

        await _lock_epoch_before_run(session, user_id=user_id, run_id=run_id)
        run = await _owner_run(session, user_id, run_id)
        if candidate_id is not None:
            candidate = await _owner_candidate(session, user_id, candidate_id)
            if candidate.run_id != run.id:
                raise ValueError("RESEARCH_TRIAL_CANDIDATE_RUN_MISMATCH")

        existing_result = await session.execute(
            select(ResearchTrial).where(
                ResearchTrial.run_id == run.id,
                ResearchTrial.idempotency_key == idempotency_key,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            if not _same_trial_request(
                existing,
                candidate_id=candidate_id,
                stage=stage,
                status=status,
                input_hash=input_hash,
                metrics=metrics,
                observed_market_performance=observed_market_performance,
                counts_as_market_trial=counts_as_market_trial,
                counting_reason=counting_reason,
                error_code=error_code,
                returns_artifact_id=returns_artifact_id,
                parent_trial_id=parent_trial_id,
            ):
                raise ValueError("RESEARCH_TRIAL_IDEMPOTENCY_CONFLICT")
            return existing

        ordinal = await session.scalar(
            select(func.max(ResearchTrial.ordinal)).where(ResearchTrial.run_id == run.id)
        )
        model = ResearchTrial(
            user_id=user_id,
            run_id=run.id,
            candidate_id=candidate_id,
            parent_trial_id=parent_trial_id,
            ordinal=int(ordinal or 0) + 1,
            idempotency_key=idempotency_key,
            stage=stage,
            status=status,
            input_hash=input_hash,
            returns_artifact_id=returns_artifact_id,
            metrics=metrics,
            observed_market_performance=observed_market_performance,
            counts_as_market_trial=counts_as_market_trial,
            counting_reason=counting_reason.strip(),
            error_code=error_code,
        )
        session.add(model)
        await session.flush()
        return model

    async def count_market_trials(self, user_id: str, run_id: str) -> int:
        """Return the full count used by multiple-testing correction gates."""

        async with database.async_session_maker() as session:
            await _owner_run(session, user_id, run_id)
            count = await session.scalar(
                select(func.count(ResearchTrial.id)).where(
                    ResearchTrial.run_id == run_id,
                    ResearchTrial.counts_as_market_trial.is_(True),
                )
            )
            return int(count or 0)


async def _owner_run(session: Any, user_id: str, run_id: str) -> ResearchRun:
    result = await session.execute(
        select(ResearchRun)
        .where(ResearchRun.id == run_id, ResearchRun.user_id == user_id)
        .with_for_update()
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise ValueError("RESEARCH_RUN_NOT_FOUND")
    return model


async def _lock_epoch_before_run(session: AsyncSession, *, user_id: str, run_id: str) -> None:
    """Write-lock an attached epoch before taking the run row lock.

    The preliminary read only distinguishes a historical NULL epoch from a
    missing run.  It is intentionally not the run lock: epoch-backed paths
    next obtain the real epoch write lock, then ``_owner_run`` takes the run
    lock in the same order as discovery preparation.
    """

    epoch_id = await session.scalar(
        select(ResearchRun.experiment_epoch_id).where(
            ResearchRun.id == run_id,
            ResearchRun.user_id == user_id,
        )
    )
    if epoch_id is not None:
        await lock_search_epoch(
            session,
            user_id=user_id,
            run_id=run_id,
            require_open=False,
        )


async def _owner_candidate(session: Any, user_id: str, candidate_id: str) -> ResearchCandidate:
    result = await session.execute(
        select(ResearchCandidate).where(
            ResearchCandidate.id == candidate_id,
            ResearchCandidate.user_id == user_id,
        )
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise ValueError("CANDIDATE_NOT_FOUND")
    return model


def _same_trial_request(
    existing: ResearchTrial,
    *,
    candidate_id: str | None,
    stage: str,
    status: str,
    input_hash: str,
    metrics: dict[str, Any],
    observed_market_performance: bool,
    counts_as_market_trial: bool,
    counting_reason: str,
    error_code: str | None,
    returns_artifact_id: str | None,
    parent_trial_id: str | None,
) -> bool:
    return (
        existing.candidate_id == candidate_id
        and existing.stage == stage
        and existing.status == status
        and existing.input_hash == input_hash
        and dict(existing.metrics or {}) == metrics
        and existing.observed_market_performance == observed_market_performance
        and existing.counts_as_market_trial == counts_as_market_trial
        and existing.counting_reason == counting_reason.strip()
        and existing.error_code == error_code
        and existing.returns_artifact_id == returns_artifact_id
        and existing.parent_trial_id == parent_trial_id
    )
