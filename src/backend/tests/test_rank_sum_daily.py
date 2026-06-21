import pandas as pd

from app.data_fetch.scripts.futures.weekly.rank_sum_daily import FuturesRankSumDaily


class _Logger:
    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass


def _rank_sum_source_row(symbol="CU2607", variety="CU", date="20260618"):
    row = {
        "symbol": symbol,
        "variety": variety,
        "date": date,
    }
    for rank in (5, 10, 15, 20):
        row[f"vol_top{rank}"] = rank * 100
        row[f"vol_chg_top{rank}"] = rank
        row[f"long_open_interest_top{rank}"] = rank * 200
        row[f"long_open_interest_chg_top{rank}"] = rank * 2
        row[f"short_open_interest_top{rank}"] = rank * 300
        row[f"short_open_interest_chg_top{rank}"] = rank * 3
    return row


def test_normalize_symbol_list_keeps_only_product_codes_and_dedupes():
    assert FuturesRankSumDaily._normalize_symbol_list(
        ["a", "a2507", " ag ", "AG", "cu0", "CU", "", None]
    ) == ["A", "AG", "CU"]


def test_transform_rank_sum_dataframe_matches_existing_table_shape():
    service = object.__new__(FuturesRankSumDaily)
    service.get_uuid = lambda: "RID"
    service.get_current_datetime = lambda: "2026-06-21 09:00:00"

    output = service._transform_rank_sum_dataframe(
        pd.DataFrame([_rank_sum_source_row()]), reference_code="CU"
    )

    assert list(output["RANK_TYPE"]) == ["top5", "top10", "top15", "top20"]
    first = output.iloc[0].to_dict()
    assert first["REFERENCE_CODE"] == "CU"
    assert first["REFERENCE_NAME"] == "CU2607"
    assert first["BASEDATE"] == "2026-06-18"
    assert first["VARIETY_CODE"] == "CU2607"
    assert first["VARIETY_NAME"] == "CU"
    assert first["RANK_NUM"] == 5
    assert first["TOTAL_VOL"] == 500
    assert first["TOTAL_LONG_POSITION"] == 1000
    assert first["TOTAL_SHORT_POSITION"] == 1500
    assert first["VOL_CHANGE"] == 5
    assert first["LONG_POSITION_CHANGE"] == 10
    assert first["SHORT_POSITION_CHANGE"] == 15


def test_run_without_parameters_uses_bounded_recent_product_symbols():
    service = object.__new__(FuturesRankSumDaily)
    service.logger = _Logger()
    service.table_name = "FUTURES_RANK_SUM_DAILY"
    service.get_future_symbol_list = lambda: ["a", "a2507", "ag", "cu"]
    service.get_latest_date = lambda *_args, **_kwargs: None
    service.get_current_date = lambda: "2026-06-21"
    service.get_current_datetime = lambda: "2026-06-21 09:00:00"
    service.get_uuid = lambda: "RID"

    calls = []

    def fake_fetch_ak_data(function_name, **kwargs):
        calls.append((function_name, kwargs))
        if kwargs["vars_list"] == ["AG"]:
            return pd.DataFrame([_rank_sum_source_row(symbol="AG2608", variety="AG")])
        return pd.DataFrame()

    saved = {}
    service.fetch_ak_data = fake_fetch_ak_data
    service.save_data = lambda **kwargs: saved.update(kwargs)

    service.run()

    assert [call[1]["vars_list"] for call in calls] == [["A"], ["AG"], ["CU"]]
    assert all(call[1]["start_day"] == "20260522" for call in calls)
    assert all(call[1]["end_day"] == "20260621" for call in calls)
    assert saved["table_name"] == "FUTURES_RANK_SUM_DAILY"
    assert saved["unique_keys"] == ["BASEDATE", "VARIETY_CODE", "RANK_TYPE"]
    assert len(saved["df"]) == 4
