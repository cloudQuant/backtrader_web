#!/usr/bin/env python3
"""
Audit whether AKSHARE_TASK_TODO.md tasks produced physical akshare_data rows.

The manual runner marks a task done when the callable returns successfully, but
some AkShare endpoints legitimately return empty frames and some legacy scripts
write to case-sensitive uppercase tables while the generic service records
lowercase row counts. This audit checks the warehouse tables directly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import mysql.connector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ops"))

from run_akshare_todo import TODO_PATH, TodoTask, parse_todo, status_counts  # noqa: E402

META_DB_DEFAULT = "backtrader_web"
DATA_DB_DEFAULT = "akshare_data"
DATE_COLUMN_PRIORITY = (
    "trade_date",
    "date",
    "datetime",
    "timestamp",
    "data_date",
    "base_date",
    "basedate",
    "report_date",
    "update_date",
    "created_at",
    "updated_at",
    "createdate",
    "updatedate",
    "time",
    "日期",
    "交易日期",
    "时间",
)


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def db_config_from_url(env_name: str, default_database: str) -> DbConfig:
    value = os.environ.get(env_name, "")
    if value:
        parsed = urlparse(value)
        return DbConfig(
            host=parsed.hostname or "127.0.0.1",
            port=parsed.port or 3306,
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            database=(parsed.path or f"/{default_database}").lstrip("/")
            or default_database,
        )
    return DbConfig(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "backtrader_web"),
        password=os.environ.get("DB_PASSWORD", "BacktraderWeb_2026"),
        database=default_database,
    )


def connect(config: DbConfig) -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        autocommit=True,
    )


def normalize_identifier(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_").lower()
    if not normalized:
        normalized = "data"
    if normalized[0].isdigit():
        normalized = f"t_{normalized}"
    return normalized


def quote_identifier(identifier: str) -> str:
    return f"`{identifier.replace('`', '``')}`"


def parse_json(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str) and value:
        return json.loads(value)
    return value


def fetch_dicts(
    conn: mysql.connector.MySQLConnection, sql: str, params: tuple[Any, ...] = ()
) -> list[dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        cursor.close()


def read_scripts(conn: mysql.connector.MySQLConnection) -> dict[str, dict[str, Any]]:
    rows = fetch_dicts(
        conn,
        """
        SELECT script_id, script_name, category, sub_category, target_table,
               module_path, function_name, is_active
        FROM ak_data_scripts
        """,
    )
    return {str(row["script_id"]): row for row in rows}


def read_latest_executions(
    conn: mysql.connector.MySQLConnection,
) -> dict[int, dict[str, Any]]:
    rows = fetch_dicts(
        conn,
        """
        SELECT e.*
        FROM ak_task_executions e
        JOIN (
            SELECT task_id, MAX(id) AS id
            FROM ak_task_executions
            WHERE task_id IS NOT NULL
            GROUP BY task_id
        ) latest ON latest.id = e.id
        """,
    )
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        row["params"] = parse_json(row.get("params"))
        row["result"] = parse_json(row.get("result"))
        result[int(row["task_id"])] = row
    return result


def read_all_executions_summary(
    conn: mysql.connector.MySQLConnection,
) -> dict[str, Any]:
    by_status = fetch_dicts(
        conn,
        "SELECT status, COUNT(*) AS count FROM ak_task_executions GROUP BY status",
    )
    manual = fetch_dicts(
        conn,
        """
        SELECT COUNT(*) AS count,
               SUM(rows_after = 0) AS rows_after_zero,
               SUM(rows_after IS NULL) AS rows_after_null,
               MIN(start_time) AS first_start,
               MAX(end_time) AS last_end
        FROM ak_task_executions
        WHERE triggered_by = 'MANUAL'
        """,
    )[0]
    return {
        "by_status": {str(row["status"]): int(row["count"]) for row in by_status},
        "manual": json_safe(manual),
    }


def read_physical_tables(
    conn: mysql.connector.MySQLConnection, data_db: str
) -> dict[str, dict[str, Any]]:
    rows = fetch_dicts(
        conn,
        """
        SELECT TABLE_NAME AS table_name, CREATE_TIME AS create_time, UPDATE_TIME AS update_time
        FROM information_schema.tables
        WHERE table_schema = %s
        """,
        (data_db,),
    )
    tables: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row["table_name"])
        tables[name] = {
            "table_name": name,
            "create_time": row.get("create_time"),
            "update_time": row.get("update_time"),
            "row_count": None,
            "columns": [],
            "date_column": None,
            "min_date": None,
            "max_date": None,
        }
    return tables


def read_columns(
    conn: mysql.connector.MySQLConnection, data_db: str
) -> dict[str, list[dict[str, str]]]:
    rows = fetch_dicts(
        conn,
        """
        SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name, DATA_TYPE AS data_type
        FROM information_schema.columns
        WHERE table_schema = %s
        ORDER BY table_name, ordinal_position
        """,
        (data_db,),
    )
    columns: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        columns[str(row["table_name"])].append(
            {
                "name": str(row["column_name"]),
                "type": str(row["data_type"]),
            }
        )
    return dict(columns)


def choose_date_column(columns: list[dict[str, str]]) -> str | None:
    by_lower = {column["name"].lower(): column["name"] for column in columns}
    by_exact = {column["name"]: column["name"] for column in columns}
    for name in DATE_COLUMN_PRIORITY:
        if name in by_exact:
            return by_exact[name]
        if name.lower() in by_lower:
            return by_lower[name.lower()]
    for column in columns:
        lowered = column["name"].lower()
        if (
            "date" in lowered
            or "time" in lowered
            or "日期" in column["name"]
            or "时间" in column["name"]
        ):
            return column["name"]
    return None


def enrich_table_stats(
    conn: mysql.connector.MySQLConnection,
    tables: dict[str, dict[str, Any]],
    columns_by_table: dict[str, list[dict[str, str]]],
) -> None:
    cursor = conn.cursor()
    try:
        for table_name, table in sorted(tables.items()):
            quoted = quote_identifier(table_name)
            cursor.execute(f"SELECT COUNT(*) FROM {quoted}")
            table["row_count"] = int(cursor.fetchone()[0] or 0)
            columns = columns_by_table.get(table_name, [])
            table["columns"] = columns
            date_column = choose_date_column(columns)
            table["date_column"] = date_column
            if date_column and table["row_count"] > 0:
                quoted_column = quote_identifier(date_column)
                try:
                    cursor.execute(
                        f"SELECT MIN({quoted_column}), MAX({quoted_column}) FROM {quoted}"
                    )
                    min_value, max_value = cursor.fetchone()
                    table["min_date"] = min_value
                    table["max_date"] = max_value
                except Exception as exc:
                    table["date_range_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        cursor.close()


def todo_extras(lines: list[str], task: TodoTask) -> dict[str, Any]:
    line = lines[task.line_index]
    extras: dict[str, Any] = {}
    for key in ("rows_before", "rows_after", "duration"):
        match = re.search(rf"\b{key}=([0-9]+(?:\.[0-9]+)?)", line)
        if not match:
            continue
        raw = match.group(1)
        extras[key] = float(raw) if "." in raw else int(raw)
    match = re.search(r'\bexecution_id="([^"]+)"', line)
    if match:
        extras["execution_id"] = match.group(1)
    match = re.search(r'\bupdated_at="([^"]+)"', line)
    if match:
        extras["updated_at"] = match.group(1)
    return extras


def add_candidate(candidates: list[str], value: Any) -> None:
    if value is None:
        return
    candidate = str(value).strip()
    if not candidate:
        return
    for item in (
        candidate,
        normalize_identifier(candidate),
        candidate.upper(),
        candidate.lower(),
    ):
        if item and item not in candidates:
            candidates.append(item)


def candidate_tables(
    task: TodoTask, script: dict[str, Any] | None, execution: dict[str, Any] | None
) -> list[str]:
    candidates: list[str] = []
    target = (script or {}).get("target_table")
    add_candidate(candidates, target)
    add_candidate(candidates, task.script_id)
    params = dict(task.params or {})
    if execution and execution.get("params"):
        params.update(execution["params"])
    result = execution.get("result") if execution else None
    if isinstance(result, dict):
        add_candidate(candidates, result.get("table_name"))

    base_values = [value for value in (target, task.script_id) if value]
    symbol = params.get("symbol") or params.get("code") or params.get("ticker")
    if symbol:
        for base in base_values:
            generated = (
                f"{normalize_identifier(str(base))}_{normalize_identifier(str(symbol))}"
            )
            add_candidate(candidates, generated)
    return candidates


def match_table(
    candidates: list[str], physical_tables: dict[str, dict[str, Any]]
) -> tuple[str | None, str | None, list[str]]:
    lower_map: dict[str, list[str]] = defaultdict(list)
    for table_name in physical_tables:
        lower_map[table_name.lower()].append(table_name)

    for candidate in candidates:
        if candidate in physical_tables:
            return candidate, "exact", [candidate]

    folded_matches: list[str] = []
    for candidate in candidates:
        folded_matches.extend(lower_map.get(candidate.lower(), []))
    folded_matches = sorted(set(folded_matches))
    if folded_matches:
        best = max(
            folded_matches, key=lambda name: physical_tables[name].get("row_count") or 0
        )
        return best, "case_insensitive", folded_matches
    return None, None, []


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def build_audit(
    lines: list[str],
    tasks: list[TodoTask],
    scripts: dict[str, dict[str, Any]],
    executions: dict[int, dict[str, Any]],
    physical_tables: dict[str, dict[str, Any]],
    execution_summary: dict[str, Any],
) -> dict[str, Any]:
    task_records: list[dict[str, Any]] = []
    table_to_tasks: dict[str, list[int]] = defaultdict(list)
    counters: Counter[str] = Counter()
    by_category: dict[str, Counter[str]] = defaultdict(Counter)

    for task in tasks:
        script = scripts.get(task.script_id)
        execution = executions.get(task.task_id)
        extras = todo_extras(lines, task)
        candidates = candidate_tables(task, script, execution)
        matched_table, match_type, matched_candidates = match_table(
            candidates, physical_tables
        )
        table = physical_tables.get(matched_table) if matched_table else None
        row_count = int(table.get("row_count") or 0) if table else None

        if matched_table and row_count and row_count > 0:
            status = "has_data"
        elif matched_table:
            status = "empty_table"
        else:
            status = "missing_table"

        category = task.category or (script or {}).get("category") or "unknown"
        counters[status] += 1
        by_category[category][status] += 1
        if matched_table:
            table_to_tasks[matched_table].append(task.task_id)

        execution_rows_after = execution.get("rows_after") if execution else None
        todo_rows_after = extras.get("rows_after")
        rows_after_zero_but_physical_data = bool(row_count and row_count > 0) and (
            execution_rows_after == 0 or todo_rows_after == 0
        )
        if rows_after_zero_but_physical_data:
            counters["rows_after_zero_but_physical_data"] += 1
            by_category[category]["rows_after_zero_but_physical_data"] += 1
        if task.checked and status != "has_data":
            counters["checked_without_data"] += 1
            by_category[category]["checked_without_data"] += 1

        task_records.append(
            {
                "task_id": task.task_id,
                "script_id": task.script_id,
                "name": task.name,
                "category": category,
                "sub_category": task.sub_category or (script or {}).get("sub_category"),
                "todo_checked": task.checked,
                "todo_status": "done" if task.checked else task.status,
                "todo_attempts": task.attempts,
                "todo_rows_before": extras.get("rows_before"),
                "todo_rows_after": todo_rows_after,
                "target_table": (script or {}).get("target_table"),
                "candidate_tables": candidates,
                "matched_table": matched_table,
                "match_type": match_type,
                "matched_candidates": matched_candidates,
                "data_status": status,
                "physical_row_count": row_count,
                "date_column": table.get("date_column") if table else None,
                "min_date": table.get("min_date") if table else None,
                "max_date": table.get("max_date") if table else None,
                "latest_execution": json_safe(
                    {
                        "id": execution.get("id") if execution else None,
                        "execution_id": execution.get("execution_id")
                        if execution
                        else None,
                        "status": execution.get("status") if execution else None,
                        "start_time": execution.get("start_time")
                        if execution
                        else None,
                        "end_time": execution.get("end_time") if execution else None,
                        "duration": execution.get("duration") if execution else None,
                        "rows_before": execution.get("rows_before")
                        if execution
                        else None,
                        "rows_after": execution_rows_after,
                        "error_message": execution.get("error_message")
                        if execution
                        else None,
                        "result": execution.get("result") if execution else None,
                    }
                ),
                "rows_after_zero_but_physical_data": rows_after_zero_but_physical_data,
            }
        )

    mapped_tables = set(table_to_tasks)
    orphan_tables = [
        table
        for table in physical_tables.values()
        if table["table_name"] not in mapped_tables
        and int(table.get("row_count") or 0) > 0
    ]
    orphan_tables.sort(key=lambda item: int(item.get("row_count") or 0), reverse=True)

    physical_counts = Counter()
    for table in physical_tables.values():
        if int(table.get("row_count") or 0) > 0:
            physical_counts["non_empty"] += 1
        else:
            physical_counts["empty"] += 1

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "todo": {
            "total_tasks": len(tasks),
            "status_counts": status_counts(tasks),
        },
        "metadata_scripts": len(scripts),
        "execution_summary": execution_summary,
        "physical_tables": {
            "total": len(physical_tables),
            "non_empty": physical_counts["non_empty"],
            "empty": physical_counts["empty"],
            "mapped_non_empty": len(
                {
                    record["matched_table"]
                    for record in task_records
                    if record["data_status"] == "has_data"
                }
            ),
            "orphan_non_empty": len(orphan_tables),
        },
        "task_data_status": dict(counters),
        "category_breakdown": {
            category: dict(counter) for category, counter in sorted(by_category.items())
        },
    }

    return {
        "summary": json_safe(summary),
        "tasks": json_safe(task_records),
        "orphan_non_empty_tables": json_safe(orphan_tables[:100]),
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    summary = report["summary"]
    tasks = report["tasks"]
    missing_or_empty = [
        task
        for task in tasks
        if task["data_status"] in {"missing_table", "empty_table"}
    ]
    rows_after_zero_recovered = [
        task for task in tasks if task["rows_after_zero_but_physical_data"]
    ]
    top_missing = missing_or_empty[:80]
    lines = [
        "# AkShare Data Completeness Audit",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- TODO tasks: {summary['todo']['total_tasks']} ({summary['todo']['status_counts']})",
        f"- Physical tables: {summary['physical_tables']['total']} total, "
        f"{summary['physical_tables']['non_empty']} non-empty, "
        f"{summary['physical_tables']['empty']} empty",
        f"- Task data status: {summary['task_data_status']}",
        f"- Rows-after-zero but physical data exists: {len(rows_after_zero_recovered)}",
        f"- Checked tasks without physical data: {summary['task_data_status'].get('checked_without_data', 0)}",
        "",
        "## Category Breakdown",
        "",
        "| Category | Has Data | Empty Table | Missing Table | Checked Without Data | Rows After Zero But Data |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category, counts in summary["category_breakdown"].items():
        lines.append(
            "| {category} | {has_data} | {empty_table} | {missing_table} | {checked_without_data} | {recovered} |".format(
                category=category,
                has_data=counts.get("has_data", 0),
                empty_table=counts.get("empty_table", 0),
                missing_table=counts.get("missing_table", 0),
                checked_without_data=counts.get("checked_without_data", 0),
                recovered=counts.get("rows_after_zero_but_physical_data", 0),
            )
        )
    lines.extend(
        [
            "",
            "## First Missing Or Empty Tasks",
            "",
            "| Task | Script | Category | Status | Target | Matched Table | Rows | Latest Execution |",
            "| ---: | --- | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for task in top_missing:
        latest = task["latest_execution"]
        lines.append(
            "| {task_id} | `{script_id}` | {category}/{sub_category} | {data_status} | `{target}` | `{matched}` | {rows} | {exec_status} rows_after={exec_rows} |".format(
                task_id=task["task_id"],
                script_id=task["script_id"],
                category=task["category"],
                sub_category=task.get("sub_category") or "",
                data_status=task["data_status"],
                target=task.get("target_table") or "",
                matched=task.get("matched_table") or "",
                rows=task.get("physical_row_count")
                if task.get("physical_row_count") is not None
                else "",
                exec_status=latest.get("status"),
                exec_rows=latest.get("rows_after"),
            )
        )
    lines.extend(
        [
            "",
            "## Top Orphan Non-Empty Tables",
            "",
            "| Table | Rows | Date Column | Min | Max |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )
    for table in report["orphan_non_empty_tables"][:40]:
        lines.append(
            f"| `{table['table_name']}` | {table.get('row_count') or 0} | "
            f"{table.get('date_column') or ''} | {table.get('min_date') or ''} | {table.get('max_date') or ''} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--todo", type=Path, default=TODO_PATH)
    report_dir = ROOT / "var/reports"
    parser.add_argument(
        "--json-output",
        type=Path,
        default=report_dir / "akshare_data_completeness_audit.json",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=report_dir / "akshare_data_completeness_audit.md",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    meta_config = db_config_from_url("DATABASE_URL", META_DB_DEFAULT)
    data_config = db_config_from_url("AKSHARE_DATA_DATABASE_URL", DATA_DB_DEFAULT)

    lines, tasks = parse_todo(args.todo)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)

    with connect(meta_config) as meta_conn, connect(data_config) as data_conn:
        scripts = read_scripts(meta_conn)
        executions = read_latest_executions(meta_conn)
        execution_summary = read_all_executions_summary(meta_conn)
        physical_tables = read_physical_tables(data_conn, data_config.database)
        columns_by_table = read_columns(data_conn, data_config.database)
        enrich_table_stats(data_conn, physical_tables, columns_by_table)
        report = build_audit(
            lines=lines,
            tasks=tasks,
            scripts=scripts,
            executions=executions,
            physical_tables=physical_tables,
            execution_summary=execution_summary,
        )

    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    write_markdown(report, args.markdown_output)
    print(
        json.dumps(
            {
                "json_output": str(args.json_output),
                "markdown_output": str(args.markdown_output),
                "summary": report["summary"],
            },
            ensure_ascii=False,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
