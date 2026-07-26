from app.data_fetch.scripts.common.daily.get_roll_yield import GetRollYield


class _Logger:
    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass


def test_roll_yield_tuple_is_normalized_to_dataframe():
    df = GetRollYield._normalize_roll_yield_result(
        (-0.01, "CU2607", "CU2608"), var="CU", date="20260618"
    )

    assert df.to_dict("records") == [
        {
            "symbol": "CU",
            "name": "CU2607/CU2608",
            "data_date": "2026-06-18",
            "roll_yield": -0.01,
            "near_by": "CU2607",
            "deferred": "CU2608",
            "var": "CU",
        }
    ]


def test_fetch_data_defaults_to_recent_available_trade_date():
    service = object.__new__(GetRollYield)
    service.logger = _Logger()
    service.table_name = "GET_ROLL_YIELD"
    service.create_table_if_not_exists = lambda *_args, **_kwargs: None
    service.get_current_date = lambda: "2026-06-21"

    calls = []

    def fake_fetch_ak_data(function_name, **kwargs):
        calls.append((function_name, kwargs.copy()))
        if kwargs["date"] == "20260618":
            return (-0.01, "CU2607", "CU2608")
        return None

    saved = {}
    service.fetch_ak_data = fake_fetch_ak_data
    service.save_data = lambda df, table_name, ignore_duplicates=True: saved.update(
        {"df": df, "table_name": table_name, "ignore_duplicates": ignore_duplicates}
    )

    output = service.fetch_data()

    assert [call[1]["date"] for call in calls] == [
        "20260621",
        "20260620",
        "20260619",
        "20260618",
    ]
    assert all(call[1]["var"] == "CU" for call in calls)
    assert saved["table_name"] == "GET_ROLL_YIELD"
    assert saved["ignore_duplicates"] is True
    assert output.iloc[0]["near_by"] == "CU2607"
