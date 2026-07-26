import pandas as pd

from app.data_fetch.scripts.funds.weekly.fund_fee_em import FundFeeEm


def test_normalize_fee_frame_preserves_multi_column_status_rows():
    raw = pd.DataFrame([["开放申购", "开放赎回", "T+1", None, None, None]])

    normalized = FundFeeEm.normalize_fee_frame(raw, "交易状态")

    assert list(normalized.columns) == [
        "condition",
        "term",
        "original_rate",
        "promotion_rate",
    ]
    assert normalized.iloc[0].to_dict() == {
        "condition": "开放申购",
        "term": None,
        "original_rate": "开放赎回 | T+1",
        "promotion_rate": None,
    }


def test_normalize_fee_frame_handles_two_column_redemption_rows():
    raw = pd.DataFrame([["小于7天", "1.50%"]])

    normalized = FundFeeEm.normalize_fee_frame(raw, "赎回费率")

    assert normalized.iloc[0].to_dict() == {
        "condition": "小于7天",
        "term": None,
        "original_rate": "1.50%",
        "promotion_rate": None,
    }


def test_normalize_fee_frame_limits_rate_text_to_table_width():
    raw = pd.DataFrame([["状态", "x" * 80]])

    normalized = FundFeeEm.normalize_fee_frame(raw, "交易状态")

    assert normalized.iloc[0]["original_rate"] == "x" * 50
