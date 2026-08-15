"""Read-only lifecycle planning for immutable asset-research facts.

The first lifecycle control is deliberately non-destructive: it reports exactly
which records are due, held, or already tombstoned before a separately
authorized retention executor is ever allowed to remove a payload or redact a
user-facing artifact.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.metrics import record_asset_research_lifecycle
from app.models.asset_research import (
    AssetAnalysisExport,
    AssetAnalysisReport,
    AssetAnalysisTask,
    AssetDataSourceRegistry,
    AssetInstrument,
    AssetModelRegistry,
    AssetModelStatusEvent,
    AssetPositionContextSnapshot,
    AssetReportPublication,
    AssetScheduleManifest,
    AssetSignalOutcome,
    AssetSignalPrediction,
    AssetSignalRun,
    AssetSignalSchedule,
    AssetSourceSnapshot,
)


@dataclass(frozen=True, slots=True)
class RetentionCandidate:
    """A due fact selected for a future authorized lifecycle action."""

    table_name: str
    record_id: str
    retention_class: str
    retention_expires_at: datetime


@dataclass(frozen=True, slots=True)
class RetentionDryRunReport:
    """Bounded, auditable preview; no state is changed while producing it."""

    as_of: datetime
    candidates: tuple[RetentionCandidate, ...]
    eligible_count: int
    legal_hold_count: int
    already_tombstoned_count: int
    candidate_limit_per_table: int


_RETENTION_MODELS: tuple[type[Any], ...] = (
    AssetInstrument,
    AssetDataSourceRegistry,
    AssetPositionContextSnapshot,
    AssetSourceSnapshot,
    AssetAnalysisTask,
    AssetAnalysisReport,
    AssetAnalysisExport,
    AssetReportPublication,
    AssetScheduleManifest,
    AssetSignalSchedule,
    AssetSignalRun,
    AssetSignalPrediction,
    AssetSignalOutcome,
    AssetModelRegistry,
    AssetModelStatusEvent,
)
_RETENTION_MODELS_BY_TABLE = {model.__tablename__: model for model in _RETENTION_MODELS}


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite test values without changing the retention instant."""
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


class AssetResearchRetentionService:
    """Builds bounded lifecycle dry-runs without deleting or mutating any fact."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def plan_dry_run(
        self,
        *,
        as_of: datetime,
        table_names: Collection[str] | None = None,
        candidate_limit_per_table: int = 100,
    ) -> RetentionDryRunReport:
        """List due records after honoring legal hold and existing tombstones.

        A production executor must consume this immutable plan together with
        source-license, regional, object-storage, and dependency checks.  It
        intentionally cannot be used to delete rows.
        """
        if candidate_limit_per_table < 1 or candidate_limit_per_table > 1_000:
            raise ValueError("RETENTION_CANDIDATE_LIMIT_INVALID")
        cutoff = _as_utc(as_of)
        models = self._models_for(table_names)
        candidates: list[RetentionCandidate] = []
        eligible_count = 0
        legal_hold_count = 0
        already_tombstoned_count = 0

        for model in models:
            due = (
                model.retention_expires_at.is_not(None),
                model.retention_expires_at <= cutoff,
            )
            eligible_where = (*due, model.legal_hold.is_(False), model.tombstoned_at.is_(None))
            eligible_count += await self._count(model, *eligible_where)
            await self._record_lifecycle_counts(model, "ELIGIBLE", *eligible_where)
            legal_hold_count += await self._count(
                model,
                *due,
                model.legal_hold.is_(True),
                model.tombstoned_at.is_(None),
            )
            await self._record_lifecycle_counts(
                model,
                "HELD",
                *due,
                model.legal_hold.is_(True),
                model.tombstoned_at.is_(None),
            )
            already_tombstoned_count += await self._count(
                model,
                *due,
                model.tombstoned_at.is_not(None),
            )
            await self._record_lifecycle_counts(
                model,
                "TOMBSTONED",
                *due,
                model.tombstoned_at.is_not(None),
            )
            rows = list(
                (
                    await self.db.execute(
                        select(model)
                        .where(*eligible_where)
                        .order_by(model.retention_expires_at, model.__table__.primary_key.columns)
                        .limit(candidate_limit_per_table)
                    )
                ).scalars()
            )
            primary_key_name = inspect(model).primary_key[0].name
            candidates.extend(
                RetentionCandidate(
                    table_name=model.__tablename__,
                    record_id=str(getattr(row, primary_key_name)),
                    retention_class=str(row.retention_class),
                    retention_expires_at=_as_utc(row.retention_expires_at),
                )
                for row in rows
            )

        return RetentionDryRunReport(
            as_of=cutoff,
            candidates=tuple(candidates),
            eligible_count=eligible_count,
            legal_hold_count=legal_hold_count,
            already_tombstoned_count=already_tombstoned_count,
            candidate_limit_per_table=candidate_limit_per_table,
        )

    async def _count(self, model: type[Any], *where: Any) -> int:
        return int(
            (
                await self.db.execute(select(func.count()).select_from(model).where(*where))
            ).scalar_one()
        )

    async def _record_lifecycle_counts(self, model: type[Any], result: str, *where: Any) -> None:
        rows = (
            await self.db.execute(
                select(model.retention_class, func.count())
                .where(*where)
                .group_by(model.retention_class)
                .order_by(model.retention_class)
            )
        ).all()
        for retention_class, count in rows:
            record_asset_research_lifecycle(
                retention_class=str(retention_class),
                result=result,
                amount=int(count),
            )

    @staticmethod
    def _models_for(table_names: Collection[str] | None) -> tuple[type[Any], ...]:
        if table_names is None:
            return _RETENTION_MODELS
        unknown = sorted(set(table_names) - set(_RETENTION_MODELS_BY_TABLE))
        if unknown:
            raise ValueError("RETENTION_TABLE_UNKNOWN")
        return tuple(
            _RETENTION_MODELS_BY_TABLE[table_name]
            for table_name in _RETENTION_MODELS_BY_TABLE
            if table_name in table_names
        )
