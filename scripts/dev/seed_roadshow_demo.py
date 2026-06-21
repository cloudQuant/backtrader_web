#!/usr/bin/env python3
"""Seed investor-roadshow demo data into the local development SQLite database.

The script is idempotent. It upserts only fixed ``roadshow_*`` records and leaves
other local development data untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "data" / "dev" / "backtrader.db"

USER_PREF_PROVIDER = "volcengine_ark"
USER_PREF_MODEL = "deepseek-v4-pro"


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert(
    conn: sqlite3.Connection,
    table: str,
    key_column: str,
    row: dict[str, Any],
) -> None:
    columns = list(row)
    exists = conn.execute(
        f"SELECT 1 FROM {table} WHERE {key_column} = ?",
        (row[key_column],),
    ).fetchone()
    values = [
        json_dump(value) if isinstance(value, (dict, list)) else value
        for value in (row[column] for column in columns)
    ]
    if exists:
        assignments = ", ".join(f"{column} = ?" for column in columns if column != key_column)
        update_values = [
            json_dump(row[column]) if isinstance(row[column], (dict, list)) else row[column]
            for column in columns
            if column != key_column
        ]
        update_values.append(row[key_column])
        conn.execute(
            f"UPDATE {table} SET {assignments} WHERE {key_column} = ?",
            update_values,
        )
        return

    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        values,
    )


def get_demo_user_id(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT id FROM users WHERE username = 'admin' ORDER BY created_at LIMIT 1"
    ).fetchone()
    if row is None:
        row = conn.execute("SELECT id FROM users ORDER BY created_at LIMIT 1").fetchone()
    if row is None:
        raise RuntimeError("No users found. Start the backend once or create an admin user first.")
    user_id = str(row["id"])
    conn.execute(
        """
        UPDATE users
        SET ai_preferred_provider = ?, ai_preferred_model = ?
        WHERE id = ?
        """,
        (USER_PREF_PROVIDER, USER_PREF_MODEL, user_id),
    )
    return user_id


def param_spec(
    param_type: str,
    default: int | float | str,
    minimum: int | float | None,
    maximum: int | float | None,
    description: str,
) -> dict[str, Any]:
    return {
        "type": param_type,
        "default": default,
        "min": minimum,
        "max": maximum,
        "options": None,
        "description": description,
    }


STRATEGY_CODE = {
    "roadshow_trend_dual_ma": """import backtrader as bt


class RoadshowDualMA(bt.Strategy):
    params = (("fast_period", 10), ("slow_period", 30), ("atr_stop", 2.0))

    def __init__(self):
        self.fast_ma = bt.indicators.SMA(period=self.p.fast_period)
        self.slow_ma = bt.indicators.SMA(period=self.p.slow_period)
        self.atr = bt.indicators.ATR(period=14)
        self.cross = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
        self.stop_price = None

    def next(self):
        if not self.position and self.cross > 0:
            self.buy()
            self.stop_price = self.data.close[0] - self.p.atr_stop * self.atr[0]
        elif self.position and (self.cross < 0 or self.data.close[0] < self.stop_price):
            self.close()
""",
    "roadshow_mean_revert": """import backtrader as bt


class RoadshowBollingerReversion(bt.Strategy):
    params = (("period", 20), ("devfactor", 2.0), ("risk_fraction", 0.25))

    def __init__(self):
        self.boll = bt.indicators.BollingerBands(
            period=self.p.period,
            devfactor=self.p.devfactor,
        )

    def next(self):
        if not self.position and self.data.close[0] < self.boll.bot[0]:
            self.buy()
        elif self.position and self.data.close[0] >= self.boll.mid[0]:
            self.close()
""",
    "roadshow_vol_breakout": """import backtrader as bt


class RoadshowVolatilityBreakout(bt.Strategy):
    params = (("lookback", 20), ("atr_multiplier", 1.5), ("exit_lookback", 10))

    def __init__(self):
        self.highest = bt.indicators.Highest(self.data.high, period=self.p.lookback)
        self.lowest = bt.indicators.Lowest(self.data.low, period=self.p.exit_lookback)
        self.atr = bt.indicators.ATR(period=14)

    def next(self):
        breakout = self.data.close[0] > self.highest[-1] + self.p.atr_multiplier * self.atr[0]
        if not self.position and breakout:
            self.buy()
        elif self.position and self.data.close[0] < self.lowest[-1]:
            self.close()
""",
    "roadshow_risk_guard": """import backtrader as bt


class RoadshowRiskGuard(bt.Strategy):
    params = (("max_drawdown_pct", 8.0), ("trail_pct", 5.0), ("max_position_pct", 0.35))

    def __init__(self):
        self.peak_value = 0
        self.highest_close = 0

    def next(self):
        value = self.broker.getvalue()
        self.peak_value = max(self.peak_value, value)
        drawdown_pct = (self.peak_value - value) / self.peak_value * 100 if self.peak_value else 0
        self.highest_close = max(self.highest_close, self.data.close[0])
        trailing_stop = self.highest_close * (1 - self.p.trail_pct / 100)
        if drawdown_pct > self.p.max_drawdown_pct:
            self.close()
        elif self.position and self.data.close[0] < trailing_stop:
            self.close()
""",
}


def seed_strategies(conn: sqlite3.Connection, user_id: str, now: str) -> None:
    strategies = [
        {
            "id": "roadshow_trend_dual_ma",
            "name": "路演样例：双均线 + ATR 止损趋势策略",
            "description": "固定 Happy Path 使用的趋势策略，可从 AI 草稿保存后进入回测验证。",
            "category": "trend",
            "params": {
                "fast_period": param_spec("int", 10, 3, 60, "快均线周期"),
                "slow_period": param_spec("int", 30, 10, 180, "慢均线周期"),
                "atr_stop": param_spec("float", 2.0, 0.5, 5.0, "ATR 止损倍数"),
            },
        },
        {
            "id": "roadshow_mean_revert",
            "name": "路演样例：布林带均值回归策略",
            "description": "低频均值回归样例，展示 AI 如何解释信号边界和适用市场。",
            "category": "mean_reversion",
            "params": {
                "period": param_spec("int", 20, 10, 80, "布林带窗口"),
                "devfactor": param_spec("float", 2.0, 1.0, 3.5, "标准差倍数"),
                "risk_fraction": param_spec("float", 0.25, 0.05, 0.5, "单策略资金占比"),
            },
        },
        {
            "id": "roadshow_vol_breakout",
            "name": "路演样例：波动率突破策略",
            "description": "波动率扩张场景样例，覆盖突破、回撤退出和参数优化话术。",
            "category": "volatility",
            "params": {
                "lookback": param_spec("int", 20, 10, 120, "突破观察窗口"),
                "atr_multiplier": param_spec("float", 1.5, 0.5, 4.0, "ATR 突破阈值"),
                "exit_lookback": param_spec("int", 10, 3, 60, "退出观察窗口"),
            },
        },
        {
            "id": "roadshow_risk_guard",
            "name": "路演样例：组合风控保护策略",
            "description": "展示最大回撤、移动止损和仓位上限如何进入策略审查。",
            "category": "custom",
            "params": {
                "max_drawdown_pct": param_spec("float", 8.0, 2.0, 20.0, "最大回撤阈值"),
                "trail_pct": param_spec("float", 5.0, 1.0, 15.0, "移动止损百分比"),
                "max_position_pct": param_spec("float", 0.35, 0.05, 1.0, "最大仓位比例"),
            },
        },
    ]
    for strategy in strategies:
        upsert(
            conn,
            "strategies",
            "id",
            {
                "id": strategy["id"],
                "user_id": user_id,
                "name": strategy["name"],
                "description": strategy["description"],
                "code": STRATEGY_CODE[strategy["id"]],
                "params": strategy["params"],
                "category": strategy["category"],
                "created_at": now,
                "updated_at": now,
            },
        )


def equity_series() -> tuple[list[str], list[float], list[float]]:
    start = datetime(2025, 1, 31, tzinfo=timezone.utc)
    values = [
        1_000_000,
        1_018_500,
        1_036_200,
        1_021_800,
        1_052_400,
        1_078_900,
        1_064_300,
        1_097_500,
        1_126_800,
        1_115_600,
        1_148_200,
        1_173_900,
    ]
    peak = values[0]
    drawdowns: list[float] = []
    for value in values:
        peak = max(peak, value)
        drawdowns.append(round((value - peak) / peak * 100, 4))
    dates = [(start + timedelta(days=30 * index)).date().isoformat() for index in range(len(values))]
    return dates, values, drawdowns


def seed_backtest(conn: sqlite3.Connection, user_id: str, now: str) -> None:
    dates, values, drawdowns = equity_series()
    task_id = "roadshow_backtest_dual_ma"
    request_data = {
        "strategy_id": "roadshow_trend_dual_ma",
        "symbol": "000300.SH",
        "start_date": "2025-01-01T00:00:00+00:00",
        "end_date": "2025-12-31T00:00:00+00:00",
        "initial_cash": 1_000_000,
        "commission": 0.0003,
        "params": {"fast_period": 10, "slow_period": 30, "atr_stop": 2.0},
    }
    trades = [
        {
            "date": "2025-02-14",
            "type": "buy",
            "price": 3.92,
            "size": 80_000,
            "value": 313_600,
            "pnl": None,
        },
        {
            "date": "2025-05-22",
            "type": "sell",
            "price": 4.11,
            "size": 40_000,
            "value": 164_400,
            "pnl": 7_600,
        },
        {
            "date": "2025-07-10",
            "type": "buy",
            "price": 4.02,
            "size": 50_000,
            "value": 201_000,
            "pnl": None,
        },
        {
            "date": "2025-11-18",
            "type": "sell",
            "price": 4.35,
            "size": 45_000,
            "value": 195_750,
            "pnl": 14_850,
        },
    ]
    upsert(
        conn,
        "backtest_tasks",
        "id",
        {
            "id": task_id,
            "user_id": user_id,
            "strategy_id": "roadshow_trend_dual_ma",
            "strategy_version_id": None,
            "symbol": "000300.SH",
            "status": "completed",
            "request_data": request_data,
            "error_message": None,
            "log_dir": None,
            "created_at": now,
            "updated_at": now,
        },
    )
    upsert(
        conn,
        "backtest_results",
        "id",
        {
            "id": "roadshow_backtest_result",
            "task_id": task_id,
            "total_return": 17.39,
            "annual_return": 16.82,
            "sharpe_ratio": 1.42,
            "max_drawdown": -1.61,
            "win_rate": 61.5,
            "metrics_source": "roadshow_demo",
            "total_trades": 4,
            "profitable_trades": 3,
            "losing_trades": 1,
            "equity_curve": values,
            "equity_dates": dates,
            "drawdown_curve": drawdowns,
            "trades": trades,
            "created_at": now,
        },
    )


def seed_workspace(conn: sqlite3.Connection, user_id: str, now: str) -> None:
    workspace_id = "roadshow_workspace_ai"
    upsert(
        conn,
        "workspaces",
        "id",
        {
            "id": workspace_id,
            "user_id": user_id,
            "name": "路演研究工作区：AI 策略到回测验证",
            "description": "固定 Happy Path：自然语言想法 -> 策略草稿 -> 保存 -> 回测结果。",
            "workspace_type": "research",
            "settings": {
                "roadshow": True,
                "copilot_prompt": "设计一个沪深300ETF日线双均线趋势策略，并加入ATR止损。",
            },
            "trading_config": {},
            "created_at": now,
            "updated_at": now,
        },
    )
    units = [
        ("roadshow_unit_trend", "roadshow_trend_dual_ma", "000300.SH", "沪深300指数"),
        ("roadshow_unit_revert", "roadshow_mean_revert", "510300.SH", "沪深300ETF"),
        ("roadshow_unit_vol", "roadshow_vol_breakout", "159915.SZ", "创业板ETF"),
    ]
    for index, (unit_id, strategy_id, symbol, symbol_name) in enumerate(units, start=1):
        is_primary = strategy_id == "roadshow_trend_dual_ma"
        upsert(
            conn,
            "strategy_units",
            "id",
            {
                "id": unit_id,
                "workspace_id": workspace_id,
                "group_name": "AI Copilot Happy Path" if is_primary else "候选策略池",
                "strategy_id": strategy_id,
                "strategy_name": strategy_id,
                "symbol": symbol,
                "symbol_name": symbol_name,
                "timeframe": "1d",
                "timeframe_n": 1,
                "category": "trend" if is_primary else "candidate",
                "sort_order": index,
                "data_config": {
                    "symbol": symbol,
                    "symbol_name": symbol_name,
                    "start_date": "2025-01-01",
                    "end_date": "2025-12-31",
                    "adjustment": "qfq",
                },
                "unit_settings": {"initial_cash": 1_000_000, "commission": 0.0003},
                "params": {"fast_period": 10, "slow_period": 30, "atr_stop": 2.0}
                if is_primary
                else {},
                "optimization_config": {"enabled": True, "objective": "sharpe_ratio"}
                if is_primary
                else {},
                "trading_mode": "paper",
                "gateway_config": {"profile_id": "roadshow_broker_profile"},
                "lock_trading": 0,
                "lock_running": 0,
                "trading_instance_id": None,
                "trading_snapshot": {"mode": "paper_readonly", "status": "ready"},
                "run_status": "completed" if is_primary else "idle",
                "run_count": 1 if is_primary else 0,
                "last_run_time": 8.4 if is_primary else None,
                "last_task_id": "roadshow_backtest_dual_ma" if is_primary else None,
                "last_optimization_task_id": None,
                "bar_count": 252 if is_primary else None,
                "metrics_snapshot": {
                    "total_return": 17.39,
                    "sharpe_ratio": 1.42,
                    "max_drawdown": -1.61,
                    "win_rate": 61.5,
                }
                if is_primary
                else {},
                "created_at": now,
                "updated_at": now,
            },
        )


def portfolio_transactions() -> list[dict[str, Any]]:
    return [
        ("2025-01-02", "", "cash_deposit", 0, 0, 250_000, ["funding"], "路演初始入金"),
        ("2025-01-06", "510300.SH", "buy", 50_000, 3.86, None, ["trend"], "建仓沪深300ETF"),
        ("2025-01-15", "159915.SZ", "buy", 80_000, 1.82, None, ["growth"], "建仓创业板ETF"),
        ("2025-02-18", "510300.SH", "buy", 32_000, 3.94, None, ["trend"], "趋势确认加仓"),
        ("2025-03-12", "159915.SZ", "sell", 20_000, 1.90, None, ["rebalance"], "降低成长暴露"),
        ("2025-04-08", "510300.SH", "sell", 18_000, 4.05, None, ["risk"], "回撤控制减仓"),
        ("2025-05-09", "512880.SH", "buy", 60_000, 1.05, None, ["defensive"], "加入证券ETF观察仓"),
        ("2025-06-03", "159915.SZ", "buy", 40_000, 1.88, None, ["growth"], "均值回归补仓"),
        ("2025-07-19", "512880.SH", "sell", 20_000, 1.12, None, ["take_profit"], "兑现部分收益"),
        ("2025-08-21", "510300.SH", "buy", 18_000, 4.01, None, ["trend"], "回踩买入"),
        ("2025-09-16", "159915.SZ", "sell", 25_000, 1.97, None, ["risk"], "降低波动"),
        ("2025-10-10", "510300.SH", "sell", 10_000, 4.18, None, ["rebalance"], "再平衡"),
        ("2025-11-05", "", "dividend", 0, 0, 3_600, ["income"], "ETF 分红"),
        ("2025-12-18", "", "fee", 0, 0, 820, ["cost"], "交易费用汇总"),
    ]


def signed_cash_flow(txn: dict[str, Any]) -> float:
    trade_type = str(txn["trade_type"])
    if trade_type == "buy":
        return -abs(float(txn["quantity"]) * float(txn["price"]))
    if trade_type == "sell":
        return abs(float(txn["quantity"]) * float(txn["price"]))
    amount = float(txn.get("amount") or 0)
    if trade_type in {"cash_deposit", "dividend"}:
        return abs(amount)
    if trade_type in {"cash_withdrawal", "fee"}:
        return -abs(amount)
    return 0


def build_snapshots(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cash_balance = 1_000_000.0
    positions: dict[str, dict[str, float]] = {}
    snapshots: list[dict[str, Any]] = []
    for index, txn in enumerate(transactions, start=1):
        cash_balance += signed_cash_flow(txn)
        symbol = str(txn["symbol"])
        if symbol and txn["trade_type"] in {"buy", "sell"}:
            position = positions.setdefault(symbol, {"quantity": 0.0, "last_price": 0.0})
            sign = 1 if txn["trade_type"] == "buy" else -1
            position["quantity"] += sign * float(txn["quantity"])
            position["last_price"] = float(txn["price"])
        marked_value = sum(item["quantity"] * item["last_price"] for item in positions.values())
        snapshots.append(
            {
                "snapshot_date": txn["trade_date"],
                "snapshot_index": index,
                "cash_flow": round(signed_cash_flow(txn), 2),
                "nav": round(cash_balance + marked_value, 2),
            }
        )
    return snapshots


def seed_portfolio(conn: sqlite3.Connection, user_id: str, now: str) -> None:
    portfolio_id = "roadshow_portfolio"
    upsert(
        conn,
        "portfolio_ledgers",
        "id",
        {
            "id": portfolio_id,
            "owner_id": user_id,
            "name": "路演模拟组合账本",
            "base_currency": "CNY",
            "source_type": "roadshow_demo",
            "benchmark_symbol": "hs300",
            "tags": ["roadshow", "paper", "risk-review"],
            "notes": "包含持仓、交易、净值快照和风险摘要的模拟组合，不连接真实资金。",
            "created_at": now,
            "updated_at": now,
        },
    )
    conn.execute(
        "DELETE FROM portfolio_ledger_transactions WHERE portfolio_id = ?",
        (portfolio_id,),
    )
    transactions: list[dict[str, Any]] = []
    for index, raw in enumerate(portfolio_transactions(), start=1):
        trade_date, symbol, trade_type, quantity, price, amount, tags, notes = raw
        transactions.append(
            {
                "id": f"roadshow_txn_{index:02d}",
                "portfolio_id": portfolio_id,
                "symbol": symbol,
                "trade_type": trade_type,
                "quantity": quantity,
                "price": price,
                "amount": amount,
                "trade_date": trade_date,
                "benchmark_symbol": "hs300",
                "tags": tags,
                "notes": notes,
                "created_at": now,
            }
        )
    for txn in transactions:
        upsert(conn, "portfolio_ledger_transactions", "id", txn)
    upsert(
        conn,
        "portfolio_ledger_imports",
        "id",
        {
            "id": "roadshow_portfolio_import",
            "portfolio_id": portfolio_id,
            "import_format": "json",
            "idempotency_key": "roadshow-demo-import-v1",
            "imported_count": len(transactions),
            "created_at": now,
        },
    )
    conn.execute("DELETE FROM portfolio_ledger_snapshots WHERE portfolio_id = ?", (portfolio_id,))
    for index, snapshot in enumerate(build_snapshots(transactions), start=1):
        upsert(
            conn,
            "portfolio_ledger_snapshots",
            "id",
            {
                "id": f"roadshow_snapshot_{index:02d}",
                "portfolio_id": portfolio_id,
                **snapshot,
                "created_at": now,
            },
        )


def seed_broker_profile(conn: sqlite3.Connection, user_id: str, now: str) -> None:
    upsert(
        conn,
        "broker_connection_profiles",
        "id",
        {
            "id": "roadshow_broker_profile",
            "broker_id": "roadshow_demo",
            "account_alias": "roadshow-paper-readonly",
            "capabilities": ["health", "accounts", "positions", "orders", "quotes"],
            "credentials_ref": {"mode": "roadshow_demo", "api_key_env": "BT_ROADSHOW_DEMO"},
            "runtime_gateway_key": "roadshow:paper:readonly",
            "runtime_account_id": "ROADSHOW-PAPER-001",
            "enabled": 1,
            "last_health": {
                "status": "ok",
                "mode": "paper_readonly",
                "trade_connection": "readonly",
                "market_connection": "connected",
            },
            "created_by": user_id,
            "is_destructive_enabled": 0,
            "credentials_rotated_at": now,
            "created_at": now,
            "updated_at": now,
        },
    )


def seed_ai_observability(conn: sqlite3.Connection, user_id: str, now: str) -> None:
    upsert(
        conn,
        "prompt_templates",
        "id",
        {
            "id": "roadshow_prompt_strategy",
            "name": "backtrader_strategy",
            "version": "roadshow-v1",
            "content": "根据交易想法输出策略假设、Backtrader 草稿、风险点和回测建议。",
            "status": "active",
            "variables": ["question", "context_text", "quant_focus"],
            "rollout_percentage": 100,
            "created_at": now,
            "created_by": user_id,
        },
    )
    logs = [
        (
            "roadshow_ai_success_1",
            "knowledge_qa",
            "deepseek-v4-pro",
            1240,
            2380,
            1880,
            "success",
            None,
        ),
        (
            "roadshow_ai_success_2",
            "backtrader_strategy",
            "deepseek-v4-pro",
            1580,
            3190,
            2460,
            "success",
            None,
        ),
        (
            "roadshow_ai_success_3",
            "strategy_review",
            "deepseek-v4-pro",
            920,
            1460,
            1310,
            "success",
            None,
        ),
        (
            "roadshow_ai_failed_1",
            "trading_execution",
            "deepseek-v4-pro",
            300,
            0,
            4520,
            "failed",
            "DemoRiskGate",
        ),
    ]
    for log_id, mode, model, prompt_tokens, completion_tokens, latency, status, error in logs:
        prompt_hash = hashlib.sha256(f"{log_id}:{mode}".encode("utf-8")).hexdigest()
        upsert(
            conn,
            "ai_call_logs",
            "id",
            {
                "id": log_id,
                "user_id": user_id,
                "request_id": log_id,
                "service_name": "ai_chat",
                "mode": mode,
                "model_name": model,
                "provider": USER_PREF_PROVIDER,
                "prompt_template_id": "roadshow_prompt_strategy",
                "prompt_template_version": "roadshow-v1",
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "estimated_cost_usd": 0.0,
                "latency_ms": latency,
                "status": status,
                "error_code": error,
                "error_message": "演示风控：交易执行意图需要人工确认" if error else None,
                "created_at": now,
                "response_chars": 860 if status == "success" else 0,
                "prompt_hash": prompt_hash,
            },
        )


def seed_news(conn: sqlite3.Connection, user_id: str, now: str) -> None:
    source_id = "roadshow_news_source"
    upsert(
        conn,
        "news_sources",
        "id",
        {
            "id": source_id,
            "owner_id": user_id,
            "name": "roadshow-terminal",
            "url": "https://example.com/roadshow/rss",
            "tier": 1,
            "status": "active",
            "metadata": {"tickers": ["510300.SH", "159915.SZ", "RB2510"]},
            "created_at": now,
            "updated_at": now,
        },
    )
    articles = [
        (
            "roadshow_news_1",
            "沪深300ETF成交放量，量化趋势模型给出 bullish 确认信号",
            "510300.SH",
            "BULLISH",
            "HIGH",
            "LOW",
        ),
        (
            "roadshow_news_2",
            "创业板ETF波动率抬升，均值回归策略提示降低仓位",
            "159915.SZ",
            "NEUTRAL",
            "MEDIUM",
            "LOW",
        ),
        (
            "roadshow_news_3",
            "RB2510 surges after bullish demand shock and inventory drawdown",
            "RB2510",
            "BULLISH",
            "HIGH",
            "LOW",
        ),
        (
            "roadshow_news_4",
            "海外风险事件拖累风险偏好，组合风控策略触发复核",
            "510300.SH",
            "BEARISH",
            "HIGH",
            "HIGH",
        ),
    ]
    for index, (article_id, headline, ticker, sentiment, impact, threat) in enumerate(
        articles,
        start=1,
    ):
        canonical_url = f"https://example.com/roadshow/news/{index}"
        cluster_id = hashlib.sha256(headline.lower().encode("utf-8")).hexdigest()[:12]
        upsert(
            conn,
            "news_articles",
            "id",
            {
                "id": article_id,
                "owner_id": user_id,
                "source_id": source_id,
                "source": "roadshow-terminal",
                "headline": headline,
                "url": canonical_url,
                "canonical_url": canonical_url,
                "tickers": [ticker],
                "priority": "P1" if impact == "HIGH" else "P2",
                "tier": 1,
                "source_flag": "roadshow_demo",
                "sentiment": sentiment,
                "impact": impact,
                "threat": threat,
                "cluster_id": cluster_id,
                "summary": f"路演样例新闻：{headline}",
                "status": "ok",
                "created_at": now,
                "updated_at": now,
            },
        )
        upsert(
            conn,
            "news_analyses",
            "id",
            {
                "id": f"roadshow_analysis_{index}",
                "owner_id": user_id,
                "article_id": article_id,
                "headline": headline,
                "sentiment": sentiment,
                "impact": impact,
                "threat": threat,
                "status": "ok",
                "provider": "roadshow_rules",
                "created_at": now,
            },
        )


def required_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row["name"]) for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path")
    args = parser.parse_args()

    db_path = args.db.resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        missing = {
            "strategies",
            "workspaces",
            "strategy_units",
            "backtest_tasks",
            "backtest_results",
            "portfolio_ledgers",
            "broker_connection_profiles",
            "ai_call_logs",
            "news_articles",
        } - required_tables(conn)
        if missing:
            raise SystemExit(f"Database schema is missing tables: {', '.join(sorted(missing))}")

        now = utc_now()
        user_id = get_demo_user_id(conn)
        seed_strategies(conn, user_id, now)
        seed_backtest(conn, user_id, now)
        seed_workspace(conn, user_id, now)
        seed_portfolio(conn, user_id, now)
        seed_broker_profile(conn, user_id, now)
        seed_ai_observability(conn, user_id, now)
        seed_news(conn, user_id, now)
        conn.commit()

    print(f"Seeded roadshow demo data into {db_path}")
    print(f"Demo user id: {user_id}")
    print(f"Preferred model: {USER_PREF_PROVIDER}/{USER_PREF_MODEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
