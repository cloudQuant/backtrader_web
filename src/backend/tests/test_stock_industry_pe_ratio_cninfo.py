import pandas as pd

from app.data_fetch.scripts.stocks.weekly.stock_industry_pe_ratio_cninfo import (
    StockIndustryPeRatioCninfo,
)


def test_candidate_dates_respects_explicit_date():
    assert StockIndustryPeRatioCninfo._candidate_dates("2026-06-18") == ["20260618"]


def test_normalize_pe_data_maps_full_cninfo_schema_and_stable_id():
    raw = pd.DataFrame(
        [
            {
                "变动日期": "2026-06-18",
                "行业分类": "国证行业分类标准2019",
                "行业层级": 1,
                "行业编码": "C01",
                "行业名称": "能源",
                "公司数量": 82,
                "纳入计算公司数量": 58,
                "总市值-静态": 41785.7942,
                "净利润-静态": 2802.8453,
                "静态市盈率-加权平均": 14.91,
                "静态市盈率-中位数": 32.59,
                "静态市盈率-算术平均": 91.75,
            }
        ]
    )

    first = StockIndustryPeRatioCninfo.normalize_pe_data(raw)
    second = StockIndustryPeRatioCninfo.normalize_pe_data(raw)

    assert list(first.columns) == [
        "R_ID",
        "TRADE_DATE",
        "INDUSTRY_CATEGORY",
        "INDUSTRY_LEVEL",
        "INDUSTRY_CODE",
        "INDUSTRY_NAME",
        "COMPANY_COUNT",
        "CALC_COMPANY_COUNT",
        "TOTAL_MARKET_VALUE_STATIC",
        "NET_PROFIT_STATIC",
        "PE_WEIGHTED_STATIC",
        "PE_MEDIAN_STATIC",
        "PE_AVG_STATIC",
        "DATA_SOURCE",
    ]
    assert first.iloc[0]["R_ID"] == second.iloc[0]["R_ID"]
    assert first.iloc[0]["TRADE_DATE"] == pd.Timestamp("2026-06-18").date()
    assert first.iloc[0]["INDUSTRY_CODE"] == "C01"
    assert first.iloc[0]["PE_WEIGHTED_STATIC"] == 14.91
