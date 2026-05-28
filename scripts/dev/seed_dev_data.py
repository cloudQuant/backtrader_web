#!/usr/bin/env python
"""Seed development data for local development environments.

Creates sample users, strategies, backtest records, and knowledge bases
with documents to provide a realistic development experience.

Usage:
    python scripts/seed_dev_data.py          # Create seed data (idempotent)
    python scripts/seed_dev_data.py --reset   # Clear and regenerate all seed data
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure the backend package is importable
BACKEND_DIR = Path(__file__).resolve().parents[0] / ".." / "src" / "backend"
BACKEND_DIR = BACKEND_DIR.resolve()
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import delete, select  # noqa: E402

from app.db.database import async_session_maker, create_tables  # noqa: E402
from app.models.backtest import BacktestResultModel, BacktestTask  # noqa: E402
from app.models.knowledge_base import KBDocument, KnowledgeBase  # noqa: E402
from app.models.strategy import Strategy  # noqa: E402
from app.models.user import User  # noqa: E402
from app.utils.security import get_password_hash  # noqa: E402

# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------

SEED_PREFIX = "seed_"

SEED_USERS = [
    {
        "id": f"{SEED_PREFIX}user_001",
        "username": "demo_trader",
        "email": "demo_trader@example.com",
        "password": "DemoPass123!",
    },
    {
        "id": f"{SEED_PREFIX}user_002",
        "username": "demo_analyst",
        "email": "demo_analyst@example.com",
        "password": "AnalystPass456!",
    },
    {
        "id": f"{SEED_PREFIX}user_003",
        "username": "demo_quant",
        "email": "demo_quant@example.com",
        "password": "QuantPass789!",
    },
]

SEED_STRATEGIES = [
    {
        "id": f"{SEED_PREFIX}strategy_001",
        "user_id": f"{SEED_PREFIX}user_001",
        "name": "双均线交叉策略",
        "description": "基于快慢均线交叉信号的趋势跟踪策略",
        "category": "trend",
        "code": """import backtrader as bt

class DualMA(bt.Strategy):
    params = (('fast_period', 5), ('slow_period', 20))

    def __init__(self):
        self.fast_ma = bt.indicators.SMA(period=self.p.fast_period)
        self.slow_ma = bt.indicators.SMA(period=self.p.slow_period)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)

    def next(self):
        if self.crossover > 0:
            self.buy()
        elif self.crossover < 0:
            self.sell()
""",
        "params": {"fast_period": 5, "slow_period": 20},
    },
    {
        "id": f"{SEED_PREFIX}strategy_002",
        "user_id": f"{SEED_PREFIX}user_001",
        "name": "布林带突破策略",
        "description": "基于布林带上下轨突破的均值回归策略",
        "category": "mean_reversion",
        "code": """import backtrader as bt

class BollBreakout(bt.Strategy):
    params = (('period', 20), ('devfactor', 2.0))

    def __init__(self):
        self.boll = bt.indicators.BollingerBands(
            period=self.p.period, devfactor=self.p.devfactor
        )

    def next(self):
        if self.data.close[0] < self.boll.lines.bot[0]:
            self.buy()
        elif self.data.close[0] > self.boll.lines.top[0]:
            self.sell()
""",
        "params": {"period": 20, "devfactor": 2.0},
    },
    {
        "id": f"{SEED_PREFIX}strategy_003",
        "user_id": f"{SEED_PREFIX}user_002",
        "name": "RSI超买超卖策略",
        "description": "基于RSI指标的超买超卖反转策略",
        "category": "oscillator",
        "code": """import backtrader as bt

class RSIStrategy(bt.Strategy):
    params = (('rsi_period', 14), ('oversold', 30), ('overbought', 70))

    def __init__(self):
        self.rsi = bt.indicators.RSI(period=self.p.rsi_period)

    def next(self):
        if self.rsi[0] < self.p.oversold:
            self.buy()
        elif self.rsi[0] > self.p.overbought:
            self.sell()
""",
        "params": {"rsi_period": 14, "oversold": 30, "overbought": 70},
    },
    {
        "id": f"{SEED_PREFIX}strategy_004",
        "user_id": f"{SEED_PREFIX}user_003",
        "name": "MACD动量策略",
        "description": "基于MACD柱状图变化的动量交易策略",
        "category": "momentum",
        "code": """import backtrader as bt

class MACDStrategy(bt.Strategy):
    params = (('fast', 12), ('slow', 26), ('signal', 9))

    def __init__(self):
        self.macd = bt.indicators.MACD(
            period_me1=self.p.fast,
            period_me2=self.p.slow,
            period_signal=self.p.signal,
        )

    def next(self):
        if self.macd.macd[0] > self.macd.signal[0]:
            self.buy()
        elif self.macd.macd[0] < self.macd.signal[0]:
            self.sell()
""",
        "params": {"fast": 12, "slow": 26, "signal": 9},
    },
]

SEED_BACKTEST_TASKS = [
    {
        "id": f"{SEED_PREFIX}backtest_001",
        "user_id": f"{SEED_PREFIX}user_001",
        "strategy_id": f"{SEED_PREFIX}strategy_001",
        "symbol": "000001.SZ",
        "status": "completed",
        "request_data": {
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "initial_cash": 100000,
            "commission": 0.001,
        },
    },
    {
        "id": f"{SEED_PREFIX}backtest_002",
        "user_id": f"{SEED_PREFIX}user_001",
        "strategy_id": f"{SEED_PREFIX}strategy_002",
        "symbol": "600519.SH",
        "status": "completed",
        "request_data": {
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "initial_cash": 200000,
            "commission": 0.001,
        },
    },
    {
        "id": f"{SEED_PREFIX}backtest_003",
        "user_id": f"{SEED_PREFIX}user_002",
        "strategy_id": f"{SEED_PREFIX}strategy_003",
        "symbol": "AAPL",
        "status": "completed",
        "request_data": {
            "start_date": "2023-06-01",
            "end_date": "2023-12-31",
            "initial_cash": 50000,
            "commission": 0.0005,
        },
    },
]

SEED_BACKTEST_RESULTS = [
    {
        "id": f"{SEED_PREFIX}result_001",
        "task_id": f"{SEED_PREFIX}backtest_001",
        "total_return": 15.3,
        "annual_return": 15.3,
        "sharpe_ratio": 1.2,
        "max_drawdown": -8.5,
        "win_rate": 55.0,
        "total_trades": 42,
        "profitable_trades": 23,
        "losing_trades": 19,
    },
    {
        "id": f"{SEED_PREFIX}result_002",
        "task_id": f"{SEED_PREFIX}backtest_002",
        "total_return": 22.7,
        "annual_return": 22.7,
        "sharpe_ratio": 1.8,
        "max_drawdown": -6.2,
        "win_rate": 62.0,
        "total_trades": 28,
        "profitable_trades": 17,
        "losing_trades": 11,
    },
    {
        "id": f"{SEED_PREFIX}result_003",
        "task_id": f"{SEED_PREFIX}backtest_003",
        "total_return": -3.1,
        "annual_return": -5.8,
        "sharpe_ratio": -0.3,
        "max_drawdown": -12.4,
        "win_rate": 41.0,
        "total_trades": 35,
        "profitable_trades": 14,
        "losing_trades": 21,
    },
]

SEED_KNOWLEDGE_BASES = [
    {
        "id": f"{SEED_PREFIX}kb_001",
        "owner_id": f"{SEED_PREFIX}user_001",
        "name": "量化交易入门",
        "description": "量化交易基础知识和常用策略介绍",
        "is_public": True,
    },
    {
        "id": f"{SEED_PREFIX}kb_002",
        "owner_id": f"{SEED_PREFIX}user_002",
        "name": "技术分析指标",
        "description": "常用技术分析指标的计算方法和使用场景",
        "is_public": False,
    },
]

SEED_KB_DOCUMENTS = [
    {
        "id": f"{SEED_PREFIX}doc_001",
        "knowledge_base_id": f"{SEED_PREFIX}kb_001",
        "title": "什么是量化交易",
        "content": (
            "# 什么是量化交易\n\n"
            "量化交易是指利用数学模型和计算机程序来进行金融交易的方法。"
            "它通过对历史数据的分析，建立数学模型，"
            "并利用计算机技术自动执行交易策略。\n\n"
            "## 优势\n\n"
            "- 消除情绪干扰\n"
            "- 可回测验证\n"
            "- 执行速度快\n"
            "- 可同时监控多个市场\n"
        ),
        "content_type": "markdown",
        "sort_order": 0,
        "status": "published",
    },
    {
        "id": f"{SEED_PREFIX}doc_002",
        "knowledge_base_id": f"{SEED_PREFIX}kb_001",
        "title": "回测框架介绍",
        "content": (
            "# 回测框架介绍\n\n"
            "Backtrader 是一个功能强大的 Python 回测框架，"
            "支持多种数据源和交易策略。\n\n"
            "## 核心概念\n\n"
            "- **Strategy**: 策略类，定义交易逻辑\n"
            "- **Indicator**: 指标类，计算技术指标\n"
            "- **Broker**: 经纪商模拟，处理订单和资金\n"
            "- **Data Feed**: 数据源，提供行情数据\n"
        ),
        "content_type": "markdown",
        "sort_order": 1,
        "status": "published",
    },
    {
        "id": f"{SEED_PREFIX}doc_003",
        "knowledge_base_id": f"{SEED_PREFIX}kb_002",
        "title": "移动平均线 (MA)",
        "content": (
            "# 移动平均线 (MA)\n\n"
            "移动平均线是最基础的技术分析指标之一。\n\n"
            "## 简单移动平均线 (SMA)\n\n"
            "SMA = (P1 + P2 + ... + Pn) / n\n\n"
            "## 指数移动平均线 (EMA)\n\n"
            "EMA 对近期价格赋予更高权重，对价格变化更敏感。\n"
        ),
        "content_type": "markdown",
        "sort_order": 0,
        "status": "published",
    },
]


# ---------------------------------------------------------------------------
# Seed logic
# ---------------------------------------------------------------------------


class SeedCounter:
    """Track created/skipped counts per entity type."""

    def __init__(self) -> None:
        self.created: dict[str, int] = {}
        self.skipped: dict[str, int] = {}

    def record_created(self, entity_type: str) -> None:
        self.created[entity_type] = self.created.get(entity_type, 0) + 1

    def record_skipped(self, entity_type: str) -> None:
        self.skipped[entity_type] = self.skipped.get(entity_type, 0) + 1

    def summary(self) -> str:
        lines = []
        all_types = sorted(set(list(self.created.keys()) + list(self.skipped.keys())))
        for entity_type in all_types:
            created = self.created.get(entity_type, 0)
            skipped = self.skipped.get(entity_type, 0)
            lines.append(f"  {entity_type}: created={created}, skipped={skipped}")
        return "\n".join(lines)


async def check_exists(session, model, record_id: str) -> bool:
    """Check if a record with the given ID exists."""
    result = await session.execute(select(model).where(model.id == record_id))
    return result.scalar_one_or_none() is not None


async def reset_seed_data(session) -> None:
    """Delete all seed data (records with seed_ prefix IDs)."""
    # Delete in reverse dependency order
    await session.execute(
        delete(BacktestResultModel).where(BacktestResultModel.id.like(f"{SEED_PREFIX}%"))
    )
    await session.execute(
        delete(BacktestTask).where(BacktestTask.id.like(f"{SEED_PREFIX}%"))
    )
    await session.execute(
        delete(KBDocument).where(KBDocument.id.like(f"{SEED_PREFIX}%"))
    )
    await session.execute(
        delete(KnowledgeBase).where(KnowledgeBase.id.like(f"{SEED_PREFIX}%"))
    )
    await session.execute(
        delete(Strategy).where(Strategy.id.like(f"{SEED_PREFIX}%"))
    )
    await session.execute(
        delete(User).where(User.id.like(f"{SEED_PREFIX}%"))
    )
    await session.commit()
    print("Reset: cleared all seed data.")


async def seed_users(session, counter: SeedCounter) -> None:
    """Create seed users."""
    for user_data in SEED_USERS:
        if await check_exists(session, User, user_data["id"]):
            counter.record_skipped("users")
            continue
        user = User(
            id=user_data["id"],
            username=user_data["username"],
            email=user_data["email"],
            hashed_password=get_password_hash(user_data["password"]),
            is_active=True,
        )
        session.add(user)
        counter.record_created("users")
    await session.flush()


async def seed_strategies(session, counter: SeedCounter) -> None:
    """Create seed strategies."""
    for strat_data in SEED_STRATEGIES:
        if await check_exists(session, Strategy, strat_data["id"]):
            counter.record_skipped("strategies")
            continue
        strategy = Strategy(
            id=strat_data["id"],
            user_id=strat_data["user_id"],
            name=strat_data["name"],
            description=strat_data["description"],
            code=strat_data["code"],
            params=strat_data["params"],
            category=strat_data["category"],
        )
        session.add(strategy)
        counter.record_created("strategies")
    await session.flush()


async def seed_backtests(session, counter: SeedCounter) -> None:
    """Create seed backtest tasks and results."""
    for task_data in SEED_BACKTEST_TASKS:
        if await check_exists(session, BacktestTask, task_data["id"]):
            counter.record_skipped("backtest_tasks")
            continue
        task = BacktestTask(
            id=task_data["id"],
            user_id=task_data["user_id"],
            strategy_id=task_data["strategy_id"],
            symbol=task_data["symbol"],
            status=task_data["status"],
            request_data=task_data["request_data"],
        )
        session.add(task)
        counter.record_created("backtest_tasks")
    await session.flush()

    for result_data in SEED_BACKTEST_RESULTS:
        if await check_exists(session, BacktestResultModel, result_data["id"]):
            counter.record_skipped("backtest_results")
            continue
        result = BacktestResultModel(
            id=result_data["id"],
            task_id=result_data["task_id"],
            total_return=result_data["total_return"],
            annual_return=result_data["annual_return"],
            sharpe_ratio=result_data["sharpe_ratio"],
            max_drawdown=result_data["max_drawdown"],
            win_rate=result_data["win_rate"],
            total_trades=result_data["total_trades"],
            profitable_trades=result_data["profitable_trades"],
            losing_trades=result_data["losing_trades"],
        )
        session.add(result)
        counter.record_created("backtest_results")
    await session.flush()


async def seed_knowledge_bases(session, counter: SeedCounter) -> None:
    """Create seed knowledge bases and documents."""
    for kb_data in SEED_KNOWLEDGE_BASES:
        if await check_exists(session, KnowledgeBase, kb_data["id"]):
            counter.record_skipped("knowledge_bases")
            continue
        kb = KnowledgeBase(
            id=kb_data["id"],
            owner_id=kb_data["owner_id"],
            name=kb_data["name"],
            description=kb_data["description"],
            is_public=kb_data["is_public"],
            document_count=0,
        )
        session.add(kb)
        counter.record_created("knowledge_bases")
    await session.flush()

    for doc_data in SEED_KB_DOCUMENTS:
        if await check_exists(session, KBDocument, doc_data["id"]):
            counter.record_skipped("kb_documents")
            continue
        doc = KBDocument(
            id=doc_data["id"],
            knowledge_base_id=doc_data["knowledge_base_id"],
            title=doc_data["title"],
            content=doc_data["content"],
            content_type=doc_data["content_type"],
            sort_order=doc_data["sort_order"],
            status=doc_data["status"],
        )
        session.add(doc)
        counter.record_created("kb_documents")
    await session.flush()

    # Update document counts
    for kb_data in SEED_KNOWLEDGE_BASES:
        result = await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_data["id"])
        )
        kb = result.scalar_one_or_none()
        if kb:
            doc_count_result = await session.execute(
                select(KBDocument).where(KBDocument.knowledge_base_id == kb_data["id"])
            )
            kb.document_count = len(doc_count_result.scalars().all())


async def main() -> int:
    """Run the seed script."""
    parser = argparse.ArgumentParser(description="Seed development data")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear and regenerate all seed data",
    )
    args = parser.parse_args()

    # Verify database connectivity
    try:
        await create_tables()
    except Exception as exc:
        print(f"Error: Database unavailable - {exc}", file=sys.stderr)
        return 1

    counter = SeedCounter()

    try:
        async with async_session_maker() as session:
            if args.reset:
                await reset_seed_data(session)

            await seed_users(session, counter)
            await seed_strategies(session, counter)
            await seed_backtests(session, counter)
            await seed_knowledge_bases(session, counter)

            await session.commit()
    except Exception as exc:
        print(f"Error: Failed to seed data - {exc}", file=sys.stderr)
        return 1

    print("Seed data summary:")
    print(counter.summary())
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
