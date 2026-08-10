"""Authorized tombstone executor for immutable asset-research lifecycle facts.

The retention planner already proves which rows are eligible for cleanup.
This executor only turns an approved dry-run into tombstone records.  It never
hard-deletes research facts, never bypasses legal hold, and every action is
written as an auditable timestamp on the immutable row itself.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.asset_research.retention import (
    _RETENTION_MODELS_BY_TABLE,
    AssetResearchRetentionService,
    RetentionCandidate,
    RetentionDryRunReport,
)


@dataclass(frozen=True, slots=True)
class RetentionExecutionAction:
    """One immutable tombstone action for a due research fact."""

    table_name: str
    record_id: str
    action: str = "TOMBSTONE"


@dataclass(frozen=True, slots=True)
class RetentionExecutionReport:
    """Audit payload for one approved lifecycle execution or dry-run."""

    as_of: datetime
    approval_reference: str
    action_count: int
    actions: tuple[RetentionExecutionAction, ...]
    dry_run: bool
    already_tombstoned_count: int


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class AssetResearchRetentionExecutor:
    """Apply approved dry-run candidates as non-destructive tombstones."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute(
        self,
        *,
        as_of: datetime,
        approval_reference: str,
        table_names: Collection[str] | None = None,
        candidate_limit_per_table: int = 100,
        dry_run: bool = True,
    ) -> RetentionExecutionReport:
        """Return a plan and, when dry_run=False, tombstone eligible facts.

        Hard deletion and object-storage removal remain outside this executor
        until a separately approved storage lifecycle runbook exists.  The
        tombstone is the only durable audit boundary implemented here.
        """
        normalized_approval = approval_reference.strip()
        if not normalized_approval:
            raise ValueError("RETENTION_APPROVAL_REQUIRED")
        if len(normalized_approval) > 256:
            raise ValueError("RETENTION_APPROVAL_TOO_LONG")

        planning = AssetResearchRetentionService(self.db)
        dry_run_report = await planning.plan_dry_run(
            as_of=as_of,
            table_names=table_names,
            candidate_limit_per_table=candidate_limit_per_table,
        )
        actions = tuple(
            RetentionExecutionAction(
                table_name=candidate.table_name,
                record_id=candidate.record_id,
            )
            for candidate in dry_run_report.candidates
        )

        if not dry_run and actions:
            await self._tombstone_candidates(
                dry_run_report,
                tombstoned_at=_as_utc(as_of),
                approval_reference=normalized_approval,
            )
        await self.db.commit()

        return RetentionExecutionReport(
            as_of=_as_utc(as_of),
            approval_reference=normalized_approval,
            action_count=len(actions),
            actions=actions,
            dry_run=dry_run,
            already_tombstoned_count=dry_run_report.already_tombstoned_count,
        )

    async def _tombstone_candidates(
        self,
        report: RetentionDryRunReport,
        *,
        tombstoned_at: datetime,
        approval_reference: str,
    ) -> None:
        """Re-read each candidate and tombstone only still-eligible rows."""
        for candidate in report.candidates:
            await self._tombstone_candidate(
                candidate,
                tombstoned_at=tombstoned_at,
                approval_reference=approval_reference,
            )

    async def _tombstone_candidate(
        self,
        candidate: RetentionCandidate,
        *,
        tombstoned_at: datetime,
        approval_reference: str,
    ) -> None:
        model = _RETENTION_MODELS_BY_TABLE[candidate.table_name]
        row = await self.db.get(model, candidate.record_id)
        if row is None:
            return
        if getattr(row, "legal_hold", False):
            return
        if getattr(row, "tombstoned_at", None) is not None:
            return
        row.tombstoned_at = tombstoned_at
        retention_audit = getattr(row, "retention_audit_json", None)
        if retention_audit is not None:
            row.retention_audit_json = [
                *(retention_audit or []),
                {
                    "action": "TOMBSTONE",
                    "approved_at": tombstoned_at.isoformat(),
                    "approval_reference": approval_reference,
                },
            ]
