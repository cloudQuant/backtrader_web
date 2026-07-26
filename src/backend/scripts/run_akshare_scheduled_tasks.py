"""Run configured AkShare scheduled tasks sequentially.

This is an operations helper for backfilling the ``akshare_data`` warehouse from
the same task registry used by ``/config/data/tasks``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from app.db.database import async_session_maker
from app.models.akshare_mgmt import TriggeredBy
from app.services.akshare.script import AkshareScriptService

LOGGER = logging.getLogger("run_akshare_scheduled_tasks")


@dataclass(frozen=True)
class TaskCandidate:
    id: int
    script_id: str
    name: str
    category: str | None
    target_table: str | None
    parameters: Any
    timeout: int | None
    last_status: str | None
    last_end_time: datetime | None


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


async def _fetch_candidates(args: argparse.Namespace) -> list[TaskCandidate]:
    filters = ["s.is_active = 1"]
    params: dict[str, Any] = {}

    if args.start_id is not None:
        filters.append("t.id >= :start_id")
        params["start_id"] = args.start_id
    if args.end_id is not None:
        filters.append("t.id <= :end_id")
        params["end_id"] = args.end_id
    if args.category:
        filters.append("s.category = :category")
        params["category"] = args.category
    if args.script_id:
        filters.append("t.script_id = :script_id")
        params["script_id"] = args.script_id

    rerun_cutoff = None
    if args.skip_completed_within_hours > 0:
        rerun_cutoff = _utcnow_naive() - timedelta(hours=args.skip_completed_within_hours)
        filters.append(
            """
            NOT EXISTS (
                SELECT 1
                FROM ak_task_executions e
                WHERE e.task_id = t.id
                  AND e.status = 'COMPLETED'
                  AND e.end_time >= :rerun_cutoff
            )
            """
        )
        params["rerun_cutoff"] = rerun_cutoff

    where_sql = " AND ".join(filters)
    limit_sql = "LIMIT :limit" if args.limit is not None else ""
    if args.limit is not None:
        params["limit"] = args.limit

    async with async_session_maker() as session:
        rows = (
            (
                await session.execute(
                    text(
                        f"""
                    SELECT
                        t.id,
                        t.script_id,
                        t.name,
                        t.parameters,
                        t.timeout,
                        s.category,
                        s.target_table,
                        le.status AS last_status,
                        le.end_time AS last_end_time
                    FROM ak_scheduled_tasks t
                    JOIN ak_data_scripts s ON s.script_id = t.script_id
                    LEFT JOIN (
                        SELECT e1.task_id, e1.status, e1.end_time
                        FROM ak_task_executions e1
                        JOIN (
                            SELECT task_id, MAX(id) AS max_id
                            FROM ak_task_executions
                            GROUP BY task_id
                        ) latest ON latest.max_id = e1.id
                    ) le ON le.task_id = t.id
                    WHERE {where_sql}
                    ORDER BY t.id ASC
                    {limit_sql}
                    """
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )

    return [
        TaskCandidate(
            id=int(row["id"]),
            script_id=str(row["script_id"]),
            name=str(row["name"]),
            category=row.get("category"),
            target_table=row.get("target_table"),
            parameters=row.get("parameters"),
            timeout=int(row["timeout"] or 0),
            last_status=row.get("last_status"),
            last_end_time=row.get("last_end_time"),
        )
        for row in rows
    ]


async def _run_one(candidate: TaskCandidate, args: argparse.Namespace) -> str:
    LOGGER.info(
        "running task id=%s script=%s category=%s table=%s",
        candidate.id,
        candidate.script_id,
        candidate.category,
        candidate.target_table,
    )
    async with async_session_maker() as session:
        service = AkshareScriptService(session)
        execution = await service.run_script(
            candidate.script_id,
            parameters=candidate.parameters,
            operator_id=args.operator_id,
            task_id=candidate.id,
            triggered_by=TriggeredBy.MANUAL,
            timeout_seconds=args.timeout or candidate.timeout or None,
        )
        LOGGER.info(
            "finished task id=%s execution=%s status=%s rows=%s->%s result=%s",
            candidate.id,
            execution.execution_id,
            execution.status.value,
            execution.rows_before,
            execution.rows_after,
            execution.result,
        )
        return execution.status.value


async def _mark_stale_running_as_failed() -> None:
    async with async_session_maker() as session:
        await session.execute(
            text(
                """
                UPDATE ak_task_executions
                SET status = 'FAILED',
                    end_time = COALESCE(end_time, :now),
                    error_message = COALESCE(
                        error_message,
                        'Marked failed before manual batch run because execution was left RUNNING'
                    )
                WHERE status = 'RUNNING'
                """
            ),
            {"now": _utcnow_naive()},
        )
        await session.commit()


async def main_async(args: argparse.Namespace) -> int:
    if args.fail_stale_running:
        await _mark_stale_running_as_failed()

    candidates = await _fetch_candidates(args)
    LOGGER.info("selected %s task candidates", len(candidates))
    if args.dry_run:
        for candidate in candidates:
            LOGGER.info(
                "dry-run task id=%s script=%s category=%s table=%s last=%s at=%s",
                candidate.id,
                candidate.script_id,
                candidate.category,
                candidate.target_table,
                candidate.last_status,
                candidate.last_end_time,
            )
        return 0

    completed = 0
    failed = 0
    for index, candidate in enumerate(candidates, start=1):
        LOGGER.info("[%s/%s] task id=%s", index, len(candidates), candidate.id)
        try:
            status = await _run_one(candidate, args)
            if status.lower() == "completed":
                completed += 1
            else:
                failed += 1
        except Exception:
            failed += 1
            LOGGER.exception("task id=%s script=%s failed", candidate.id, candidate.script_id)
            if args.stop_on_failure:
                break
        if args.sleep > 0:
            await asyncio.sleep(args.sleep)

    LOGGER.info(
        "batch finished: selected=%s completed=%s failed=%s",
        len(candidates),
        completed,
        failed,
    )
    return 1 if failed and args.fail_on_any_error else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--start-id", type=int)
    parser.add_argument("--end-id", type=int)
    parser.add_argument("--category")
    parser.add_argument("--script-id")
    parser.add_argument("--timeout", type=float, default=0)
    parser.add_argument("--operator-id")
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--skip-completed-within-hours", type=float, default=24)
    parser.add_argument("--fail-stale-running", action="store_true")
    parser.add_argument("--stop-on-failure", action="store_true")
    parser.add_argument("--fail-on-any-error", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    raise SystemExit(asyncio.run(main_async(parse_args())))


if __name__ == "__main__":
    main()
