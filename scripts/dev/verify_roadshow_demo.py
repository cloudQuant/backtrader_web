#!/usr/bin/env python3
"""Verify roadshow demo acceptance gates against local files and SQLite data."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "data" / "dev" / "backtrader.db"


def scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    return conn.execute(sql, params).fetchone()[0]


def json_len(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        parsed = json.loads(value)
        return len(parsed) if isinstance(parsed, list) else 0
    return len(value) if isinstance(value, list) else 0


def check(name: str, passed: bool, evidence: str) -> tuple[str, bool, str]:
    status = "PASS" if passed else "FAIL"
    print(f"{status} {name}: {evidence}")
    return name, passed, evidence


def verify_database(conn: sqlite3.Connection) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    strategy_count = scalar(conn, "SELECT COUNT(*) FROM strategies WHERE id LIKE 'roadshow_%'")
    category_count = scalar(
        conn,
        """
        SELECT COUNT(DISTINCT category)
        FROM strategies
        WHERE id LIKE 'roadshow_%'
        """,
    )
    checks.append(
        check(
            "策略样例",
            strategy_count >= 4 and category_count >= 4,
            f"{strategy_count} strategies, {category_count} categories",
        )
    )

    workspace_units = scalar(
        conn,
        "SELECT COUNT(*) FROM strategy_units WHERE workspace_id = 'roadshow_workspace_ai'",
    )
    checks.append(
        check(
            "研究工作区",
            workspace_units >= 3,
            f"roadshow_workspace_ai has {workspace_units} units",
        )
    )

    backtest_row = conn.execute(
        """
        SELECT bt.status, br.equity_curve, br.trades
        FROM backtest_tasks bt
        JOIN backtest_results br ON br.task_id = bt.id
        WHERE bt.id = 'roadshow_backtest_dual_ma'
        """
    ).fetchone()
    equity_points = json_len(backtest_row["equity_curve"]) if backtest_row else 0
    trade_count = json_len(backtest_row["trades"]) if backtest_row else 0
    checks.append(
        check(
            "已有回测结果",
            bool(backtest_row and backtest_row["status"] == "completed" and equity_points >= 12),
            f"status={backtest_row['status'] if backtest_row else 'missing'}, "
            f"equity_points={equity_points}, trades={trade_count}",
        )
    )

    tx_count = scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM portfolio_ledger_transactions
        WHERE portfolio_id = 'roadshow_portfolio'
        """,
    )
    snapshot_count = scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM portfolio_ledger_snapshots
        WHERE portfolio_id = 'roadshow_portfolio'
        """,
    )
    checks.append(
        check(
            "组合台账",
            tx_count >= 12 and snapshot_count >= 12,
            f"{tx_count} transactions, {snapshot_count} snapshots",
        )
    )

    broker = conn.execute(
        """
        SELECT broker_id, is_destructive_enabled, last_health
        FROM broker_connection_profiles
        WHERE id = 'roadshow_broker_profile'
        """
    ).fetchone()
    checks.append(
        check(
            "模拟券商 Profile",
            bool(broker and broker["broker_id"] == "roadshow_demo" and not broker[1]),
            f"broker={broker['broker_id'] if broker else 'missing'}, write_enabled="
            f"{broker['is_destructive_enabled'] if broker else 'missing'}",
        )
    )

    ai_success = scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM ai_call_logs
        WHERE id LIKE 'roadshow_ai_success_%' AND status = 'success'
        """,
    )
    ai_tokens = scalar(
        conn,
        "SELECT COALESCE(SUM(total_tokens), 0) FROM ai_call_logs WHERE id LIKE 'roadshow_ai_%'",
    )
    checks.append(
        check(
            "AI 可观测成功样例",
            ai_success >= 3 and ai_tokens > 0,
            f"{ai_success} success logs, {ai_tokens} total tokens",
        )
    )

    news_count = scalar(
        conn,
        "SELECT COUNT(*) FROM news_articles WHERE id LIKE 'roadshow_news_%'",
    )
    checks.append(check("新闻情报样例", news_count >= 4, f"{news_count} articles"))

    model_pref = conn.execute(
        """
        SELECT ai_preferred_provider, ai_preferred_model
        FROM users
        WHERE username = 'admin'
        """
    ).fetchone()
    checks.append(
        check(
            "默认模型偏好",
            bool(
                model_pref
                and model_pref["ai_preferred_provider"] == "volcengine_ark"
                and model_pref["ai_preferred_model"] == "deepseek-v4-pro"
            ),
            f"{dict(model_pref) if model_pref else 'missing admin'}",
        )
    )
    return checks


def verify_files() -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    registry = REPO_ROOT / "src" / "frontend" / "src" / "i18n" / "locales" / "registry.ts"
    registry_text = registry.read_text(encoding="utf-8")
    checks.append(
        check(
            "中文默认语言",
            "DEFAULT_LOCALE: LocaleCode = 'zh-CN'" in registry_text,
            str(registry.relative_to(REPO_ROOT)),
        )
    )

    screenshot_dir = REPO_ROOT / "docs" / "pitch" / "assets" / "screenshots"
    screenshot_count = len(list(screenshot_dir.glob("*.png")))
    audit_file = REPO_ROOT / "docs" / "pitch" / "assets" / "playwright-investor-audit.json"
    checks.append(
        check(
            "Playwright 截图与审计资产",
            screenshot_count >= 31 and audit_file.is_file(),
            f"{screenshot_count} screenshots, audit_exists={audit_file.is_file()}",
        )
    )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path")
    args = parser.parse_args()

    db_path = args.db.resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        checks = verify_database(conn) + verify_files()

    failed = [name for name, passed, _ in checks if not passed]
    if failed:
        print("\nRoadshow demo verification failed:")
        for name in failed:
            print(f"- {name}")
        return 1
    print("\nRoadshow demo verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
