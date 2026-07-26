import pandas as pd

from app.data_fetch.scripts.funds.daily.fund_em_hk_rank import FundEmHkRank


def test_normalize_rank_data_maps_hong_kong_fund_columns():
    raw = pd.DataFrame(
        [
            {
                "基金代码": "968063",
                "基金简称": "摩根太平洋科技美元",
                "日期": "2026-06-17",
                "单位净值": 28.44,
            }
        ]
    )

    normalized = FundEmHkRank.normalize_rank_data(raw)

    assert list(normalized.columns) == ["symbol", "name", "data_date"]
    assert normalized.iloc[0].to_dict() == {
        "symbol": "968063",
        "name": "摩根太平洋科技美元",
        "data_date": pd.Timestamp("2026-06-17").date(),
    }


def test_normalize_rank_data_returns_empty_for_unexpected_schema():
    normalized = FundEmHkRank.normalize_rank_data(pd.DataFrame({"foo": ["bar"]}))

    assert normalized.empty
    assert list(normalized.columns) == ["symbol", "name", "data_date"]
