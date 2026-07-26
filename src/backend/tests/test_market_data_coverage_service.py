"""Deterministic coverage and futures-quality tests for iteration 184."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.market_data_coverage_service import (
    _WAREHOUSE_COVERAGE_PROFILES,
    LocalCsvProfile,
    MarketDataCoverageService,
    _warehouse_quality_status,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "iteration_184"


def _inspect(name: str, timeframe: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    coverage, reports = MarketDataCoverageService()._inspect_csv(
        LocalCsvProfile(
            path=_FIXTURES / name,
            asset_type="futures",
            symbol="RB0",
            timeframe=timeframe,
        )
    )
    assert coverage is not None
    return coverage, reports


def test_futures_fixture_preserves_cross_midnight_trading_day_without_session_error():
    coverage, reports = _inspect("RB0_H1_normal_cross_midnight.csv", "1h")

    assert coverage["row_count"] == 6
    assert not any(report["issue_type"] == "futures_night_session_gap" for report in reports)
    assert not any(report["issue_type"] == "futures_holiday_bar" for report in reports)


def test_futures_night_session_gap_is_a_blocking_quality_issue():
    _, reports = _inspect("RB0_H1_night_gap.csv", "1h")

    gap = next(report for report in reports if report["issue_type"] == "futures_night_session_gap")
    assert gap["severity"] == "error"
    assert gap["issue_count"] == 1
    assert gap["sample_payload"] == {
        "trading_day": "2024-01-03",
        "missing_at": "2024-01-02 22:00:00",
    }


def test_futures_roll_price_jump_warns_but_does_not_block_data_quality():
    _, reports = _inspect("RB0_D1_roll_jump.csv", "1d")

    jump = next(report for report in reports if report["issue_type"] == "futures_roll_price_jump")
    assert jump["severity"] == "warning"
    assert jump["issue_count"] == 1


def test_futures_holiday_bar_is_a_blocking_calendar_violation():
    _, reports = _inspect("RB0_H1_holiday_bar.csv", "1h")

    holiday = next(report for report in reports if report["issue_type"] == "futures_holiday_bar")
    assert holiday["severity"] == "error"
    assert holiday["sample_payload"]["trading_day"] == "2024-01-02"


def test_warehouse_quality_marks_outdated_market_data_as_failed():
    assert _warehouse_quality_status("stock", "2024-12-31") == "failed"


@pytest.mark.asyncio
async def test_warehouse_coverage_filters_symbols_before_grouping():
    """MySQL cannot resolve source columns from the HAVING clause here."""

    class _Result:
        def mappings(self):
            return self

        def all(self):
            return [
                {
                    "symbol": "000001",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-02",
                    "row_count": 2,
                }
            ]

    class _Connection:
        query = ""
        parameters: dict[str, object] = {}

        async def execute(self, statement, parameters):
            self.query = str(statement)
            self.parameters = parameters
            return _Result()

    class _ConnectionContext:
        def __init__(self, connection):
            self.connection = connection

        async def __aenter__(self):
            return self.connection

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class _Engine:
        def __init__(self):
            self.connection = _Connection()

        def connect(self):
            return _ConnectionContext(self.connection)

    engine = _Engine()
    rows = await MarketDataCoverageService._warehouse_coverage_rows(
        engine=engine,
        profile=_WAREHOUSE_COVERAGE_PROFILES[0],
        symbol="000001",
        limit=20,
    )

    assert rows[0]["symbol"] == "000001"
    assert "HAVING" not in engine.connection.query.upper()
    assert "AND (:symbol IS NULL OR UPPER(" in engine.connection.query
    assert engine.connection.parameters == {"symbol": "000001", "limit": 20}
