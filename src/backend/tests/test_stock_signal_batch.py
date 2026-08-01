"""After-close batch scheduling contracts without live provider calls."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services.stock_signal.batch import Sse50SignalBatchRunner
from app.services.stock_signal.decision_policy import SignalPolicy
from app.services.stock_signal.quality import DataQualityGate


class _Calendar:
    async def is_trading_day(self, value: date) -> bool:
        return value == date(2026, 7, 30)

    async def next_trading_day(self, value: date) -> date:
        return value + timedelta(days=1)


class _Universe:
    async def members(self) -> list[dict[str, str]]:
        return [
            {"symbol": "600000.SH", "name": "浦发银行"},
            {"symbol": "601398.SH", "name": "工商银行"},
        ]


def _configured_runner() -> Sse50SignalBatchRunner:
    runner = Sse50SignalBatchRunner(calendar=_Calendar(), universe=_Universe())
    runner.settings = SimpleNamespace(
        STOCK_SIGNAL_ROUND_TRIP_COST_BPS=20.0,
        STOCK_SIGNAL_BUY_SUCCESS_THRESHOLD_BPS=30.0,
        STOCK_SIGNAL_SELL_SUCCESS_THRESHOLD_BPS=30.0,
        STOCK_SIGNAL_MAX_CONCURRENCY=2,
        STOCK_SIGNAL_MIN_HISTORY_BARS=60,
        STOCK_SIGNAL_MAX_FINANCIAL_AGE_DAYS=210,
        STOCK_SIGNAL_MAX_NEWS_AGE_DAYS=7,
    )
    runner.policy = SignalPolicy(
        round_trip_cost_bps=20.0,
        buy_success_threshold_bps=30.0,
        sell_success_threshold_bps=30.0,
    )
    runner.quality_gate = DataQualityGate()
    return runner


@pytest.mark.asyncio
async def test_batch_claims_one_idempotent_run_and_records_all_member_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _configured_runner()
    calls: list[str] = []

    async def process_member(*, member: dict[str, str], **_kwargs: object) -> tuple[str, str | None]:
        calls.append(member["symbol"])
        return ("eligible" if member["symbol"] == "600000.SH" else "degraded", None)

    monkeypatch.setattr(runner, "_process_member", process_member)

    first = await runner.run(as_of_date=date(2026, 7, 30))
    second = await runner.run(as_of_date=date(2026, 7, 30))

    assert first is not None
    assert first.status == "completed"
    assert first.expected_count == 2
    assert first.created_count == 2
    assert first.eligible_count == 1
    assert first.degraded_count == 1
    assert second is not None
    assert second.id == first.id
    assert calls == ["600000.SH", "601398.SH"]


@pytest.mark.asyncio
async def test_batch_refuses_non_trading_dates_without_inferring_weekdays() -> None:
    runner = _configured_runner()

    result = await runner.run(as_of_date=date(2026, 8, 1))

    assert result is None


@pytest.mark.asyncio
async def test_second_worker_does_not_process_a_run_already_claimed_by_another_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _configured_runner()
    members = await runner.universe.members()
    claimed, did_claim = await runner._claim_run(date(2026, 7, 30), members)

    async def process_member(**_kwargs: object) -> tuple[str, str | None]:
        raise AssertionError("a second worker must not process an already-running batch")

    monkeypatch.setattr(runner, "_process_member", process_member)
    returned = await runner.run(as_of_date=date(2026, 7, 30))

    assert did_claim is True
    assert returned is not None
    assert returned.id == claimed.id
    assert returned.status == "running"
