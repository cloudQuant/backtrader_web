from datetime import date

from app.data_fetch.scripts.common.daily.nlp_answer import NlpAnswer
from app.data_fetch.scripts.common.daily.nlp_ownthink import NlpOwnthink
from app.data_fetch.scripts.common.weekly.match_main_contract import MatchMainContract


def test_nlp_ownthink_normalizes_string_result():
    normalized = NlpOwnthink.normalize_scalar_result(
        "人工智能[计算机科学的一个分支]",
        source_symbol="人工智能",
        data_date=date(2026, 6, 21),
    )

    assert normalized.iloc[0].to_dict() == {
        "symbol": "人工智能",
        "name": "人工智能[计算机科学的一个分支]",
        "data_date": date(2026, 6, 21),
    }


def test_nlp_answer_normalizes_string_result():
    normalized = NlpAnswer.normalize_scalar_result(
        "人工智能是计算机科学的一个分支",
        source_symbol="人工智能",
        data_date=date(2026, 6, 21),
    )

    assert normalized.iloc[0]["name"] == "人工智能是计算机科学的一个分支"


def test_match_main_contract_normalizes_string_result():
    normalized = MatchMainContract.normalize_scalar_result(
        "IF2609,TF2609", source_symbol="cffex", data_date=date(2026, 6, 21)
    )

    assert normalized.iloc[0].to_dict() == {
        "symbol": "cffex",
        "name": "IF2609,TF2609",
        "data_date": date(2026, 6, 21),
    }
