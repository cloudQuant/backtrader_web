#!/usr/bin/env python3
"""
Spread akshare scheduled tasks across week-long time windows.

The script is intentionally conservative: by default it updates cron expressions
and keeps tasks paused. Pass ``--activate`` only after checking the generated
schedule.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/backend"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.db.database import async_session_maker  # noqa: E402
from app.models.akshare_mgmt import (  # noqa: E402
    DataScript,
    ScheduledTask,
    ScheduleType,
    TaskExecution,
    TaskStatus,
)

DOW_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

CATEGORY_WINDOWS = {
    "stocks": ([0, 1, 2, 3, 4], list(range(18, 24))),
    "indexs": ([0, 1, 2, 3, 4], list(range(18, 23))),
    "funds": ([1, 3, 5, 6], [0, 1, 20, 21, 22, 23]),
    "futures": ([0, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4, 5, 21, 22, 23]),
    "bonds": ([0, 1, 2, 3, 4, 5], [6, 7, 8, 9, 19, 20, 21]),
    "common": ([0, 1, 2, 3, 4, 5, 6], list(range(24))),
}

WEEKLY_FALLBACK_DAYS = [5, 6]
MONTHLY_DAYS = tuple(range(1, 29))


@dataclass(frozen=True)
class TaskPlan:
    task_id: int
    script_id: str
    category: str
    sub_category: str
    schedule_expression: str


def stable_offset(value: str, modulo: int) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % modulo


def category_window(category: str) -> tuple[list[int], list[int]]:
    return CATEGORY_WINDOWS.get(category, CATEGORY_WINDOWS["common"])


def rotate(values: Iterable[int], offset: int) -> list[int]:
    items = list(values)
    if not items:
        return []
    offset %= len(items)
    return items[offset:] + items[:offset]


class WeeklySlotAllocator:
    def __init__(self) -> None:
        self.used: set[tuple[int, int, int]] = set()

    def reserve_hourly_occurrences(self, minute: int, phase: int) -> None:
        for day in range(5):
            for hour in ((phase + step) % 24 for step in (0, 6, 12, 18)):
                self.used.add((day, hour, minute))

    def assign(
        self,
        script_id: str,
        category: str,
        preferred_days: list[int] | None = None,
        preferred_hours: list[int] | None = None,
    ) -> tuple[int, int, int]:
        days, hours = category_window(category)
        if preferred_days:
            days = preferred_days
        if preferred_hours:
            hours = preferred_hours

        day_candidates = rotate(days, stable_offset(script_id + ":day", len(days)))
        hour_candidates = rotate(hours, stable_offset(script_id + ":hour", len(hours)))
        minute_candidates = rotate(range(60), stable_offset(script_id + ":minute", 60))

        for day in day_candidates:
            for hour in hour_candidates:
                for minute in minute_candidates:
                    slot = (day, hour, minute)
                    if slot not in self.used:
                        self.used.add(slot)
                        return slot

        for day in range(7):
            for hour in range(24):
                for minute in range(60):
                    slot = (day, hour, minute)
                    if slot not in self.used:
                        self.used.add(slot)
                        return slot

        raise RuntimeError("No weekly cron slot available")


class MonthlySlotAllocator:
    def __init__(self) -> None:
        self.used: set[tuple[int, int, int]] = set()

    def assign(self, script_id: str, category: str) -> tuple[int, int, int]:
        _, hours = category_window(category)
        day_candidates = rotate(MONTHLY_DAYS, stable_offset(script_id + ":monthday", 28))
        hour_candidates = rotate(hours, stable_offset(script_id + ":monthhour", len(hours)))
        minute_candidates = rotate(range(60), stable_offset(script_id + ":monthminute", 60))
        for day in day_candidates:
            for hour in hour_candidates:
                for minute in minute_candidates:
                    slot = (day, hour, minute)
                    if slot not in self.used:
                        self.used.add(slot)
                        return slot
        raise RuntimeError("No monthly cron slot available")


def build_plans(tasks: list[ScheduledTask]) -> list[TaskPlan]:
    hourly_slots: set[tuple[int, int]] = set()
    weekly_allocator = WeeklySlotAllocator()
    monthly_allocator = MonthlySlotAllocator()
    plans: list[TaskPlan] = []

    sorted_tasks = sorted(
        tasks,
        key=lambda task: (
            (task.script.sub_category or ""),
            task.script.category,
            task.script.script_id,
            task.id,
        ),
    )

    for task in sorted_tasks:
        script = task.script
        category = str(script.category or "common")
        sub_category = str(script.sub_category or "weekly").lower()
        script_id = str(script.script_id)

        if sub_category == "hourly":
            start = stable_offset(script_id, 6 * 60)
            for offset in range(6 * 60):
                candidate = (start + offset) % (6 * 60)
                phase = candidate // 60
                minute = candidate % 60
                if (phase, minute) not in hourly_slots:
                    hourly_slots.add((phase, minute))
                    weekly_allocator.reserve_hourly_occurrences(minute, phase)
                    hours = ",".join(str((phase + step) % 24) for step in (0, 6, 12, 18))
                    expression = f"{minute} {hours} * * mon-fri"
                    break
            else:
                raise RuntimeError("No hourly cron slot available")
        elif sub_category == "monthly":
            day, hour, minute = monthly_allocator.assign(script_id, category)
            expression = f"{minute} {hour} {day} * *"
        else:
            preferred_days: list[int] | None = None
            preferred_hours: list[int] | None = None
            if sub_category == "weekly":
                preferred_days = WEEKLY_FALLBACK_DAYS
                preferred_hours = list(range(0, 24))
            day, hour, minute = weekly_allocator.assign(
                script_id,
                category,
                preferred_days=preferred_days,
                preferred_hours=preferred_hours,
            )
            expression = f"{minute} {hour} * * {DOW_NAMES[day]}"

        plans.append(
            TaskPlan(
                task_id=int(task.id),
                script_id=script_id,
                category=category,
                sub_category=sub_category,
                schedule_expression=expression,
            )
        )

    return sorted(plans, key=lambda item: item.task_id)


def summarize(plans: list[TaskPlan], active: bool, cancelled_executions: int) -> dict[str, object]:
    by_sub_category: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for plan in plans:
        by_sub_category[plan.sub_category] = by_sub_category.get(plan.sub_category, 0) + 1
        by_category[plan.category] = by_category.get(plan.category, 0) + 1
    return {
        "tasks_updated": len(plans),
        "tasks_active": active,
        "cancelled_running_executions": cancelled_executions,
        "by_sub_category": dict(sorted(by_sub_category.items())),
        "by_category": dict(sorted(by_category.items())),
        "sample": [
            {
                "task_id": plan.task_id,
                "script_id": plan.script_id,
                "sub_category": plan.sub_category,
                "schedule_expression": plan.schedule_expression,
            }
            for plan in plans[:10]
        ],
    }


async def run(activate: bool, cancel_running: bool) -> dict[str, object]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(ScheduledTask)
            .options(selectinload(ScheduledTask.script))
            .join(DataScript, DataScript.script_id == ScheduledTask.script_id)
            .order_by(ScheduledTask.id)
        )
        tasks = list(result.scalars().all())
        plans = build_plans(tasks)
        plan_by_task_id = {plan.task_id: plan for plan in plans}

        cancelled = 0
        if cancel_running:
            running_result = await session.execute(
                select(TaskExecution).where(TaskExecution.status == TaskStatus.RUNNING)
            )
            for execution in running_result.scalars().all():
                execution.status = TaskStatus.CANCELLED
                execution.end_time = datetime.now(timezone.utc)
                execution.error_message = (
                    "Cancelled during akshare schedule redistribution after scheduler overload."
                )
                cancelled += 1

        for task in tasks:
            plan = plan_by_task_id[int(task.id)]
            task.schedule_type = ScheduleType.CRON
            task.schedule_expression = plan.schedule_expression
            task.is_active = activate
            task.next_execution_at = None

        await session.commit()
        return summarize(plans, active=activate, cancelled_executions=cancelled)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Enable tasks after rewriting schedules. Default keeps all tasks paused.",
    )
    parser.add_argument(
        "--keep-running-executions",
        action="store_true",
        help="Do not mark currently RUNNING execution rows as cancelled.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = asyncio.run(
        run(
            activate=args.activate,
            cancel_running=not args.keep_running_executions,
        )
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
