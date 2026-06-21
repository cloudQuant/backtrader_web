from datetime import datetime

from app.data_fetch.scripts.futures.daily.minute_market import FuturesMinuteMarket


def test_format_latest_datetime_accepts_string_and_datetime():
    assert (
        FuturesMinuteMarket._format_latest_datetime("2026-06-20 09:31:00")
        == "2026-06-20 09:31:00"
    )
    assert (
        FuturesMinuteMarket._format_latest_datetime(datetime(2026, 6, 20, 9, 31))
        == "2026-06-20 09:31:00"
    )


def test_format_latest_datetime_rejects_invalid_values():
    assert FuturesMinuteMarket._format_latest_datetime(None) is None
    assert FuturesMinuteMarket._format_latest_datetime("not-a-date") is None


def test_select_main_continuous_symbols_filters_month_contracts_and_dedupes():
    symbols = ["TA0", "TA2610", "rb0", "RB2609", " IF0 ", "IF0", "", None]

    assert FuturesMinuteMarket._select_main_continuous_symbols(symbols) == [
        "TA0",
        "RB0",
        "IF0",
    ]


def test_coerce_bool_accepts_scheduler_string_values():
    assert FuturesMinuteMarket._coerce_bool(True) is True
    assert FuturesMinuteMarket._coerce_bool("true") is True
    assert FuturesMinuteMarket._coerce_bool("1") is True
    assert FuturesMinuteMarket._coerce_bool("false") is False
    assert FuturesMinuteMarket._coerce_bool(None) is False
