#!/usr/bin/env python3
"""
Drain AKSHARE_TASK_TODO.md by manually running scheduled akshare tasks.

The runner is resumable: successful tasks are checked off in the TODO file,
while failed or timed-out tasks remain unchecked with their latest status and
attempt count.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/backend"))

from app.db.database import async_session_maker  # noqa: E402
from app.models.akshare_mgmt import TriggeredBy  # noqa: E402
from app.services.akshare.script import AkshareScriptService  # noqa: E402

TODO_PATH = ROOT / "docs/operations/akshare/AKSHARE_TASK_TODO.md"
TASK_LINE_RE = re.compile(
    r"^- \[(?P<checked>[ x])\] "
    r"task_id=(?P<task_id>\d+) "
    r"script_id=(?P<script_id>\"(?:\\.|[^\"])*\") "
    r"category=(?P<category>\"(?:\\.|[^\"])*\"|null) "
    r"sub_category=(?P<sub_category>\"(?:\\.|[^\"])*\"|null) "
    r"cron=(?P<cron>\"(?:\\.|[^\"])*\"|null) "
    r"timeout=(?P<timeout>\d+) "
    r"status=(?P<status>[a-z_]+) "
    r"attempts=(?P<attempts>\d+) "
    r"params=(?P<params>.*) "
    r"name=(?P<name>\"(?:\\.|[^\"])*\")"
    r"(?: .*)?$"
)


@dataclass(frozen=True)
class TodoTask:
    line_index: int
    task_id: int
    script_id: str
    category: str | None
    sub_category: str | None
    cron: str | None
    timeout: int
    status: str
    attempts: int
    params: dict[str, Any]
    name: str
    checked: bool


@dataclass(frozen=True)
class TaskResult:
    task: TodoTask
    status: str
    checked: bool
    attempts: int
    execution_id: str | None = None
    duration: float | None = None
    rows_before: int | None = None
    rows_after: int | None = None
    error: str | None = None


def decode_json(value: str) -> Any:
    if value == "null":
        return None
    return json.loads(value)


def encode_json(value: Any) -> str:
    if value is None:
        return "null"
    return json.dumps(value, ensure_ascii=False)


def parse_todo(path: Path) -> tuple[list[str], list[TodoTask]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    tasks: list[TodoTask] = []
    for index, line in enumerate(lines):
        match = TASK_LINE_RE.match(line)
        if not match:
            continue
        params_raw = match.group("params")
        params = {} if params_raw == "null" else json.loads(params_raw)
        if not isinstance(params, dict):
            raise ValueError(f"Task params must be an object on line {index + 1}")
        tasks.append(
            TodoTask(
                line_index=index,
                task_id=int(match.group("task_id")),
                script_id=decode_json(match.group("script_id")),
                category=decode_json(match.group("category")),
                sub_category=decode_json(match.group("sub_category")),
                cron=decode_json(match.group("cron")),
                timeout=int(match.group("timeout")),
                status=match.group("status"),
                attempts=int(match.group("attempts")),
                params=params,
                name=decode_json(match.group("name")),
                checked=match.group("checked") == "x",
            )
        )
    return lines, tasks


def status_counts(tasks: list[TodoTask]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in tasks:
        status = "done" if task.checked else task.status
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def format_line(task: TodoTask, result: TaskResult | None = None) -> str:
    checked = "x" if (result.checked if result else task.checked) else " "
    status = result.status if result else task.status
    attempts = result.attempts if result else task.attempts
    parts = [
        f"- [{checked}]",
        f"task_id={task.task_id}",
        f"script_id={encode_json(task.script_id)}",
        f"category={encode_json(task.category)}",
        f"sub_category={encode_json(task.sub_category)}",
        f"cron={encode_json(task.cron)}",
        f"timeout={task.timeout}",
        f"status={status}",
        f"attempts={attempts}",
        f"params={json.dumps(task.params, ensure_ascii=False, sort_keys=True, separators=(',', ':')) if task.params else 'null'}",
        f"name={encode_json(task.name)}",
    ]
    if result:
        if result.execution_id:
            parts.append(f"execution_id={encode_json(result.execution_id)}")
        if result.duration is not None:
            parts.append(f"duration={result.duration:.2f}s")
        if result.rows_before is not None:
            parts.append(f"rows_before={result.rows_before}")
        if result.rows_after is not None:
            parts.append(f"rows_after={result.rows_after}")
        if result.error:
            parts.append(f"error={encode_json(result.error[:500])}")
        parts.append(
            "updated_at="
            + encode_json(datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S CST"))
        )
    return " ".join(parts)


def write_lines_atomic(path: Path, lines: list[str]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def update_task_line(path: Path, task: TodoTask, result: TaskResult) -> None:
    lines, _ = parse_todo(path)
    lines[task.line_index] = format_line(task, result)
    write_lines_atomic(path, lines)


def selected_tasks(
    tasks: list[TodoTask],
    statuses: set[str],
    limit: int | None,
    task_ids: set[int] | None = None,
    script_ids: set[str] | None = None,
    include_checked: bool = False,
) -> list[TodoTask]:
    selected: list[TodoTask] = []
    for task in tasks:
        if task_ids is not None and task.task_id not in task_ids:
            continue
        if script_ids is not None and task.script_id not in script_ids:
            continue
        if task.checked and not include_checked:
            continue
        if task.status not in statuses and not (include_checked and task.checked):
            continue
        selected.append(task)
        if limit is not None and len(selected) >= limit:
            break
    return selected


def classify_error(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower():
        return "timeout"
    return "failed"


async def run_one(task: TodoTask, timeout_seconds: float) -> TaskResult:
    started = time.monotonic()
    try:
        async with async_session_maker() as session:
            service = AkshareScriptService(session)
            execution = await service.run_script(
                task.script_id,
                parameters=task.params,
                operator_id=None,
                task_id=task.task_id,
                triggered_by=TriggeredBy.MANUAL,
                timeout_seconds=timeout_seconds,
            )
        duration = time.monotonic() - started
        return TaskResult(
            task=task,
            status="done",
            checked=True,
            attempts=task.attempts + 1,
            execution_id=execution.execution_id,
            duration=duration,
            rows_before=getattr(execution, "rows_before", None),
            rows_after=getattr(execution, "rows_after", None),
        )
    except Exception as exc:
        duration = time.monotonic() - started
        error = f"{type(exc).__name__}: {exc}"
        if not error.strip():
            error = traceback.format_exc(limit=3).strip()
        return TaskResult(
            task=task,
            status=classify_error(exc),
            checked=False,
            attempts=task.attempts + 1,
            duration=duration,
            error=error,
        )


async def drain(args: argparse.Namespace) -> int:
    lines, tasks = parse_todo(args.todo)
    if not tasks:
        raise RuntimeError(f"No task lines found in {args.todo}")
    print(json.dumps({"todo": str(args.todo), "total_tasks": len(tasks), "counts": status_counts(tasks)}, ensure_ascii=False))

    statuses = {item.strip() for item in args.statuses.split(",") if item.strip()}
    task_ids = set(args.task_id) if args.task_id else None
    script_ids = set(args.script_id) if args.script_id else None
    pending = selected_tasks(
        tasks,
        statuses=statuses,
        limit=args.limit,
        task_ids=task_ids,
        script_ids=script_ids,
        include_checked=args.include_checked,
    )
    if not pending:
        print(json.dumps({"selected": 0, "message": "No matching unchecked tasks"}, ensure_ascii=False))
        return 0
    if args.dry_run:
        print(
            json.dumps(
                {
                    "selected": len(pending),
                    "tasks": [
                        {
                            "task_id": task.task_id,
                            "script_id": task.script_id,
                            "status": task.status,
                            "attempts": task.attempts,
                        }
                        for task in pending
                    ],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if not args.no_mark_running:
        running_by_line = {
            task.line_index: format_line(
                task,
                TaskResult(
                    task=task,
                    status="running",
                    checked=False,
                    attempts=task.attempts,
                ),
            )
            for task in pending
        }
        for line_index, line in running_by_line.items():
            lines[line_index] = line
        write_lines_atomic(args.todo, lines)

    queue: asyncio.Queue[TodoTask] = asyncio.Queue()
    for task in pending:
        queue.put_nowait(task)

    summary = {"done": 0, "failed": 0, "timeout": 0}
    write_lock = asyncio.Lock()

    async def worker(worker_id: int) -> None:
        while True:
            try:
                task = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            print(
                json.dumps(
                    {
                        "event": "start",
                        "worker": worker_id,
                        "task_id": task.task_id,
                        "script_id": task.script_id,
                        "attempt": task.attempts + 1,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            result = await run_one(task, timeout_seconds=args.timeout)
            async with write_lock:
                update_task_line(args.todo, task, result)
            summary[result.status] = summary.get(result.status, 0) + 1
            print(
                json.dumps(
                    {
                        "event": "finish",
                        "worker": worker_id,
                        "task_id": task.task_id,
                        "script_id": task.script_id,
                        "status": result.status,
                        "duration": round(result.duration or 0, 2),
                        "execution_id": result.execution_id,
                        "error": result.error,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            queue.task_done()

    worker_count = min(max(1, args.concurrency), len(pending))
    await asyncio.gather(*(worker(index + 1) for index in range(worker_count)))

    _, after_tasks = parse_todo(args.todo)
    print(
        json.dumps(
            {
                "selected": len(pending),
                "run_summary": summary,
                "counts_after": status_counts(after_tasks),
            },
            ensure_ascii=False,
        )
    )
    return 0 if summary.get("failed", 0) == 0 and summary.get("timeout", 0) == 0 else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--todo", type=Path, default=TODO_PATH)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--task-id",
        action="append",
        type=int,
        help="Run only the given task id. May be passed multiple times.",
    )
    parser.add_argument(
        "--script-id",
        action="append",
        help="Run only the given script id. May be passed multiple times.",
    )
    parser.add_argument(
        "--include-checked",
        action="store_true",
        help="Allow already checked tasks to be selected by --task-id/--script-id for reruns.",
    )
    parser.add_argument(
        "--statuses",
        default="todo",
        help="Comma-separated unchecked statuses to run, e.g. todo,failed,timeout.",
    )
    parser.add_argument(
        "--no-mark-running",
        action="store_true",
        help="Do not pre-mark selected tasks as running before execution.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print selected tasks and exit.")
    return parser.parse_args()


def main() -> int:
    return asyncio.run(drain(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
