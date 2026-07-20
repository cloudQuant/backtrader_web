"""Deterministic coverage and futures-quality tests for iteration 184."""

from __future__ import annotations

from pathlib import Path

from app.services.market_data_coverage_service import (
    LocalCsvProfile,
    MarketDataCoverageService,
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
