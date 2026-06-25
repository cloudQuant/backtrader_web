#!/usr/bin/env python3
"""Generate a prioritized list of AkShare tasks that still have no physical data."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FINANCIAL_TOKENS = (
    "financial",
    "finance",
    "balance",
    "cash_flow",
    "profit",
    "report",
    "notice",
    "disclosure",
    "research",
    "indicator",
    "zcfz",
    "xjll",
    "lrb",
    "yjbb",
    "yjkb",
    "yjyg",
)
HISTORY_TOKENS = ("hist", "daily", "minute", "tick", "kline")
FLOW_TOKENS = (
    "fund_flow",
    "hold",
    "rank",
    "hot",
    "lhb",
    "margin",
    "hsgt",
    "shareholder",
)
REALTIME_TOKENS = ("spot", "current", "realtime", "pool")
CORE_CATEGORIES = {"stocks", "funds", "futures", "indexs", "bonds"}


def score_task(task: dict[str, Any]) -> tuple[int, list[str]]:
    script_id = str(task.get("script_id") or "").lower()
    target_table = str(task.get("target_table") or "").lower()
    text = f"{script_id} {target_table}"
    category = str(task.get("category") or "")
    data_status = str(task.get("data_status") or "")
    latest = task.get("latest_execution") or {}
    latest_status = str(latest.get("status") or "")

    priority = 0
    reasons: list[str] = []

    if category in CORE_CATEGORIES:
        priority += 25
        reasons.append("核心资产类别")
    if any(token in text for token in FINANCIAL_TOKENS):
        priority += 40
        reasons.append("财务/公告/报表")
    if any(token in text for token in HISTORY_TOKENS):
        priority += 35
        reasons.append("行情历史/分钟/tick")
    if any(token in text for token in FLOW_TOKENS):
        priority += 25
        reasons.append("资金流/持仓/榜单")
    if any(token in text for token in REALTIME_TOKENS):
        priority += 15
        reasons.append("实时/池类数据")
    if data_status == "empty_table":
        priority += 10
        reasons.append("已有空表，可能只需修保存/参数")
    if latest_status == "FAILED":
        priority += 10
        reasons.append("最新执行已暴露失败原因")
    if category == "common" and "macro" in script_id:
        priority -= 10
        reasons.append("宏观但非交易核心")
    if data_status == "missing_table":
        priority += 5

    return priority, reasons


def build_items(audit: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for task in audit.get("tasks", []):
        if task.get("data_status") == "has_data":
            continue
        priority, reasons = score_task(task)
        latest = task.get("latest_execution") or {}
        items.append(
            {
                "priority": priority,
                "task_id": task.get("task_id"),
                "script_id": task.get("script_id"),
                "category": task.get("category"),
                "sub_category": task.get("sub_category"),
                "data_status": task.get("data_status"),
                "target_table": task.get("target_table"),
                "latest_execution_status": latest.get("status"),
                "latest_error": latest.get("error_message") or "",
                "reasons": reasons,
            }
        )
    return sorted(
        items,
        key=lambda item: (
            -int(item["priority"]),
            str(item.get("category") or ""),
            str(item.get("script_id") or ""),
        ),
    )


def write_markdown(
    output: Path,
    title: str,
    audit_path: Path,
    audit: dict[str, Any],
    items: list[dict[str, Any]],
) -> None:
    summary = audit.get("summary", {})
    task_status = summary.get("task_data_status", {})
    total = summary.get("todo", {}).get("total_tasks", len(audit.get("tasks", [])))
    has_data = task_status.get("has_data", 0)

    lines = [
        f"# {title}",
        "",
        f"- Source audit: `{audit_path}`",
        f"- Remaining gaps: {len(items)}",
        f"- Has data: {has_data} / {total}",
        "",
        "## Top Remaining Gaps",
        "",
        "| Priority | Task | Script | Category | Status | Target | Latest | Reason |",
        "| ---: | ---: | --- | --- | --- | --- | --- | --- |",
    ]
    for item in items[:150]:
        latest = item.get("latest_execution_status") or ""
        error = str(item.get("latest_error") or "")
        if error:
            latest = f"{latest}: {error[:140]}"
        reasons = ", ".join(item.get("reasons") or [])
        lines.append(
            "| {priority} | {task_id} | `{script_id}` | {category}/{sub_category} | "
            "{data_status} | `{target_table}` | {latest} | {reasons} |".format(
                priority=item.get("priority"),
                task_id=item.get("task_id"),
                script_id=item.get("script_id"),
                category=item.get("category") or "",
                sub_category=item.get("sub_category") or "",
                data_status=item.get("data_status") or "",
                target_table=item.get("target_table") or "",
                latest=latest,
                reasons=reasons,
            )
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--title", default="AkShare Gap Priority")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit = json.loads(args.audit_json.read_text(encoding="utf-8"))
    items = build_items(audit)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_audit": str(args.audit_json),
        "summary": audit.get("summary", {}),
        "items": items,
    }
    args.json_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    write_markdown(args.markdown_output, args.title, args.audit_json, audit, items)
    print(
        json.dumps(
            {
                "json_output": str(args.json_output),
                "markdown_output": str(args.markdown_output),
                "remaining_gaps": len(items),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
