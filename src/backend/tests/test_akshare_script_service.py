from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from app.data_fetch.scripts.common.daily.article_rlab_rv import ArticleRlabRv
from app.data_fetch.scripts.common.daily.get_receipt import GetReceipt
from app.data_fetch.scripts.common.daily.get_roll_yield import GetRollYield
from app.data_fetch.scripts.common.daily.migration_area_baidu import MigrationAreaBaidu
from app.data_fetch.scripts.common.weekly.get_cffex_rank_table import GetCffexRankTable
from app.data_fetch.scripts.common.weekly.get_rank_table_czce import GetRankTableCzce
from app.data_fetch.scripts.common.weekly.get_shfe_rank_table import GetShfeRankTable
from app.data_fetch.scripts.funds.daily.option_current_em import OptionCurrentEm
from app.data_fetch.scripts.funds.hourly.option_minute_em import OptionMinuteEm
from app.data_fetch.scripts.funds.hourly.option_sse_minute_sina import OptionSseMinuteSina
from app.data_fetch.scripts.funds.weekly.fund_individual_analysis_xq import FundAnalysisXq
from app.data_fetch.scripts.funds.weekly.fund_scale_open_sina import FundScaleOpenSina
from app.data_fetch.scripts.funds.weekly.fund_value_estimation_em import FundValueEstimationEm
from app.data_fetch.scripts.funds.weekly.option_hist_czce import OptionHistCzce
from app.data_fetch.scripts.funds.weekly.option_hist_shfe import OptionHistShfe
from app.data_fetch.scripts.futures.daily.futures_hold_pos_sina import FuturesHoldPosSina
from app.data_fetch.scripts.futures.hourly.futures_foreign_commodity_realtime import (
    FuturesForeignCommodityRealtime,
)
from app.data_fetch.scripts.futures.weekly._dict_result import flatten_dict_result
from app.data_fetch.scripts.futures.weekly.daily_market_data import FuturesDailyMarket
from app.data_fetch.scripts.futures.weekly.futures_gfex_position_rank import (
    FuturesGfexPositionRank,
)
from app.data_fetch.scripts.futures.weekly.futures_gfex_warehouse_receipt import (
    FuturesGfexWarehouseReceipt,
)
from app.data_fetch.scripts.futures.weekly.futures_shfe_warehouse_receipt import (
    FuturesShfeWarehouseReceipt,
)
from app.data_fetch.scripts.futures.weekly.futures_warehouse_receipt_czce import (
    FuturesWarehouseReceiptCzce,
)
from app.data_fetch.scripts.futures.weekly.member_position_rank import (
    FuturesMemberPositionRank,
)
from app.data_fetch.scripts.indexs.daily.index_zh_a_hist import IndexZhAHist
from app.data_fetch.scripts.stocks.daily.stock_bid_ask_em import StockBidAskEm
from app.data_fetch.scripts.stocks.daily.stock_dzjy_mrtj import StockDzjyMrtj
from app.data_fetch.scripts.stocks.daily.stock_esg_hz_sina import StockEsgHzSina
from app.data_fetch.scripts.stocks.daily.stock_esg_rate_sina import StockEsgRateSina
from app.data_fetch.scripts.stocks.daily.stock_esg_zd_sina import StockEsgZdSina
from app.data_fetch.scripts.stocks.daily.stock_gdfx_free_holding_analyse_em import (
    StockGdfxFreeHoldingAnalyseEm,
)
from app.data_fetch.scripts.stocks.daily.stock_gdfx_free_holding_change_em import (
    StockGdfxFreeHoldingChangeEm,
)
from app.data_fetch.scripts.stocks.daily.stock_gdfx_free_holding_statistics_em import (
    StockGdfxFreeHoldingStatisticsEm,
)
from app.data_fetch.scripts.stocks.daily.stock_gdfx_free_holding_teamwork_em import (
    StockGdfxFreeHoldingTeamworkEm,
)
from app.data_fetch.scripts.stocks.daily.stock_gdfx_holding_statistics_em import (
    StockGdfxHoldingStatisticsEm,
)
from app.data_fetch.scripts.stocks.daily.stock_hk_hot_rank_em import StockHkHotRankEm
from app.data_fetch.scripts.stocks.daily.stock_hot_follow_xq import StockHotFollowXq
from app.data_fetch.scripts.stocks.daily.stock_hot_rank_em import StockHotRankEm
from app.data_fetch.scripts.stocks.daily.stock_hot_up_em import StockHotUpEm
from app.data_fetch.scripts.stocks.daily.stock_hsgt_board_rank_em import (
    StockHsgtBoardRankEm,
)
from app.data_fetch.scripts.stocks.daily.stock_hsgt_individual_detail_em import (
    StockHsgtIndividualDetailEm,
)
from app.data_fetch.scripts.stocks.daily.stock_hsgt_institution_statistics_em import (
    StockHsgtInstitutionStatisticsEm,
)
from app.data_fetch.scripts.stocks.daily.stock_individual_fund_flow import (
    StockIndividualFundFlow,
)
from app.data_fetch.scripts.stocks.daily.stock_individual_info_em import StockIndividualInfoEm
from app.data_fetch.scripts.stocks.daily.stock_intraday_sina import StockIntradaySina
from app.data_fetch.scripts.stocks.daily.stock_jgdy_detail_em import StockJgdyDetailEm
from app.data_fetch.scripts.stocks.daily.stock_jgdy_tj_em import StockJgdyTjEm
from app.data_fetch.scripts.stocks.daily.stock_lh_yyb_capital import StockLhYybCapital
from app.data_fetch.scripts.stocks.daily.stock_lh_yyb_most import StockLhYybMost
from app.data_fetch.scripts.stocks.daily.stock_main_fund_flow import StockMainFundFlow
from app.data_fetch.scripts.stocks.daily.stock_market_fund_flow import StockMarketFundFlow
from app.data_fetch.scripts.stocks.daily.stock_repurchase_em import StockRepurchaseEm
from app.data_fetch.scripts.stocks.daily.stock_sse_deal_daily import StockSseDealDaily
from app.data_fetch.scripts.stocks.daily.stock_sy_yq_em import StockSyYqEm
from app.data_fetch.scripts.stocks.daily.stock_xgsr_ths import StockXgsrThs
from app.data_fetch.scripts.stocks.daily.stock_yysj_em import StockYysjEm
from app.data_fetch.scripts.stocks.daily.stock_zh_a_hist import StockZhAHist
from app.data_fetch.scripts.stocks.daily.stock_zh_vote_baidu import StockZhVoteBaidu
from app.data_fetch.scripts.stocks.hourly.stock_board_industry_hist_min_em import (
    StockBoardIndustryHistMinEm,
)
from app.data_fetch.scripts.stocks.hourly.stock_us_hist_min_em import StockUsHistMinEm
from app.data_fetch.scripts.stocks.hourly.stock_us_spot_em import StockUsSpotEm
from app.data_fetch.scripts.stocks.weekly.stock_concept_fund_flow_hist import (
    StockConceptFundFlowHist,
)
from app.data_fetch.scripts.stocks.weekly.stock_individual_fund_flow_rank import (
    StockIndividualFundFlowRank,
)
from app.data_fetch.scripts.stocks.weekly.stock_industry_clf_hist_sw import (
    StockIndustryClfHistSw,
)
from app.data_fetch.scripts.stocks.weekly.stock_rank_cxd_ths import StockRankCxdThs
from app.data_fetch.scripts.stocks.weekly.stock_sector_fund_flow_hist import (
    StockSectorFundFlowHist,
)
from app.data_fetch.scripts.stocks.weekly.stock_sns_sseinfo import StockSnsSseinfo
from app.services.akshare import script as script_module
from app.services.akshare.data import AkshareDataService
from app.services.akshare.script import AkshareScriptService
from scripts.backfill_market_history import (
    CacheCandidate,
    _fund_sina_symbol,
    _history_cache_payloads,
)


def test_default_script_root_resolves_to_app_data_fetch_scripts(monkeypatch):
    monkeypatch.setattr(
        script_module.settings,
        "AKSHARE_SCRIPT_ROOT",
        "app/data_fetch/scripts",
    )

    service = AkshareScriptService.__new__(AkshareScriptService)

    expected = Path(__file__).resolve().parents[1] / "app" / "data_fetch" / "scripts"
    assert service._script_root() == expected


def test_akshare_catalog_endpoint_has_safe_default_parameters():
    script = SimpleNamespace(script_id="akshare_catalog_endpoint")

    params = AkshareScriptService._apply_safe_default_parameters(script.script_id, {})

    assert params["endpoint_name"] == "air_city_table"
    assert params["call_timeout"] == 30


def test_market_history_cache_payloads_normalize_rows():
    candidate = CacheCandidate(
        asset_type="fund",
        symbol="510300",
        name="沪深300ETF",
        market="CN",
        history_rows=0,
        latest_history_date=None,
    )

    payloads = _history_cache_payloads(
        candidate,
        "daily",
        [
            {
                "date": "2026-07-03",
                "open": "4.1",
                "high": "4.2",
                "low": "4.0",
                "close": "4.15",
                "volume": "1000",
                "change_pct": "1.2",
                "turnover_rate": float("nan"),
            },
            {"open": 1.0},
        ],
    )

    assert len(payloads) == 1
    assert payloads[0]["r_id"] == "fund|510300|daily|2026-07-03"
    assert payloads[0]["symbol"] == "510300"
    assert payloads[0]["name"] == "沪深300ETF"
    assert payloads[0]["open"] == 4.1
    assert payloads[0]["volume"] == 1000
    assert payloads[0]["change_pct"] == 1.2
    assert payloads[0]["turnover_rate"] is None
    assert payloads[0]["provider"] == "akshare"


def test_fund_sina_symbol_adds_exchange_prefix():
    assert _fund_sina_symbol("513090") == "sh513090"
    assert _fund_sina_symbol("159707") == "sz159707"
    assert _fund_sina_symbol("SH510300") == "sh510300"
    assert _fund_sina_symbol("510300.SH") == "sh510300"


def test_bond_info_cm_has_page_limited_default():
    params = AkshareScriptService._apply_safe_default_parameters("bond_info_cm", {})

    assert params["max_pages"] == 1
    assert params["_call_timeout"] >= 90


def test_akshare_catalog_endpoint_defaults_do_not_override_explicit_parameters():
    script = SimpleNamespace(script_id="akshare_catalog_endpoint")

    params = AkshareScriptService._apply_safe_default_parameters(
        script.script_id,
        {"endpoint_name": "tool_trade_date_hist_sina"},
    )

    assert params["endpoint_name"] == "tool_trade_date_hist_sina"
    assert params["call_timeout"] == 30


def test_existing_legacy_table_name_preserves_case():
    assert (
        AkshareDataService.normalize_existing_table_name("STOCK_ZT_POOL_EM")
        == "STOCK_ZT_POOL_EM"
    )


def test_legacy_script_target_table_preserves_case():
    script = SimpleNamespace(target_table="STOCK_ZH_A_DAILY")

    assert AkshareScriptService._legacy_table_name(script) == "STOCK_ZH_A_DAILY"


def test_legacy_callable_table_name_preserves_case():
    class LegacyScript:
        table_name = "FUND_MANAGER_EM"

        def save_data(self):
            raise AssertionError("not called")

        def fetch_data(self):
            raise AssertionError("not called")

    assert (
        AkshareScriptService._legacy_callable_table_name(LegacyScript().fetch_data)
        == "FUND_MANAGER_EM"
    )


def test_empty_completion_raises_when_target_table_has_no_rows():
    try:
        AkshareScriptService._raise_if_empty_completion(
            script_id="stock_zh_a_hist",
            table_name="STOCK_ZH_A_HIST",
            rows_before=0,
            rows_after=0,
            result=pd.DataFrame(),
        )
    except RuntimeError as exc:
        assert "returned no data" in str(exc)
        assert "STOCK_ZH_A_HIST" in str(exc)
    else:
        raise AssertionError("empty completion should fail when target table is empty")


def test_empty_completion_allows_existing_table_rows():
    AkshareScriptService._raise_if_empty_completion(
        script_id="stock_zh_a_hist",
        table_name="STOCK_ZH_A_HIST",
        rows_before=100,
        rows_after=100,
        result=pd.DataFrame(),
    )


def test_empty_completion_detects_empty_records_payload():
    assert AkshareScriptService._result_is_empty_marker({"records": []})
    assert not AkshareScriptService._result_is_empty_marker({"records": [{"x": 1}]})


def test_empty_completion_raises_when_truthy_result_left_target_empty():
    try:
        AkshareScriptService._raise_if_empty_completion(
            script_id="fund_aum_hist_em",
            table_name="FUND_AUM_HIST_EM",
            rows_before=0,
            rows_after=0,
            result=True,
        )
    except RuntimeError as exc:
        assert "left no rows" in str(exc)
        assert "FUND_AUM_HIST_EM" in str(exc)
    else:
        raise AssertionError("truthy result should fail when target table is empty")


def test_empty_completion_allows_catalog_endpoint_multi_target_script():
    AkshareScriptService._raise_if_empty_completion(
        script_id="akshare_catalog_endpoint",
        table_name="akshare_catalog_endpoint",
        rows_before=0,
        rows_after=0,
        result=True,
    )


def test_index_zh_a_hist_wrapper_cleans_by_normalized_data_date(monkeypatch):
    script = IndexZhAHist()
    deleted = []
    saved = []

    def fake_fetch_ak_data(function_name, **kwargs):
        assert function_name == "index_zh_a_hist"
        return pd.DataFrame(
            {
                "日期": ["2026-06-19", "2026-06-19", "2026-06-22"],
                "收盘": [1.0, 1.0, 2.0],
            }
        )

    monkeypatch.setattr(script, "fetch_ak_data", fake_fetch_ak_data)
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "delete_data",
        lambda table, conditions: deleted.append((table, conditions)) or True,
    )
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data(symbol="000300", start_date="20260619", end_date="20260622")

    assert deleted == [
        ("INDEX_ZH_A_HIST", {"data_date": "2026-06-19"}),
        ("INDEX_ZH_A_HIST", {"data_date": "2026-06-22"}),
    ]
    assert len(saved) == 1
    assert "data_date" in saved[0].columns
    assert len(result) == 2


def test_long_fund_scripts_have_bounded_default_codes():
    for script_id in ("etf_minute_hist_em", "fund_detail_info", "lof_minute_hist_em"):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["max_codes"] == 20


def test_recoverable_cross_asset_history_scripts_have_short_window_defaults():
    bond_params = AkshareScriptService._apply_safe_default_parameters(
        "bond_buy_back_hist_em", {}
    )
    bond_spot_params = AkshareScriptService._apply_safe_default_parameters(
        "bond_zh_hs_spot", {}
    )
    bond_detail_params = AkshareScriptService._apply_safe_default_parameters(
        "bond_info_detail_cm", {}
    )
    etf_params = AkshareScriptService._apply_safe_default_parameters("fund_etf_hist_em", {})
    etf_min_params = AkshareScriptService._apply_safe_default_parameters(
        "fund_etf_hist_min_em", {}
    )
    lof_min_params = AkshareScriptService._apply_safe_default_parameters(
        "fund_lof_hist_min_em", {}
    )
    fund_hold_params = AkshareScriptService._apply_safe_default_parameters(
        "fund_portfolio_hold_em", {}
    )
    index_params = AkshareScriptService._apply_safe_default_parameters("index_zh_a_hist", {})

    assert bond_params["symbol"] == "204001"
    assert bond_params["_call_timeout"] == 60
    assert bond_spot_params["start_page"] == "1"
    assert bond_spot_params["end_page"] == "1"
    assert bond_detail_params["symbol"] == "淮安农商行CDSD2022021012"
    assert etf_params["symbol"] == "510300"
    assert etf_params["period"] == "daily"
    assert etf_params["start_date"].isdigit()
    assert etf_params["end_date"].isdigit()
    assert etf_min_params["symbol"] == "510300"
    assert etf_min_params["start_date"] < etf_min_params["end_date"]
    assert lof_min_params["symbol"] == "166009"
    assert lof_min_params["period"] == "5"
    assert fund_hold_params["fund_code"] == "000001"
    assert fund_hold_params["year"] == "2024"
    assert index_params["symbol"] == "000300"
    assert index_params["period"] == "daily"


def test_recoverable_common_macro_scripts_have_defaults():
    bank_params = AkshareScriptService._apply_safe_default_parameters(
        "bank_fjcf_table_detail", {}
    )

    assert bank_params["page"] == 1
    assert bank_params["item"] == "分局本级"
    assert bank_params["begin"] == 1
    assert bank_params["_call_timeout"] == 60

    for script_id in (
        "macro_china_trade_balance",
        "macro_usa_non_farm",
        "macro_usa_trade_balance",
        "macro_usa_unemployment_rate",
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["_call_timeout"] == 60


def test_recoverable_common_static_scripts_have_defaults():
    air_params = AkshareScriptService._apply_safe_default_parameters(
        "air_quality_watch_point", {}
    )
    assert air_params["city"] == "北京"
    assert air_params["start_date"] == "20220408"
    assert air_params["end_date"] == "20220409"
    assert air_params["_call_timeout"] == 60

    for script_id in (
        "amac_aoin_info",
        "migration_area_baidu",
        "spot_hog_three_way_soozhu",
        "spot_hog_year_trend_soozhu",
        "spot_mixed_feed_soozhu",
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})
        assert params["_call_timeout"] == 60

    for script_id in (
        "amac_fund_info",
        "amac_manager_classify_info",
        "amac_manager_info",
        "amac_member_info",
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})
        assert params["start_page"] == "1"
        assert params["end_page"] == "1"
        assert params["_call_timeout"] == 60

    for script_id in (
        "amac_fund_abs",
        "amac_fund_account_info",
        "amac_fund_sub_info",
        "amac_futures_info",
        "amac_manager_cancelled_info",
        "amac_member_sub_info",
        "amac_securities_info",
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})
        assert params["max_pages"] == 1
        assert params["_call_timeout"] == 60

    article_params = AkshareScriptService._apply_safe_default_parameters(
        "article_rlab_rv", {}
    )
    assert article_params["symbol"] == "39693"
    assert article_params["_call_timeout"] == 60

    us_stock_params = AkshareScriptService._apply_safe_default_parameters(
        "get_us_stock_name", {}
    )
    assert us_stock_params["max_pages"] == 1
    assert us_stock_params["_call_timeout"] == 60

    hurun_params = AkshareScriptService._apply_safe_default_parameters("hurun_rank", {})
    assert hurun_params["indicator"] == "胡润百富榜"
    assert hurun_params["year"] == "2023"
    assert hurun_params["_call_timeout"] == 60

    migration_params = AkshareScriptService._apply_safe_default_parameters(
        "migration_area_baidu", {}
    )
    assert migration_params["area"] == "重庆市"
    assert migration_params["indicator"] == "move_in"
    assert migration_params["date"] == "20240601"
    assert migration_params["_call_timeout"] == 60


def test_recoverable_common_exchange_rank_scripts_have_defaults_and_nonunique_indexes():
    cffex_params = AkshareScriptService._apply_safe_default_parameters(
        "get_cffex_rank_table", {}
    )
    czce_params = AkshareScriptService._apply_safe_default_parameters(
        "get_rank_table_czce", {}
    )
    shfe_params = AkshareScriptService._apply_safe_default_parameters(
        "get_shfe_rank_table", {}
    )

    assert cffex_params["date"] == "20240223"
    assert czce_params["date"] == "20240223"
    assert shfe_params["date"] == "20240223"
    assert shfe_params["vars_list"] == ["CU", "AL"]

    receipt_params = AkshareScriptService._apply_safe_default_parameters("get_receipt", {})
    roll_params = AkshareScriptService._apply_safe_default_parameters("get_roll_yield", {})
    assert receipt_params["start_date"] == "20240223"
    assert receipt_params["end_date"] == "20240223"
    assert receipt_params["vars_list"] == ["CU", "AL"]
    assert receipt_params["_call_timeout"] == 60
    assert roll_params["date"] == "20240223"
    assert roll_params["var"] == "CU"
    assert roll_params["_call_timeout"] == 60

    for script in (GetCffexRankTable(), GetRankTableCzce(), GetShfeRankTable()):
        assert "UNIQUE KEY uk_symbol_date" not in script.create_table_sql
        assert "INDEX idx_symbol_date (`symbol`, `data_date`)" in script.create_table_sql


def test_get_receipt_maps_var_and_date_columns(monkeypatch):
    script = GetReceipt()
    saved = []

    monkeypatch.setattr(
        script,
        "fetch_ak_data",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "var": ["CU", "AL"],
                "receipt": [1, 2],
                "receipt_chg": [0, 1],
                "date": ["2024-02-23", "2024-02-23"],
            }
        ),
    )
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data()

    assert result["symbol"].tolist() == ["CU", "AL"]
    assert result["data_date"].astype(str).tolist() == ["2024-02-23", "2024-02-23"]
    assert len(saved) == 1


def test_get_roll_yield_tuple_result_is_normalized(monkeypatch):
    script = GetRollYield()
    saved = []

    monkeypatch.setattr(script, "fetch_ak_data", lambda *args, **kwargs: (0.01, "CU2404", "CU2405"))
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data(date="20240223", var="CU")

    assert result["symbol"].tolist() == ["CU"]
    assert result["data_date"].astype(str).tolist() == ["2024-02-23"]
    assert result["roll_yield"].tolist() == [0.01]
    assert len(saved) == 1


def test_article_rlab_rv_normalizes_series_result(monkeypatch):
    script = ArticleRlabRv()
    saved = []

    values = pd.Series(
        [0.1, 0.2],
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
        name="RV",
    )
    values.index.name = "date"

    monkeypatch.setattr(script, "fetch_ak_data", lambda *args, **kwargs: values)
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data(symbol="39693")

    assert len(result) == 2
    assert result["symbol"].tolist() == ["39693", "39693"]
    assert result["data_date"].astype(str).tolist() == ["2024-01-02", "2024-01-03"]
    assert result["RV"].tolist() == [0.1, 0.2]
    assert len(saved) == 1


def test_migration_area_baidu_maps_city_and_date(monkeypatch):
    script = MigrationAreaBaidu()
    deleted = []
    saved = []

    monkeypatch.setattr(
        script,
        "fetch_ak_data",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "city_name": ["成都市", "广安市"],
                "province_name": ["四川省", "四川省"],
                "value": ["14.43", "7.84"],
            }
        ),
    )
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "delete_data",
        lambda table, conditions: deleted.append((table, conditions)) or True,
    )
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data(area="重庆市", indicator="move_in", date="20240601")

    assert result["symbol"].tolist() == ["四川省/成都市", "四川省/广安市"]
    assert result["name"].tolist() == ["成都市", "广安市"]
    assert result["data_date"].astype(str).tolist() == ["2024-06-01", "2024-06-01"]
    assert result["area"].tolist() == ["重庆市", "重庆市"]
    assert result["indicator"].tolist() == ["move_in", "move_in"]
    assert result["value"].tolist() == [14.43, 7.84]
    assert deleted == [
        (
            "MIGRATION_AREA_BAIDU",
            {"area": "重庆市", "indicator": "move_in", "data_date": "2024-06-01"},
        )
    ]
    assert "UNIQUE KEY uk_symbol_date" not in script.create_table_sql
    assert "INDEX idx_symbol_date (`symbol`, `data_date`)" in script.create_table_sql
    assert len(saved) == 1


def test_recoverable_option_and_stock_gap_scripts_have_defaults():
    czce_params = AkshareScriptService._apply_safe_default_parameters("option_hist_czce", {})
    shfe_params = AkshareScriptService._apply_safe_default_parameters("option_hist_shfe", {})
    option_current_params = AkshareScriptService._apply_safe_default_parameters(
        "option_current_em", {}
    )
    industry_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_industry_clf_hist_sw", {}
    )
    sse_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_sse_deal_daily", {}
    )
    dzjy_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_dzjy_mrtj", {}
    )
    vote_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_zh_vote_baidu", {}
    )
    hot_rank_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hot_rank_em", {}
    )

    assert czce_params["symbol"] == "白糖期权"
    assert czce_params["trade_date"] == "20191017"
    assert czce_params["_call_timeout"] == 60
    assert shfe_params["symbol"] == "铝期权"
    assert shfe_params["trade_date"] == "20250418"
    assert shfe_params["_call_timeout"] == 60
    assert option_current_params["max_pages"] == 1
    assert option_current_params["include_cffex"] is True
    assert option_current_params["_call_timeout"] == 60
    assert industry_params["_call_timeout"] == 60
    assert sse_params["date"] == "20241216"
    assert sse_params["_call_timeout"] == 60
    assert dzjy_params["start_date"] == "20240102"
    assert dzjy_params["end_date"] == "20240102"
    assert dzjy_params["_call_timeout"] == 60
    assert vote_params["symbol"] == "000001"
    assert vote_params["indicator"] == "指数"
    assert vote_params["_call_timeout"] == 60
    assert hot_rank_params["page_size"] == 100
    assert hot_rank_params["_call_timeout"] == 60

    industry_script = StockIndustryClfHistSw()
    assert "UNIQUE KEY uk_symbol_date" not in industry_script.create_table_sql
    assert "INDEX idx_symbol_date (`symbol`, `data_date`)" in industry_script.create_table_sql

    vote_script = StockZhVoteBaidu()
    assert "UNIQUE KEY uk_symbol_date" not in vote_script.create_table_sql
    assert "INDEX idx_symbol_date (`symbol`, `data_date`)" in vote_script.create_table_sql

    for script_id, expected_date in (
        ("fund_rating_ja", "20230331"),
        ("fund_rating_sh", "20230630"),
        ("fund_rating_zs", "20230331"),
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})
        assert params["date"] == expected_date

    announcement_params = AkshareScriptService._apply_safe_default_parameters(
        "fund_announcement_personnel_em", {}
    )
    analysis_params = AkshareScriptService._apply_safe_default_parameters(
        "fund_individual_analysis_xq", {}
    )
    portfolio_params = AkshareScriptService._apply_safe_default_parameters(
        "fund_portfolio_change_em", {}
    )
    value_params = AkshareScriptService._apply_safe_default_parameters(
        "fund_value_estimation_em", {}
    )

    assert announcement_params == {"symbol": "000001"}
    assert analysis_params == {"fund_code": "000001"}
    assert portfolio_params == {
        "fund_code": "003567",
        "indicator": "累计买入",
        "year": "2023",
    }
    assert value_params == {"fund_type": "全部"}


def test_dated_option_and_sse_wrappers_use_parameter_data_date(monkeypatch):
    def run_script(script, kwargs, expected_date):
        saved = []
        monkeypatch.setattr(
            script,
            "fetch_ak_data",
            lambda *args, **fetch_kwargs: pd.DataFrame({"value": [1, 2]}),
        )
        monkeypatch.setattr(
            script, "create_table_if_not_exists", lambda *args, **kwargs: None
        )
        monkeypatch.setattr(
            script,
            "save_data",
            lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
        )

        result = script.fetch_data(**kwargs)

        assert result["data_date"].astype(str).tolist() == [expected_date, expected_date]
        assert saved[0]["data_date"].astype(str).tolist() == [expected_date, expected_date]

    run_script(OptionHistCzce(), {"trade_date": "20191017"}, "2019-10-17")
    run_script(OptionHistShfe(), {"trade_date": "20250418"}, "2025-04-18")
    run_script(StockSseDealDaily(), {"date": "20241216"}, "2024-12-16")


def test_option_sse_minute_resolves_active_symbol_and_maps_date(monkeypatch):
    script = OptionSseMinuteSina()
    calls = []
    deleted = []
    saved = []

    def fake_fetch_ak_data(function_name, **kwargs):
        calls.append((function_name, kwargs))
        if function_name == "option_sse_codes_sina":
            return pd.DataFrame({"序号": [1], "期权代码": ["10011251"]})
        if function_name == "option_sse_minute_sina":
            return pd.DataFrame(
                {
                    "日期": ["2026-06-22", "2026-06-22"],
                    "时间": ["09:30:00", "09:31:00"],
                    "价格": [0.0, 0.391],
                }
            )
        raise AssertionError(function_name)

    monkeypatch.setattr(script, "fetch_ak_data", fake_fetch_ak_data)
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "delete_data",
        lambda table, conditions: deleted.append((table, conditions)) or True,
    )
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data(
        option_type="看涨期权",
        trade_date="202606",
        underlying="510050",
        _call_timeout=60,
    )

    assert calls == [
        (
            "option_sse_codes_sina",
            {
                "symbol": "看涨期权",
                "trade_date": "202606",
                "underlying": "510050",
                "_call_timeout": 60,
            },
        ),
        ("option_sse_minute_sina", {"symbol": "10011251", "_call_timeout": 60}),
    ]
    assert result["symbol"].tolist() == ["10011251", "10011251"]
    assert result["data_date"].astype(str).tolist() == ["2026-06-22", "2026-06-22"]
    assert deleted == [
        ("OPTION_SSE_MINUTE_SINA", {"symbol": "10011251", "data_date": "2026-06-22"})
    ]
    assert "UNIQUE KEY uk_symbol_date" not in script.create_table_sql
    assert "INDEX idx_symbol_date (`symbol`, `data_date`)" in script.create_table_sql
    assert len(saved) == 1


def test_fund_scale_open_sina_normalizes_codes_and_system_fields(monkeypatch):
    script = FundScaleOpenSina()
    inserted = []

    monkeypatch.setattr(
        script,
        "query_data",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        script,
        "insert_data",
        lambda df, table, columns: inserted.append((df.copy(), table, columns)) or True,
    )
    monkeypatch.setattr(
        script,
        "execute_sql",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "akshare.fund_scale_open_sina",
        lambda symbol: pd.DataFrame(
            {
                "基金代码": [123, "510300"],
                "基金简称": ["A", "B"],
                "单位净值": [1.0, 2.0],
                "总募集规模": [100.0, 200.0],
                "最近总份额": [10.0, 20.0],
                "成立日期": ["2020-01-01", "2021-01-01"],
                "基金经理": ["甲", "乙"],
                "更新日期": ["2026-06-18", "2026-06-18"],
            }
        ),
    )

    df = script.fetch_fund_scale("股票型基金")
    assert df["fund_code"].tolist() == ["000123", "510300"]
    assert df["r_id"].tolist() == ["FSOS_股票_000123", "FSOS_股票_510300"]

    assert script.save_fund_scale(df)
    saved_df, table, columns = inserted[0]
    assert table == "FUND_SCALE_OPEN_SINA"
    assert saved_df["is_active"].tolist() == [1, 1]
    assert saved_df["data_source"].tolist() == ["新浪财经", "新浪财经"]
    assert "is_active" in columns
    assert "data_source" in columns


def test_fund_value_estimation_maps_dynamic_trade_date_columns():
    script = FundValueEstimationEm()
    df = pd.DataFrame(
        {
            "序号": [1],
            "基金代码": ["001716"],
            "基金名称": ["工银新趋势灵活配置混合A"],
            "2026-06-22-估算数据-估算值": ["3.4891"],
            "2026-06-22-估算数据-估算增长率": ["8.93%"],
            "2026-06-22-公布数据-单位净值": ["3.2030"],
            "2026-06-22-公布数据-日增长率": ["-1.75%"],
            "估算偏差": ["10.68%"],
            "2026-06-18-单位净值": ["3.2600"],
            "FUND_TYPE": ["全部"],
        }
    )

    processed = script.process_estimation_data(df)

    assert processed["TRADE_DATE"].astype(str).tolist() == ["2026-06-22"]
    assert processed["ESTIMATED_VALUE"].tolist() == [3.4891]
    assert processed["ESTIMATED_RETURN"].tolist() == [8.93]
    assert processed["PUBLISHED_NAV"].tolist() == [3.203]
    assert processed["PUBLISHED_RETURN"].tolist() == [-1.75]
    assert processed["ESTIMATION_DEVIATION"].tolist() == ["10.68%"]


def test_fund_analysis_xq_fetches_with_bounded_timeouts(monkeypatch):
    script = FundAnalysisXq()
    calls = []

    monkeypatch.setattr(
        script,
        "fetch_ak_data",
        lambda *args, **kwargs: calls.append((args, kwargs))
        or pd.DataFrame({"周期": ["近1年"]}),
    )

    result = script.fetch_analysis_data("000001")

    assert result["FUND_CODE"].tolist() == ["000001"]
    assert calls == [
        (
            ("fund_individual_analysis_xq",),
            {"symbol": "000001", "timeout": 20, "_call_timeout": 60},
        )
    ]


def test_stock_dzjy_mrtj_maps_symbol_and_trade_date(monkeypatch):
    script = StockDzjyMrtj()
    saved = []

    monkeypatch.setattr(
        script,
        "fetch_ak_data",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "证券代码": ["000563", "600000"],
                "交易日期": ["2024-01-02", "2024-01-02"],
                "成交总额": [100.0, 200.0],
            }
        ),
    )
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data()

    assert result["symbol"].tolist() == ["000563", "600000"]
    assert result["data_date"].astype(str).tolist() == ["2024-01-02", "2024-01-02"]
    assert len(saved) == 1


def test_stock_zh_vote_baidu_maps_symbol(monkeypatch):
    script = StockZhVoteBaidu()
    saved = []

    monkeypatch.setattr(
        script,
        "fetch_ak_data",
        lambda *args, **kwargs: pd.DataFrame(
            {"周期": ["今日", "一周"], "看涨": [1, 2], "看跌": [3, 4]}
        ),
    )
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data(symbol="000001", indicator="指数")

    assert result["symbol"].tolist() == ["000001", "000001"]
    assert "data_date" in result.columns
    assert len(saved) == 1


def test_stock_individual_fund_flow_maps_symbol_and_date(monkeypatch):
    script = StockIndividualFundFlow()
    saved = []

    monkeypatch.setattr(
        script,
        "fetch_ak_data",
        lambda *args, **kwargs: pd.DataFrame(
            {"日期": ["2026-06-22"], "主力净流入-净额": [100.0]}
        ),
    )
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data(stock="600094", market="sh")

    assert result["symbol"].tolist() == ["sh600094"]
    assert result["name"].tolist() == ["600094"]
    assert result["data_date"].astype(str).tolist() == ["2026-06-22"]
    assert len(saved) == 1


def test_stock_market_fund_flow_maps_market_symbol_and_date(monkeypatch):
    script = StockMarketFundFlow()
    saved = []

    monkeypatch.setattr(
        script,
        "fetch_ak_data",
        lambda *args, **kwargs: pd.DataFrame({"日期": ["2026-06-22"], "上证-收盘价": [4163.1]}),
    )
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data()

    assert result["symbol"].tolist() == ["market"]
    assert result["name"].tolist() == ["大盘资金流"]
    assert result["data_date"].astype(str).tolist() == ["2026-06-22"]
    assert len(saved) == 1


def test_stock_concept_fund_flow_hist_maps_symbol_and_date(monkeypatch):
    script = StockConceptFundFlowHist()
    deleted = []
    saved = []

    monkeypatch.setattr(
        script,
        "fetch_ak_data",
        lambda *args, **kwargs: pd.DataFrame(
            {"日期": ["2026-06-22"], "主力净流入-净额": [5979770000.0]}
        ),
    )
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "delete_data",
        lambda table, conditions: deleted.append((table, conditions)) or True,
    )
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data(symbol="数据要素", _call_timeout=120)

    assert result["symbol"].tolist() == ["数据要素"]
    assert result["name"].tolist() == ["数据要素"]
    assert result["data_date"].astype(str).tolist() == ["2026-06-22"]
    assert deleted == [
        ("STOCK_CONCEPT_FUND_FLOW_HIST", {"symbol": "数据要素", "data_date": "2026-06-22"})
    ]
    assert "UNIQUE KEY uk_symbol_date (`symbol`, `data_date`)" in script.create_table_sql
    assert len(saved) == 1


def test_stock_sector_fund_flow_hist_maps_symbol_and_date(monkeypatch):
    script = StockSectorFundFlowHist()
    deleted = []
    saved = []

    monkeypatch.setattr(
        script,
        "fetch_ak_data",
        lambda *args, **kwargs: pd.DataFrame(
            {"日期": ["2026-06-22"], "主力净流入-净额": [11210230000.0]}
        ),
    )
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "delete_data",
        lambda table, conditions: deleted.append((table, conditions)) or True,
    )
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data(symbol="有色金属", _call_timeout=120)

    assert result["symbol"].tolist() == ["有色金属"]
    assert result["name"].tolist() == ["有色金属"]
    assert result["data_date"].astype(str).tolist() == ["2026-06-22"]
    assert deleted == [
        ("STOCK_SECTOR_FUND_FLOW_HIST", {"symbol": "有色金属", "data_date": "2026-06-22"})
    ]
    assert "UNIQUE KEY uk_symbol_date (`symbol`, `data_date`)" in script.create_table_sql
    assert len(saved) == 1


def test_stock_hsgt_board_rank_maps_board_and_date(monkeypatch):
    script = StockHsgtBoardRankEm()
    deleted = []
    saved = []

    monkeypatch.setattr(
        script,
        "fetch_board_rank",
        lambda **kwargs: pd.DataFrame(
            {
                "BOARD_CODE": ["BK0727", "BK0425"],
                "BOARD_NAME": ["医疗服务", "水泥建材"],
                "TRADE_DATE": ["2024-08-16 00:00:00", "2024-08-16 00:00:00"],
                "ADD_MARKET_CAP": [-117037636.6887, -74654842.828],
            }
        ),
    )
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "delete_data",
        lambda table, conditions: deleted.append((table, conditions)) or True,
    )
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data(
        symbol="北向资金增持行业板块排行",
        indicator="今日",
        page_size=500,
        max_pages=1,
        _call_timeout=60,
    )

    assert result["symbol"].tolist() == ["BK0727", "BK0425"]
    assert result["name"].tolist() == ["医疗服务", "水泥建材"]
    assert result["data_date"].astype(str).tolist() == ["2024-08-16", "2024-08-16"]
    assert result["board_rank_type"].tolist() == [
        "北向资金增持行业板块排行",
        "北向资金增持行业板块排行",
    ]
    assert result["indicator"].tolist() == ["今日", "今日"]
    assert deleted == [
        (
            "STOCK_HSGT_BOARD_RANK_EM",
            {
                "board_rank_type": "北向资金增持行业板块排行",
                "indicator": "今日",
                "data_date": "2024-08-16",
            },
        )
    ]
    assert "UNIQUE KEY uk_symbol_date" not in script.create_table_sql
    assert "INDEX idx_symbol_date (`symbol`, `data_date`)" in script.create_table_sql
    assert len(saved) == 1


def test_stock_hsgt_individual_detail_maps_symbol_institution_and_date(monkeypatch):
    script = StockHsgtIndividualDetailEm()
    deleted = []
    saved = []

    monkeypatch.setattr(
        script,
        "fetch_ak_data",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "持股日期": ["2024-06-28", "2024-06-28"],
                "机构名称": ["中国银行(香港)有限公司", "香港上海汇丰银行有限公司"],
                "持股数量": [144300, 7319575],
            }
        ),
    )
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "delete_data",
        lambda table, conditions: deleted.append((table, conditions)) or True,
    )
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data(symbol="002008")

    assert result["symbol"].tolist() == ["002008", "002008"]
    assert result["name"].tolist() == ["中国银行(香港)有限公司", "香港上海汇丰银行有限公司"]
    assert result["institution_name"].tolist() == [
        "中国银行(香港)有限公司",
        "香港上海汇丰银行有限公司",
    ]
    assert result["data_date"].astype(str).tolist() == ["2024-06-28", "2024-06-28"]
    assert deleted == [
        ("STOCK_HSGT_INDIVIDUAL_DETAIL_EM", {"symbol": "002008", "data_date": "2024-06-28"})
    ]
    assert "UNIQUE KEY uk_symbol_date" not in script.create_table_sql
    assert "INDEX idx_symbol_date (`symbol`, `data_date`)" in script.create_table_sql
    assert len(saved) == 1


def test_stock_hsgt_institution_statistics_maps_market_institution_and_date(monkeypatch):
    script = StockHsgtInstitutionStatisticsEm()
    deleted = []
    saved = []

    monkeypatch.setattr(
        script,
        "fetch_ak_data",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "持股日期": ["2024-01-10", "2024-01-10"],
                "机构名称": ["兴证国际证券有限公司", "东兴证券(香港)有限公司"],
                "持股只数": [153, 2],
            }
        ),
    )
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "delete_data",
        lambda table, conditions: deleted.append((table, conditions)) or True,
    )
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data(market="北向持股")

    assert result["symbol"].tolist() == ["兴证国际证券有限公司", "东兴证券(香港)有限公司"]
    assert result["name"].tolist() == ["兴证国际证券有限公司", "东兴证券(香港)有限公司"]
    assert result["market"].tolist() == ["北向持股", "北向持股"]
    assert result["data_date"].astype(str).tolist() == ["2024-01-10", "2024-01-10"]
    assert deleted == [
        (
            "STOCK_HSGT_INSTITUTION_STATISTICS_EM",
            {"market": "北向持股", "data_date": "2024-01-10"},
        )
    ]
    assert "UNIQUE KEY uk_symbol_date" not in script.create_table_sql
    assert "INDEX idx_symbol_date (`symbol`, `data_date`)" in script.create_table_sql
    assert len(saved) == 1


def test_futures_gfex_warehouse_receipt_flattens_dict_result(monkeypatch):
    script = FuturesGfexWarehouseReceipt()
    saved = []

    monkeypatch.setattr(
        script,
        "fetch_ak_data",
        lambda *args, **kwargs: {
            "LC": pd.DataFrame({"品种": ["碳酸锂"], "仓库/分库": ["仓库A"], "今日仓单量": [1]}),
            "SI": pd.DataFrame({"品种": ["工业硅"], "仓库/分库": ["仓库B"], "今日仓单量": [2]}),
        },
    )
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data(date="20240122")

    assert result["symbol"].tolist() == ["LC", "SI"]
    assert result["name"].tolist() == ["碳酸锂", "工业硅"]
    assert result["data_date"].astype(str).tolist() == ["2024-01-22", "2024-01-22"]
    assert result["R_ID"].str.startswith("GFEX_20240122_").all()
    assert result["PRODUCT_CODE"].tolist() == ["LC", "SI"]
    assert result["BASEDATE"].astype(str).tolist() == ["2024-01-22", "2024-01-22"]
    assert "UNIQUE KEY uk_symbol_date" not in script.create_table_sql
    assert "KEY `idx_symbol_date` (`symbol`, `data_date`)" in script.create_table_sql
    assert len(saved) == 1


def test_stock_lh_yyb_rank_scripts_map_rank_symbol_and_name(monkeypatch):
    for script, prefix in ((StockLhYybCapital(), "capital"), (StockLhYybMost(), "most")):
        saved = []
        monkeypatch.setattr(
            script,
            "fetch_ak_data",
            lambda *args, **kwargs: pd.DataFrame(
                {"序号": [1], "营业部名称": ["中国国际金融股份有限公司上海分公司"]}
            ),
        )
        monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)

        def fake_save_data(df, table, ignore_duplicates=False, bucket=saved):
            bucket.append(df.copy())
            return len(df)

        monkeypatch.setattr(
            script,
            "save_data",
            fake_save_data,
        )

        result = script.fetch_data()

        assert result["symbol"].tolist() == [f"{prefix}_1"]
        assert result["name"].tolist() == ["中国国际金融股份有限公司上海分公司"]
        assert "data_date" in result.columns
        assert len(saved) == 1


def test_stock_sy_yq_em_maps_stock_and_announcement_date(monkeypatch):
    script = StockSyYqEm()
    saved = []

    monkeypatch.setattr(
        script,
        "fetch_ak_data",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "股票代码": ["546"],
                "股票简称": ["金圆股份"],
                "公告日期": ["2024-07-13"],
                "最新商誉报告期": ["2023-09-30"],
            }
        ),
    )
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data()

    assert result["symbol"].tolist() == ["000546"]
    assert result["name"].tolist() == ["金圆股份"]
    assert result["data_date"].astype(str).tolist() == ["2024-07-13"]
    assert "UNIQUE KEY uk_symbol_date" not in script.create_table_sql
    assert "INDEX idx_symbol_date (`symbol`, `data_date`)" in script.create_table_sql
    assert len(saved) == 1


def test_slow_fund_scripts_have_smaller_safe_defaults():
    dividend_params = AkshareScriptService._apply_safe_default_parameters("fund_dividend_em", {})
    fee_params = AkshareScriptService._apply_safe_default_parameters("fund_fee_em", {})
    split_params = AkshareScriptService._apply_safe_default_parameters("fund_split_em", {})
    open_hist_params = AkshareScriptService._apply_safe_default_parameters("open_fund_hist_em", {})

    assert dividend_params["max_codes"] == 5
    assert fee_params["limit"] == 1
    assert split_params["max_codes"] == 5
    assert open_hist_params["max_codes"] == 2
    assert open_hist_params["indicators"] == ["unit_nav"]


def test_slow_market_scripts_have_bounded_safe_defaults():
    reits_params = AkshareScriptService._apply_safe_default_parameters("reits_hist_em", {})
    minute_params = AkshareScriptService._apply_safe_default_parameters("minute_market", {})
    daily_params = AkshareScriptService._apply_safe_default_parameters("daily_market_data", {})

    assert reits_params["max_symbols"] == 3
    assert minute_params["max_symbols"] == 5
    assert minute_params["max_workers"] == 2
    assert daily_params["markets"] == "CFFEX"
    assert daily_params["lookback_days"] == 10
    assert daily_params["max_windows"] == 1


def test_slow_futures_history_scripts_have_window_safe_defaults():
    shfe_delivery_params = AkshareScriptService._apply_safe_default_parameters(
        "shfe_delivery_data", {}
    )
    czce_delivery_params = AkshareScriptService._apply_safe_default_parameters(
        "czce_delivery_data", {}
    )
    czce_to_spot_params = AkshareScriptService._apply_safe_default_parameters(
        "czce_to_spot", {}
    )
    delivery_match_params = AkshareScriptService._apply_safe_default_parameters(
        "futures_delivery_match_czce", {}
    )

    assert shfe_delivery_params["lookback_months"] == 3
    assert shfe_delivery_params["max_months"] == 1
    assert czce_delivery_params["lookback_days"] == 10
    assert czce_delivery_params["max_days"] == 1
    assert czce_to_spot_params["lookback_days"] == 10
    assert czce_to_spot_params["max_days"] == 1
    assert delivery_match_params["lookback_days"] == 10
    assert delivery_match_params["max_days"] == 1


def test_recoverable_futures_dict_scripts_have_defaults_and_nonunique_indexes():
    display_params = AkshareScriptService._apply_safe_default_parameters(
        "futures_display_main_sina", {}
    )
    gfex_params = AkshareScriptService._apply_safe_default_parameters(
        "futures_gfex_position_rank", {}
    )
    hold_pos_params = AkshareScriptService._apply_safe_default_parameters(
        "futures_hold_pos_sina", {}
    )
    shfe_params = AkshareScriptService._apply_safe_default_parameters(
        "futures_shfe_warehouse_receipt", {}
    )
    czce_params = AkshareScriptService._apply_safe_default_parameters(
        "futures_warehouse_receipt_czce", {}
    )

    assert display_params["_call_timeout"] == 60
    assert gfex_params["date"] == "20240223"
    assert gfex_params["vars_list"] == ["SI", "LC"]
    assert hold_pos_params["symbol"] == "成交量"
    assert hold_pos_params["contract"] == "RB2405"
    assert hold_pos_params["date"] == "20240223"
    assert shfe_params["date"] == "20240223"
    assert czce_params["date"] == "20240223"

    for script in (
        FuturesGfexPositionRank(),
        FuturesShfeWarehouseReceipt(),
        FuturesWarehouseReceiptCzce(),
    ):
        assert "UNIQUE KEY uk_symbol_date" not in script.create_table_sql
        assert "INDEX idx_symbol_date (`symbol`, `data_date`)" in script.create_table_sql


def test_futures_hold_pos_sina_normalizes_rank_columns():
    df = pd.DataFrame(
        {
            "名次": [1, 2],
            "会员简称": ["中信期货", "东证期货"],
            "成交量": [197458, 140947],
            "比上交易增减": [-86180, -78702],
        }
    )

    mapped = FuturesHoldPosSina.normalize_columns(
        df,
        contract="rb2405",
        rank_type="成交量",
        date="20240223",
    )

    assert mapped["symbol"].tolist() == ["RB2405", "RB2405"]
    assert mapped["name"].tolist() == ["RB2405 成交量", "RB2405 成交量"]
    assert mapped["data_date"].astype(str).tolist() == ["2024-02-23", "2024-02-23"]
    assert mapped["rank_num"].tolist() == [1, 2]
    assert mapped["member_name"].tolist() == ["中信期货", "东证期货"]
    assert mapped["rank_value"].tolist() == [197458, 140947]
    assert mapped["change_value"].tolist() == [-86180, -78702]
    assert mapped["raw_value_column"].tolist() == ["成交量", "成交量"]


def test_futures_dict_result_flattens_nonempty_frames():
    result = flatten_dict_result(
        {
            "si2403": pd.DataFrame({"rank": [1, 2], "member": ["A", "B"]}),
            "empty": pd.DataFrame(),
        },
        data_date="20240223",
    )

    assert list(result["symbol"]) == ["si2403", "si2403"]
    assert list(result["rank"]) == [1, 2]
    assert result["data_date"].astype(str).tolist() == ["2024-02-23", "2024-02-23"]


def test_slow_futures_contract_info_scripts_have_window_safe_defaults():
    for script_id in (
        "futures_contract_info_cffex",
        "futures_contract_info_czce",
        "futures_contract_info_ine",
        "futures_contract_info_shfe",
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["lookback_days"] == 10
        assert params["max_days"] == 1
        assert params["sleep_seconds"] == 0


def test_slow_futures_weekly_scripts_have_bounded_safe_defaults():
    inventory_params = AkshareScriptService._apply_safe_default_parameters(
        "inventory_data", {}
    )
    member_params = AkshareScriptService._apply_safe_default_parameters(
        "member_position_rank", {}
    )
    rank_params = AkshareScriptService._apply_safe_default_parameters("rank_sum_daily", {})
    stock_weekly_params = AkshareScriptService._apply_safe_default_parameters(
        "shfe_stock_weekly", {}
    )
    trading_rules_params = AkshareScriptService._apply_safe_default_parameters(
        "trading_rules", {}
    )

    assert inventory_params["max_symbols"] == 5
    assert member_params["exchanges"] == "郑商所,中金所,广期所,上期所"
    assert member_params["start_date"] == "2024-02-23"
    assert member_params["end_date"] == "2024-02-23"
    assert rank_params["max_symbols"] == 2
    assert rank_params["lookback_days"] == 10
    assert rank_params["sleep_seconds"] == 0
    assert stock_weekly_params["lookback_days"] == 30
    assert stock_weekly_params["max_reports"] == 1
    assert stock_weekly_params["sleep_seconds"] == 0
    assert trading_rules_params["lookback_days"] == 10
    assert trading_rules_params["max_days"] == 1


def test_member_position_rank_accepts_fixed_date_window(monkeypatch):
    script = FuturesMemberPositionRank()
    calls = []

    monkeypatch.setattr(script, "table_exists", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        script,
        "_update_czce_rank_table",
        lambda begin_date, end_date=None: calls.append(("CZCE", begin_date, end_date)),
    )
    monkeypatch.setattr(
        script,
        "_update_cffex_rank_table",
        lambda begin_date, end_date=None: calls.append(("CFFEX", begin_date, end_date)),
    )
    monkeypatch.setattr(
        script,
        "_update_gfex_rank_table",
        lambda begin_date, end_date=None: calls.append(("GFEX", begin_date, end_date)),
    )
    monkeypatch.setattr(
        script,
        "_update_shfe_rank_table",
        lambda begin_date, end_date=None: calls.append(("SHFE", begin_date, end_date)),
    )

    script.run(
        exchanges="郑商所,中金所,广期所,上期所",
        start_date="2024-02-23",
        end_date="2024-02-23",
    )

    assert calls == [
        ("CZCE", "2024-02-23", "2024-02-23"),
        ("CFFEX", "2024-02-23", "2024-02-23"),
        ("GFEX", "2024-02-23", "2024-02-23"),
        ("SHFE", "2024-02-23", "2024-02-23"),
    ]


def test_member_position_rank_maps_named_shfe_rank_columns():
    df = pd.DataFrame(
        {
            "symbol": ["CU2404"],
            "rank": [1],
            "vol_party_name": ["中信期货"],
            "vol": [14366],
            "vol_chg": [1185],
            "long_party_name": ["中信期货"],
            "long_open_interest": [22595],
            "long_open_interest_chg": [2391],
            "short_party_name": ["中信期货"],
            "short_open_interest": [15566],
            "short_open_interest_chg": [51],
            "variety": ["CU"],
        }
    )

    mapped = FuturesMemberPositionRank._rename_lowercase_rank_columns(df)

    assert mapped["SYMBOL"].tolist() == ["CU2404"]
    assert mapped["RANK_NUM"].tolist() == [1]
    assert mapped["VOL_PARTY_NAME"].tolist() == ["中信期货"]
    assert mapped["LONG_OPEN_INTEREST"].tolist() == [22595]
    assert mapped["SHORT_OPEN_INTEREST_CHG"].tolist() == [51]


def test_slow_warehouse_receipt_scripts_have_bounded_safe_defaults():
    czce_params = AkshareScriptService._apply_safe_default_parameters(
        "warehouse_receipt_czce", {}
    )
    dce_params = AkshareScriptService._apply_safe_default_parameters("warehouse_receipt_dce", {})

    assert czce_params["start_date"] == "20240223"
    assert czce_params["end_date"] == "20240223"
    assert czce_params["max_days"] == 1
    assert dce_params["lookback_days"] == 7
    assert dce_params["max_days"] == 1


def test_slow_index_history_scripts_have_bounded_safe_defaults():
    constituent_params = AkshareScriptService._apply_safe_default_parameters(
        "index_constituent_weights_csindex", {}
    )
    cni_market_params = AkshareScriptService._apply_safe_default_parameters(
        "index_daily_market_cni", {}
    )
    min_params = AkshareScriptService._apply_safe_default_parameters(
        "index_zh_a_hist_min_em", {}
    )
    em_daily_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_zh_index_daily_em", {}
    )

    assert constituent_params["max_symbols"] == 3
    assert constituent_params["max_workers"] == 2
    assert cni_market_params["max_symbols"] == 3
    assert cni_market_params["lookback_days"] == 30
    assert cni_market_params["max_workers"] == 2
    assert min_params["max_symbols"] == 5
    assert min_params["period"] == "1"
    assert em_daily_params["max_symbols"] == 5
    assert em_daily_params["lookback_days"] == 30
    assert em_daily_params["max_workers"] == 2

    detail_params = AkshareScriptService._apply_safe_default_parameters(
        "index_detail_cni", {}
    )
    assert detail_params["max_symbols"] == 3
    assert detail_params["max_months"] == 1


def test_slow_index_list_scripts_have_bounded_safe_defaults():
    for script_id in ("index_global_hist_em", "index_global_hist_sina"):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["max_indices"] == 3

    adjust_params = AkshareScriptService._apply_safe_default_parameters(
        "index_hist_adjust_cni", {}
    )
    assert adjust_params["max_symbols"] == 3
    assert adjust_params["max_workers"] == 2

    for script_id in (
        "stock_hk_index_daily_em",
        "stock_hk_index_daily_sina",
        "stock_zh_index_daily",
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["max_symbols"] == 5

    tx_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_zh_index_daily_tx", {}
    )
    assert tx_params["max_symbols"] == 1


def test_slow_sw_index_scripts_have_bounded_safe_defaults():
    for script_id in (
        "sw_fund_index_historical",
        "sw_index_components",
        "sw_index_historical",
        "sw_index_minute",
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["max_symbols"] == 3
        assert params["max_workers"] == 2

    analysis_params = AkshareScriptService._apply_safe_default_parameters(
        "sw_index_analysis_daily", {}
    )
    assert analysis_params["lookback_days"] == 30
    assert analysis_params["max_workers"] == 2

    cons_params = AkshareScriptService._apply_safe_default_parameters(
        "sw_industry_third_cons", {}
    )
    assert cons_params["max_codes"] == 3
    assert cons_params["max_workers"] == 2


def test_stock_board_industry_min_has_bounded_safe_default():
    params = AkshareScriptService._apply_safe_default_parameters(
        "stock_board_industry_min_em", {}
    )
    concept_hist_min_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_board_concept_hist_min_em", {}
    )
    industry_hist_min_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_board_industry_hist_min_em", {}
    )

    assert params["max_symbols"] == 3
    assert params["period"] == "1"
    assert concept_hist_min_params["symbol"] == "长寿药"
    assert concept_hist_min_params["period"] == "5"
    assert industry_hist_min_params["symbol"] == "小金属"
    assert industry_hist_min_params["period"] == "1"

    industry_hist_min_script = StockBoardIndustryHistMinEm()
    assert "UNIQUE KEY uk_symbol_date" not in industry_hist_min_script.create_table_sql
    assert "INDEX idx_symbol_date (`symbol`, `data_date`)" in industry_hist_min_script.create_table_sql


def test_stock_board_industry_hist_min_maps_symbol_and_datetime(monkeypatch):
    script = StockBoardIndustryHistMinEm()
    saved = []

    monkeypatch.setattr(
        script,
        "fetch_ak_data",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "日期时间": ["2026-06-22 09:30", "2026-06-22 09:31"],
                "开盘": [1.0, 1.1],
            }
        ),
    )
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "save_data",
        lambda df, table, ignore_duplicates=False: saved.append(df.copy()) or len(df),
    )

    result = script.fetch_data(symbol="小金属", period="1")

    assert result["symbol"].tolist() == ["小金属", "小金属"]
    assert result["data_date"].astype(str).tolist() == ["2026-06-22", "2026-06-22"]
    assert len(saved) == 1


def test_stock_history_scripts_have_narrow_safe_defaults():
    for script_id in ("stock_zh_a_daily", "stock_zh_a_hist", "stock_zh_a_hist_tx"):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["start_date"].isdigit()
        assert params["end_date"].isdigit()
        assert int(params["end_date"]) >= int(params["start_date"])

    us_params = AkshareScriptService._apply_safe_default_parameters("stock_us_daily", {})
    minute_params = AkshareScriptService._apply_safe_default_parameters("stock_zh_a_minute", {})
    ah_params = AkshareScriptService._apply_safe_default_parameters("stock_zh_ah_daily", {})
    b_params = AkshareScriptService._apply_safe_default_parameters("stock_zh_b_daily", {})
    b_min_params = AkshareScriptService._apply_safe_default_parameters("stock_zh_b_minute", {})
    cdr_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_zh_a_cdr_daily", {}
    )
    kcb_params = AkshareScriptService._apply_safe_default_parameters("stock_zh_kcb_daily", {})
    index_hist_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_zh_index_hist_csindex", {}
    )

    assert us_params["symbol"] == "AAPL"
    assert minute_params["symbol"] == "sh600519"
    assert minute_params["period"] == "1"
    assert int(ah_params["end_year"]) - int(ah_params["start_year"]) == 1
    assert b_params["symbol"] == "sh900901"
    assert b_params["_call_timeout"] == 60
    assert b_min_params["symbol"] == "sh900901"
    assert b_min_params["period"] == "1"
    assert cdr_params["symbol"] == "sh689009"
    assert kcb_params["symbol"] == "sh688399"
    assert index_hist_params["symbol"] == "000928"
    assert index_hist_params["start_date"].isdigit()
    assert index_hist_params["end_date"].isdigit()


def test_stock_zh_a_hist_upserts_by_symbol_date_without_date_wide_delete(monkeypatch):
    script = StockZhAHist()
    saved = {}

    monkeypatch.setattr(
        script,
        "fetch_ak_data",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "日期": ["2026-06-19", "2026-06-22"],
                "开盘": [10.0, 10.2],
                "收盘": [10.1, 10.4],
                "最高": [10.3, 10.6],
                "最低": [9.9, 10.1],
                "成交量": [100, 200],
                "成交额": [1000.0, 2200.0],
            }
        ),
    )
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        script,
        "delete_data",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not delete by date")),
    )

    def fake_save_data(df, table, **kwargs):
        saved["df"] = df.copy()
        saved["table"] = table
        saved["kwargs"] = kwargs
        return len(df)

    monkeypatch.setattr(script, "save_data", fake_save_data)

    result = script.fetch_data(symbol="000002", start_date="20260601", end_date="20260703")

    assert result["symbol"].tolist() == ["000002", "000002"]
    assert result["data_date"].tolist() == ["2026-06-19", "2026-06-22"]
    assert saved["table"] == "STOCK_ZH_A_HIST"
    assert saved["kwargs"] == {
        "on_duplicate_update": True,
        "unique_keys": ["symbol", "data_date"],
    }


def test_stock_zh_a_hist_can_fetch_directly_from_tencent(monkeypatch):
    script = StockZhAHist()
    calls = []
    saved = {}

    def fake_fetch_ak_data(name, **kwargs):
        calls.append((name, kwargs))
        if name == "stock_zh_a_hist":
            raise AssertionError("eastmoney should be skipped in tencent mode")
        return pd.DataFrame(
            {
                "date": ["2026-06-19"],
                "open": [10.0],
                "close": [10.1],
                "high": [10.2],
                "low": [9.9],
                "amount": [100],
            }
        )

    monkeypatch.setattr(script, "fetch_ak_data", fake_fetch_ak_data)
    monkeypatch.setattr(script, "create_table_if_not_exists", lambda *args, **kwargs: None)
    monkeypatch.setattr(script, "save_data", lambda df, table, **kwargs: saved.update(df=df.copy()))

    result = script.fetch_data(
        symbol="000002",
        start_date="20260601",
        end_date="20260703",
        source="tencent",
    )

    assert [call[0] for call in calls] == ["stock_zh_a_hist_tx"]
    assert calls[0][1]["symbol"] == "sz000002"
    assert result["symbol"].tolist() == ["000002"]
    assert saved["df"]["data_date"].tolist() == ["2026-06-19"]


def test_futures_daily_market_falls_back_to_sina_dce_main_contracts(monkeypatch):
    script = FuturesDailyMarket()
    script.DCE_SINA_MAIN_SYMBOLS = ("M0", "Y0")
    calls = []
    saved = {}
    next_id = iter(["RID1", "RID2"])

    def fake_fetch_ak_data(function_name, **kwargs):
        calls.append((function_name, kwargs))
        return pd.DataFrame(
            {
                "date": ["2025-07-02", "2026-07-03"],
                "open": [3000, 2980],
                "high": [3010, 2986],
                "low": [2990, 2957],
                "close": [3005, 2962],
                "volume": [100, 721030],
                "hold": [200, 1831847],
                "settle": [3001, 2969],
            }
        )

    def fake_save_data(df, table_name, **kwargs):
        saved["df"] = df.copy()
        saved["table_name"] = table_name
        saved["kwargs"] = kwargs
        return True

    monkeypatch.setattr(script, "fetch_ak_data", fake_fetch_ak_data)
    monkeypatch.setattr(script, "get_uuid", lambda: next(next_id))
    monkeypatch.setattr(script, "save_data", fake_save_data)

    result = script._backfill_dce_sina_main_contracts(
        start_date="2025-07-03",
        end_date="2026-07-03",
        table_name="FUTURES_DAILY_MARKET",
        _call_timeout=7,
    )

    assert result is True
    assert [call[0] for call in calls] == ["futures_zh_daily_sina", "futures_zh_daily_sina"]
    assert [call[1]["symbol"] for call in calls] == ["M0", "Y0"]
    assert all(call[1]["_call_timeout"] == 7 for call in calls)
    assert saved["table_name"] == "FUTURES_DAILY_MARKET"
    assert saved["kwargs"] == {
        "on_duplicate_update": True,
        "unique_keys": ["MARKET", "SYMBOL", "TRADE_DATE"],
    }
    assert saved["df"]["SYMBOL"].tolist() == ["M0", "Y0"]
    assert saved["df"]["VARIETY"].tolist() == ["M", "Y"]
    assert saved["df"]["TRADE_DATE"].tolist() == ["2026-07-03", "2026-07-03"]
    assert saved["df"]["MARKET"].tolist() == ["DCE", "DCE"]
    assert saved["df"]["OPEN_INTEREST"].tolist() == [1831847, 1831847]
    assert saved["df"]["DATA_SOURCE"].tolist() == ["新浪期货兜底", "新浪期货兜底"]


def test_intraday_history_scripts_have_recent_datetime_defaults():
    for script_id in (
        "stock_hk_hist_min_em",
        "stock_zh_a_hist_min_em",
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["start_date"] < params["end_date"]
        assert ":" in params["start_date"]
        assert ":" in params["end_date"]

    us_hist_min_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_us_hist_min_em", {}
    )
    us_spot_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_us_spot", {}
    )
    us_hist_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_us_hist", {}
    )
    pre_min_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_zh_a_hist_pre_min_em", {}
    )
    tick_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_zh_a_tick_tx_js", {}
    )
    assert us_hist_min_params["symbol"] == "105.AAPL"
    assert us_hist_min_params["start_date"] == "1979-09-01 09:32:00"
    assert us_hist_min_params["end_date"] == "2222-01-01 09:32:00"
    assert us_spot_params["max_pages"] == 1
    assert us_hist_params["symbol"] == "105.MSFT"
    assert us_hist_params["start_date"].isdigit()
    assert us_hist_params["end_date"].isdigit()
    assert pre_min_params["symbol"] == "000001"
    assert pre_min_params["start_time"] == "09:30:00"
    assert pre_min_params["_call_timeout"] == 60
    assert tick_params["symbol"] == "sz000001"
    assert tick_params["_call_timeout"] == 120


def test_zt_pool_scripts_use_current_date_default():
    for script_id in (
        "stock_zt_pool_dtgc_em",
        "stock_zt_pool_em",
        "stock_zt_pool_strong_em",
        "stock_zt_pool_sub_new_em",
        "stock_zt_pool_zbgc_em",
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["date"].isdigit()


def test_stock_disclosure_scripts_have_recent_date_defaults():
    for script_id in (
        "stock_zh_a_disclosure_relation_cninfo",
        "stock_zh_a_disclosure_report_cninfo",
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["symbol"] == "000001"
        assert params["market"] == "沪深京"
        assert params["start_date"].isdigit()
        assert params["end_date"].isdigit()
        assert params["_call_timeout"] == 120
        assert int(params["end_date"]) - int(params["start_date"]) > 10000


def test_recoverable_stock_gap_scripts_have_explicit_fetch_defaults():
    profit_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hk_profit_forecast_et", {}
    )
    hot_rank_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hk_hot_rank_latest_em", {}
    )
    delisted_balance_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_balance_sheet_by_report_delisted_em", {}
    )
    concept_flow_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_concept_fund_flow_hist", {}
    )
    sector_flow_hist_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_sector_fund_flow_hist", {}
    )
    sector_summary_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_sector_fund_flow_summary", {}
    )
    hsgt_hist_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hsgt_hist_em", {}
    )
    hsgt_board_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hsgt_board_rank_em", {}
    )
    hsgt_individual_detail_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hsgt_individual_detail_em", {}
    )
    hsgt_institution_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hsgt_institution_statistics_em", {}
    )
    hold_change_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hold_change_cninfo", {}
    )
    hold_control_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hold_control_cninfo", {}
    )
    hold_num_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hold_num_cninfo", {}
    )
    hot_deal_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hot_deal_xq", {}
    )
    lhb_detail_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_lhb_detail_em", {}
    )
    lhb_ggtj_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_lhb_ggtj_sina", {}
    )

    assert profit_params["symbol"] == "00700"
    assert profit_params["indicator"] == "盈利预测概览"
    assert profit_params["_call_timeout"] == 90
    assert hot_rank_params["symbol"] == "00700"
    assert hot_rank_params["_call_timeout"] == 90
    assert delisted_balance_params["symbol"] == "SZ000013"
    assert delisted_balance_params["_call_timeout"] == 90
    assert concept_flow_params["symbol"] == "数据要素"
    assert concept_flow_params["_call_timeout"] == 120
    assert sector_flow_hist_params["symbol"] == "有色金属"
    assert sector_flow_hist_params["_call_timeout"] == 120
    assert sector_summary_params["symbol"] == "非银金融"
    assert sector_summary_params["indicator"] == "今日"
    assert sector_summary_params["_call_timeout"] == 90
    assert hsgt_hist_params["symbol"] == "沪股通"
    assert hsgt_hist_params["_call_timeout"] == 120
    assert hsgt_board_params["symbol"] == "北向资金增持行业板块排行"
    assert hsgt_board_params["indicator"] == "今日"
    assert hsgt_board_params["page_size"] == 500
    assert hsgt_board_params["max_pages"] == 1
    assert hsgt_board_params["_call_timeout"] == 60
    assert hsgt_individual_detail_params["symbol"] == "002008"
    assert hsgt_individual_detail_params["start_date"] == "20240101"
    assert hsgt_individual_detail_params["end_date"] == "20240630"
    assert hsgt_individual_detail_params["_call_timeout"] == 90
    assert hsgt_institution_params["market"] == "北向持股"
    assert hsgt_institution_params["start_date"] == "20240110"
    assert hsgt_institution_params["end_date"] == "20240110"
    assert hsgt_institution_params["_call_timeout"] == 60
    assert hold_change_params["symbol"] == "全部"
    assert hold_change_params["_call_timeout"] == 60
    assert hold_control_params["symbol"] == "全部"
    assert hold_control_params["_call_timeout"] == 60
    assert hold_num_params["date"].isdigit()
    assert hold_num_params["_call_timeout"] == 60
    assert hot_deal_params["symbol"] == "最热门"
    assert hot_deal_params["max_pages"] == 1
    assert hot_deal_params["_call_timeout"] == 60
    assert lhb_detail_params["start_date"].isdigit()
    assert lhb_detail_params["end_date"].isdigit()
    assert int(lhb_detail_params["end_date"]) >= int(lhb_detail_params["start_date"])
    assert lhb_detail_params["_call_timeout"] == 60
    assert lhb_ggtj_params["symbol"] == "5"
    assert lhb_ggtj_params["_call_timeout"] == 60


def test_recoverable_report_scripts_have_explicit_fetch_defaults():
    fund_industry_params = AkshareScriptService._apply_safe_default_parameters(
        "fund_report_industry_allocation_cninfo", {}
    )
    fund_stock_params = AkshareScriptService._apply_safe_default_parameters(
        "fund_report_stock_cninfo", {}
    )
    cash_flow_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_cash_flow_sheet_by_quarterly_em", {}
    )
    analysis_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_financial_analysis_indicator", {}
    )
    notice_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_notice_report", {}
    )
    profit_forecast_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_profit_forecast_em", {}
    )
    ths_forecast_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_profit_forecast_ths", {}
    )
    profit_quarterly_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_profit_sheet_by_quarterly_em", {}
    )
    profit_yearly_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_profit_sheet_by_yearly_em", {}
    )
    research_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_research_report_em", {}
    )
    zcfz_bj_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_zcfz_bj_em", {}
    )
    kcb_report_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_zh_kcb_report_em", {}
    )

    assert fund_industry_params["date"].isdigit()
    assert fund_industry_params["_call_timeout"] == 60
    assert fund_stock_params["date"] == fund_industry_params["date"]
    assert fund_stock_params["_call_timeout"] == 60
    assert cash_flow_params["symbol"] == "SH600519"
    assert cash_flow_params["_call_timeout"] == 180
    assert analysis_params["symbol"] == "600519"
    assert analysis_params["start_year"] == "2020"
    assert analysis_params["_call_timeout"] == 90
    assert notice_params["symbol"] == "全部"
    assert notice_params["date"].isdigit()
    assert notice_params["_call_timeout"] == 90
    assert profit_forecast_params["symbol"] == ""
    assert profit_forecast_params["_call_timeout"] == 90
    assert ths_forecast_params["symbol"] == "600519"
    assert ths_forecast_params["indicator"] == "预测年报每股收益"
    assert ths_forecast_params["_call_timeout"] == 60
    assert profit_quarterly_params["symbol"] == "SH600519"
    assert profit_quarterly_params["_call_timeout"] == 180
    assert profit_yearly_params["symbol"] == "SH600519"
    assert profit_yearly_params["_call_timeout"] == 120
    assert research_params["symbol"] == "000001"
    assert research_params["_call_timeout"] == 60
    assert zcfz_bj_params["date"] == fund_industry_params["date"]
    assert zcfz_bj_params["_call_timeout"] == 60
    assert kcb_report_params["from_page"] == 1
    assert kcb_report_params["to_page"] == 3
    assert kcb_report_params["_call_timeout"] == 60


def test_recoverable_fund_history_scripts_have_explicit_codes():
    graded_hist_params = AkshareScriptService._apply_safe_default_parameters(
        "graded_fund_hist_em", {}
    )
    money_hist_params = AkshareScriptService._apply_safe_default_parameters(
        "money_fund_hist_em", {}
    )
    option_yearly_params = AkshareScriptService._apply_safe_default_parameters(
        "option_hist_yearly_czce", {}
    )
    option_minute_params = AkshareScriptService._apply_safe_default_parameters(
        "option_minute_em", {}
    )
    futures_table_params = AkshareScriptService._apply_safe_default_parameters(
        "futures_hist_table_em", {}
    )

    assert graded_hist_params["fund_codes"] == ["150232"]
    assert graded_hist_params["max_pages"] == 1
    assert money_hist_params["fund_codes"] == ["000009"]
    assert money_hist_params["max_pages"] == 1
    assert option_yearly_params["symbol"] == "SR"
    assert option_yearly_params["year"].isdigit()
    assert option_yearly_params["_call_timeout"] == 120
    assert option_minute_params["max_current_pages"] == 1
    assert option_minute_params["include_cffex"] is True
    assert option_minute_params["_call_timeout"] == 60
    assert futures_table_params["_call_timeout"] == 60


def test_recoverable_option_and_base_info_scripts_have_defaults():
    etf_info_params = AkshareScriptService._apply_safe_default_parameters(
        "fund_etf_fund_info_em", {}
    )
    cffex_hs300_params = AkshareScriptService._apply_safe_default_parameters(
        "option_cffex_hs300_list_sina", {}
    )
    cffex_sz50_params = AkshareScriptService._apply_safe_default_parameters(
        "option_cffex_sz50_list_sina", {}
    )
    cffex_zz1000_params = AkshareScriptService._apply_safe_default_parameters(
        "option_cffex_zz1000_list_sina", {}
    )
    comm_info_params = AkshareScriptService._apply_safe_default_parameters(
        "option_comm_info", {}
    )
    sse_codes_params = AkshareScriptService._apply_safe_default_parameters(
        "option_sse_codes_sina", {}
    )
    sse_expire_params = AkshareScriptService._apply_safe_default_parameters(
        "option_sse_expire_day_sina", {}
    )
    sse_list_params = AkshareScriptService._apply_safe_default_parameters(
        "option_sse_list_sina", {}
    )
    sse_minute_params = AkshareScriptService._apply_safe_default_parameters(
        "option_sse_minute_sina", {}
    )
    foreign_symbols_params = AkshareScriptService._apply_safe_default_parameters(
        "futures_foreign_commodity_subscribe_exchange_symbol", {}
    )
    sgx_params = AkshareScriptService._apply_safe_default_parameters(
        "futures_settlement_price_sgx", {}
    )
    board_change_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_board_change_em", {}
    )
    concept_cons_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_board_concept_cons_em", {}
    )
    changes_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_changes_em", {}
    )

    assert etf_info_params["fund"] == "510300"
    assert etf_info_params["start_date"].isdigit()
    assert etf_info_params["end_date"].isdigit()
    assert etf_info_params["_call_timeout"] == 90
    assert cffex_hs300_params["_call_timeout"] == 30
    assert cffex_sz50_params["_call_timeout"] == 30
    assert cffex_zz1000_params["_call_timeout"] == 30
    assert comm_info_params["symbol"] == "工业硅期权"
    assert comm_info_params["_call_timeout"] == 60
    assert sse_codes_params["symbol"] == "看涨期权"
    assert sse_codes_params["trade_date"].isdigit()
    assert sse_codes_params["underlying"] == "510050"
    assert sse_expire_params["symbol"] == "50ETF"
    assert sse_expire_params["exchange"] == "null"
    assert sse_expire_params["trade_date"].isdigit()
    assert sse_list_params["symbol"] == "50ETF"
    assert sse_list_params["exchange"] == "null"
    assert sse_minute_params["option_type"] == "看涨期权"
    assert sse_minute_params["trade_date"].isdigit()
    assert sse_minute_params["underlying"] == "510050"
    assert sse_minute_params["_call_timeout"] == 60
    assert foreign_symbols_params["_call_timeout"] == 30
    assert sgx_params["date"].isdigit()
    assert sgx_params["_call_timeout"] == 60
    assert board_change_params["_call_timeout"] == 60
    assert concept_cons_params["symbol"] == "数据要素"
    assert concept_cons_params["_call_timeout"] == 60
    assert changes_params["symbol"] == "大笔买入"
    assert changes_params["_call_timeout"] == 60


def test_recoverable_stock_basic_info_scripts_have_defaults():
    a_code_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_info_a_code_name", {}
    )
    bj_code_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_info_bj_name_code", {}
    )
    individual_info_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_individual_info_em", {}
    )
    bid_ask_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_bid_ask_em", {}
    )
    xq_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_individual_basic_info_xq", {}
    )
    hk_xq_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_individual_basic_info_hk_xq", {}
    )
    us_xq_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_individual_basic_info_us_xq", {}
    )
    industry_category_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_industry_category_cninfo", {}
    )
    industry_change_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_industry_change_cninfo", {}
    )
    comment_params = AkshareScriptService._apply_safe_default_parameters("stock_comment_em", {})
    cyq_params = AkshareScriptService._apply_safe_default_parameters("stock_cyq_em", {})
    fhps_params = AkshareScriptService._apply_safe_default_parameters("stock_fhps_em", {})
    hkggt_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hk_ggt_components_em", {}
    )
    hk_dividend_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hk_dividend_payout_em", {}
    )
    hk_gxl_params = AkshareScriptService._apply_safe_default_parameters("stock_hk_gxl_lg", {})
    recommend_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_institute_recommend", {}
    )
    intraday_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_intraday_em", {}
    )
    intraday_sina_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_intraday_sina", {}
    )

    assert a_code_params["_call_timeout"] == 60
    assert bj_code_params["_call_timeout"] == 60
    assert individual_info_params["symbol"] == "000001"
    assert individual_info_params["timeout"] == 20
    assert individual_info_params["_call_timeout"] == 60
    assert bid_ask_params["symbol"] == "000001"
    assert bid_ask_params["_call_timeout"] == 60
    assert xq_params["symbol"] == "SH600519"
    assert xq_params["timeout"] == 20
    assert hk_xq_params["symbol"] == "00700"
    assert hk_xq_params["timeout"] == 20
    assert us_xq_params["symbol"] == "NVDA"
    assert us_xq_params["timeout"] == 20
    assert industry_category_params["symbol"] == "巨潮行业分类标准"
    assert industry_change_params["symbol"] == "002594"
    assert industry_change_params["start_date"] == "20091227"
    assert industry_change_params["end_date"].isdigit()
    assert comment_params["_call_timeout"] == 90
    assert cyq_params["symbol"] == "600519"
    assert cyq_params["adjust"] == ""
    assert fhps_params["date"].isdigit()
    assert hkggt_params["_call_timeout"] == 60
    assert hk_dividend_params["symbol"] == "03900"
    assert hk_gxl_params["_call_timeout"] == 60
    assert recommend_params["symbol"] == "最新投资评级"
    assert intraday_params["symbol"] == "000001"
    assert intraday_sina_params["symbol"] == "sz000001"


def test_recoverable_stock_event_and_margin_scripts_have_defaults():
    for script_id in (
        "stock_register_bj",
        "stock_register_cyb",
        "stock_register_db",
        "stock_register_kcb",
        "stock_register_sh",
        "stock_register_sz",
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["_call_timeout"] == 60

    restricted_detail_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_restricted_release_detail_em", {}
    )
    restricted_queue_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_restricted_release_queue_em", {}
    )
    ggcg_params = AkshareScriptService._apply_safe_default_parameters("stock_ggcg_em", {})
    margin_ratio_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_margin_ratio_pa", {}
    )
    xgsglb_params = AkshareScriptService._apply_safe_default_parameters("stock_xgsglb_em", {})

    assert restricted_detail_params["start_date"].isdigit()
    assert restricted_detail_params["end_date"].isdigit()
    assert restricted_detail_params["_call_timeout"] == 60
    assert restricted_queue_params["symbol"] == "600000"
    assert ggcg_params["symbol"] == "全部"
    assert ggcg_params["max_pages"] == 1
    assert margin_ratio_params["symbol"] == "深市"
    assert margin_ratio_params["date"].isdigit()
    assert xgsglb_params["symbol"] == "全部股票"

    for script_id in (
        "stock_dzjy_sctj",
        "stock_esg_msci_sina",
        "stock_gddh_em",
        "stock_margin_account_info",
        "stock_pg_em",
        "stock_qbzf_em",
        "stock_zh_ab_comparison_em",
        "stock_zh_ah_name",
        "stock_zh_a_new",
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["_call_timeout"] >= 60

    for script_id, symbol in (
        ("stock_dzjy_hygtj", "近三月"),
        ("stock_dzjy_hyyybtj", "近3日"),
        ("stock_dzjy_yybph", "近三月"),
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["symbol"] == symbol
        assert params["_call_timeout"] == 60


def test_recoverable_stock_shareholder_scripts_have_defaults():
    free_analyse_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_gdfx_free_holding_analyse_em", {}
    )
    free_change_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_gdfx_free_holding_change_em", {}
    )
    free_detail_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_gdfx_free_holding_detail_em", {}
    )
    free_statistics_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_gdfx_free_holding_statistics_em", {}
    )
    free_teamwork_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_gdfx_free_holding_teamwork_em", {}
    )
    holding_analyse_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_gdfx_holding_analyse_em", {}
    )
    holding_change_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_gdfx_holding_change_em", {}
    )
    holding_detail_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_gdfx_holding_detail_em", {}
    )
    holding_statistics_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_gdfx_holding_statistics_em", {}
    )
    teamwork_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_gdfx_holding_teamwork_em", {}
    )
    top10_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_gdfx_top_10_em", {}
    )
    institute_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_institute_hold_detail", {}
    )
    management_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hold_management_detail_cninfo", {}
    )

    assert free_analyse_params["date"].isdigit()
    assert free_analyse_params["max_pages"] == 1
    assert free_change_params["date"] == free_analyse_params["date"]
    assert free_change_params["max_pages"] == 1
    assert free_detail_params["date"].isdigit()
    assert free_detail_params["max_pages"] == 1
    assert free_statistics_params["date"] == free_analyse_params["date"]
    assert free_statistics_params["max_pages"] == 1
    assert free_teamwork_params["symbol"] == "社保"
    assert free_teamwork_params["max_pages"] == 1
    assert holding_analyse_params["date"] == free_detail_params["date"]
    assert holding_analyse_params["max_pages"] == 1
    assert holding_change_params["date"] == free_detail_params["date"]
    assert holding_change_params["max_pages"] == 1
    assert holding_detail_params["indicator"] == "个人"
    assert holding_detail_params["symbol"] == "新进"
    assert holding_detail_params["max_pages"] == 1
    assert holding_statistics_params["date"] == free_analyse_params["date"]
    assert holding_statistics_params["max_pages"] == 1
    assert teamwork_params["symbol"] == "社保"
    assert teamwork_params["max_pages"] == 1
    assert top10_params["symbol"] == "sh600519"
    assert top10_params["date"] == free_detail_params["date"]
    assert institute_params["stock"] == "600519"
    assert institute_params["quarter"].isdigit()
    assert management_params["symbol"] == "增持"

    for script in (
        StockGdfxFreeHoldingAnalyseEm(),
        StockGdfxFreeHoldingChangeEm(),
        StockGdfxFreeHoldingStatisticsEm(),
        StockGdfxFreeHoldingTeamworkEm(),
        StockGdfxHoldingStatisticsEm(),
    ):
        assert "UNIQUE KEY uk_symbol_date" not in script.create_table_sql
        assert "INDEX idx_symbol_date (`symbol`, `data_date`)" in script.create_table_sql

    for script_id, symbol in (
        ("stock_share_hold_change_bse", "430489"),
        ("stock_share_hold_change_sse", "600000"),
        ("stock_shareholder_change_ths", "688981"),
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["symbol"] == symbol
        assert params["_call_timeout"] == 60


def test_recoverable_stock_feature_and_profile_scripts_have_defaults():
    pledge_detail_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_gpzy_pledge_ratio_detail_em", {}
    )
    pledge_ratio_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_gpzy_pledge_ratio_em", {}
    )
    gsrl_params = AkshareScriptService._apply_safe_default_parameters("stock_gsrl_gsdt_em", {})
    hk_fhpx_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hk_fhpx_detail_ths", {}
    )
    sy_params = AkshareScriptService._apply_safe_default_parameters("stock_sy_em", {})
    sy_hy_params = AkshareScriptService._apply_safe_default_parameters("stock_sy_hy_em", {})
    sy_jz_params = AkshareScriptService._apply_safe_default_parameters("stock_sy_jz_em", {})
    tfp_params = AkshareScriptService._apply_safe_default_parameters("stock_tfp_em", {})
    yzxdr_params = AkshareScriptService._apply_safe_default_parameters("stock_yzxdr_em", {})
    zdht_params = AkshareScriptService._apply_safe_default_parameters("stock_zdhtmx_em", {})
    zygc_params = AkshareScriptService._apply_safe_default_parameters("stock_zygc_em", {})
    zyjs_params = AkshareScriptService._apply_safe_default_parameters("stock_zyjs_ths", {})
    sector_params = AkshareScriptService._apply_safe_default_parameters("stock_sector_detail", {})

    assert pledge_detail_params["max_pages"] == 1
    assert pledge_ratio_params["date"] == "20240906"
    assert pledge_ratio_params["_call_timeout"] == 90
    assert gsrl_params["date"].isdigit()
    assert hk_fhpx_params["symbol"] == "0700"
    assert sy_params["date"].isdigit()
    assert sy_params["_call_timeout"] == 90
    assert sy_hy_params["date"] == sy_params["date"]
    assert sy_jz_params["date"] == sy_params["date"]
    assert tfp_params["date"].isdigit()
    assert yzxdr_params["date"] == sy_params["date"]
    assert zdht_params["start_date"].isdigit()
    assert zdht_params["end_date"].isdigit()
    assert int(zdht_params["end_date"]) - int(zdht_params["start_date"]) > 10000
    assert zygc_params["symbol"] == "SH600519"
    assert zyjs_params["symbol"] == "600519"
    assert sector_params["sector"] == "gn_gfgn"

    for script_id in ("stock_ebs_lg", "stock_gpzy_profile_em"):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["_call_timeout"] == 60


def test_recoverable_stock_static_and_comparison_scripts_have_defaults():
    gdhs_params = AkshareScriptService._apply_safe_default_parameters("stock_zh_a_gdhs", {})
    gbjg_params = AkshareScriptService._apply_safe_default_parameters("stock_zh_a_gbjg_em", {})
    gdhs_detail_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_zh_a_gdhs_detail_em", {}
    )
    growth_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_zh_growth_comparison_em", {}
    )
    scale_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_zh_scale_comparison_em", {}
    )
    valuation_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_zh_valuation_baidu", {}
    )
    valuation_comparison_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_zh_valuation_comparison_em", {}
    )
    index_value_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_zh_index_value_csindex", {}
    )

    assert gdhs_params["symbol"].isdigit()
    assert gdhs_params["max_pages"] == 1
    assert gbjg_params["symbol"] == "600519.SH"
    assert gdhs_detail_params["symbol"] == "000001"
    assert growth_params["symbol"] == "SZ000895"
    assert scale_params["symbol"] == "SZ000895"
    assert valuation_params["symbol"] == "002044"
    assert valuation_params["indicator"] == "总市值"
    assert valuation_params["period"] == "近一年"
    assert valuation_comparison_params["symbol"] == "SZ000895"
    assert index_value_params["symbol"] == "H30374"

    for script_id in (
        "stock_sgt_reference_exchange_rate_sse",
        "stock_sgt_reference_exchange_rate_szse",
        "stock_sgt_settlement_exchange_rate_sse",
        "stock_sgt_settlement_exchange_rate_szse",
        "stock_staq_net_stop",
    ):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["_call_timeout"] == 60


def test_recoverable_stock_hot_lhb_and_rank_scripts_have_defaults():
    hot_search_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hot_search_baidu", {}
    )
    hot_tweet_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hot_tweet_xq", {}
    )
    hot_follow_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hot_follow_xq", {}
    )
    hot_up_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hot_up_em", {}
    )
    hk_hot_rank_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hk_hot_rank_em", {}
    )
    lhb_jg_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_lhb_jgstatistic_em", {}
    )
    yyb_detail_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_lhb_yyb_detail_em", {}
    )
    yybph_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_lhb_yybph_em", {}
    )
    yytj_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_lhb_yytj_sina", {}
    )
    cxd_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_rank_cxd_ths", {}
    )
    xstp_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_rank_xstp_ths", {}
    )
    xxtp_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_rank_xxtp_ths", {}
    )
    fund_flow_rank_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_individual_fund_flow_rank", {}
    )

    assert hot_search_params["symbol"] == "A股"
    assert hot_search_params["date"].isdigit()
    assert hot_search_params["time"] == "今日"
    assert hot_tweet_params["symbol"] == "最热门"
    assert hot_tweet_params["max_pages"] == 1
    assert hot_follow_params["symbol"] == "最热门"
    assert hot_follow_params["max_pages"] == 30
    assert hot_follow_params["_call_timeout"] >= 90
    assert hot_up_params["page_size"] == 100
    assert hot_up_params["_call_timeout"] >= 60
    assert hk_hot_rank_params["page_size"] == 100
    assert hk_hot_rank_params["_call_timeout"] >= 60
    assert lhb_jg_params["symbol"] == "近一月"
    assert yyb_detail_params["symbol"] == "10188715"
    assert yybph_params["symbol"] == "近一月"
    assert yytj_params["symbol"] == "5"
    assert cxd_params["symbol"] == "创月新低"
    assert cxd_params["max_pages"] == 1
    assert xstp_params["symbol"] == "500日均线"
    assert xxtp_params["symbol"] == "500日均线"
    assert fund_flow_rank_params["indicator"] == "今日"
    assert fund_flow_rank_params["_call_timeout"] >= 180

    for script_id in ("stock_lhb_yytj_sina",):
        params = AkshareScriptService._apply_safe_default_parameters(script_id, {})

        assert params["_call_timeout"] >= 60

    main_flow_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_main_fund_flow", {}
    )
    assert main_flow_params["symbol"] == "全部股票"
    assert main_flow_params["_call_timeout"] >= 240


def test_stock_rank_cxd_ths_populates_standard_columns():
    df = pd.DataFrame(
        {
            "序号": [1],
            "股票代码": ["16"],
            "股票简称": [" *ST康佳A "],
            "涨跌幅": ["-4.48%"],
            "换手率": ["1.92%"],
            "最新价": ["2.56"],
            "前期低点": ["2.68"],
            "前期低点日期": ["2026-06-18"],
        }
    )

    mapped = StockRankCxdThs.normalize_columns(df)

    assert mapped["symbol"].tolist() == ["000016"]
    assert mapped["name"].tolist() == ["*ST康佳A"]
    assert mapped["data_date"].astype(str).tolist() == ["2026-06-18"]
    assert mapped["涨跌幅"].tolist() == [-4.48]


def test_stock_main_fund_flow_populates_standard_columns():
    df = pd.DataFrame(
        {
            "代码": ["1", "688496"],
            "名称": [" 平安银行 ", "*ST清越"],
            "最新价": [11.25, 1.06],
        }
    )

    mapped = StockMainFundFlow.normalize_columns(df)

    assert mapped["symbol"].tolist() == ["000001", "688496"]
    assert mapped["name"].tolist() == ["平安银行", "*ST清越"]
    assert "代码" in mapped.columns
    assert "名称" in mapped.columns


def test_stock_individual_fund_flow_rank_populates_standard_columns():
    df = pd.DataFrame(
        {
            "代码": ["59", "600030"],
            "名称": [" 东方财富 ", "中信证券"],
            "今日主力净流入-净额": [3671633152.0, 1863331280.0],
        }
    )

    mapped = StockIndividualFundFlowRank.normalize_columns(df, indicator="今日")

    assert mapped["symbol"].tolist() == ["000059", "600030"]
    assert mapped["name"].tolist() == ["东方财富", "中信证券"]
    assert mapped["indicator"].tolist() == ["今日", "今日"]
    assert "今日主力净流入-净额" in mapped.columns


def test_slow_stock_repurchase_schedule_and_xgsr_scripts_have_defaults_and_mappings():
    repurchase_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_repurchase_em", {}
    )
    schedule_params = AkshareScriptService._apply_safe_default_parameters("stock_yysj_em", {})
    xgsr_params = AkshareScriptService._apply_safe_default_parameters("stock_xgsr_ths", {})

    assert repurchase_params["_call_timeout"] >= 240
    assert schedule_params["_call_timeout"] >= 240
    assert xgsr_params["_call_timeout"] >= 240

    repurchase_df = pd.DataFrame(
        {
            "股票代码": ["5066", "003000"],
            "股票简称": [" 天正电气 ", "劲仔食品"],
            "最新公告日期": ["2026-06-23", "2026-06-22"],
        }
    )
    repurchase_mapped = StockRepurchaseEm.normalize_columns(repurchase_df)
    assert repurchase_mapped["symbol"].tolist() == ["005066", "003000"]
    assert repurchase_mapped["name"].tolist() == ["天正电气", "劲仔食品"]
    assert repurchase_mapped["data_date"].astype(str).tolist() == [
        "2026-06-23",
        "2026-06-22",
    ]

    schedule_df = pd.DataFrame(
        {
            "股票代码": ["2007", "600396"],
            "股票简称": [" 华兰生物 ", "华电辽能"],
            "实际披露时间": ["2020-04-08", "2020-04-09"],
        }
    )
    schedule_mapped = StockYysjEm.normalize_columns(schedule_df)
    assert schedule_mapped["symbol"].tolist() == ["002007", "600396"]
    assert schedule_mapped["name"].tolist() == ["华兰生物", "华电辽能"]
    assert schedule_mapped["data_date"].astype(str).tolist() == [
        "2020-04-08",
        "2020-04-09",
    ]

    xgsr_df = pd.DataFrame(
        {
            "股票代码": ["920126", "1669"],
            "股票简称": ["永大股份", " 高特电子 "],
            "上市日期": ["2026-06-15", "2026-06-09"],
        }
    )
    xgsr_mapped = StockXgsrThs.normalize_columns(xgsr_df)
    assert xgsr_mapped["symbol"].tolist() == ["920126", "001669"]
    assert xgsr_mapped["name"].tolist() == ["永大股份", "高特电子"]
    assert xgsr_mapped["data_date"].astype(str).tolist() == [
        "2026-06-15",
        "2026-06-09",
    ]


def test_stock_jgdy_detail_has_bounded_defaults_and_standard_columns():
    params = AkshareScriptService._apply_safe_default_parameters("stock_jgdy_detail_em", {})

    assert params["date"] == "20240601"
    assert params["max_pages"] == 3
    assert params["_call_timeout"] >= 90

    df = pd.DataFrame(
        {
            "代码": ["1314", "300750"],
            "名称": [" 亿道信息 ", "宁德时代"],
            "调研日期": ["2026-06-22", "2026-06-21"],
            "调研机构": ["安宏基投资", "某机构"],
        }
    )
    mapped = StockJgdyDetailEm.normalize_columns(df)

    assert mapped["symbol"].tolist() == ["001314", "300750"]
    assert mapped["name"].tolist() == ["亿道信息", "宁德时代"]
    assert mapped["data_date"].astype(str).tolist() == ["2026-06-22", "2026-06-21"]
    assert "调研机构" in mapped.columns


def test_stock_jgdy_tj_has_bounded_defaults_and_standard_columns():
    params = AkshareScriptService._apply_safe_default_parameters("stock_jgdy_tj_em", {})

    assert params["date"] == "20240601"
    assert params["max_pages"] == 3
    assert params["_call_timeout"] >= 120

    script = StockJgdyTjEm()
    assert "UNIQUE KEY uk_symbol_date" not in script.create_table_sql
    assert "INDEX idx_symbol_date (`symbol`, `data_date`)" in script.create_table_sql

    df = pd.DataFrame(
        {
            "代码": ["1298", "300750"],
            "名称": [" 好上好 ", "宁德时代"],
            "接待日期": ["2026-06-20", "2026-06-19"],
            "接待机构数量": [24, 100],
        }
    )
    mapped = StockJgdyTjEm.normalize_columns(df)

    assert mapped["symbol"].tolist() == ["001298", "300750"]
    assert mapped["name"].tolist() == ["好上好", "宁德时代"]
    assert mapped["data_date"].astype(str).tolist() == ["2026-06-20", "2026-06-19"]
    assert "接待机构数量" in mapped.columns


def test_stock_sns_sseinfo_has_bounded_defaults_and_standard_columns():
    params = AkshareScriptService._apply_safe_default_parameters("stock_sns_sseinfo", {})

    assert params["symbol"] == "600000"
    assert params["uid"] == "65"
    assert params["max_pages"] == 3
    assert params["_call_timeout"] >= 120

    script = StockSnsSseinfo()
    assert "UNIQUE KEY uk_symbol_date" not in script.create_table_sql
    assert "INDEX idx_symbol_date (`symbol`, `data_date`)" in script.create_table_sql

    df = pd.DataFrame(
        {
            "股票代码": ["603119", "688001"],
            "公司简称": [" 浙江荣泰 ", "华兴源创"],
            "问题时间": ["2026年06月18日 13:10", "2026-06-17 09:30"],
            "问题": ["问题A", "问题B"],
        }
    )
    mapped = StockSnsSseinfo.normalize_columns(df)

    assert mapped["symbol"].tolist() == ["603119", "688001"]
    assert mapped["name"].tolist() == ["浙江荣泰", "华兴源创"]
    assert mapped["data_date"].astype(str).tolist() == ["2026-06-18", "2026-06-17"]
    assert "问题" in mapped.columns


def test_slow_esg_scripts_have_defaults_and_standard_columns():
    hz_params = AkshareScriptService._apply_safe_default_parameters("stock_esg_hz_sina", {})
    rate_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_esg_rate_sina", {}
    )
    zd_params = AkshareScriptService._apply_safe_default_parameters("stock_esg_zd_sina", {})

    assert hz_params["_call_timeout"] >= 300
    assert rate_params["max_pages"] == 3
    assert rate_params["_call_timeout"] >= 180
    assert zd_params["_call_timeout"] >= 300

    hz_df = pd.DataFrame(
        {
            "股票代码": ["1", "600519"],
            "股票名称": [" 平安银行 ", "贵州茅台"],
            "日期": ["2025-12-31", "2025-12-30"],
        }
    )
    hz_mapped = StockEsgHzSina.normalize_columns(hz_df)
    assert hz_mapped["symbol"].tolist() == ["000001", "600519"]
    assert hz_mapped["name"].tolist() == ["平安银行", "贵州茅台"]
    assert hz_mapped["data_date"].astype(str).tolist() == ["2025-12-31", "2025-12-30"]

    rate_df = pd.DataFrame(
        {
            "成分股代码": ["2", "300750"],
            "评级机构": ["机构A", "机构B"],
            "评级季度": ["2025Q4", "2025Q4"],
        }
    )
    rate_mapped = StockEsgRateSina.normalize_columns(rate_df)
    assert rate_mapped["symbol"].tolist() == ["000002", "300750"]
    assert rate_mapped["name"].tolist() == ["机构A", "机构B"]
    assert rate_mapped["data_date"].notna().all()

    zd_df = pd.DataFrame(
        {
            "股票代码": ["333", "688001"],
            "评分日期": ["2025-12-31", "2025-12-30"],
            "ESG评分": [80, 75],
        }
    )
    zd_mapped = StockEsgZdSina.normalize_columns(zd_df)
    assert zd_mapped["symbol"].tolist() == ["000333", "688001"]
    assert zd_mapped["data_date"].astype(str).tolist() == ["2025-12-31", "2025-12-30"]


def test_recoverable_realtime_gap_scripts_have_explicit_defaults():
    foreign_params = AkshareScriptService._apply_safe_default_parameters(
        "futures_foreign_commodity_realtime", {}
    )
    futures_spot_params = AkshareScriptService._apply_safe_default_parameters(
        "futures_zh_spot", {}
    )
    bj_params = AkshareScriptService._apply_safe_default_parameters("stock_bj_a_spot_em", {})
    concept_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_board_concept_spot_em", {}
    )
    cy_params = AkshareScriptService._apply_safe_default_parameters("stock_cy_a_spot_em", {})
    hk_main_params = AkshareScriptService._apply_safe_default_parameters(
        "stock_hk_main_board_spot_em", {}
    )
    hk_params = AkshareScriptService._apply_safe_default_parameters("stock_hk_spot", {})
    hk_em_params = AkshareScriptService._apply_safe_default_parameters("stock_hk_spot_em", {})
    sh_params = AkshareScriptService._apply_safe_default_parameters("stock_sh_a_spot_em", {})
    sz_params = AkshareScriptService._apply_safe_default_parameters("stock_sz_a_spot_em", {})
    us_em_params = AkshareScriptService._apply_safe_default_parameters("stock_us_spot_em", {})
    zh_params = AkshareScriptService._apply_safe_default_parameters("stock_zh_a_spot", {})
    zh_em_params = AkshareScriptService._apply_safe_default_parameters("stock_zh_a_spot_em", {})

    assert foreign_params["_call_timeout"] == 60
    assert futures_spot_params["symbol"] == "RB0"
    assert futures_spot_params["market"] == "CF"
    assert futures_spot_params["adjust"] == "0"
    assert futures_spot_params["_call_timeout"] == 30
    assert bj_params["_call_timeout"] == 120
    assert concept_params["symbol"] == "数据要素"
    assert concept_params["_call_timeout"] == 120
    assert cy_params["_call_timeout"] == 180
    assert hk_main_params["_call_timeout"] == 180
    assert hk_params["_call_timeout"] == 120
    assert hk_em_params["_call_timeout"] == 180
    assert sh_params["_call_timeout"] == 180
    assert sz_params["_call_timeout"] == 180
    assert us_em_params["max_pages"] == 1
    assert us_em_params["_call_timeout"] == 60
    assert zh_params["_call_timeout"] == 90
    assert zh_em_params["_call_timeout"] == 240


def test_stock_us_spot_em_populates_standard_columns():
    df = pd.DataFrame(
        {
            "代码": ["105.MSFT"],
            "名称": [" Microsoft "],
            "最新价": ["450.1"],
            "涨跌幅": ["1.2"],
        }
    )

    mapped = StockUsSpotEm.normalize_columns(df)

    assert mapped["symbol"].tolist() == ["105.MSFT"]
    assert mapped["name"].tolist() == ["Microsoft"]
    assert mapped["最新价"].tolist() == [450.1]
    assert "data_date" in mapped.columns


def test_stock_us_hist_min_em_preserves_intraday_rows():
    df = pd.DataFrame(
        {
            "时间": ["2026-06-18 21:30:00", "2026-06-18 21:31:00"],
            "开盘": ["298.44", "298.39"],
            "收盘": ["298.39", "299.68"],
            "最高": ["298.44", "299.75"],
            "最低": ["298.155", "298.07"],
            "成交量": ["683088", "10437130"],
            "成交额": ["203275700", "3115194000"],
            "最新价": ["297.5835", "298.4175"],
        }
    )

    mapped = StockUsHistMinEm.normalize_columns(df, symbol="105.AAPL")

    assert "UNIQUE KEY uk_symbol_date" not in StockUsHistMinEm().create_table_sql
    assert mapped["symbol"].tolist() == ["105.AAPL", "105.AAPL"]
    assert mapped["name"].tolist() == ["105.AAPL", "105.AAPL"]
    assert mapped["data_date"].astype(str).tolist() == ["2026-06-18", "2026-06-18"]
    assert mapped["开盘"].tolist() == [298.44, 298.39]


def test_option_current_em_populates_unique_standard_symbol():
    df = pd.DataFrame(
        {
            "市场标识": [151],
            "代码": ["ni2609C184000"],
            "名称": [" 沪镍26年09月购184000 "],
            "最新价": ["276"],
            "成交量": ["51"],
        }
    )

    mapped = OptionCurrentEm.normalize_columns(df)

    assert mapped["symbol"].tolist() == ["151.ni2609C184000"]
    assert mapped["name"].tolist() == ["沪镍26年09月购184000"]
    assert mapped["最新价"].tolist() == [276]
    assert "data_date" in mapped.columns


def test_option_minute_em_preserves_intraday_rows():
    df = pd.DataFrame(
        {
            "time": ["2026-06-22 09:00", "2026-06-22 09:01"],
            "close": ["2", "2.5"],
            "high": ["2", "2.5"],
            "low": ["2", "2"],
            "volume": ["0", "10"],
            "amount": ["0", "25"],
            "symbol": ["151.ni2609C184000", "151.ni2609C184000"],
            "name": [" 沪镍26年09月购184000 ", "沪镍26年09月购184000"],
        }
    )

    mapped = OptionMinuteEm.normalize_columns(df)

    assert "UNIQUE KEY uk_symbol_date" not in OptionMinuteEm().create_table_sql
    assert mapped["symbol"].tolist() == ["151.ni2609C184000", "151.ni2609C184000"]
    assert mapped["data_date"].astype(str).tolist() == ["2026-06-22", "2026-06-22"]
    assert mapped["close"].tolist() == [2.0, 2.5]


def test_stock_hot_rank_em_populates_standard_columns():
    df = pd.DataFrame(
        {
            "当前排名": ["1"],
            "代码": ["SZ300059"],
            "股票名称": [" 东方财富 "],
            "最新价": ["20.97"],
            "涨跌幅": ["1.5"],
        }
    )

    mapped = StockHotRankEm.normalize_columns(df)

    assert mapped["symbol"].tolist() == ["SZ300059"]
    assert mapped["name"].tolist() == ["东方财富"]
    assert mapped["当前排名"].tolist() == [1]
    assert mapped["最新价"].tolist() == [20.97]
    assert "data_date" in mapped.columns


def test_stock_hot_up_em_populates_standard_columns():
    df = pd.DataFrame(
        {
            "排名较昨日变动": ["4732"],
            "当前排名": ["470"],
            "代码": ["SZ920790"],
            "股票名称": [" 联迪信息 "],
            "最新价": ["26.1"],
            "涨跌幅": ["29.98"],
        }
    )

    mapped = StockHotUpEm.normalize_columns(df)

    assert mapped["symbol"].tolist() == ["SZ920790"]
    assert mapped["name"].tolist() == ["联迪信息"]
    assert mapped["排名较昨日变动"].tolist() == [4732]
    assert mapped["最新价"].tolist() == [26.1]
    assert "data_date" in mapped.columns


def test_stock_hk_hot_rank_em_populates_standard_columns():
    df = pd.DataFrame(
        {
            "当前排名": ["1"],
            "代码": ["00700"],
            "股票名称": [" 腾讯控股 "],
            "最新价": ["433"],
            "涨跌幅": ["-1.64"],
        }
    )

    mapped = StockHkHotRankEm.normalize_columns(df)

    assert mapped["symbol"].tolist() == ["00700"]
    assert mapped["name"].tolist() == ["腾讯控股"]
    assert mapped["当前排名"].tolist() == [1]
    assert mapped["最新价"].tolist() == [433]
    assert "data_date" in mapped.columns


def test_stock_hot_follow_xq_populates_standard_columns():
    df = pd.DataFrame(
        {
            "股票代码": ["SH600519"],
            "股票简称": [" 贵州茅台 "],
            "关注": ["3659967"],
            "最新价": ["1241.41"],
        }
    )

    mapped = StockHotFollowXq.normalize_columns(df)

    assert mapped["symbol"].tolist() == ["SH600519"]
    assert mapped["name"].tolist() == ["贵州茅台"]
    assert mapped["关注"].tolist() == [3659967]
    assert mapped["最新价"].tolist() == [1241.41]
    assert "data_date" in mapped.columns


def test_stock_individual_info_em_preserves_item_rows_with_standard_columns():
    df = pd.DataFrame(
        {
            "item": ["股票代码", "股票简称", "行业"],
            "value": ["000001", " 平安银行 ", "银行"],
        }
    )

    mapped = StockIndividualInfoEm.normalize_columns(df)

    assert "UNIQUE KEY uk_symbol_date" not in StockIndividualInfoEm().create_table_sql
    assert mapped["symbol"].tolist() == ["000001", "000001", "000001"]
    assert mapped["name"].tolist() == ["平安银行", "平安银行", "平安银行"]
    assert "data_date" in mapped.columns


def test_stock_bid_ask_em_preserves_item_rows_with_standard_columns():
    df = pd.DataFrame(
        {
            "item": ["sell_1", "buy_1"],
            "value": ["10.65", "10.64"],
            "symbol": ["000001", "000001"],
            "name": [" 平安银行 ", "平安银行"],
        }
    )

    mapped = StockBidAskEm.normalize_columns(df)

    assert "UNIQUE KEY uk_symbol_date" not in StockBidAskEm().create_table_sql
    assert mapped["symbol"].tolist() == ["000001", "000001"]
    assert mapped["name"].tolist() == ["平安银行", "平安银行"]
    assert mapped["value"].tolist() == [10.65, 10.64]
    assert "data_date" in mapped.columns


def test_foreign_commodity_realtime_accepts_list_symbol_catalog():
    assert FuturesForeignCommodityRealtime._extract_symbol_codes(["GC", "SI", None]) == [
        "GC",
        "SI",
    ]


def test_stock_intraday_sina_does_not_collapse_ticks_by_day():
    assert "UNIQUE KEY uk_symbol_date" not in StockIntradaySina().create_table_sql
    assert "INDEX idx_symbol_date (`symbol`, `data_date`)" in StockIntradaySina().create_table_sql


def test_recoverable_hk_indicator_has_explicit_symbol():
    params = AkshareScriptService._apply_safe_default_parameters("stock_hk_indicator_eniu", {})

    assert params["symbol"] == "hk01093"
    assert params["indicator"] == "市盈率"
    assert params["_call_timeout"] == 90


def test_long_minute_fund_defaults_do_not_override_explicit_codes():
    params = AkshareScriptService._apply_safe_default_parameters(
        "etf_minute_hist_em",
        {"max_codes": 3},
    )

    assert params["max_codes"] == 3
