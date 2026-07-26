import asyncio
import csv
import io
import math
import time
import uuid
from typing import Any

import pytest

pytest.importorskip("pytest_benchmark")


CSV_TEXT = "symbol,trade_type,quantity,price,trade_date\n" + "\n".join(
    (
        f"RB2510,{'buy' if index % 2 == 0 else 'sell'},1,"
        f"{3500 + index % 5},2026-05-{index % 28 + 1:02d}"
    )
    for index in range(1000)
)


def _p95_ms(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def _measure_ms(func: Any, *, rounds: int) -> list[float]:
    durations: list[float] = []
    for _ in range(rounds):
        started = time.perf_counter()
        func()
        durations.append((time.perf_counter() - started) * 1000)
    return durations


def _parse_transactions() -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(CSV_TEXT))
    return [
        {
            "symbol": row["symbol"],
            "trade_type": row["trade_type"],
            "quantity": int(row["quantity"]),
            "price": float(row["price"]),
            "trade_date": row["trade_date"],
        }
        for row in reader
    ]


async def _run_import_async() -> dict[str, Any]:
    from app.db.database import async_session_maker
    from app.services.portfolio_ledger import PortfolioLedgerService

    async with async_session_maker() as session:
        service = PortfolioLedgerService(session)
        portfolio = await service.create_portfolio(
            "perf-user",
            "perf-ledger",
            "CNY",
            "manual",
        )
        result = await service.import_transactions(
            "perf-user",
            portfolio["id"],
            idempotency_key=str(uuid.uuid4()),
            transactions=_parse_transactions(),
        )
        assert result is not None
        return result


def _run_import() -> dict[str, Any]:
    return asyncio.run(_run_import_async())


@pytest.mark.performance
def test_portfolio_ledger_1000_row_import_under_two_seconds(benchmark: Any) -> None:
    result = _run_import()
    assert result["imported_count"] == 1000

    benchmark.pedantic(_run_import, rounds=3, iterations=1)

    p95_ms = _p95_ms(_measure_ms(_run_import, rounds=10))
    assert p95_ms <= 2000.0
