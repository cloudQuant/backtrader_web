"""Reserve a family-wide search slot in the discovery journal's transaction."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_research_v2 import (
    ResearchDiscoveryExecution,
    ResearchExperimentEpoch,
    ResearchRun,
    ResearchTrial,
)
from app.services.research.canonical import content_hash


@dataclass(frozen=True, slots=True)
class DiscoverySearchSlot:
    """Server-derived allocation; the caller persists it with the command."""

    epoch_id: str
    ordinal: int
    budget_hash: str


async def lock_search_epoch(
    session: AsyncSession, *, user_id: str, run_id: str, require_open: bool = True
) -> ResearchExperimentEpoch:
    """Acquire a real row write lock, including on SQLite (which ignores FOR UPDATE).

    All search allocation and trial publication paths acquire this lock before
    run/task/journal locks. No process-local lock or SELECT-then-insert counter
    is an authorization boundary. The no-op UPDATE holds the lock to commit.
    """

    epoch_id = await session.scalar(
        select(ResearchRun.experiment_epoch_id).where(
            ResearchRun.id == run_id, ResearchRun.user_id == user_id
        )
    )
    if epoch_id is None:
        raise ValueError("DISCOVERY_EXECUTION_PREPARE_DENIED")
    return await lock_experiment_epoch(
        session,
        user_id=user_id,
        epoch_id=epoch_id,
        require_open=require_open,
        denied_code="DISCOVERY_EXECUTION_PREPARE_DENIED",
    )


async def lock_experiment_epoch(
    session: AsyncSession,
    *,
    user_id: str,
    epoch_id: str,
    require_open: bool = True,
    denied_code: str = "EXPERIMENT_EPOCH_LOCK_DENIED",
) -> ResearchExperimentEpoch:
    """Serialize every family-expanding writer on one database epoch row."""

    conditions = [
        ResearchExperimentEpoch.id == epoch_id,
        ResearchExperimentEpoch.user_id == user_id,
    ]
    if require_open:
        conditions += [
            ResearchExperimentEpoch.status == "OPEN",
            ResearchExperimentEpoch.selected_candidate_id.is_(None),
        ]
    locked = await session.execute(
        update(ResearchExperimentEpoch)
        .where(*conditions)
        .values(status=ResearchExperimentEpoch.status)
        .execution_options(synchronize_session=False)
    )
    if locked.rowcount != 1:
        raise ValueError(denied_code)
    epoch = await session.get(ResearchExperimentEpoch, epoch_id, populate_existing=True)
    if epoch is None:
        raise ValueError(denied_code)
    return epoch


async def next_search_slot(
    session: AsyncSession, *, epoch: ResearchExperimentEpoch
) -> DiscoverySearchSlot:
    """Count every submitted command, plus unlinked historical trials.

    PREPARED/UNKNOWN/failed commands remain occupied. Re-reading one receipt
    uses its existing journal row, not this function. Legacy NULL allocation
    evidence is counted through the original run; we never fabricate it or
    silently reset a family's budget after migration.
    """

    budget = epoch.search_budget
    limit = budget.get("max_trials") if type(budget) is dict else None
    if type(limit) is not int or not 1 <= limit <= 2_147_483_647:
        raise ValueError("DISCOVERY_SEARCH_BUDGET_INVALID")
    try:
        budget_hash = content_hash(budget)
    except (TypeError, ValueError) as exc:
        raise ValueError("DISCOVERY_SEARCH_BUDGET_INVALID") from exc
    family_runs = select(ResearchRun.id).where(
        ResearchRun.experiment_epoch_id == epoch.id,
        ResearchRun.user_id == epoch.user_id,
    )
    journals = ResearchDiscoveryExecution
    # A run cannot move a persisted allocation into another family's budget.
    in_family = (journals.run_id.in_(family_runs)) | (journals.search_epoch_id == epoch.id)
    drifted = await session.scalar(
        select(journals.id)
        .where(
            in_family,
            journals.search_budget_hash.is_not(None),
            (journals.search_budget_hash != budget_hash) | (journals.search_epoch_id != epoch.id),
        )
        .limit(1)
    )
    if drifted is not None:
        raise ValueError("DISCOVERY_SEARCH_BUDGET_DRIFT")
    journal_count = await session.scalar(select(func.count(journals.id)).where(in_family))
    # A canonical journal->trial link is the only deduplication rule. No key
    # prefix or caller-supplied "technical retry" label can exempt a new run.
    linked = exists(select(journals.id).where(journals.trial_id == ResearchTrial.id))
    legacy_count = await session.scalar(
        select(func.count(ResearchTrial.id)).where(
            ResearchTrial.run_id.in_(family_runs),
            ~linked,
        )
    )
    used = int(journal_count or 0) + int(legacy_count or 0)
    if used >= limit:
        raise ValueError("DISCOVERY_SEARCH_BUDGET_EXHAUSTED")
    last_ordinal = await session.scalar(
        select(func.max(journals.search_ordinal)).where(journals.search_epoch_id == epoch.id)
    )
    return DiscoverySearchSlot(epoch.id, max(used, int(last_ordinal or 0)) + 1, budget_hash)
