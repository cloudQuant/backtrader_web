from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scanner_plan import ScannerPlanModel, ScannerPlanRunModel
from app.services.scanner_service import ScannerService


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_run_date() -> str:
    return _utc_now().date().isoformat()


_SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,119}$")


class ScannerPlanService:
    def __init__(self, db: AsyncSession, scanner_service: ScannerService) -> None:
        self.db = db
        self.scanner_service = scanner_service

    async def save_plan(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("scanner_plan_name_required")
        universe_pool_id = str(
            payload.get("universe_pool_id") or payload.get("pool_id") or ""
        ).strip()
        if not universe_pool_id:
            raise ValueError("scanner_plan_universe_pool_required")
        condition = str(payload.get("condition") or "").strip()
        if not condition:
            raise ValueError("scanner_plan_condition_required")

        existing_result = await self.db.execute(
            select(ScannerPlanModel).where(
                ScannerPlanModel.owner_id == user_id,
                ScannerPlanModel.name == name,
            )
        )
        plan = existing_result.scalar_one_or_none()
        if plan is None:
            plan = ScannerPlanModel(owner_id=user_id, name=name)
            self.db.add(plan)
        plan.universe_pool_id = universe_pool_id
        plan.indicator_rules = list(payload.get("indicator_rules") or [])
        plan.condition = condition
        plan.lookback_days = int(payload.get("lookback_days") or 20)
        plan.timeframe = str(payload.get("timeframe") or "1d")
        plan.schedule_enabled = bool(payload.get("schedule_enabled", True))
        plan.schedule_frequency = str(payload.get("schedule_frequency") or "daily")
        plan.status = str(payload.get("status") or "active")
        plan.updated_at = _utc_now()

        await self.db.commit()
        await self.db.refresh(plan)
        return self._serialize_plan(plan)

    async def update_plan(
        self,
        user_id: str,
        plan_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        plan = await self._get_plan(user_id, plan_id)
        if plan is None:
            return None
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("scanner_plan_name_required")
        universe_pool_id = str(
            payload.get("universe_pool_id") or payload.get("pool_id") or ""
        ).strip()
        if not universe_pool_id:
            raise ValueError("scanner_plan_universe_pool_required")
        condition = str(payload.get("condition") or "").strip()
        if not condition:
            raise ValueError("scanner_plan_condition_required")

        plan.name = name
        plan.universe_pool_id = universe_pool_id
        plan.indicator_rules = list(payload.get("indicator_rules") or [])
        plan.condition = condition
        plan.lookback_days = int(payload.get("lookback_days") or 20)
        plan.timeframe = str(payload.get("timeframe") or "1d")
        plan.schedule_enabled = bool(payload.get("schedule_enabled", True))
        plan.schedule_frequency = str(payload.get("schedule_frequency") or "daily")
        plan.status = str(payload.get("status") or "active")
        plan.updated_at = _utc_now()

        await self.db.commit()
        await self.db.refresh(plan)
        return self._serialize_plan(plan)

    async def delete_plan(self, user_id: str, plan_id: str) -> bool | None:
        plan = await self._get_plan(user_id, plan_id)
        if plan is None:
            return None
        if plan.result_table_name:
            await self._drop_table_if_exists(str(plan.result_table_name))
        await self.db.delete(plan)
        await self.db.commit()
        return True

    async def list_plans(self, user_id: str) -> dict[str, Any]:
        result = await self.db.execute(
            select(ScannerPlanModel)
            .where(ScannerPlanModel.owner_id == user_id)
            .order_by(ScannerPlanModel.updated_at.desc())
        )
        items = [self._serialize_plan(plan) for plan in result.scalars().all()]
        return {"items": items, "total": len(items)}

    async def run_plan(
        self,
        user_id: str,
        plan_id: str,
        *,
        run_date: str | None = None,
        force: bool = False,
    ) -> dict[str, Any] | None:
        plan = await self._get_plan(user_id, plan_id)
        if plan is None:
            return None
        return await self._run_plan_model(user_id, plan, run_date=run_date, force=force)

    async def run_daily_plans(self, user_id: str, *, run_date: str | None = None) -> dict[str, Any]:
        resolved_run_date = run_date or _default_run_date()
        result = await self.db.execute(
            select(ScannerPlanModel)
            .where(
                ScannerPlanModel.owner_id == user_id,
                ScannerPlanModel.status == "active",
                ScannerPlanModel.schedule_enabled.is_(True),
                ScannerPlanModel.schedule_frequency == "daily",
            )
            .order_by(ScannerPlanModel.updated_at.desc())
        )
        plans = list(result.scalars().all())
        runs = [
            await self._run_plan_model(
                user_id,
                plan,
                run_date=resolved_run_date,
                force=False,
            )
            for plan in plans
        ]
        return {"run_date": resolved_run_date, "items": runs, "total": len(runs)}

    async def list_runs(self, user_id: str, plan_id: str) -> dict[str, Any] | None:
        plan = await self._get_plan(user_id, plan_id)
        if plan is None:
            return None
        result = await self.db.execute(
            select(ScannerPlanRunModel)
            .where(
                ScannerPlanRunModel.owner_id == user_id,
                ScannerPlanRunModel.plan_id == plan_id,
            )
            .order_by(ScannerPlanRunModel.started_at.desc())
        )
        items = [self._serialize_run(row) for row in result.scalars().all()]
        return {"items": items, "total": len(items)}

    async def create_result_table(self, user_id: str, plan_id: str) -> dict[str, Any] | None:
        plan = await self._get_plan(user_id, plan_id)
        if plan is None:
            return None
        table_name = str(plan.result_table_name or self._result_table_name(plan.id))
        await self._create_result_table_if_missing(table_name)
        plan.result_table_name = table_name
        plan.result_table_status = "ready"
        plan.updated_at = _utc_now()
        await self.db.commit()
        await self.db.refresh(plan)
        return self._serialize_plan(plan)

    async def delete_result_table(self, user_id: str, plan_id: str) -> dict[str, Any] | None:
        plan = await self._get_plan(user_id, plan_id)
        if plan is None:
            return None
        if plan.result_table_name:
            await self._drop_table_if_exists(str(plan.result_table_name))
        plan.result_table_status = "dropped"
        plan.updated_at = _utc_now()
        await self.db.commit()
        await self.db.refresh(plan)
        return self._serialize_plan(plan)

    async def _run_plan_model(
        self,
        user_id: str,
        plan: ScannerPlanModel,
        *,
        run_date: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        resolved_run_date = run_date or _default_run_date()
        existing_result = await self.db.execute(
            select(ScannerPlanRunModel).where(
                ScannerPlanRunModel.owner_id == user_id,
                ScannerPlanRunModel.plan_id == plan.id,
                ScannerPlanRunModel.run_date == resolved_run_date,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None and not force:
            return {**self._serialize_run(existing), "cache_status": "existing"}
        if existing is not None:
            await self.db.delete(existing)
            await self.db.flush()

        started_at = _utc_now()
        result = self.scanner_service.run(
            [],
            str(plan.condition),
            lookback_days=int(plan.lookback_days),
            timeframe=str(plan.timeframe),
            universe_pool_id=str(plan.universe_pool_id),
            user_id=user_id,
        )
        matches = list(result.get("matches") or [])
        row = ScannerPlanRunModel(
            owner_id=user_id,
            plan_id=plan.id,
            run_date=resolved_run_date,
            status=str(result.get("status") or "completed"),
            universe_pool_id=str(plan.universe_pool_id),
            condition=str(plan.condition),
            lookback_days=int(plan.lookback_days),
            timeframe=str(plan.timeframe),
            universe_count=int(result.get("universe_count") or 0),
            match_count=len(matches),
            matches=matches,
            metrics={
                "factor_cache_status": result.get("factor_cache_status"),
                "source_task_id": result.get("task_id"),
            },
            source_task_id=str(result.get("task_id") or ""),
            started_at=started_at,
            completed_at=_utc_now(),
        )
        self.db.add(row)
        await self.db.flush()
        if plan.result_table_status == "ready" and plan.result_table_name:
            await self._replace_result_table_rows(plan, row, matches)
        await self.db.commit()
        await self.db.refresh(row)
        return {**self._serialize_run(row), "cache_status": "created"}

    async def _get_plan(self, user_id: str, plan_id: str) -> ScannerPlanModel | None:
        result = await self.db.execute(
            select(ScannerPlanModel).where(
                ScannerPlanModel.owner_id == user_id,
                ScannerPlanModel.id == plan_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _serialize_plan(plan: ScannerPlanModel) -> dict[str, Any]:
        return {
            "id": plan.id,
            "name": plan.name,
            "universe_pool_id": plan.universe_pool_id,
            "indicator_rules": list(plan.indicator_rules or []),
            "condition": plan.condition,
            "lookback_days": plan.lookback_days,
            "timeframe": plan.timeframe,
            "schedule_enabled": bool(plan.schedule_enabled),
            "schedule_frequency": plan.schedule_frequency,
            "status": plan.status,
            "result_table_name": plan.result_table_name,
            "result_table_status": plan.result_table_status,
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
            "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
        }

    @staticmethod
    def _serialize_run(row: ScannerPlanRunModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "plan_id": row.plan_id,
            "run_date": row.run_date,
            "status": row.status,
            "universe_pool_id": row.universe_pool_id,
            "condition": row.condition,
            "lookback_days": row.lookback_days,
            "timeframe": row.timeframe,
            "universe_count": row.universe_count,
            "match_count": row.match_count,
            "matches": list(row.matches or []),
            "metrics": dict(row.metrics or {}),
            "source_task_id": row.source_task_id,
            "error": row.error,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }

    @staticmethod
    def _result_table_name(plan_id: str) -> str:
        suffix = re.sub(r"[^A-Za-z0-9_]", "_", plan_id).strip("_") or "plan"
        return f"scanner_plan_result_{suffix}"[:120]

    def _quote_identifier(self, identifier: str) -> str:
        if not _SAFE_IDENTIFIER_PATTERN.fullmatch(identifier):
            raise ValueError("scanner_plan_result_table_name_invalid")
        bind = self.db.get_bind()
        return bind.dialect.identifier_preparer.quote(identifier)

    async def _create_result_table_if_missing(self, table_name: str) -> None:
        quoted = self._quote_identifier(table_name)
        await self.db.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {quoted} (
                    id VARCHAR(36) PRIMARY KEY,
                    plan_id VARCHAR(36) NOT NULL,
                    run_id VARCHAR(36) NOT NULL,
                    run_date VARCHAR(20) NOT NULL,
                    symbol VARCHAR(64) NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )

    async def _drop_table_if_exists(self, table_name: str) -> None:
        quoted = self._quote_identifier(table_name)
        await self.db.execute(text(f"DROP TABLE IF EXISTS {quoted}"))

    async def _replace_result_table_rows(
        self,
        plan: ScannerPlanModel,
        row: ScannerPlanRunModel,
        matches: list[dict[str, Any]],
    ) -> None:
        table_name = str(plan.result_table_name or "")
        if not table_name:
            return
        await self._create_result_table_if_missing(table_name)
        quoted = self._quote_identifier(table_name)
        await self.db.execute(
            text(f"DELETE FROM {quoted} WHERE plan_id = :plan_id AND run_date = :run_date"),
            {"plan_id": plan.id, "run_date": row.run_date},
        )
        created_at = _utc_now()
        for match in matches:
            await self.db.execute(
                text(
                    f"""
                    INSERT INTO {quoted}
                    (id, plan_id, run_id, run_date, symbol, payload_json, created_at)
                    VALUES (:id, :plan_id, :run_id, :run_date, :symbol, :payload_json, :created_at)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "plan_id": plan.id,
                    "run_id": row.id,
                    "run_date": row.run_date,
                    "symbol": str(match.get("symbol") or ""),
                    "payload_json": json.dumps(match, ensure_ascii=False),
                    "created_at": created_at,
                },
            )
