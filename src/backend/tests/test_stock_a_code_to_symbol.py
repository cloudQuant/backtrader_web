from datetime import date

from app.data_fetch.scripts.stocks.weekly.stock_a_code_to_symbol import (
    PREFER_LOCAL_SCRIPT,
    StockACodeToSymbol,
)


def test_script_prefers_local_entrypoint_for_scalar_interface():
    assert PREFER_LOCAL_SCRIPT is True


def test_normalize_code_to_symbol_wraps_scalar_result():
    normalized = StockACodeToSymbol.normalize_code_to_symbol(
        "sz000300", source_code="000300", data_date=date(2026, 6, 21)
    )

    assert list(normalized.columns) == ["symbol", "name", "data_date"]
    assert normalized.iloc[0].to_dict() == {
        "symbol": "000300",
        "name": "sz000300",
        "data_date": date(2026, 6, 21),
    }
