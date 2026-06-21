from datetime import date

import pandas as pd

from app.data_fetch.scripts.funds.weekly.fund_manager_em import FundManagerEm


def test_normalize_manager_data_maps_and_cleans_eastmoney_columns():
    raw = pd.DataFrame(
        [
            {
                "序号": 1,
                "姓名": "艾邦妮",
                "所属公司": "华夏基金",
                "现任基金代码": "001924",
                "现任基金": "华夏国企改革混合",
                "累计从业时间": "3年290天",
                "现任基金资产总规模": "2.85亿元",
                "现任基金最佳回报": "50.53%",
            },
            {
                "序号": 2,
                "姓名": "测试经理",
                "所属公司": "测试基金",
                "现任基金代码": "000001",
                "现任基金": "测试基金A",
                "累计从业时间": "--",
                "现任基金资产总规模": "--",
                "现任基金最佳回报": "--",
            },
        ]
    )

    normalized = FundManagerEm.normalize_manager_data(raw, update_date=date(2026, 6, 21))

    assert list(normalized.columns) == [
        "R_ID",
        "MANAGER_ID",
        "MANAGER_NAME",
        "COMPANY",
        "FUND_CODE",
        "FUND_NAME",
        "WORK_DAYS",
        "TOTAL_ASSETS",
        "BEST_RETURN",
        "UPDATE_DATE",
    ]
    assert normalized.iloc[0].to_dict() == {
        "R_ID": "FME_1_001924",
        "MANAGER_ID": 1,
        "MANAGER_NAME": "艾邦妮",
        "COMPANY": "华夏基金",
        "FUND_CODE": "001924",
        "FUND_NAME": "华夏国企改革混合",
        "WORK_DAYS": 1385,
        "TOTAL_ASSETS": 2.85,
        "BEST_RETURN": 50.53,
        "UPDATE_DATE": date(2026, 6, 21),
    }
    assert pd.isna(normalized.iloc[1]["WORK_DAYS"])
    assert pd.isna(normalized.iloc[1]["TOTAL_ASSETS"])
    assert pd.isna(normalized.iloc[1]["BEST_RETURN"])
