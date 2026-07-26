import pandas as pd

from app.data_fetch.scripts.futures.weekly.warehouse_receipt_czce import (
    FuturesCzceWarehouseReceipt,
)


class _Logger:
    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass

    def debug(self, *_args, **_kwargs):
        pass


def test_run_defaults_to_recent_window_and_current_akshare_function():
    service = object.__new__(FuturesCzceWarehouseReceipt)
    service.logger = _Logger()
    service.table_name = "FUTURES_CZCE_WAREHOUSE_RECEIPT"
    service.table_exists = lambda _table_name: True
    service.create_table = lambda _sql: None
    service.connect_db = lambda: None
    service.disconnect_db = lambda: None
    service.get_current_date = lambda: "2026-06-21"
    service.get_latest_date = lambda _table_name: None
    service.get_current_datetime = lambda: "2026-06-21 09:00:00"
    service.get_uuid = lambda: "RID"

    trading_day_args = {}

    def fake_get_trading_day_list(start_date, end_date):
        trading_day_args["start_date"] = start_date
        trading_day_args["end_date"] = end_date
        return ["2026-06-18"]

    service.get_trading_day_list = fake_get_trading_day_list

    calls = []

    def fake_fetch_ak_data(function_name, date):
        calls.append((function_name, date))
        return {
            "SR": pd.DataFrame(
                [
                    {
                        "仓库编号": "0103",
                        "仓库简称": "藁城永安",
                        "年度": "2526",
                        "等级": "1",
                        "品牌": "佰惠生",
                        "仓单数量": 900,
                        "当日增减": 0,
                        "有效预报": 0,
                        "升贴水": 60,
                    }
                ]
            )
        }

    saved = {}
    service.fetch_ak_data = fake_fetch_ak_data
    service.save_data = lambda df, table_name: saved.update({"df": df, "table_name": table_name})

    output = service.run()

    assert trading_day_args == {"start_date": "2026-06-14", "end_date": "2026-06-21"}
    assert calls == [("futures_warehouse_receipt_czce", "20260618")]
    assert saved["table_name"] == "FUTURES_CZCE_WAREHOUSE_RECEIPT"
    assert saved["df"].iloc[0]["PRODUCT_CODE"] == "SR"
    assert saved["df"].iloc[0]["RECEIPT_VOLUME"] == 900
    assert len(output) == 1
