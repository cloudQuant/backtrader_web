"""
Integration tests for akshare data management APIs.
"""

import asyncio
import inspect
import sys
import time
from datetime import datetime
from types import ModuleType

import pandas as pd
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db.database import async_session_maker, create_default_admin
from app.models.akshare_mgmt import DataTable, TaskExecution, TaskStatus, TriggeredBy
from app.models.akshare_mgmt import DataScript
from app.services.akshare.data import AkshareDataService
from app.services.akshare.execution import AkshareExecutionService
from app.services.akshare.script import AkshareScriptService

settings = get_settings()


async def get_admin_headers(client: AsyncClient) -> dict[str, str]:
    await create_default_admin()
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD,
        },
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture
def dummy_akshare_module() -> ModuleType:
    module = ModuleType("akshare")
    large_default_values = [f"symbol_{index:03d}" for index in range(80)]

    def stock_zh_a_hist(**_: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "日期": "2024-01-02",
                    "开盘": 10.0,
                    "收盘": 10.5,
                    "最高": 10.8,
                    "最低": 9.9,
                    "成交量": 1000,
                },
                {
                    "日期": "2024-01-03",
                    "开盘": 10.5,
                    "收盘": 10.2,
                    "最高": 10.7,
                    "最低": 10.1,
                    "成交量": 900,
                },
            ]
        )

    def stock_zh_a_spot() -> pd.DataFrame:
        return pd.DataFrame([{"symbol": "000001", "name": "PingAn"}])

    def stock_big_default(vars_list=large_default_values) -> pd.DataFrame:
        return pd.DataFrame([{"symbol": "000001"}])

    module.stock_zh_a_hist = stock_zh_a_hist
    module.stock_zh_a_spot = stock_zh_a_spot
    module.stock_big_default = stock_big_default
    return module


@pytest.fixture
async def warehouse_engine(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    import app.db.akshare_data_database as akshare_db_module

    monkeypatch.setattr(akshare_db_module, "_akshare_data_engine", engine)
    monkeypatch.setattr(akshare_db_module, "_akshare_data_session_maker", None)

    yield engine
    await engine.dispose()


def test_akshare_data_database_url_falls_back_to_mysql_database_url(monkeypatch):
    import app.db.akshare_data_database as akshare_db_module

    monkeypatch.setattr(akshare_db_module.settings, "AKSHARE_DATA_DATABASE_URL", "")
    monkeypatch.setattr(
        akshare_db_module.settings,
        "DATABASE_URL",
        "mysql+aiomysql://root:secret@127.0.0.1:3306/backtrader_web?charset=utf8mb4",
    )

    resolved_url = akshare_db_module._resolve_akshare_data_database_url()

    assert resolved_url is not None
    assert resolved_url.drivername == "mysql+aiomysql"
    assert resolved_url.username == "root"
    assert resolved_url.password == "secret"
    assert resolved_url.host == "127.0.0.1"
    assert resolved_url.port == 3306
    assert resolved_url.database == "akshare_data"
    assert resolved_url.query == {"charset": "utf8mb4"}


def test_data_fetch_db_config_falls_back_to_mysql_database_url(monkeypatch):
    import app.data_fetch.configs.db_config as db_config_module

    monkeypatch.setattr(db_config_module.settings, "AKSHARE_DATA_DATABASE_URL", "")
    monkeypatch.setattr(
        db_config_module.settings,
        "DATABASE_URL",
        "mysql+aiomysql://root:secret@127.0.0.1:3307/backtrader_web?charset=utf8mb4",
    )

    config = db_config_module._build_db_config()

    assert config == {
        "host": "127.0.0.1",
        "user": "root",
        "password": "secret",
        "database": "akshare_data",
        "port": 3307,
    }


@pytest.mark.asyncio
async def test_table_preview_returns_empty_state_when_warehouse_unavailable(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch,
):
    import app.services.akshare.data as akshare_data_service_module

    monkeypatch.setattr(akshare_data_service_module, "_get_akshare_data_engine", lambda: None)

    async with async_session_maker() as session:
        session.add(
            DataTable(
                id=1292,
                table_name="STOCK_HK_DAILY",
                table_comment="港股日线",
                category="stocks",
                row_count=21561,
                metadata_json={"columns": ["date", "symbol", "close"]},
            )
        )
        await session.commit()

    rows_resp = await client.get("/api/v1/data/tables/1292/data", headers=auth_headers)
    assert rows_resp.status_code == 200
    rows_data = rows_resp.json()
    assert rows_data["table_name"] == "STOCK_HK_DAILY"
    assert rows_data["columns"] == ["date", "symbol", "close"]
    assert rows_data["rows"] == []
    assert rows_data["total"] == 0
    assert rows_data["data_available"] is False
    assert rows_data["error"] == "Akshare data warehouse is not configured"

    schema_resp = await client.get("/api/v1/data/tables/1292/schema", headers=auth_headers)
    assert schema_resp.status_code == 200
    schema_data = schema_resp.json()
    assert [column["name"] for column in schema_data["columns"]] == ["date", "symbol", "close"]
    assert schema_data["data_available"] is False
    assert schema_data["error"] == "Akshare data warehouse is not configured"


def test_run_script_accepts_json_string_parameters():
    params = AkshareScriptService._normalize_parameters('{"symbol": "000001"}')

    assert params == {"symbol": "000001"}


def test_run_script_accepts_double_encoded_json_string_parameters():
    params = AkshareScriptService._normalize_parameters('"{}"')

    assert params == {}


def test_run_script_does_not_apply_implicit_runtime_sample_limits():
    params = AkshareScriptService._apply_safe_default_parameters("amac_fund_info", {})

    assert params == {}

    for script_id in (
        "daily_market_data",
        "etf_fund_hist_em",
        "futures_contract_info_shfe",
        "member_position_rank",
        "macro_china_nbs_nation",
        "stock_gpzy_pledge_ratio_detail_em",
        "stock_dxsyl_em",
        "trading_commissions_info",
    ):
        assert AkshareScriptService._apply_safe_default_parameters(script_id, {}) == {}

    explicit_params = {"lookback_days": 3}
    assert (
        AkshareScriptService._apply_safe_default_parameters(
            "daily_market_data", explicit_params
        )
        == explicit_params
    )


def test_run_script_applies_safe_page_defaults_for_expensive_default_tasks():
    assert AkshareScriptService._apply_safe_default_parameters(
        "stock_hold_management_detail_em", {}
    ) == {"max_pages": 5}
    assert AkshareScriptService._apply_safe_default_parameters(
        "stock_share_hold_change_szse", {}
    ) == {"max_pages": 10}
    assert AkshareScriptService._apply_safe_default_parameters(
        "stock_zh_kcb_report_em", {}
    ) == {"to_page": 10}
    assert AkshareScriptService._apply_safe_default_parameters(
        "stock_gdfx_holding_change_em", {}
    ) == {"max_pages": 1}
    assert AkshareScriptService._apply_safe_default_parameters(
        "stock_hot_deal_xq", {}
    ) == {"max_pages": 1}

    explicit_params = {"max_pages": 99}
    assert (
        AkshareScriptService._apply_safe_default_parameters(
            "stock_hold_management_detail_em", explicit_params
        )
        == explicit_params
    )


def test_incremental_legacy_scripts_default_to_full_update_ranges():
    from app.data_fetch.scripts.funds.daily.etf_minute_hist_em import EtfMinuteHistEm
    from app.data_fetch.scripts.funds.daily.lof_minute_hist_em import LofMinuteHistEm
    from app.data_fetch.scripts.funds.weekly.etf_fund_hist_em import EtfFundHistEm
    from app.data_fetch.scripts.funds.weekly.fund_detail_info import FundDetailInfoXq
    from app.data_fetch.scripts.funds.weekly.fund_dividend_em import FundDividendEm
    from app.data_fetch.scripts.funds.weekly.fund_split_em import FundSplitEm
    from app.data_fetch.scripts.funds.weekly.graded_fund_hist_em import GradedFundHistEm
    from app.data_fetch.scripts.funds.weekly.money_fund_hist_em import MoneyFundHistEm
    from app.data_fetch.scripts.funds.weekly.open_fund_hist_em import OpenFundHistEm
    from app.data_fetch.scripts.futures.weekly.daily_market_data import FuturesDailyMarket
    from app.data_fetch.scripts.futures.weekly.futures_contract_info_cffex import (
        FuturesContractInfoCffex,
    )
    from app.data_fetch.scripts.futures.weekly.futures_contract_info_ine import (
        FuturesContractInfoIne,
    )
    from app.data_fetch.scripts.futures.weekly.futures_contract_info_shfe import (
        FuturesContractInfoShfe,
    )
    from app.data_fetch.scripts.futures.weekly.czce_delivery_data import FuturesDeliveryCzce
    from app.data_fetch.scripts.futures.weekly.member_position_rank import (
        FuturesMemberPositionRank,
    )
    from app.data_fetch.scripts.futures.weekly.rank_sum_daily import FuturesRankSumDaily
    from app.data_fetch.scripts.futures.weekly.trading_commissions_info import (
        FuturesCommissionInfo,
    )
    from app.data_fetch.scripts.futures.weekly.trading_rules import FuturesRules
    from app.data_fetch.scripts.futures.monthly.shfe_delivery_data import FuturesDeliveryShfe

    expectations = [
        (EtfMinuteHistEm.run, {"max_codes": None}),
        (EtfMinuteHistEm.update_etf_minute_data, {"max_codes": None}),
        (LofMinuteHistEm.run, {"max_codes": None}),
        (LofMinuteHistEm.update_lof_minute_data, {"max_codes": None}),
        (EtfFundHistEm.run, {"max_codes": None}),
        (FundDetailInfoXq.run, {"max_codes": None}),
        (FundDividendEm.run, {"max_codes": None}),
        (FundSplitEm.run, {"max_codes": None}),
        (GradedFundHistEm.run, {"max_codes": None, "max_pages": None}),
        (MoneyFundHistEm.run, {"max_codes": None, "max_pages": None}),
        (OpenFundHistEm.run, {"max_codes": None}),
        (FuturesDailyMarket.run, {"lookback_days": None, "max_windows": None}),
        (FuturesContractInfoCffex.run, {"lookback_days": None, "max_days": None}),
        (FuturesContractInfoIne.run, {"lookback_days": None, "max_days": None}),
        (FuturesContractInfoShfe.run, {"lookback_days": None, "max_days": None}),
        (FuturesDeliveryCzce.run, {"sleep_seconds": 0}),
        (FuturesDeliveryShfe.run, {"sleep_seconds": 0}),
        (FuturesMemberPositionRank.run, {"lookback_days": None, "max_exchanges": None}),
        (FuturesRankSumDaily.run, {"max_symbols": None, "lookback_days": None}),
        (FuturesRules.run, {"lookback_days": None, "max_days": None}),
    ]

    for func, expected_defaults in expectations:
        signature = inspect.signature(func)
        for parameter_name, expected_default in expected_defaults.items():
            assert signature.parameters[parameter_name].default is expected_default

    assert inspect.signature(FuturesCommissionInfo.run).parameters["symbol"].default == "所有"


def test_etf_fund_hist_uses_existing_latest_date_for_default_start():
    from app.data_fetch.scripts.funds.weekly.etf_fund_hist_em import EtfFundHistEm

    captured: dict[str, object] = {}
    service = object.__new__(EtfFundHistEm)
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service._get_existing_dates = lambda fund_code: {datetime(2024, 1, 5).date()}

    def fake_fetch_ak_data(endpoint, **kwargs):
        captured.update(kwargs)
        return pd.DataFrame()

    service.fetch_ak_data = fake_fetch_ak_data

    service.fetch_fund_hist_data("510050")

    assert captured["start_date"] == "20240105"


def test_open_fund_hist_runs_all_supported_indicators_by_default():
    from app.data_fetch.scripts.funds.weekly.open_fund_hist_em import OpenFundHistEm

    indicators: list[str] = []
    service = object.__new__(OpenFundHistEm)
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.cursor = None
    service.conn = None
    service.connection = None
    service.supported_indicators = ["unit_nav", "acc_nav", "rank"]
    service._get_all_fund_codes = lambda: ["000001"]
    service.create_table_if_not_exists = lambda: None

    def fake_fetch_fund_hist_data(fund_code, indicator, period):
        indicators.append(indicator)
        return pd.DataFrame()

    service.fetch_fund_hist_data = fake_fetch_fund_hist_data

    service.run()

    assert indicators == ["unit_nav", "acc_nav", "rank"]


def test_shfe_stock_weekly_empty_table_starts_from_documented_available_date():
    from app.data_fetch.scripts.futures.weekly.shfe_stock_weekly import FuturesStockWeeklyShfe

    captured: dict[str, str] = {}
    service = object.__new__(FuturesStockWeeklyShfe)
    service.table_name = "FUTURES_STOCK_WEEKLY_SHFE"
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.table_exists = lambda table_name: True
    service.get_previous_date = lambda: "2026-06-19"
    service.get_latest_date = lambda table_name, column_name: None
    service.disconnect_db = lambda: None

    def fake_get_trading_day_list(start_date, end_date):
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        return []

    service.get_trading_day_list = fake_get_trading_day_list

    service.run()

    assert captured == {"start_date": "2024-04-19", "end_date": "2026-06-19"}


def test_index_zh_a_hist_uses_latest_trade_date_and_replaces_overlap():
    from app.data_fetch.scripts.indexs.daily.index_zh_a_hist import IndexZhAHist

    calls: list[tuple[str, object]] = []
    service = object.__new__(IndexZhAHist)
    service.table_name = "INDEX_ZH_A_HIST"
    service.create_table_sql = "CREATE TABLE INDEX_ZH_A_HIST"
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service._get_latest_trade_date = lambda: "2026-02-13"
    service.create_table_if_not_exists = lambda *args, **kwargs: None

    def fake_fetch_ak_data(function_name, **kwargs):
        calls.append(("fetch", kwargs))
        return pd.DataFrame(
            [
                {"日期": "2026-02-13", "开盘": 0.9, "收盘": 1.5},
                {"日期": "2026-02-14", "开盘": 1.0, "收盘": 2.0},
            ]
        )

    service.fetch_ak_data = fake_fetch_ak_data
    service.delete_data = lambda table_name, conditions: calls.append(("delete", conditions))
    service.save_data = lambda df, table_name, **kwargs: calls.append(("save", df["日期"].tolist()))

    result = service.fetch_data()

    assert result["日期"].tolist() == ["2026-02-13", "2026-02-14"]
    assert calls[0] == (
        "fetch",
        {"start_date": "20260213", "end_date": datetime.now().strftime("%Y%m%d")},
    )
    assert calls[1] == ("delete", {"日期": "2026-02-13"})
    assert calls[2] == ("delete", {"日期": "2026-02-14"})
    assert calls[3] == ("save", ["2026-02-13", "2026-02-14"])


def test_index_daily_market_cni_uses_per_symbol_latest_trade_date_by_default():
    from app.data_fetch.scripts.indexs.weekly.index_daily_market_cni import (
        IndexDailyMarketCNI,
    )

    calls: list[tuple[str, str, str]] = []
    service = object.__new__(IndexDailyMarketCNI)
    service.table_name = "INDEX_DAILY_MARKET_CNI"
    service.create_table_sql = "CREATE TABLE INDEX_DAILY_MARKET_CNI"
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.table_exists = lambda table_name: True
    service.get_current_date = lambda: "2026-06-22"
    service.get_data_by_columns = lambda table_name, columns: pd.DataFrame(
        {"INDEX_CODE": ["399001", "399002", "399001"]}
    )
    def fake_get_latest_date(table_name, date_column, conditions=None):
        if not conditions:
            return None
        return {
            "399001": "2026-06-18",
            "399002": "2026-06-19",
        }[conditions["INDEX_CODE"]]

    service.get_latest_date = fake_get_latest_date

    def fake_fetch_index_market_data(symbol, start_date, end_date):
        calls.append((symbol, start_date, end_date))
        return pd.DataFrame()

    service.fetch_index_market_data = fake_fetch_index_market_data

    assert service.run(max_workers=1) is True
    assert calls == [
        ("399001", "20260618", "20260622"),
        ("399002", "20260619", "20260622"),
    ]


def test_index_daily_market_cni_skips_symbols_complete_through_today():
    from app.data_fetch.scripts.indexs.weekly.index_daily_market_cni import (
        IndexDailyMarketCNI,
    )

    calls: list[tuple[str, str, str]] = []
    service = object.__new__(IndexDailyMarketCNI)
    service.table_name = "INDEX_DAILY_MARKET_CNI"
    service.create_table_sql = "CREATE TABLE INDEX_DAILY_MARKET_CNI"
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.table_exists = lambda table_name: True
    service.get_current_date = lambda: "2026-06-20"
    service.get_data_by_columns = lambda table_name, columns: pd.DataFrame(
        {"INDEX_CODE": ["399001"]}
    )
    service.get_latest_date = (
        lambda table_name, date_column, conditions=None: "2026-06-20"
    )
    def fake_fetch_index_market_data(symbol, start_date, end_date):
        calls.append((symbol, start_date, end_date))
        return pd.DataFrame()

    service.fetch_index_market_data = fake_fetch_index_market_data

    assert service.run(max_workers=1) is True
    assert calls == [("399001", "20260620", "20260620")]


def test_index_daily_market_cni_skips_weekend_only_gap():
    from app.data_fetch.scripts.indexs.weekly.index_daily_market_cni import (
        IndexDailyMarketCNI,
    )

    calls: list[tuple[str, str, str]] = []
    service = object.__new__(IndexDailyMarketCNI)
    service.table_name = "INDEX_DAILY_MARKET_CNI"
    service.create_table_sql = "CREATE TABLE INDEX_DAILY_MARKET_CNI"
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.table_exists = lambda table_name: True
    service.get_current_date = lambda: "2026-06-20"
    service.get_data_by_columns = lambda table_name, columns: pd.DataFrame(
        {"INDEX_CODE": ["399001"]}
    )
    service.get_latest_date = (
        lambda table_name, date_column, conditions=None: "2026-06-19"
    )
    def fake_fetch_index_market_data(symbol, start_date, end_date):
        calls.append((symbol, start_date, end_date))
        return pd.DataFrame()

    service.fetch_index_market_data = fake_fetch_index_market_data

    assert service.run(max_workers=1) is True
    assert calls == [("399001", "20260619", "20260619")]


def test_index_daily_market_cni_caps_default_end_to_source_latest_date():
    from app.data_fetch.scripts.indexs.weekly.index_daily_market_cni import (
        IndexDailyMarketCNI,
    )

    calls: list[tuple[str, str, str]] = []
    saved: list[str] = []
    service = object.__new__(IndexDailyMarketCNI)
    service.table_name = "INDEX_DAILY_MARKET_CNI"
    service.create_table_sql = "CREATE TABLE INDEX_DAILY_MARKET_CNI"
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.table_exists = lambda table_name: True
    service.get_current_date = lambda: "2026-06-20"
    service.get_data_by_columns = lambda table_name, columns: pd.DataFrame(
        {"INDEX_CODE": ["399001", "399002"]}
    )

    def fake_get_latest_date(table_name, date_column, conditions=None):
        if not conditions:
            return "2026-06-18"
        return {
            "399001": "2026-06-18",
            "399002": "2026-02-20",
        }[conditions["INDEX_CODE"]]

    service.get_latest_date = fake_get_latest_date
    service.query_data = lambda query, params=None: [("399001",)]

    def fake_fetch_index_market_data(symbol, start_date, end_date):
        calls.append((symbol, start_date, end_date))
        if symbol == "399001":
            return pd.DataFrame()
        return pd.DataFrame([{"INDEX_CODE": symbol, "TRADE_DATE": "2026-02-24"}])

    service.fetch_index_market_data = fake_fetch_index_market_data
    def fake_save_data(df, table_name, **kwargs):
        saved.extend(df["INDEX_CODE"].tolist())
        return True

    service.save_data = fake_save_data

    assert service.run(max_workers=1) is True
    assert calls == [
        ("399001", "20260619", "20260620"),
        ("399001", "20260618", "20260618"),
        ("399002", "20260220", "20260618"),
    ]
    assert saved == ["399002"]


def test_sw_index_components_runs_all_symbols_by_default():
    from app.data_fetch.scripts.indexs.weekly.sw_index_components import SWIndexComponents

    fetched: list[str] = []
    saved: list[str] = []
    service = object.__new__(SWIndexComponents)
    service.table_name = "SW_INDEX_COMPONENTS"
    service.create_table_sql = "CREATE TABLE SW_INDEX_COMPONENTS"
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.table_exists = lambda table_name: True
    service.get_symbol_list = lambda: ["801001", "801002"]

    def fake_fetch_components_data(symbol):
        fetched.append(symbol)
        return pd.DataFrame([{"INDEX_CODE": symbol, "STOCK_CODE": f"{symbol}01"}])

    service.fetch_components_data = fake_fetch_components_data
    service.save_data = lambda df, table_name, **kwargs: saved.extend(df["INDEX_CODE"].tolist())

    assert service.run(max_workers=1) is True
    assert fetched == ["801001", "801002"]
    assert saved == ["801001", "801002"]


def test_index_hist_adjust_cni_runs_all_symbols_by_default():
    from app.data_fetch.scripts.indexs.weekly.index_hist_adjust_cni import (
        IndexHistAdjustCNI,
    )

    fetched: list[str] = []
    saved: list[str] = []
    service = object.__new__(IndexHistAdjustCNI)
    service.table_name = "INDEX_HIST_ADJUST_CNI"
    service.create_table_sql = "CREATE TABLE INDEX_HIST_ADJUST_CNI"
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.table_exists = lambda table_name: True
    service.get_symbol_list = lambda: ["399001", "399002"]

    def fake_fetch_hist_adjust_data(symbol):
        fetched.append(symbol)
        if symbol == "399001":
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {
                    "INDEX_CODE": symbol,
                    "STOCK_CODE": f"{symbol}01",
                    "START_DATE": "2026-01-01",
                }
            ]
        )

    service.fetch_hist_adjust_data = fake_fetch_hist_adjust_data
    service.save_data = lambda df, table_name, **kwargs: saved.extend(df["INDEX_CODE"].tolist())

    assert service.run(max_workers=1) is True
    assert fetched == ["399001", "399002"]
    assert saved == ["399002"]


def test_sw_industry_third_cons_runs_all_industries_by_default():
    from app.data_fetch.scripts.indexs.weekly.sw_industry_third_cons import (
        SWIndustryThirdCons,
    )

    fetched: list[str] = []
    saved: list[str] = []
    service = object.__new__(SWIndustryThirdCons)
    service.table_name = "SW_INDUSTRY_THIRD_CONS"
    service.create_table_sql = "CREATE TABLE SW_INDUSTRY_THIRD_CONS"
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.table_exists = lambda table_name: True
    service.get_all_industry_code = lambda: ["850111.SI", "850112.SI"]

    def fake_fetch_industry_cons(industry_code):
        fetched.append(industry_code)
        if industry_code == "850111.SI":
            return pd.DataFrame()
        return pd.DataFrame(
            [{"INDUSTRY_CODE": industry_code, "STOCK_CODE": "000001"}]
        )

    service.fetch_industry_cons = fake_fetch_industry_cons
    service.save_data = lambda df, table_name, **kwargs: saved.extend(
        df["INDUSTRY_CODE"].tolist()
    )

    assert service.run(max_workers=1) is True
    assert fetched == ["850111.SI", "850112.SI"]
    assert saved == ["850112.SI"]


def test_sw_index_minute_runs_all_symbols_by_default():
    from app.data_fetch.scripts.indexs.weekly.sw_index_minute import SWIndexMinute

    fetched: list[str] = []
    saved: list[str] = []
    service = object.__new__(SWIndexMinute)
    service.table_name = "SW_INDEX_MINUTE"
    service.create_table_sql = "CREATE TABLE SW_INDEX_MINUTE"
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.table_exists = lambda table_name: True
    service.get_symbol_list = lambda: ["801001", "801002"]

    def fake_fetch_minute_data(symbol):
        fetched.append(symbol)
        if symbol == "801001":
            return pd.DataFrame()
        return pd.DataFrame([{"INDEX_CODE": symbol, "TRADE_DATE": "2026-06-20"}])

    service.fetch_minute_data = fake_fetch_minute_data
    service.save_data = lambda df, table_name, **kwargs: saved.extend(
        df["INDEX_CODE"].tolist()
    )

    assert service.run(max_workers=1) is True
    assert fetched == ["801001", "801002"]
    assert saved == ["801002"]


def test_sw_index_historical_runs_all_symbols_by_default_and_filters_incremental():
    from app.data_fetch.scripts.indexs.weekly.sw_index_historical import SWIndexHistorical

    fetched: list[tuple[str, str, object]] = []
    saved: list[str] = []
    service = object.__new__(SWIndexHistorical)
    service.table_name = "SW_INDEX_HISTORICAL"
    service.create_table_sql = "CREATE TABLE SW_INDEX_HISTORICAL"
    service.valid_periods = ["day", "week", "month"]
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.table_exists = lambda table_name: True
    service.get_symbol_list = lambda: ["801001", "801002"]
    service.get_latest_date = (
        lambda table_name, date_column, conditions=None: "2026-06-19"
        if conditions and conditions["INDEX_CODE"] == "801001"
        else None
    )

    def fake_fetch_historical_data(symbol, period, start_after=None):
        fetched.append((symbol, period, start_after))
        if symbol == "801001":
            return pd.DataFrame([{"INDEX_CODE": symbol, "TRADE_DATE": "2026-06-20"}])
        return pd.DataFrame()

    service.fetch_historical_data = fake_fetch_historical_data
    service.save_data = lambda df, table_name, **kwargs: saved.extend(
        df["INDEX_CODE"].tolist()
    )

    assert service.run(max_workers=1) is True
    assert fetched == [
        ("801001", "day", pd.Timestamp("2026-06-19").date()),
        ("801002", "day", None),
    ]
    assert saved == ["801001"]


def test_sw_index_historical_rechecks_latest_stored_date():
    from app.data_fetch.scripts.indexs.weekly.sw_index_historical import SWIndexHistorical

    service = object.__new__(SWIndexHistorical)
    service.valid_periods = ["day", "week", "month"]
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.get_uuid = lambda: "RID"
    service.fetch_ak_data = lambda *args, **kwargs: pd.DataFrame(
        [
            {"代码": "801001", "日期": "2026-06-18", "收盘": 1, "开盘": 1, "最高": 1, "最低": 1, "成交量": 1, "成交额": 1},
            {"代码": "801001", "日期": "2026-06-19", "收盘": 2, "开盘": 2, "最高": 2, "最低": 2, "成交量": 2, "成交额": 2},
            {"代码": "801001", "日期": "2026-06-20", "收盘": 3, "开盘": 3, "最高": 3, "最低": 3, "成交量": 3, "成交额": 3},
        ]
    )

    result = service.fetch_historical_data(
        "801001", "day", pd.Timestamp("2026-06-19").date()
    )

    assert result["TRADE_DATE"].astype(str).tolist() == ["2026-06-19", "2026-06-20"]


def test_sw_fund_index_historical_runs_all_symbols_by_default_and_filters_incremental():
    from app.data_fetch.scripts.indexs.weekly.sw_fund_index_historical import (
        SWFundIndexHistorical,
    )

    fetched: list[tuple[str, str, object]] = []
    saved: list[str] = []
    service = object.__new__(SWFundIndexHistorical)
    service.table_name = "SW_FUND_INDEX_HISTORICAL"
    service.create_table_sql = "CREATE TABLE SW_FUND_INDEX_HISTORICAL"
    service.valid_periods = ["day", "week", "month"]
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.table_exists = lambda table_name: True
    service.get_symbol_list = lambda: ["807100", "807200"]
    service.get_latest_date = (
        lambda table_name, date_column, conditions=None: "2026-06-19"
        if conditions and conditions["INDEX_CODE"] == "807100"
        else None
    )

    def fake_fetch_historical_data(symbol, period, start_after=None):
        fetched.append((symbol, period, start_after))
        if symbol == "807100":
            return pd.DataFrame([{"INDEX_CODE": symbol, "TRADE_DATE": "2026-06-20"}])
        return pd.DataFrame()

    service.fetch_historical_data = fake_fetch_historical_data
    service.save_data = lambda df, table_name, **kwargs: saved.extend(
        df["INDEX_CODE"].tolist()
    )

    assert service.run(max_workers=1) is True
    assert fetched == [
        ("807100", "day", pd.Timestamp("2026-06-19").date()),
        ("807200", "day", None),
    ]
    assert saved == ["807100"]


def test_sw_fund_index_historical_rechecks_latest_stored_date():
    from app.data_fetch.scripts.indexs.weekly.sw_fund_index_historical import (
        SWFundIndexHistorical,
    )

    service = object.__new__(SWFundIndexHistorical)
    service.valid_periods = ["day", "week", "month"]
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.get_uuid = lambda: "RID"
    service.fetch_ak_data = lambda *args, **kwargs: pd.DataFrame(
        [
            {"日期": "2026-06-18", "收盘指数": 1, "开盘指数": 1, "最高指数": 1, "最低指数": 1, "涨跌幅": 1},
            {"日期": "2026-06-19", "收盘指数": 2, "开盘指数": 2, "最高指数": 2, "最低指数": 2, "涨跌幅": 2},
            {"日期": "2026-06-20", "收盘指数": 3, "开盘指数": 3, "最高指数": 3, "最低指数": 3, "涨跌幅": 3},
        ]
    )

    result = service.fetch_historical_data(
        "807100", "day", pd.Timestamp("2026-06-19").date()
    )

    assert result["TRADE_DATE"].astype(str).tolist() == ["2026-06-19", "2026-06-20"]


def test_sw_index_analysis_daily_rechecks_latest_stored_date_by_default():
    from app.data_fetch.scripts.indexs.weekly.sw_index_analysis_daily import (
        SWIndexAnalysisDaily,
    )

    calls: list[tuple[str, str, str]] = []
    service = object.__new__(SWIndexAnalysisDaily)
    service.table_name = "SW_INDEX_ANALYSIS_DAILY"
    service.create_table_sql = "CREATE TABLE SW_INDEX_ANALYSIS_DAILY"
    service.valid_symbols = ["市场表征", "一级行业", "二级行业", "风格指数"]
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.table_exists = lambda table_name: True
    service.get_current_date = lambda: "2026-06-20"

    def fake_get_latest_date(table_name, date_column, conditions=None):
        assert conditions is None
        return "2026-06-19"

    service.get_latest_date = fake_get_latest_date

    def fake_fetch_analysis_data(symbol, start_date, end_date):
        calls.append((symbol, start_date, end_date))
        return pd.DataFrame()

    service.fetch_analysis_data = fake_fetch_analysis_data

    assert service.run(symbol="市场表征", max_workers=1) is True
    assert calls == [("市场表征", "20260619", "20260620")]


def test_stock_zh_index_daily_em_uses_normalized_symbol_latest_dates():
    from app.data_fetch.scripts.indexs.weekly.stock_zh_index_daily_em import (
        StockZhIndexDailyEm,
    )

    calls: list[tuple[str, str, str]] = []
    saved: list[str] = []
    service = object.__new__(StockZhIndexDailyEm)
    service.table_name = "STOCK_ZH_INDEX_DAILY_EM"
    service.create_table_sql = "CREATE TABLE STOCK_ZH_INDEX_DAILY_EM"
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.table_exists = lambda table_name: True
    service.get_em_index_code = lambda: ["sz000001", "sh000002"]
    service.get_current_date = lambda: "2026-06-20"
    service.get_latest_date = lambda table_name, date_column, conditions=None: {
        "sz000001": "2026-06-18",
        "sh000002": "2026-06-19",
    }[conditions["INDEX_CODE"]]

    def fake_fetch_index_daily(symbol, start_date, end_date):
        calls.append((symbol, start_date, end_date))
        return pd.DataFrame([{"INDEX_CODE": symbol, "TRADE_DATE": start_date}])

    service.fetch_index_daily = fake_fetch_index_daily

    def fake_stock_save_data(df, table_name, **kwargs):
        saved.extend(df["INDEX_CODE"].tolist())
        return True

    service.save_data = fake_stock_save_data

    assert service.run(max_workers=1) is True
    assert calls == [
        ("sz000001", "20260618", "20260620"),
        ("sh000002", "20260619", "20260620"),
    ]
    assert saved == ["sz000001", "sh000002"]


def test_index_hist_cni_returns_empty_for_empty_source_response(monkeypatch):
    from akshare.index import index_cni

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"data": []}}

    monkeypatch.setattr(index_cni.requests, "get", lambda *args, **kwargs: Response())

    result = index_cni.index_hist_cni(
        symbol="399001", start_date="20260620", end_date="20260620"
    )

    assert result.empty
    assert list(result.columns) == [
        "日期",
        "开盘价",
        "最高价",
        "最低价",
        "收盘价",
        "涨跌幅",
        "成交量",
        "成交额",
    ]


def test_index_zh_a_hist_returns_empty_when_eastmoney_unreachable(monkeypatch):
    from akshare.index import index_zh_em

    index_zh_em.index_code_id_map_em.cache_clear()

    def fail_paginated_data(*args, **kwargs):
        raise RuntimeError("Eastmoney paginated endpoint request failed")

    def fail_request(*args, **kwargs):
        raise index_zh_em.requests.ConnectionError("connection closed")

    monkeypatch.setattr(index_zh_em, "fetch_paginated_data", fail_paginated_data)
    monkeypatch.setattr(index_zh_em.requests, "get", fail_request)

    result = index_zh_em.index_zh_a_hist(symbol="000859")

    assert result.empty


def test_index_zh_a_hist_min_em_returns_empty_when_eastmoney_unreachable(monkeypatch):
    from akshare.index import index_zh_em

    index_zh_em.index_code_id_map_em.cache_clear()
    monkeypatch.setattr(index_zh_em, "index_code_id_map_em", lambda: {})
    monkeypatch.setattr(
        index_zh_em.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            index_zh_em.requests.ConnectionError("connection closed")
        ),
    )

    result = index_zh_em.index_zh_a_hist_min_em(symbol="000001", period="1")

    assert result.empty
    assert result.columns.tolist() == ["时间", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "均价"]


def test_bond_zh_hs_cov_pre_min_returns_empty_when_eastmoney_unreachable(monkeypatch):
    from akshare.bond import bond_zh_cov

    monkeypatch.setattr(
        bond_zh_cov.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            bond_zh_cov.requests.ConnectionError("connection closed")
        ),
    )

    result = bond_zh_cov.bond_zh_hs_cov_pre_min(symbol="sh113570")

    assert result.empty
    assert result.columns.tolist() == ["时间", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "最新价"]


def test_bond_zh_hs_cov_min_returns_empty_when_eastmoney_returns_null_data(monkeypatch):
    from akshare.bond import bond_zh_cov

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": None}

    monkeypatch.setattr(bond_zh_cov.requests, "get", lambda *args, **kwargs: Response())

    result = bond_zh_cov.bond_zh_hs_cov_min(symbol="sh113570", period="1")

    assert result.empty
    assert result.columns.tolist() == ["时间", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "最新价"]


def test_bond_cov_comparison_falls_back_to_delay_endpoint(monkeypatch):
    from akshare.bond import bond_zh_cov

    calls = []

    def fake_fetch_paginated_data(url, params):
        calls.append(url)
        if "16.push2" in url:
            raise RuntimeError("primary unavailable")
        return pd.DataFrame(
            [
                {
                    "index": 1,
                    "f1": 3,
                    "f2": 101.5,
                    "f3": 1.2,
                    "f12": "118071",
                    "f13": 1,
                    "f14": "华峰转债",
                    "f26": "20260101",
                    "f152": 2,
                    "f227": "-",
                    "f228": 90,
                    "f229": 9.8,
                    "f230": 2.1,
                    "f231": 2,
                    "f232": "688200",
                    "f233": 1,
                    "f234": "华峰测控",
                    "f235": 10.5,
                    "f236": 107.14,
                    "f237": 0.5,
                    "f238": 3.2,
                    "f239": 80,
                    "f240": 130,
                    "f241": 110,
                    "f242": "20260701",
                    "f243": "20260102",
                }
            ]
        )

    monkeypatch.setattr(bond_zh_cov, "fetch_paginated_data", fake_fetch_paginated_data)

    result = bond_zh_cov.bond_cov_comparison()

    assert calls[0].startswith("https://16.push2")
    assert calls[1].startswith("https://push2delay")
    assert result.loc[0, "转债代码"] == "118071"
    assert result.loc[0, "转债名称"] == "华峰转债"
    assert result.loc[0, "正股代码"] == "688200"
    assert result.loc[0, "纯债价值"] == 90
    assert result.columns.tolist() == [
        "序号",
        "转债代码",
        "转债名称",
        "转债最新价",
        "转债涨跌幅",
        "正股代码",
        "正股名称",
        "正股最新价",
        "正股涨跌幅",
        "转股价",
        "转股价值",
        "转股溢价率",
        "纯债溢价率",
        "回售触发价",
        "强赎触发价",
        "到期赎回价",
        "纯债价值",
        "开始转股日",
        "上市日期",
        "申购日期",
    ]


def test_bond_info_cm_reuses_session_and_fetches_all_pages(monkeypatch):
    import akshare.bond.bond_info_cm as bond_info_cm_module

    bond_info_cm_module.bond_info_cm.cache_clear()

    class Response:
        status_code = 200

        def __init__(self, page_no):
            self.page_no = str(page_no)

        def raise_for_status(self):
            return None

        def json(self):
            rows = {
                "1": [
                    {
                        "bondDefinedCode": "query-1",
                        "bondName": "债券1",
                        "bondCode": "000001",
                        "issueStartDate": "2024-01-01",
                        "bondType": "国债",
                        "entyFullName": "发行人1",
                        "debtRtng": "AAA",
                    }
                ],
                "2": [
                    {
                        "bondDefinedCode": "query-2",
                        "bondName": "债券2",
                        "bondCode": "000002",
                        "issueStartDate": "2024-01-02",
                        "bondType": "政策性金融债",
                        "entyFullName": "发行人2",
                        "debtRtng": "AA+",
                    }
                ],
            }
            return {"data": {"pageTotal": 2, "resultList": rows[self.page_no]}}

    class FakeSession:
        instances = []

        def __init__(self):
            self.calls = []
            self.instances.append(self)

        def post(self, url, data, headers, timeout):
            self.calls.append(str(data["pageNo"]))
            return Response(data["pageNo"])

    monkeypatch.setattr(bond_info_cm_module.requests, "Session", FakeSession)
    monkeypatch.setattr(bond_info_cm_module, "bond_china_close_return_map", lambda: None)

    result = bond_info_cm_module.bond_info_cm()

    assert len(FakeSession.instances) == 1
    assert FakeSession.instances[0].calls == ["1", "2"]
    assert result["债券代码"].tolist() == ["000001", "000002"]
    assert result["查询代码"].tolist() == ["query-1", "query-2"]

    bond_info_cm_module.bond_info_cm.cache_clear()


def test_bond_info_detail_cm_returns_empty_when_lookup_has_no_match(monkeypatch):
    import akshare.bond.bond_info_cm as bond_info_cm_module

    bond_info_cm_module.bond_info_detail_cm.cache_clear()
    monkeypatch.setattr(bond_info_cm_module, "bond_china_close_return_map", lambda: None)
    monkeypatch.setattr(
        bond_info_cm_module,
        "bond_info_cm",
        lambda **kwargs: pd.DataFrame(columns=["债券简称", "查询代码"]),
    )

    result = bond_info_cm_module.bond_info_detail_cm(symbol="missing")

    assert result.empty
    assert result.columns.tolist() == ["name", "value"]

    bond_info_cm_module.bond_info_detail_cm.cache_clear()


def test_bond_zh_hs_spot_returns_empty_when_sina_returns_invalid_payload(monkeypatch):
    from akshare.bond import bond_zh_sina

    class Response:
        text = ""
        status_code = 200

        def raise_for_status(self):
            return None

    monkeypatch.setattr(bond_zh_sina, "get_zh_bond_hs_page_count", lambda: 1)
    monkeypatch.setattr(bond_zh_sina.requests, "get", lambda *args, **kwargs: Response())

    result = bond_zh_sina.bond_zh_hs_spot(start_page="1", end_page="1")

    assert result.empty
    assert result.columns.tolist() == [
        "代码",
        "名称",
        "最新价",
        "涨跌额",
        "涨跌幅",
        "买入",
        "卖出",
        "昨收",
        "今开",
        "最高",
        "最低",
        "成交量",
        "成交额",
    ]


def test_sunrise_daily_uses_calculated_fallback_when_timeanddate_is_blocked(monkeypatch):
    from akshare.air import sunrise_tad

    monkeypatch.setattr(
        sunrise_tad,
        "_get_timeanddate_page",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("timeanddate endpoint returned HTTP 403")
        ),
    )

    result = sunrise_tad.sunrise_daily(date="20240428", city="beijing")

    assert len(result) == 1
    assert result.loc[0, "date"].isoformat() == "2024-04-28"
    assert "Sunrise" in result.columns
    assert "Sunset" in result.columns


def test_sunrise_monthly_uses_calculated_fallback_when_timeanddate_is_blocked(monkeypatch):
    from akshare.air import sunrise_tad

    monkeypatch.setattr(
        sunrise_tad,
        "_get_timeanddate_page",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("timeanddate endpoint returned HTTP 403")
        ),
    )

    result = sunrise_tad.sunrise_monthly(date="20240428", city="beijing")

    assert len(result) == 30
    assert set(result["date"]) == {"202404"}
    assert "Sunrise" in result.columns
    assert "Sunset" in result.columns


def test_video_variety_show_returns_empty_when_endata_old_endpoint_is_unavailable(monkeypatch):
    from akshare.movie import video_yien

    class Response:
        status_code = 405
        text = "<html>405 Not Allowed</html>"
        encoding = "utf8"

    monkeypatch.setattr(video_yien.requests, "post", lambda *args, **kwargs: Response())

    result = video_yien.video_variety_show()

    assert result.empty
    assert result.columns.tolist() == [
        "排序",
        "名称",
        "类型",
        "播映指数",
        "媒体热度",
        "用户热度",
        "好评度",
        "观看度",
        "统计日期",
    ]


def test_energy_carbon_eu_parses_single_page_when_pagebar_missing(monkeypatch):
    from akshare.energy import energy_carbon

    class Response:
        status_code = 200
        text = """
        <html><body>
          <table>
            <tr>
              <th>交易日期</th><th>市场交易指数</th><th>开盘价</th><th>最高价</th>
              <th>最低价</th><th>成交均价</th><th>收盘价</th><th>成交量</th><th>成交额</th>
            </tr>
            <tr>
              <td>2020-04-29</td><td>欧盟EUA</td><td></td><td></td><td></td>
              <td></td><td>20.19</td><td>18621000</td><td></td>
            </tr>
          </table>
        </body></html>
        """

    monkeypatch.setattr(energy_carbon.requests, "get", lambda *args, **kwargs: Response())

    result = energy_carbon.energy_carbon_eu()

    assert len(result) == 1
    assert result.loc[0, "市场交易指数"] == "欧盟EUA"
    assert result.loc[0, "收盘价"] == 20.19


def test_get_roll_yield_bar_returns_empty_when_daily_sources_fail(monkeypatch):
    from akshare.futures import futures_roll_yield

    monkeypatch.setattr(
        futures_roll_yield,
        "get_futures_daily",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("empty response")),
    )

    result = futures_roll_yield.get_roll_yield_bar(type_method="var", date="20201030")

    assert result.empty
    assert result.columns.tolist() == ["roll_yield", "near_by", "deferred", "date"]


def test_amac_fund_abs_reuses_session_and_includes_first_page(monkeypatch):
    from akshare.fund import fund_amac

    calls = []

    class FakeSession:
        pass

    def fake_post_json(url, **kwargs):
        calls.append((kwargs["params"]["page"], kwargs.get("session")))
        page = int(kwargs["params"]["page"])
        return {
            "totalPages": 2,
            "content": [
                {
                    "id": f"id-{page}",
                    "userTenantId": page,
                    "productName": f"计划{page}",
                    "productCode": f"S{page}",
                    "orgName": f"管理人{page}",
                    "trustee": f"托管人{page}",
                    "registeredDate": 1714521600000,
                    "fundFoundDate": 1714435200000,
                    "fundDueDate": 1745971200000,
                }
            ],
        }

    monkeypatch.setattr(fund_amac.requests, "Session", FakeSession)
    monkeypatch.setattr(fund_amac, "_post_json", fake_post_json)

    result = fund_amac.amac_fund_abs()

    assert [page for page, _session in calls] == ["0", 1]
    assert calls[0][1] is calls[1][1]
    assert result["备案编号"].tolist() == ["S0", "S1"]
    assert result["编号"].tolist() == [1, 2]


def test_amac_member_info_uses_supported_page_size(monkeypatch):
    from akshare.fund import fund_amac

    calls = []

    def fake_post_json(url, **kwargs):
        params = kwargs["params"]
        calls.append(dict(params))
        assert params["size"] == "20"
        page = int(params["page"])
        return {
            "totalPages": 1,
            "content": [
                {
                    "managerName": f"机构{page}",
                    "memberBehalf": f"代表{page}",
                    "memberType": "普通会员",
                    "memberCode": f"PT{page}",
                    "memberDate": 1338940800000,
                    "primaryInvestType": "公募基金管理公司",
                    "markStar": "N",
                }
            ],
        }

    monkeypatch.setattr(fund_amac, "_post_json", fake_post_json)

    result = fund_amac.amac_member_info()

    assert [call["page"] for call in calls] == ["1", 0]
    assert result["机构（会员）名称"].tolist() == ["机构0"]
    assert result.columns.tolist() == [
        "机构（会员）名称",
        "会员代表",
        "会员类型",
        "会员编号",
        "入会时间",
        "机构类型",
        "是否星标",
    ]


def test_amac_member_info_returns_standard_empty_when_endpoint_rejects(monkeypatch):
    from akshare.fund import fund_amac

    monkeypatch.setattr(
        fund_amac,
        "_post_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("AMAC endpoint returned HTTP 400")
        ),
    )

    result = fund_amac.amac_member_info()

    assert result.empty
    assert result.columns.tolist() == [
        "机构（会员）名称",
        "会员代表",
        "会员类型",
        "会员编号",
        "入会时间",
        "机构类型",
        "是否星标",
    ]


def test_amac_fund_sub_info_uses_supported_page_size(monkeypatch):
    from akshare.fund import fund_amac

    calls = []

    def fake_post_json(url, **kwargs):
        params = kwargs["params"]
        calls.append(dict(params))
        assert params["size"] == "20"
        page = int(params["page"])
        return {
            "totalPages": 1,
            "content": [
                {
                    "productCode": f"P{page}",
                    "productName": f"产品{page}",
                    "mgrName": f"管理人{page}",
                    "trustee": f"托管人{page}",
                    "foundDate": 1714435200000,
                    "registeredDate": 1714521600000,
                }
            ],
        }

    monkeypatch.setattr(fund_amac, "_post_json", fake_post_json)

    result = fund_amac.amac_fund_sub_info()

    assert [call["page"] for call in calls] == ["1", 0]
    assert result["产品编码"].tolist() == ["P0"]
    assert result.columns.tolist() == [
        "产品编码",
        "产品名称",
        "私募基金管理人名称",
        "托管人名称",
        "成立日期",
        "备案日期",
    ]


def test_amac_fund_sub_info_returns_standard_empty_when_endpoint_rejects(monkeypatch):
    from akshare.fund import fund_amac

    monkeypatch.setattr(
        fund_amac,
        "_post_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("AMAC endpoint returned HTTP 400")
        ),
    )

    result = fund_amac.amac_fund_sub_info()

    assert result.empty
    assert result.columns.tolist() == [
        "产品编码",
        "产品名称",
        "私募基金管理人名称",
        "托管人名称",
        "成立日期",
        "备案日期",
    ]


def test_amac_aoin_info_uses_supported_page_size(monkeypatch):
    from akshare.fund import fund_amac

    calls = []

    def fake_post_json(url, **kwargs):
        params = kwargs["params"]
        calls.append(dict(params))
        assert params["size"] == "20"
        page = int(params["page"])
        return {
            "totalPages": 1,
            "content": [
                {
                    "code": f"A{page}",
                    "name": f"产品{page}",
                    "aoinName": f"直投{page}",
                    "managerName": f"管理机构{page}",
                    "createDate": 1714521600000,
                }
            ],
        }

    monkeypatch.setattr(fund_amac, "_post_json", fake_post_json)

    result = fund_amac.amac_aoin_info()

    assert [call["page"] for call in calls] == ["1", 0]
    assert result["产品编码"].tolist() == ["A0"]
    assert result.columns.tolist() == [
        "产品编码",
        "产品名称",
        "直投子公司",
        "管理机构",
        "设立日期",
    ]


def test_amac_aoin_info_returns_standard_empty_when_endpoint_rejects(monkeypatch):
    from akshare.fund import fund_amac

    monkeypatch.setattr(
        fund_amac,
        "_post_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("AMAC endpoint returned HTTP 400")
        ),
    )

    result = fund_amac.amac_aoin_info()

    assert result.empty
    assert result.columns.tolist() == [
        "产品编码",
        "产品名称",
        "直投子公司",
        "管理机构",
        "设立日期",
    ]


def test_amac_member_sub_info_returns_standard_empty_when_endpoint_rejects(monkeypatch):
    from akshare.fund import fund_amac

    monkeypatch.setattr(
        fund_amac,
        "_post_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("AMAC endpoint request failed")
        ),
    )

    result = fund_amac.amac_member_sub_info()

    assert result.empty
    assert result.columns.tolist() == [
        "机构（会员）名称",
        "会员代表",
        "会员类型",
        "会员编号",
        "入会时间",
        "公司类型",
    ]


def test_amac_member_sub_info_reuses_session_and_bounds_page_timeout(monkeypatch):
    from akshare.fund import fund_amac

    calls = []

    class FakeSession:
        pass

    def fake_post_json(url, **kwargs):
        calls.append(
            {
                "page": kwargs["params"]["page"],
                "session": kwargs.get("session"),
                "timeout": kwargs.get("timeout"),
                "max_retries": kwargs.get("max_retries"),
            }
        )
        page = int(kwargs["params"]["page"])
        return {
            "totalPages": 1,
            "content": [
                {
                    "managerName": f"机构{page}",
                    "memberBehalf": f"代表{page}",
                    "memberType": "普通会员",
                    "memberCode": f"PT{page}",
                    "memberDate": 1338940800000,
                    "primaryInvestType": "证券公司私募基金子公司",
                }
            ],
        }

    monkeypatch.setattr(fund_amac.requests, "Session", FakeSession)
    monkeypatch.setattr(fund_amac, "_post_json", fake_post_json)

    result = fund_amac.amac_member_sub_info()

    assert [call["page"] for call in calls] == ["1", 0]
    assert calls[0]["session"] is calls[1]["session"]
    assert [call["timeout"] for call in calls] == [8, 8]
    assert [call["max_retries"] for call in calls] == [1, 1]
    assert result["机构（会员）名称"].tolist() == ["机构0"]


def test_amac_manager_cancelled_info_uses_supported_page_size(monkeypatch):
    from akshare.fund import fund_amac

    calls = []

    class FakeSession:
        pass

    def fake_post_json(url, **kwargs):
        params = kwargs["params"]
        calls.append(
            {
                "params": dict(params),
                "session": kwargs.get("session"),
                "timeout": kwargs.get("timeout"),
                "max_retries": kwargs.get("max_retries"),
            }
        )
        assert params["size"] == "20"
        page = int(params["page"])
        return {
            "totalPages": 1,
            "content": [
                {
                    "orgName": f"管理人{page}",
                    "orgCode": f"C{page}",
                    "orgSignDate": 1714435200000,
                    "cancelDate": 1714521600000,
                    "status": "主动注销",
                }
            ],
        }

    monkeypatch.setattr(fund_amac.requests, "Session", FakeSession)
    monkeypatch.setattr(fund_amac, "_post_json", fake_post_json)

    result = fund_amac.amac_manager_cancelled_info()

    assert [call["params"]["page"] for call in calls] == ["1", 0]
    assert calls[0]["session"] is calls[1]["session"]
    assert [call["timeout"] for call in calls] == [8, 8]
    assert [call["max_retries"] for call in calls] == [1, 1]
    assert result["管理人名称"].tolist() == ["管理人0"]
    assert result.columns.tolist() == [
        "管理人名称",
        "统一社会信用代码",
        "登记时间",
        "注销时间",
        "注销类型",
    ]


def test_amac_manager_cancelled_info_returns_standard_empty_when_endpoint_rejects(
    monkeypatch,
):
    from akshare.fund import fund_amac

    monkeypatch.setattr(
        fund_amac,
        "_post_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("AMAC endpoint returned HTTP 400")
        ),
    )

    result = fund_amac.amac_manager_cancelled_info()

    assert result.empty
    assert result.columns.tolist() == [
        "管理人名称",
        "统一社会信用代码",
        "登记时间",
        "注销时间",
        "注销类型",
    ]


def test_amac_fund_account_info_uses_supported_page_size(monkeypatch):
    from akshare.fund import fund_amac

    calls = []

    class FakeSession:
        pass

    def fake_post_json(url, **kwargs):
        params = kwargs["params"]
        calls.append(
            {
                "params": dict(params),
                "session": kwargs.get("session"),
                "timeout": kwargs.get("timeout"),
                "max_retries": kwargs.get("max_retries"),
            }
        )
        assert params["size"] == "20"
        page = int(params["page"])
        return {
            "totalPages": 1,
            "content": [
                {
                    "registerDate": 1714435200000,
                    "registerCode": f"AC{page}",
                    "name": f"产品{page}",
                    "manager": f"管理人{page}",
                }
            ],
        }

    monkeypatch.setattr(fund_amac.requests, "Session", FakeSession)
    monkeypatch.setattr(fund_amac, "_post_json", fake_post_json)

    result = fund_amac.amac_fund_account_info()

    assert [call["params"]["page"] for call in calls] == ["1", 0]
    assert calls[0]["session"] is calls[1]["session"]
    assert [call["timeout"] for call in calls] == [8, 8]
    assert [call["max_retries"] for call in calls] == [1, 1]
    assert result["产品编码"].tolist() == ["AC0"]
    assert result.columns.tolist() == [
        "成立日期",
        "产品编码",
        "产品名称",
        "管理人名称",
    ]


def test_amac_fund_account_info_returns_standard_empty_when_endpoint_rejects(
    monkeypatch,
):
    from akshare.fund import fund_amac

    monkeypatch.setattr(
        fund_amac,
        "_post_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("AMAC endpoint returned HTTP 400")
        ),
    )

    result = fund_amac.amac_fund_account_info()

    assert result.empty
    assert result.columns.tolist() == [
        "成立日期",
        "产品编码",
        "产品名称",
        "管理人名称",
    ]


def test_amac_post_json_retries_transient_server_error(monkeypatch):
    from akshare.fund import fund_amac

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = "temporary upstream failure"

        def json(self):
            return self._payload

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def post(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return FakeResponse(502, {})
            return FakeResponse(200, {"content": [], "totalPages": 0})

    session = FakeSession()
    monkeypatch.setattr(fund_amac.time, "sleep", lambda *_args, **_kwargs: None)

    result = fund_amac._post_json(
        "https://gs.amac.org.cn/amac-infodisc/api/fund/abs",
        params={"page": 0},
        json={},
        headers={},
        session=session,
    )

    assert session.calls == 2
    assert result == {"content": [], "totalPages": 0}


def test_amac_post_json_retries_request_timeout(monkeypatch):
    from akshare.fund import fund_amac

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"content": [], "totalPages": 0}

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def post(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise fund_amac.requests.exceptions.ReadTimeout("timeout")
            return FakeResponse()

    session = FakeSession()
    monkeypatch.setattr(fund_amac.time, "sleep", lambda *_args, **_kwargs: None)

    result = fund_amac._post_json(
        "https://gs.amac.org.cn/amac-infodisc/api/pof/pofMember",
        params={"page": 0},
        json={},
        headers={},
        session=session,
    )

    assert session.calls == 2
    assert result == {"content": [], "totalPages": 0}


def test_stock_zh_index_spot_em_returns_empty_when_eastmoney_unreachable(monkeypatch):
    from akshare.index import index_stock_zh

    def fail_paginated_data(*args, **kwargs):
        raise RuntimeError("Eastmoney paginated endpoint request failed")

    monkeypatch.setattr(index_stock_zh, "fetch_paginated_data", fail_paginated_data)

    result = index_stock_zh.stock_zh_index_spot_em(symbol="上证系列指数")

    assert result.empty
    assert result.columns.tolist() == [
        "序号",
        "代码",
        "名称",
        "最新价",
        "涨跌幅",
        "涨跌额",
        "成交量",
        "成交额",
        "振幅",
        "最高",
        "最低",
        "今开",
        "昨收",
        "量比",
    ]


def test_stock_zh_index_daily_em_returns_empty_when_eastmoney_disconnects(monkeypatch):
    from akshare.index import index_stock_zh

    monkeypatch.setattr(
        index_stock_zh.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            index_stock_zh.requests.ConnectionError("connection closed")
        ),
    )

    result = index_stock_zh.stock_zh_index_daily_em(
        symbol="sz000001", start_date="20260619", end_date="20260620"
    )

    assert result.empty
    assert result.columns.tolist() == [
        "date",
        "open",
        "close",
        "high",
        "low",
        "volume",
        "amount",
    ]


def test_stock_hk_index_daily_em_uses_default_market_for_missing_mapping(monkeypatch):
    from akshare.index import index_stock_hk

    requested: dict[str, str] = {}
    monkeypatch.setattr(index_stock_hk, "_symbol_code_dict", lambda: {})

    class Response:
        def json(self):
            return {"data": {"klines": ["2026-06-19,1,2,3,4,5,6,7,8,9,10,11,12,13"]}}

    def fake_get(url, params=None, **kwargs):
        requested["secid"] = params["secid"]
        return Response()

    monkeypatch.setattr(index_stock_hk.requests, "get", fake_get)

    result = index_stock_hk.stock_hk_index_daily_em(symbol="HSTECF2L")

    assert requested["secid"] == "100.HSTECF2L"
    assert result["date"].tolist() == ["2026-06-19"]
    assert result["latest"].tolist() == [2]


def test_stock_hk_index_daily_em_returns_empty_when_eastmoney_disconnects(monkeypatch):
    from akshare.index import index_stock_hk

    monkeypatch.setattr(index_stock_hk, "_symbol_code_dict", lambda: {})
    monkeypatch.setattr(
        index_stock_hk.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            index_stock_hk.requests.ConnectionError("connection closed")
        ),
    )

    result = index_stock_hk.stock_hk_index_daily_em(symbol="HSTECF2L")

    assert result.empty
    assert result.columns.tolist() == ["date", "open", "high", "low", "latest"]


def test_index_component_sw_accepts_mixed_timezone_dates(monkeypatch):
    from akshare.index import index_research_sw

    class Response:
        def json(self):
            return {
                "data": {
                    "results": [
                        {
                            "stockcode": "000001",
                            "stockname": "平安银行",
                            "newweight": "1.23",
                            "beginningdate": "2024-01-01T00:00:00+08:00",
                        },
                        {
                            "stockcode": "000002",
                            "stockname": "万科A",
                            "newweight": "2.34",
                            "beginningdate": "2024-01-02T00:00:00Z",
                        },
                    ]
                }
            }

    monkeypatch.setattr(index_research_sw.requests, "get", lambda *args, **kwargs: Response())

    result = index_research_sw.index_component_sw(symbol="801003")

    assert result["计入日期"].astype(str).tolist() == ["2024-01-01", "2024-01-02"]
    assert result["最新权重"].tolist() == [1.23, 2.34]


def test_sw_index_third_cons_returns_empty_when_table_missing(monkeypatch):
    from akshare.index import index_sw

    def raise_no_table(*args, **kwargs):
        raise ValueError("No tables found")

    monkeypatch.setattr(index_sw.pd, "read_html", raise_no_table)
    monkeypatch.setattr(
        index_sw.requests,
        "get",
        lambda *args, **kwargs: type("Response", (), {"text": "<html></html>"})(),
    )

    result = index_sw.sw_index_third_cons(symbol="850111.SI")

    assert result.empty
    assert "股票代码" in result.columns


def test_sw_index_third_cons_accepts_extra_source_columns(monkeypatch):
    from akshare.index import index_sw

    source = pd.DataFrame([list(range(18))])
    monkeypatch.setattr(index_sw.pd, "read_html", lambda *args, **kwargs: [source])
    monkeypatch.setattr(
        index_sw.requests,
        "get",
        lambda *args, **kwargs: type("Response", (), {"text": "<table></table>"})(),
    )

    result = index_sw.sw_index_third_cons(symbol="850111.SI")

    assert len(result.columns) == 17
    assert "营业收入同比增长(06-30)" in result.columns


@pytest.mark.parametrize(
    ("function_name", "expected_columns"),
    [
        (
            "sw_index_first_info",
            ["行业代码", "行业名称", "成份个数", "静态市盈率", "TTM(滚动)市盈率", "市净率", "静态股息率"],
        ),
        (
            "sw_index_second_info",
            [
                "行业代码",
                "行业名称",
                "上级行业",
                "成份个数",
                "静态市盈率",
                "TTM(滚动)市盈率",
                "市净率",
                "静态股息率",
            ],
        ),
        (
            "sw_index_third_info",
            [
                "行业代码",
                "行业名称",
                "上级行业",
                "成份个数",
                "静态市盈率",
                "TTM(滚动)市盈率",
                "市净率",
                "静态股息率",
            ],
        ),
    ],
)
def test_sw_index_info_returns_empty_when_source_container_missing(
    monkeypatch, function_name, expected_columns
):
    from akshare.index import index_sw

    monkeypatch.setattr(
        index_sw.requests,
        "get",
        lambda *args, **kwargs: type("Response", (), {"text": "<html></html>"})(),
    )

    result = getattr(index_sw, function_name)()

    assert result.empty
    assert result.columns.tolist() == expected_columns


def test_index_min_sw_returns_empty_when_source_unreachable(monkeypatch):
    from akshare.index import index_research_sw

    monkeypatch.setattr(
        index_research_sw.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            index_research_sw.requests.ConnectionError("connection closed")
        ),
    )

    result = index_research_sw.index_min_sw(symbol="801001")

    assert result.empty
    assert result.columns.tolist() == ["代码", "名称", "价格", "日期", "时间"]


def test_index_hist_sw_returns_empty_when_source_unreachable(monkeypatch):
    from akshare.index import index_research_sw

    monkeypatch.setattr(
        index_research_sw.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            index_research_sw.requests.ConnectionError("connection closed")
        ),
    )

    result = index_research_sw.index_hist_sw(symbol="801001", period="day")

    assert result.empty
    assert result.columns.tolist() == [
        "代码",
        "日期",
        "收盘",
        "开盘",
        "最高",
        "最低",
        "成交量",
        "成交额",
    ]


def test_index_volume_cflp_returns_empty_when_source_unreachable(monkeypatch):
    from akshare.index import index_cflp

    monkeypatch.setattr(
        index_cflp.requests,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            index_cflp.requests.ConnectionError("connection closed")
        ),
    )

    result = index_cflp.index_volume_cflp(symbol="月指数")

    assert result.empty
    assert result.columns.tolist() == ["日期", "定基指数", "环比指数", "同比指数"]


def test_index_hist_fund_sw_returns_empty_when_source_unreachable(monkeypatch):
    from akshare.index import index_research_fund_sw

    monkeypatch.setattr(
        index_research_fund_sw.requests,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            index_research_fund_sw.requests.SSLError("certificate verify failed")
        ),
    )

    result = index_research_fund_sw.index_hist_fund_sw(symbol="807100", period="day")

    assert result.empty
    assert result.columns.tolist() == ["日期", "收盘指数", "开盘指数", "最高指数", "最低指数", "涨跌幅"]


def test_index_analysis_daily_sw_returns_empty_when_source_empty(monkeypatch):
    from akshare.index import index_research_sw

    captured_params: list[dict[str, object]] = []

    class Response:
        def json(self):
            return {"data": {"count": 0, "results": []}}

    def fake_get(*args, **kwargs):
        captured_params.append(dict(kwargs["params"]))
        return Response()

    monkeypatch.setattr(index_research_sw.requests, "get", fake_get)

    result = index_research_sw.index_analysis_daily_sw(
        symbol="市场表征", start_date="20260620", end_date="20260620"
    )

    assert result.empty
    assert captured_params[0]["page_size"] == "10000"
    assert result.columns.tolist() == [
        "指数代码",
        "指数名称",
        "发布日期",
        "收盘指数",
        "成交量",
        "涨跌幅",
        "换手率",
        "市盈率",
        "市净率",
        "均价",
        "成交额占比",
        "流通市值",
        "平均流通市值",
        "股息率",
    ]


def test_index_sugar_msweet_numeric_patch_handles_string_columns(monkeypatch):
    from akshare.index import index_sugar

    class Response:
        def json(self):
            return {
                "category": [f"2020-01-{index % 28 + 1:02d}" for index in range(3227)],
                "data": [["1.1", "2.2", "3.3"] for _ in range(3227)],
            }

    monkeypatch.setattr(index_sugar.requests, "get", lambda *args, **kwargs: Response())

    result = index_sugar.index_sugar_msweet()

    assert result.loc[3226, "原糖价格"] == 12.88
    assert pd.api.types.is_numeric_dtype(result["原糖价格"])


def test_index_inner_quote_sugar_msweet_numeric_patch_handles_string_columns(monkeypatch):
    from akshare.index import index_sugar

    class Response:
        def json(self):
            row = ["1.1"] * 12
            row[4] = "=(E9+F9)/2-(C9+D9)/2"
            return {
                "category": [f"2020/01/{index % 28 + 1:02d}" for index in range(989)],
                "data": [row for _ in range(989)],
            }

    monkeypatch.setattr(index_sugar.requests, "get", lambda *args, **kwargs: Response())

    result = index_sugar.index_inner_quote_sugar_msweet()

    assert result.loc[988, "泰国糖"] == 4045.2
    assert pd.api.types.is_numeric_dtype(result["泰国糖"])
    assert pd.api.types.is_numeric_dtype(result["利润MA5"])
    assert pd.isna(result.loc[8, "利润MA5"])


def test_index_stock_cons_weight_csindex_returns_empty_on_bad_source(monkeypatch):
    from akshare.index import index_cons

    class Response:
        status_code = 404
        content = b"not excel"

    monkeypatch.setattr(index_cons.requests, "get", lambda *args, **kwargs: Response())

    result = index_cons.index_stock_cons_weight_csindex(symbol="930715")

    assert result.empty
    assert result.columns.tolist() == [
        "日期",
        "指数代码",
        "指数名称",
        "指数英文名称",
        "成分券代码",
        "成分券名称",
        "成分券英文名称",
        "交易所",
        "交易所英文名称",
        "权重",
    ]


def test_index_stock_cons_weight_csindex_normalizes_13_column_bond_files(monkeypatch):
    from akshare.index import index_cons

    class Response:
        status_code = 200
        content = b"excel"

    source_df = pd.DataFrame(
        [
            [
                20260529,
                923,
                "公司债指",
                "Enterprise Bond",
                "12中交03",
                "ETCB 20120809 15Y 5.15%",
                122175.0,
                "12中交03",
                None,
                None,
                None,
                None,
                0.061,
            ]
        ]
    )

    monkeypatch.setattr(index_cons.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(index_cons.pd, "read_excel", lambda *args, **kwargs: source_df)

    result = index_cons.index_stock_cons_weight_csindex(symbol="000923")

    assert result.loc[0, "指数代码"] == "000923"
    assert result.loc[0, "成分券代码"] == "122175"
    assert result.loc[0, "成分券名称"] == "12中交03"
    assert result.loc[0, "交易所"] == "上海证券交易所"
    assert result.loc[0, "权重"] == 0.061


def test_bond_buy_back_em_returns_empty_after_request_errors(monkeypatch):
    from requests import ConnectionError

    from akshare.bond import bond_buy_back_em

    def fake_get(*args, **kwargs):
        raise ConnectionError("remote closed")

    monkeypatch.setattr(bond_buy_back_em.requests, "get", fake_get)

    sh_result = bond_buy_back_em.bond_sh_buy_back_em()
    sz_result = bond_buy_back_em.bond_sz_buy_back_em()

    assert sh_result.empty
    assert sz_result.empty
    assert sh_result.columns.tolist() == [
        "序号",
        "代码",
        "名称",
        "最新价",
        "涨跌额",
        "涨跌幅",
        "今开",
        "最高",
        "最低",
        "昨收",
        "成交量",
        "成交额",
    ]


def test_bond_buy_back_em_formats_valid_response(monkeypatch):
    from akshare.bond import bond_buy_back_em

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "diff": [
                        {
                            "f2": "1234",
                            "f3": "567",
                            "f4": "89",
                            "f5": "100",
                            "f6": "200",
                            "f12": "204001",
                            "f14": "GC001",
                            "f15": "1300",
                            "f16": "1200",
                            "f17": "1210",
                            "f18": "1220",
                        }
                    ]
                }
            }

    monkeypatch.setattr(bond_buy_back_em.requests, "get", lambda *args, **kwargs: Response())

    result = bond_buy_back_em.bond_sh_buy_back_em()

    assert result.loc[0, "代码"] == "204001"
    assert result.loc[0, "最新价"] == 1.234
    assert result.loc[0, "涨跌幅"] == 5.67


def test_bond_buy_back_hist_em_returns_empty_on_bad_source(monkeypatch):
    from akshare.bond import bond_buy_back_em

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"klines": ["2026-06-20,1,2"]}}

    monkeypatch.setattr(bond_buy_back_em.requests, "get", lambda *args, **kwargs: Response())

    result = bond_buy_back_em.bond_buy_back_hist_em("204001")

    assert result.empty
    assert result.columns.tolist() == ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额"]


def test_bond_china_close_return_returns_empty_on_empty_records(monkeypatch):
    from akshare.bond import bond_china_money

    monkeypatch.setattr(
        bond_china_money,
        "bond_china_close_return_map",
        lambda: pd.DataFrame([{"cnLabel": "国债", "value": "CYCC000"}]),
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"records": []}

    monkeypatch.setattr(bond_china_money.requests, "get", lambda *args, **kwargs: Response())

    result = bond_china_money.bond_china_close_return(
        symbol="国债", start_date="20260619", end_date="20260619"
    )

    assert result.empty
    assert result.columns.tolist() == ["日期", "期限", "到期收益率", "即期收益率", "远期收益率"]


def test_bond_china_close_return_handles_missing_new_date_value(monkeypatch):
    from akshare.bond import bond_china_money

    monkeypatch.setattr(
        bond_china_money,
        "bond_china_close_return_map",
        lambda: pd.DataFrame([{"cnLabel": "国债", "value": "CYCC000"}]),
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "records": [
                    {
                        "newDateValueCN": "2026-06-18",
                        "yearTermStr": "0.083",
                        "maturityYieldStr": "1.0415",
                        "currentYieldStr": "1.0415",
                        "futureYieldStr": "---",
                    }
                ]
            }

    monkeypatch.setattr(bond_china_money.requests, "get", lambda *args, **kwargs: Response())

    result = bond_china_money.bond_china_close_return(
        symbol="国债", start_date="20260618", end_date="20260618"
    )

    assert result.loc[0, "日期"] == pd.Timestamp("2026-06-18").date()
    assert result.loc[0, "期限"] == 0.083
    assert result.loc[0, "到期收益率"] == 1.0415
    assert pd.isna(result.loc[0, "远期收益率"])


def test_index_bloomberg_billionaires_returns_empty_when_table_missing(monkeypatch):
    from akshare.fortune import fortune_bloomberg

    class Response:
        text = "<html><body><div>blocked or changed page</div></body></html>"

    monkeypatch.setattr(fortune_bloomberg.requests, "get", lambda *args, **kwargs: Response())

    result = fortune_bloomberg.index_bloomberg_billionaires()

    assert result.empty
    assert result.columns.tolist() == [
        "rank",
        "name",
        "total_net_worth",
        "last_change",
        "YTD_change",
        "country",
        "industry",
    ]


def test_index_bloomberg_billionaires_hist_returns_empty_when_table_missing(monkeypatch):
    from akshare.fortune import fortune_bloomberg

    class Response:
        text = "<html><body><div>blocked or changed page</div></body></html>"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(fortune_bloomberg.requests, "get", lambda *args, **kwargs: Response())

    result = fortune_bloomberg.index_bloomberg_billionaires_hist(year="2021")

    assert result.empty
    assert result.columns.tolist() == [
        "rank",
        "name",
        "age",
        "country",
        "total_net_worth",
        "last_change",
        "ytd_change",
        "industry",
    ]


def test_xincaifu_rank_returns_standard_empty_when_source_unavailable(monkeypatch):
    from akshare.fortune import fortune_xincaifu_500

    monkeypatch.setattr(
        fortune_xincaifu_500.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            fortune_xincaifu_500.requests.RequestException("dns failed")
        ),
    )

    result = fortune_xincaifu_500.xincaifu_rank()

    assert result.empty
    assert result.columns.tolist() == [
        "排名",
        "财富",
        "姓名",
        "主要公司",
        "相关行业",
        "公司总部",
        "性别",
        "年龄",
        "年份",
    ]


def test_index_global_hist_em_returns_empty_when_eastmoney_unreachable(monkeypatch):
    from akshare.index import index_global_em

    monkeypatch.setattr(
        index_global_em.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            index_global_em.requests.ConnectionError("connection closed")
        ),
    )

    result = index_global_em.index_global_hist_em(symbol="美元指数")

    assert result.empty
    assert result.columns.tolist() == [
        "日期",
        "代码",
        "名称",
        "今开",
        "最新价",
        "最高",
        "最低",
        "振幅",
    ]


def test_index_global_hist_sina_accepts_legacy_default_alias(monkeypatch):
    from akshare.index import index_global_sina

    class Response:
        def json(self):
            return {"result": {"data": []}}

    monkeypatch.setattr(index_global_sina.requests, "get", lambda *args, **kwargs: Response())

    result = index_global_sina.index_global_hist_sina(symbol="OMX")

    assert result.empty
    assert result.columns.tolist() == ["date", "open", "high", "low", "close", "volume"]


def test_index_global_hist_sina_defaults_to_all_indices(monkeypatch):
    from akshare.index import index_global_sina

    calls = []

    class Response:
        def json(self):
            return {
                "result": {
                    "data": [
                        {
                            "d": "2026-06-19",
                            "o": "1",
                            "h": "2",
                            "l": "0.5",
                            "c": "1.5",
                            "v": "100",
                        }
                    ]
                }
            }

    monkeypatch.setattr(
        index_global_sina,
        "index_global_sina_symbol_map",
        {"指数A": "AAA", "指数B": "BBB"},
    )

    def fake_get(*args, **kwargs):
        calls.append(kwargs["params"]["symbol"])
        return Response()

    monkeypatch.setattr(index_global_sina.requests, "get", fake_get)

    result = index_global_sina.index_global_hist_sina()

    assert calls == ["AAA", "BBB"]
    assert result["index_name"].tolist() == ["指数A", "指数B"]
    assert result.columns.tolist() == [
        "index_name",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]


def test_stock_hk_index_spot_em_returns_empty_when_eastmoney_unreachable(monkeypatch):
    from akshare.index import index_stock_hk

    def fail_paginated_data(*args, **kwargs):
        raise RuntimeError("Eastmoney paginated endpoint request failed")

    monkeypatch.setattr(index_stock_hk, "fetch_paginated_data", fail_paginated_data)

    result = index_stock_hk.stock_hk_index_spot_em()

    assert result.empty
    assert result.columns.tolist() == [
        "序号",
        "内部编号",
        "代码",
        "名称",
        "最新价",
        "涨跌额",
        "涨跌幅",
        "今开",
        "最高",
        "最低",
        "昨收",
        "成交量",
        "成交额",
    ]


def test_futures_dce_position_rank_returns_empty_for_non_zip_response(monkeypatch):
    import akshare.futures.cot as cot

    class FakeResponse:
        content = b"<html>service unavailable</html>"
        status_code = 200

        def raise_for_status(self):
            return None

    monkeypatch.setattr(cot, "calendar", {"20240102"})
    monkeypatch.setattr(cot.requests, "post", lambda *args, **kwargs: FakeResponse())

    assert cot.futures_dce_position_rank(date="20240102") == {}


def test_futures_dce_position_rank_returns_empty_for_http_error(monkeypatch):
    import akshare.futures.cot as cot

    class FakeResponse:
        content = b""
        status_code = 412

    monkeypatch.setattr(cot, "calendar", {"20240102"})
    monkeypatch.setattr(cot.requests, "post", lambda *args, **kwargs: FakeResponse())

    assert cot.futures_dce_position_rank(date="20240102") == {}


def test_futures_delivery_match_czce_returns_empty_for_non_excel_response(monkeypatch):
    from akshare.futures import futures_to_spot

    class FakeResponse:
        content = b"<html>not found</html>"
        status_code = 200
        encoding = None

    monkeypatch.setattr(
        futures_to_spot.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )

    result = futures_to_spot.futures_delivery_match_czce(date="20251203")

    assert result.empty
    assert result.columns.tolist() == [
        "卖方会员",
        "卖方会员-会员简称",
        "买方会员",
        "买方会员-会员简称",
        "交割量",
        "配对日期",
        "合约代码",
    ]


def test_futures_delivery_czce_returns_empty_for_non_excel_response(monkeypatch):
    from akshare.futures import futures_to_spot

    class FakeResponse:
        content = b"<html>not found</html>"
        status_code = 200
        encoding = None

    monkeypatch.setattr(
        futures_to_spot.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )

    result = futures_to_spot.futures_delivery_czce(date="20251203")

    assert result.empty
    assert result.columns.tolist() == ["品种", "交割数量", "交割额"]


def test_futures_to_spot_dce_returns_empty_when_no_tables(monkeypatch):
    from akshare.futures import futures_to_spot

    class FakeResponse:
        text = "<html></html>"

    monkeypatch.setattr(futures_to_spot.requests, "post", lambda *args, **kwargs: FakeResponse())

    result = futures_to_spot.futures_to_spot_dce(date="202312")

    assert result.empty


def test_futures_to_spot_shfe_returns_empty_for_non_json_response(monkeypatch):
    from akshare.futures import futures_to_spot

    class FakeResponse:
        status_code = 200

        def json(self):
            raise ValueError("not json")

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(futures_to_spot, "_get_session_with_ssl", lambda: FakeSession())

    result = futures_to_spot.futures_to_spot_shfe(date="202606")

    assert result.empty
    assert result.columns.tolist() == ["日期", "合约", "交割量", "期转现量"]


def test_futures_delivery_shfe_returns_empty_for_non_json_response(monkeypatch):
    from akshare.futures import futures_to_spot

    class FakeResponse:
        status_code = 200
        encoding = None

        def json(self):
            raise ValueError("not json")

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(futures_to_spot, "_get_session_with_ssl", lambda: FakeSession())

    result = futures_to_spot.futures_delivery_shfe(date="202602")

    assert result.empty
    assert result.columns.tolist() == [
        "品种",
        "交割量-本月",
        "交割量-比重",
        "交割量-本年累计",
        "交割量-累计同比",
    ]


def test_futures_zh_spot_returns_empty_for_expired_symbol_response(monkeypatch):
    from akshare.futures import futures_zh_sina

    class FakeResponse:
        text = 'var hq_str_nf_V2309="";'

    monkeypatch.setattr(futures_zh_sina.requests, "get", lambda *args, **kwargs: FakeResponse())

    result = futures_zh_sina.futures_zh_spot(symbol="V2309", market="CF", adjust="0")

    assert result.empty


def test_foreign_commodity_realtime_fetches_all_symbols_when_missing_param():
    from app.data_fetch.scripts.futures.hourly.futures_foreign_commodity_realtime import (
        FuturesForeignCommodityRealtime,
    )

    calls: list[tuple[str, dict[str, object]]] = []
    service = object.__new__(FuturesForeignCommodityRealtime)
    service.table_name = "FUTURES_FOREIGN_COMMODITY_REALTIME"
    service.create_table_sql = "CREATE TABLE FUTURES_FOREIGN_COMMODITY_REALTIME"
    service.logger = type(
        "Logger",
        (),
        {
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.create_table_if_not_exists = lambda *args, **kwargs: None
    service.save_data = lambda *args, **kwargs: None

    def fake_fetch_ak_data(function_name, **kwargs):
        calls.append((function_name, kwargs))
        if function_name == "futures_foreign_commodity_subscribe_exchange_symbol":
            return pd.DataFrame({"symbol": ["伦敦金", "伦敦银"], "code": ["XAU", "XAG"]})
        return pd.DataFrame([{"symbol": "XAU"}])

    service.fetch_ak_data = fake_fetch_ak_data

    result = service.fetch_data()

    assert result.to_dict("records") == [{"symbol": "XAU", "data_date": result.loc[0, "data_date"]}]
    assert calls[1] == ("futures_foreign_commodity_realtime", {"symbol": ["XAU", "XAG"]})


def test_akshare_foreign_commodity_realtime_defaults_to_all_symbols(monkeypatch):
    from akshare.futures import futures_hq_sina

    captured_urls: list[str] = []

    class FakeResponse:
        text = 'var hq_str_hf_XAU="1,2,3,4,5,6,7,8,9,10,11,12,2026-06-20,伦敦金";'

    monkeypatch.setattr(
        futures_hq_sina,
        "futures_foreign_commodity_subscribe_exchange_symbol",
        lambda: pd.DataFrame({"symbol": ["伦敦金"], "code": ["XAU"]}),
    )

    def fake_get(url, **kwargs):
        captured_urls.append(url)
        return FakeResponse()

    monkeypatch.setattr(futures_hq_sina.requests, "get", fake_get)

    result = futures_hq_sina.futures_foreign_commodity_realtime()

    assert any("hf_XAU" in url for url in captured_urls)
    assert not result.empty


def test_akshare_foreign_commodity_realtime_accepts_subscribe_list(monkeypatch):
    from akshare.futures import futures_hq_sina

    class FakeResponse:
        text = 'var hq_str_hf_XAU="1,2,3,4,5,6,7,8,9,10,11,12,2026-06-20,伦敦金";'

    monkeypatch.setattr(
        futures_hq_sina,
        "futures_foreign_commodity_subscribe_exchange_symbol",
        lambda: ["XAU"],
    )
    monkeypatch.setattr(futures_hq_sina.requests, "get", lambda *args, **kwargs: FakeResponse())

    result = futures_hq_sina.futures_foreign_commodity_realtime()

    assert not result.empty


def test_futures_spot_sys_returns_empty_when_symbol_list_missing(monkeypatch):
    from akshare.futures_derivative import futures_spot_sys

    class FakeResponse:
        text = "<html></html>"

    monkeypatch.setattr(futures_spot_sys.requests, "get", lambda *args, **kwargs: FakeResponse())

    result = futures_spot_sys.futures_spot_sys(symbol="铜", indicator="市场价格")

    assert result.empty


def test_shfe_delivery_script_uses_shfe_target_table():
    from app.data_fetch.scripts.futures.monthly.shfe_delivery_data import FuturesDeliveryShfe

    calls: list[tuple[str, object]] = []
    service = object.__new__(FuturesDeliveryShfe)
    service.table_name = "FUTURES_DELIVERY_SHFE"
    service.table_exists = lambda table_name: True
    service.fetch_ak_data = lambda *args, **kwargs: pd.DataFrame(
        [
            {
                "品种": "铜",
                "交割量-本月": "1",
                "交割量-比重": "0.1",
                "交割量-本年累计": "2",
                "交割量-累计同比": "0.2",
            }
        ]
    )
    service.get_uuid = lambda: "RID"
    service.get_current_datetime = lambda: "2024-01-01 00:00:00"
    service.delete_data = lambda table_name, conditions: calls.append(("delete", table_name))
    service.save_data = lambda df, table_name, **kwargs: calls.append(("save", table_name))
    service.disconnect_db = lambda: None
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()

    service.run(start_month="202401", end_month="202401")

    assert calls == [
        ("delete", "FUTURES_DELIVERY_SHFE"),
        ("save", "FUTURES_DELIVERY_SHFE"),
    ]


def test_shfe_contract_info_rebuilds_legacy_chinese_schema():
    from app.data_fetch.scripts.futures.weekly.futures_contract_info_shfe import (
        FuturesContractInfoShfe,
    )

    executed: list[object] = []

    class FakeCursor:
        def execute(self, statement, params=None):
            executed.append((statement, params))

        def fetchall(self):
            return [
                ("合约代码", "text", "YES", "", None, ""),
                ("上市日", "text", "YES", "", None, ""),
                ("交易日", "text", "YES", "", None, ""),
                ("data_date", "text", "YES", "", None, ""),
            ]

    class FakeConnection:
        def commit(self):
            executed.append(("COMMIT", None))

        def rollback(self):
            executed.append(("ROLLBACK", None))

    service = object.__new__(FuturesContractInfoShfe)
    service.table_name = "FUTURES_CONTRACT_INFO_SHFE"
    service.create_table_sql = "CREATE TABLE `FUTURES_CONTRACT_INFO_SHFE` (`TRADE_DATE` DATE)"
    service.required_columns = {"R_ID", "CONTRACT_CODE", "TRADE_DATE"}
    service.target_columns = ["R_ID", "CONTRACT_CODE", "TRADE_DATE"]
    service.cursor = FakeCursor()
    service.connection = FakeConnection()
    service._columns_cache = {}
    service._table_exists_cache = {}
    service.logger = type(
        "Logger",
        (),
        {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
            "error": lambda *args, **kwargs: None,
        },
    )()
    service.table_exists = lambda table_name: True
    service.connect_db = lambda: None
    service.disconnect_db = lambda: None
    service._migrate_legacy_rows = lambda backup_table: executed.append(("MIGRATE", backup_table))

    service._ensure_current_table_schema()

    statements = [item[0] for item in executed]
    assert statements[0] == "SHOW COLUMNS FROM `FUTURES_CONTRACT_INFO_SHFE`"
    assert any(
        statement.startswith(
            "RENAME TABLE `FUTURES_CONTRACT_INFO_SHFE` TO `FUTURES_CONTRACT_INFO_SHFE_LEGACY_"
        )
        for statement in statements
        if isinstance(statement, str)
    )
    assert "CREATE TABLE `FUTURES_CONTRACT_INFO_SHFE` (`TRADE_DATE` DATE)" in statements
    assert ("COMMIT", None) in executed
    assert any(
        item[0] == "MIGRATE"
        and str(item[1]).startswith("FUTURES_CONTRACT_INFO_SHFE_LEGACY_")
        for item in executed
    )


def test_normalize_dataframe_makes_non_ascii_columns_unique():
    service = object.__new__(AkshareDataService)
    dataframe = pd.DataFrame([[1, 2, 3, 4]], columns=["品种", "名称", "data", "品种"])

    normalized = service.normalize_dataframe(dataframe)

    assert normalized.columns.tolist() == ["col_1", "col_2", "data", "col_4"]


def test_normalize_dataframe_serializes_complex_cell_values():
    service = object.__new__(AkshareDataService)
    dataframe = pd.DataFrame(
        [{"stats": {"ok": 1, "failed": 0}, "failures": [{"endpoint": "demo"}]}]
    )

    normalized = service.normalize_dataframe(dataframe)

    assert normalized.loc[0, "stats"] == '{"ok": 1, "failed": 0}'
    assert normalized.loc[0, "failures"] == '[{"endpoint": "demo"}]'


def test_mysql_table_creation_uses_dynamic_row_format_for_wide_frames():
    class DummyDialect:
        name = "mysql"

    class DummyConnection:
        dialect = DummyDialect()

        def __init__(self) -> None:
            self.statements: list[str] = []

        def exec_driver_sql(self, statement: str) -> None:
            self.statements.append(statement)

    connection = DummyConnection()
    dataframe = pd.DataFrame(
        {
            "symbol": ["000001"],
            "ratio": [1.23],
            "amount": [100],
            "reported_at": pd.to_datetime(["2024-01-01 09:30:00"]),
        }
    )

    AkshareDataService._create_mysql_table_for_dataframe(
        connection,
        "wide_financial_report",
        dataframe,
    )

    statement = connection.statements[0]
    assert "ENGINE=InnoDB ROW_FORMAT=DYNAMIC" in statement
    assert "`symbol` LONGTEXT NULL" in statement
    assert "`ratio` DOUBLE NULL" in statement
    assert "`amount` BIGINT NULL" in statement
    assert "`reported_at` DATETIME NULL" in statement


def test_compact_mysql_dataframe_preserves_wide_rows_as_json_payload():
    dataframe = pd.DataFrame(
        [
            {
                "symbol": "000001",
                "name": "平安银行",
                "ratio": 1.23,
            }
        ]
    )

    compact = AkshareDataService._compact_dataframe_for_mysql(dataframe)

    assert compact.columns.tolist() == ["_akshare_row", "_akshare_payload"]
    assert compact.loc[0, "_akshare_row"] == 1
    assert '"symbol": "000001"' in compact.loc[0, "_akshare_payload"]
    assert '"name": "平安银行"' in compact.loc[0, "_akshare_payload"]


@pytest.mark.asyncio
async def test_persist_dataframe_handles_empty_columnless_dataframe(warehouse_engine):
    async with async_session_maker() as session:
        session.add(
            DataTable(
                id=1,
                table_name="fx_quote_baidu",
                table_comment="old",
                row_count=99,
                metadata_json={"columns": ["old"]},
            )
        )
        await session.commit()

        script = DataScript(
            script_id="fx_quote_baidu",
            script_name="FX Quote Baidu",
            target_table="fx_quote_baidu",
            category="common",
        )
        service = AkshareDataService(session)

        table = await service.persist_dataframe(script, pd.DataFrame(), {})

        assert table.table_name == "fx_quote_baidu"
        assert table.row_count == 0
        assert table.metadata_json == {"columns": []}


@pytest.mark.asyncio
async def test_persist_dataframe_preserves_existing_table_on_empty_columned_result(warehouse_engine):
    async with warehouse_engine.begin() as conn:
        await conn.execute(text("CREATE TABLE index_zh_a_hist (`日期` TEXT, `开盘` REAL)"))
        await conn.execute(
            text("INSERT INTO index_zh_a_hist (`日期`, `开盘`) VALUES ('2026-02-13', 1.0)")
        )

    async with async_session_maker() as session:
        session.add(
            DataTable(
                id=2,
                table_name="index_zh_a_hist",
                table_comment="old",
                row_count=1,
                metadata_json={"columns": ["日期", "开盘"]},
            )
        )
        await session.commit()

        script = DataScript(
            script_id="index_zh_a_hist",
            script_name="Index Zh A Hist",
            target_table="INDEX_ZH_A_HIST",
            category="indexs",
        )
        service = AkshareDataService(session)

        table = await service.persist_dataframe(script, pd.DataFrame(columns=["日期", "开盘"]), {})

    async with warehouse_engine.connect() as conn:
        count = await conn.scalar(text("SELECT COUNT(*) FROM index_zh_a_hist"))

    assert count == 1
    assert table.row_count == 1
    assert table.metadata_json == {"columns": ["日期", "开盘"]}


@pytest.mark.asyncio
async def test_persist_dataframe_preserves_historical_table_on_smaller_result(warehouse_engine):
    async with warehouse_engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE index_global_hist_sina "
                "(date TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO index_global_hist_sina "
                "(date, open, high, low, close, volume) "
                "VALUES ('2026-06-18', 1, 2, 0.5, 1.5, 100), "
                "('2026-06-19', 2, 3, 1.5, 2.5, 200)"
            )
        )

    async with async_session_maker() as session:
        session.add(
            DataTable(
                id=3,
                table_name="index_global_hist_sina",
                table_comment="old",
                row_count=2,
                metadata_json={"columns": ["date", "open", "high", "low", "close", "volume"]},
            )
        )
        await session.commit()

        script = DataScript(
            script_id="index_global_hist_sina",
            script_name="Index Global Hist Sina",
            target_table="INDEX_GLOBAL_HIST_SINA",
            category="indexs",
        )
        service = AkshareDataService(session)

        table = await service.persist_dataframe(
            script,
            pd.DataFrame(
                [
                    {
                        "date": "2026-06-19",
                        "open": 2,
                        "high": 3,
                        "low": 1.5,
                        "close": 2.5,
                        "volume": 200,
                    }
                ]
            ),
            {},
        )

    async with warehouse_engine.connect() as conn:
        count = await conn.scalar(text("SELECT COUNT(*) FROM index_global_hist_sina"))

    assert count == 2
    assert table.row_count == 2
    assert table.metadata_json == {"columns": ["date", "open", "high", "low", "close", "volume"]}


def test_resolve_module_callable_prefers_legacy_fetch_data_over_stale_main():
    module = ModuleType("test_legacy_fetch_script")

    def fetch_data(self, **kwargs):
        return pd.DataFrame([{"value": kwargs["value"]}])

    legacy_class = type(
        "LegacyFetchScript",
        (),
        {
            "__module__": module.__name__,
            "fetch_data": fetch_data,
        },
    )

    def main():
        raise AttributeError("'LegacyFetchScript' object has no attribute 'run'")

    module.LegacyFetchScript = legacy_class
    module.main = main

    service = object.__new__(AkshareScriptService)
    callable_obj = service._resolve_module_callable(module, "main")

    assert callable_obj(value=1).to_dict("records") == [{"value": 1}]


def test_coerce_series_result_to_dataframe_preserves_named_index():
    service = object.__new__(AkshareScriptService)
    series = pd.Series(
        [0.12],
        index=pd.Index([pd.Timestamp("2026-06-19")], name="date"),
        name="RV",
    )

    dataframe = service._coerce_to_dataframe(series)

    assert dataframe.columns.tolist() == ["date", "RV"]
    assert dataframe["RV"].tolist() == [0.12]


@pytest.mark.asyncio
async def test_resolve_callable_prefers_akshare_interface_over_generated_module(monkeypatch):
    def interface_callable():
        return "interface"

    def module_callable():
        return "module"

    async def fake_resolve_interface(script):
        return interface_callable

    service = object.__new__(AkshareScriptService)
    monkeypatch.setattr(service, "_resolve_callable_from_interface", fake_resolve_interface)
    monkeypatch.setattr(service, "_resolve_module_callable", lambda module, func_name: module_callable)
    monkeypatch.setattr("app.services.akshare.script.importlib.import_module", lambda name: ModuleType(name))

    script = DataScript(
        script_id="spot_mixed_feed_soozhu",
        module_path="app.data_fetch.scripts.common.hourly.spot_mixed_feed_soozhu",
        function_name=None,
        source="akshare",
        is_custom=False,
    )

    callable_obj = await service._resolve_callable(script)

    assert callable_obj is interface_callable


@pytest.mark.asyncio
async def test_resolve_callable_uses_preferred_local_script(monkeypatch):
    def interface_callable():
        return "interface"

    def module_callable():
        return "module"

    async def fake_resolve_interface(script):
        return interface_callable

    module = ModuleType("local_preferred_script")
    module.PREFER_LOCAL_SCRIPT = True

    service = object.__new__(AkshareScriptService)
    monkeypatch.setattr(service, "_resolve_callable_from_interface", fake_resolve_interface)
    monkeypatch.setattr(service, "_resolve_module_callable", lambda module, func_name: module_callable)
    monkeypatch.setattr("app.services.akshare.script.importlib.import_module", lambda name: module)

    script = DataScript(
        script_id="macro_china_nbs_region",
        module_path="app.data_fetch.scripts.common.daily.macro_china_nbs_region",
        function_name=None,
        source="akshare",
        is_custom=False,
    )

    callable_obj = await service._resolve_callable(script)

    assert callable_obj is module_callable


def test_macro_china_nbs_region_default_queries_are_flattened(monkeypatch):
    from app.data_fetch.scripts.common.daily import macro_china_nbs_region

    script = object.__new__(macro_china_nbs_region.MacroChinaNbsRegion)
    script.table_name = "MACRO_CHINA_NBS_REGION"
    script.create_table_sql = ""
    script.logger = type(
        "Logger",
        (),
        {
            "warning": lambda self, *args, **kwargs: None,
            "info": lambda self, *args, **kwargs: None,
            "error": lambda self, *args, **kwargs: None,
        },
    )()
    created_tables = []
    saved = []
    calls = []

    def fake_create_table(table_name, create_sql):
        created_tables.append(table_name)

    def fake_fetch_ak_data(function_name, **kwargs):
        calls.append((function_name, kwargs))
        return pd.DataFrame(
            [[1.0, 2.0]],
            index=["北京市"],
            columns=pd.Index(["2024年第一季度", "2024年第二季度"], name="地区生产总值_累计值(亿元)"),
        )

    def fake_save_data(df, table_name, **kwargs):
        saved.append((df.copy(), table_name, kwargs))
        return True

    script.create_table_if_not_exists = fake_create_table
    script.fetch_ak_data = fake_fetch_ak_data
    script.save_data = fake_save_data

    result = script.fetch_data()

    assert created_tables == ["MACRO_CHINA_NBS_REGION"]
    assert len(calls) == len(macro_china_nbs_region.DEFAULT_REGION_QUERIES)
    assert all(call[0] == "macro_china_nbs_region" for call in calls)
    assert len(result) == 4
    assert result["record_key"].is_unique
    assert result["item_name"].tolist() == ["北京市", "北京市", "北京市", "北京市"]
    assert result["data_period"].tolist() == [
        "2024年第一季度",
        "2024年第二季度",
        "2024年第一季度",
        "2024年第二季度",
    ]
    assert saved[0][1] == "MACRO_CHINA_NBS_REGION"
    assert saved[0][2] == {
        "on_duplicate_update": True,
        "unique_keys": ["record_key"],
    }


def test_macro_china_nbs_nation_default_queries_are_flattened(monkeypatch):
    from app.data_fetch.scripts.common.daily import macro_china_nbs_nation

    script = object.__new__(macro_china_nbs_nation.MacroChinaNbsNation)
    script.table_name = "MACRO_CHINA_NBS_NATION"
    script.create_table_sql = ""
    script.logger = type(
        "Logger",
        (),
        {
            "warning": lambda self, *args, **kwargs: None,
            "info": lambda self, *args, **kwargs: None,
            "error": lambda self, *args, **kwargs: None,
        },
    )()
    created_tables = []
    saved = []
    calls = []

    def fake_fetch_ak_data(function_name, **kwargs):
        calls.append((function_name, kwargs))
        return pd.DataFrame(
            [[1.0, 2.0]],
            index=["年末总人口(万人)"],
            columns=["2025年", "2024年"],
        )

    script.create_table_if_not_exists = lambda table_name, create_sql: created_tables.append(
        table_name
    )
    script.fetch_ak_data = fake_fetch_ak_data
    script.save_data = lambda df, table_name, **kwargs: saved.append(
        (df.copy(), table_name, kwargs)
    ) or True

    result = script.fetch_data()

    assert created_tables == ["MACRO_CHINA_NBS_NATION"]
    assert len(calls) == len(macro_china_nbs_nation.DEFAULT_NATION_QUERIES)
    assert all(call[0] == "macro_china_nbs_nation" for call in calls)
    assert len(result) == 4
    assert result["record_key"].is_unique
    assert result["item_name"].tolist() == ["年末总人口(万人)"] * 4
    assert result["data_period"].tolist() == ["2025年", "2024年", "2025年", "2024年"]
    assert saved[0][1] == "MACRO_CHINA_NBS_NATION"
    assert saved[0][2] == {
        "on_duplicate_update": True,
        "unique_keys": ["record_key"],
    }


def test_forex_em_returns_standard_empty_when_eastmoney_unreachable(monkeypatch):
    from akshare.forex import forex_em

    monkeypatch.setattr(
        forex_em,
        "fetch_paginated_data",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("closed")),
    )
    monkeypatch.setattr(
        forex_em.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            forex_em.requests.exceptions.ConnectionError("closed")
        ),
    )

    spot = forex_em.forex_spot_em()
    hist = forex_em.forex_hist_em("USDCNH")

    assert spot.empty
    assert spot.columns.tolist() == [
        "序号",
        "代码",
        "名称",
        "最新价",
        "涨跌额",
        "涨跌幅",
        "今开",
        "最高",
        "最低",
        "昨收",
    ]
    assert hist.empty
    assert hist.columns.tolist() == ["日期", "代码", "名称", "今开", "最新价", "最高", "最低", "振幅"]


def test_forex_hist_em_default_uses_spot_universe(monkeypatch):
    from app.data_fetch.scripts.common.daily import forex_hist_em

    script = object.__new__(forex_hist_em.ForexHistEm)
    script.table_name = "FOREX_HIST_EM"
    script.create_table_sql = ""
    script.logger = type(
        "Logger",
        (),
        {
            "warning": lambda self, *args, **kwargs: None,
            "info": lambda self, *args, **kwargs: None,
            "error": lambda self, *args, **kwargs: None,
        },
    )()
    calls = []
    saved = []

    def fake_fetch_ak_data(function_name, **kwargs):
        calls.append((function_name, kwargs))
        if function_name == "forex_spot_em":
            return pd.DataFrame({"代码": ["USDCNH", "EURCNYC"]})
        return pd.DataFrame(
            [
                {
                    "日期": pd.Timestamp("2026-06-19").date(),
                    "代码": kwargs["symbol"],
                    "名称": kwargs["symbol"],
                    "今开": 1.0,
                    "最新价": 1.1,
                    "最高": 1.2,
                    "最低": 0.9,
                    "振幅": 0.3,
                }
            ]
        )

    script.create_table_if_not_exists = lambda *args, **kwargs: None
    script.fetch_ak_data = fake_fetch_ak_data
    script.save_data = lambda df, table_name, **kwargs: saved.append(
        (df.copy(), table_name, kwargs)
    ) or True

    result = script.fetch_data()

    assert calls[0][0] == "forex_spot_em"
    assert [call[1].get("symbol") for call in calls[1:]] == ["USDCNH", "EURCNYC"]
    assert result["代码"].tolist() == ["USDCNH", "EURCNYC"]
    assert saved[0][1] == "FOREX_HIST_EM"
    assert saved[0][2] == {
        "on_duplicate_update": True,
        "unique_keys": ["代码", "日期"],
    }


def test_movie_boxoffice_returns_standard_empty_when_endata_unavailable(monkeypatch):
    from akshare.movie import movie_yien

    monkeypatch.setattr(movie_yien, "_post_endata_json", lambda *args, **kwargs: {})

    cinema_daily = movie_yien.movie_boxoffice_cinema_daily(date="20240219")
    yearly_first_week = movie_yien.movie_boxoffice_yearly_first_week(date="20240219")

    assert cinema_daily.empty
    assert cinema_daily.columns.tolist() == [
        "排序",
        "影院名称",
        "单日票房",
        "单日场次",
        "场均人次",
        "场均票价",
        "上座率",
    ]
    assert yearly_first_week.empty
    assert yearly_first_week.columns.tolist() == [
        "排序",
        "影片名称",
        "类型",
        "首周票房",
        "占总票房比重",
        "场均人次",
        "国家及地区",
        "上映日期",
        "首周天数",
    ]


def test_artist_yien_returns_standard_empty_when_endata_unavailable(monkeypatch):
    from akshare.movie import artist_yien

    monkeypatch.setattr(
        artist_yien, "_post_endata_artist_json", lambda *args, **kwargs: {}
    )

    business = artist_yien.business_value_artist()
    online = artist_yien.online_value_artist()

    assert business.empty
    assert business.columns.tolist() == [
        "排名",
        "艺人",
        "商业价值",
        "专业热度",
        "关注热度",
        "预测热度",
        "美誉度",
        "统计日期",
    ]
    assert online.empty
    assert online.columns.tolist() == [
        "排名",
        "艺人",
        "流量价值",
        "专业热度",
        "关注热度",
        "预测热度",
        "带货力",
        "统计日期",
    ]


def test_energy_carbon_sz_returns_standard_empty_when_cerx_times_out(monkeypatch):
    from akshare.energy import energy_carbon

    monkeypatch.setattr(
        energy_carbon.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            energy_carbon.requests.exceptions.ReadTimeout("timeout")
        ),
    )

    result = energy_carbon.energy_carbon_sz()

    assert result.empty
    assert result.columns.tolist() == [
        "交易日期",
        "市场交易指数",
        "开盘价",
        "最高价",
        "最低价",
        "成交均价",
        "收盘价",
        "成交量",
        "成交额",
    ]


def test_energy_carbon_gz_returns_standard_empty_when_cnemission_blocks(monkeypatch):
    from akshare.energy import energy_carbon

    class Response:
        status_code = 418
        text = ""

    monkeypatch.setattr(
        energy_carbon.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )

    result = energy_carbon.energy_carbon_gz()

    assert result.empty
    assert result.columns.tolist() == [
        "日期",
        "品种",
        "开盘价",
        "收盘价",
        "最高价",
        "最低价",
        "涨跌",
        "涨跌幅",
        "成交数量",
        "成交金额",
    ]


def test_energy_carbon_hb_returns_standard_empty_when_hbets_unreachable(monkeypatch):
    from akshare.energy import energy_carbon

    monkeypatch.setattr(
        energy_carbon.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            energy_carbon.requests.exceptions.ConnectTimeout("timeout")
        ),
    )

    result = energy_carbon.energy_carbon_hb()

    assert result.empty
    assert result.columns.tolist() == [
        "日期",
        "成交价",
        "成交量",
        "最新",
        "涨跌",
    ]


def test_energy_carbon_domestic_returns_standard_empty_when_source_refuses(monkeypatch):
    from akshare.energy import energy_carbon

    monkeypatch.setattr(
        energy_carbon.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            energy_carbon.requests.exceptions.ConnectionError("refused")
        ),
    )

    result = energy_carbon.energy_carbon_domestic()

    assert result.empty
    assert result.columns.tolist() == [
        "日期",
        "成交价",
        "成交量",
        "成交额",
        "地点",
    ]


def test_energy_carbon_bj_returns_standard_empty_when_bjets_blocks(monkeypatch):
    from akshare.energy import energy_carbon

    class Response:
        status_code = 521
        text = ""

    monkeypatch.setattr(
        energy_carbon.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )

    result = energy_carbon.energy_carbon_bj()

    assert result.empty
    assert result.columns.tolist() == [
        "日期",
        "成交量",
        "成交均价",
        "成交额",
        "成交单位",
    ]


def test_article_rlab_rv_returns_empty_series_when_page_unexpected(monkeypatch):
    from akshare.article import risk_rv

    class Response:
        status_code = 200
        text = "<html><body>unexpected</body></html>"

    monkeypatch.setattr(
        risk_rv.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )

    result = risk_rv.article_rlab_rv()

    assert result.empty
    assert result.name == "RV"
    assert result.index.name == "date"


def test_article_oman_rv_returns_empty_series_when_endpoint_unreachable(monkeypatch):
    from akshare.article import risk_rv

    monkeypatch.setattr(
        risk_rv.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            risk_rv.requests.exceptions.ConnectTimeout("timeout")
        ),
    )

    result = risk_rv.article_oman_rv(symbol="FTSE", index="rk_th2")
    short = risk_rv.article_oman_rv_short(symbol="FTSE")

    assert result.empty
    assert result.name == "FTSE-rk_th2"
    assert result.index.name == "date"
    assert short.empty
    assert short.name == "FTSE"
    assert short.index.name == "date"


def test_macro_china_urban_unemployment_returns_standard_empty_on_404(monkeypatch):
    from akshare.economic import macro_china

    class Response:
        status_code = 404
        text = "not found"

    monkeypatch.setattr(
        macro_china.requests,
        "post",
        lambda *args, **kwargs: Response(),
    )

    result = macro_china.macro_china_urban_unemployment()

    assert result.empty
    assert result.columns.tolist() == ["date", "item", "value"]


def test_currency_convert_returns_standard_empty_without_valid_api_key(monkeypatch):
    from akshare.currency import currency

    class Response:
        status_code = 401

        def json(self):
            return {"message": "invalid api key"}

    monkeypatch.setattr(
        currency.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )

    result = currency.currency_convert()

    assert result.empty
    assert result.columns.tolist() == ["item", "value"]


def test_currency_latest_returns_standard_empty_without_valid_api_key(monkeypatch):
    from akshare.currency import currency

    class Response:
        status_code = 401

        def json(self):
            return {"message": "invalid api key"}

    monkeypatch.setattr(
        currency.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )

    result = currency.currency_latest()

    assert result.empty
    assert result.columns.tolist() == ["currency", "date", "base", "rates"]


def test_currency_history_returns_standard_empty_without_valid_api_key(monkeypatch):
    from akshare.currency import currency

    class Response:
        status_code = 401

        def json(self):
            return {"message": "invalid api key"}

    monkeypatch.setattr(
        currency.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )

    result = currency.currency_history()

    assert result.empty
    assert result.columns.tolist() == ["currency", "date", "base", "rates"]


def test_currency_time_series_returns_standard_empty_without_valid_api_key(monkeypatch):
    from akshare.currency import currency

    class Response:
        status_code = 401

        def json(self):
            return {"message": "invalid api key"}

    monkeypatch.setattr(
        currency.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )

    result = currency.currency_time_series()

    assert result.empty
    assert result.columns.tolist() == ["date"]


def test_currency_pair_map_returns_standard_empty_when_investing_blocks(monkeypatch):
    from akshare.fx import currency_investing

    class Response:
        status_code = 403
        text = ""

    monkeypatch.setattr(
        currency_investing.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )

    result = currency_investing.currency_pair_map()

    assert result.empty
    assert result.columns.tolist() == ["name", "code"]


def test_air_quality_hebei_returns_standard_empty_when_endpoint_times_out(monkeypatch):
    from akshare.air import air_hebei

    monkeypatch.setattr(
        air_hebei.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            air_hebei.requests.exceptions.ConnectTimeout("timeout")
        ),
    )

    result = air_hebei.air_quality_hebei()

    assert result.empty
    assert result.columns.tolist() == [
        "城市",
        "区域",
        "监测点",
        "时间",
        "AQI",
        "空气质量等级",
        "首要污染物",
        "经度",
        "纬度",
        "PM10_IAQI",
        "PM10_浓度",
        "PM2.5_IAQI",
        "PM2.5_浓度",
        "一氧化碳_IAQI",
        "一氧化碳_浓度",
        "二氧化氮_IAQI",
        "二氧化氮_浓度",
        "二氧化硫_IAQI",
        "二氧化硫_浓度",
        "臭氧1小时_IAQI",
        "臭氧1小时_浓度",
        "臭氧8小时_IAQI",
        "臭氧8小时_浓度",
    ]


def test_air_quality_hist_returns_empty_when_endpoint_fails(monkeypatch):
    from akshare.air import air_zhenqi

    monkeypatch.setattr(
        air_zhenqi.requests,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            air_zhenqi.requests.exceptions.ConnectTimeout("timeout")
        ),
    )

    result = air_zhenqi.air_quality_hist()

    assert result.empty


@pytest.mark.asyncio
async def test_execute_callable_times_out_threaded_function():
    def slow_callable():
        time.sleep(0.2)
        return "late"

    with pytest.raises(asyncio.TimeoutError):
        await AkshareScriptService._execute_callable(slow_callable, {}, timeout_s=0.01)


@pytest.mark.asyncio
async def test_mark_failed_handles_naive_start_time():
    async with async_session_maker() as session:
        service = AkshareExecutionService(session)
        execution = await service.create_execution(script_id="stock_zh_a_hist")
        execution.status = TaskStatus.RUNNING
        execution.start_time = datetime.utcnow()
        await session.commit()
        await session.refresh(execution)

        failed = await service.mark_failed(execution, "boom")

        assert failed.status == TaskStatus.FAILED
        assert failed.error_message == "boom"
        assert failed.duration is not None


def test_execution_duration_is_never_negative():
    start = datetime(2026, 6, 20, 1, 0, 1)
    end = datetime(2026, 6, 20, 1, 0, 0)

    assert AkshareExecutionService._duration_seconds(start, end) == 0


def test_akshare_catalog_batch_falls_back_to_installed_akshare(monkeypatch):
    from app.data_fetch.scripts.common.hourly import akshare_catalog_batch

    module = ModuleType("akshare")

    def stock_demo():
        return None

    module.stock_demo = stock_demo
    module.not_callable = "ignored"
    module._private = stock_demo

    monkeypatch.setattr(akshare_catalog_batch, "_load_catalog_file", lambda: None)
    monkeypatch.setitem(sys.modules, "akshare", module)

    assert akshare_catalog_batch._load_endpoints_flat() == {"stock_demo": {}}


def test_akshare_catalog_batch_limits_installed_catalog_batches(monkeypatch):
    from app.data_fetch.scripts.common.hourly import akshare_catalog_batch

    calls = []

    def fake_run_endpoint(**kwargs):
        calls.append(kwargs["endpoint_name"])
        return {"success": True, "rows": 1}

    monkeypatch.setattr(
        akshare_catalog_batch,
        "_load_endpoint_catalog",
        lambda: ({f"endpoint_{index}": {} for index in range(5)}, "installed"),
    )
    monkeypatch.setattr(akshare_catalog_batch, "run_endpoint", fake_run_endpoint)
    monkeypatch.setenv("AKSHARE_CATALOG_FALLBACK_BATCH_SIZE", "2")
    monkeypatch.setenv("AKSHARE_CATALOG_CALL_TIMEOUT", "4")

    result = akshare_catalog_batch.run(batch_size=30, batch_index=0)

    assert calls == ["endpoint_0", "endpoint_1"]
    assert result["stats"]["selected"] == 2
    assert result["stats"]["ok"] == 2
    assert result["stats"]["call_timeout"] == 4


def test_script_timeout_prefers_task_override():
    script = DataScript(
        script_id="demo",
        script_name="Demo",
        category="common",
        timeout=120,
    )

    assert AkshareScriptService._script_timeout_seconds(script, timeout_seconds=300) == 300


def test_script_timeout_uses_minimum_for_long_paginated_scripts():
    script = DataScript(
        script_id="stock_us_spot_em",
        script_name="US Stock Spot",
        category="stocks",
        timeout=120,
    )

    assert AkshareScriptService._script_timeout_seconds(script, timeout_seconds=300) == 600
    assert AkshareScriptService._script_timeout_seconds(script, timeout_seconds=900) == 900


@pytest.mark.skip(reason="Tests require real akshare or complex mocking that doesn't work in CI")
class TestAkshareManagementApi:
    async def test_scan_scripts_and_create_task(
        self,
        client: AsyncClient,
        monkeypatch,
        dummy_akshare_module: ModuleType,
    ):
        admin_headers = await get_admin_headers(client)
        monkeypatch.setitem(sys.modules, "akshare", dummy_akshare_module)
        monkeypatch.delitem(
            sys.modules,
            "app.data_fetch.scripts.stocks.daily.stock_zh_a_hist",
            raising=False,
        )

        scan_resp = await client.post("/api/v1/data/scripts/scan", headers=admin_headers)
        assert scan_resp.status_code == 200
        scan_data = scan_resp.json()
        assert scan_data["registered"] + scan_data["updated"] >= 1

        list_resp = await client.get("/api/v1/data/scripts", headers=admin_headers)
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert any(item["script_id"] == "stock_zh_a_hist" for item in list_data["items"])

        task_resp = await client.post(
            "/api/v1/data/tasks",
            headers=admin_headers,
            json={
                "name": "日线采集任务",
                "script_id": "stock_zh_a_hist",
                "schedule_type": "cron",
                "schedule_expression": "0 8 * * 1-5",
                "parameters": {"symbol": "000001"},
                "is_active": True,
                "retry_on_failure": True,
                "max_retries": 3,
                "timeout": 0,
            },
        )
        assert task_resp.status_code == 201
        task_data = task_resp.json()
        assert task_data["script_id"] == "stock_zh_a_hist"

        tasks_resp = await client.get("/api/v1/data/tasks", headers=admin_headers)
        assert tasks_resp.status_code == 200
        assert tasks_resp.json()["total"] == 1

    async def test_bootstrap_interfaces_and_list(
        self,
        client: AsyncClient,
        monkeypatch,
        dummy_akshare_module: ModuleType,
    ):
        admin_headers = await get_admin_headers(client)
        monkeypatch.setitem(sys.modules, "akshare", dummy_akshare_module)

        bootstrap_resp = await client.post(
            "/api/v1/data/interfaces/bootstrap",
            headers=admin_headers,
            params={"refresh": "true"},
        )
        assert bootstrap_resp.status_code == 200
        bootstrap_data = bootstrap_resp.json()
        assert bootstrap_data["created"] + bootstrap_data["updated"] >= 1

        categories_resp = await client.get(
            "/api/v1/data/interfaces/categories", headers=admin_headers
        )
        assert categories_resp.status_code == 200
        assert len(categories_resp.json()) >= 1

        interfaces_resp = await client.get("/api/v1/data/interfaces", headers=admin_headers)
        assert interfaces_resp.status_code == 200
        items = interfaces_resp.json()["items"]
        assert any(item["name"] == "stock_zh_a_hist" for item in items)
        big_default_interface = next(item for item in items if item["name"] == "stock_big_default")
        assert len(big_default_interface["params"][0]["default_value"]) > 255

    async def test_interfaces_endpoints_require_admin(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        categories_resp = await client.get(
            "/api/v1/data/interfaces/categories", headers=auth_headers
        )
        assert categories_resp.status_code == 403

        interfaces_resp = await client.get("/api/v1/data/interfaces", headers=auth_headers)
        assert interfaces_resp.status_code == 403

        detail_resp = await client.get("/api/v1/data/interfaces/1", headers=auth_headers)
        assert detail_resp.status_code == 403

    async def test_tables_list_schema_and_rows(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        warehouse_engine,
    ):
        async with warehouse_engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    CREATE TABLE stock_daily_000001 (
                        date TEXT,
                        close REAL
                    )
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO stock_daily_000001 (date, close)
                    VALUES ('2024-01-02', 10.5), ('2024-01-03', 10.2)
                    """
                )
            )

        async with async_session_maker() as session:
            table = DataTable(
                id=1,
                table_name="stock_daily_000001",
                table_comment="A股日线",
                category="stocks",
                script_id="stock_zh_a_hist",
                row_count=2,
                last_update_status="success",
                metadata_json={"columns": ["date", "close"]},
            )
            session.add(table)
            session.add(
                TaskExecution(
                    execution_id="ak_exec_test001",
                    script_id="stock_zh_a_hist",
                    status=TaskStatus.COMPLETED,
                    triggered_by=TriggeredBy.MANUAL,
                    result={"ok": True},
                )
            )
            await session.commit()

        list_resp = await client.get("/api/v1/data/tables", headers=auth_headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] == 1

        detail_resp = await client.get("/api/v1/data/tables/1", headers=auth_headers)
        assert detail_resp.status_code == 200
        assert detail_resp.json()["table_name"] == "stock_daily_000001"

        schema_resp = await client.get("/api/v1/data/tables/1/schema", headers=auth_headers)
        assert schema_resp.status_code == 200
        schema_data = schema_resp.json()
        assert schema_data["table_name"] == "stock_daily_000001"
        assert {column["name"] for column in schema_data["columns"]} == {"date", "close"}

        rows_resp = await client.get("/api/v1/data/tables/1/data", headers=auth_headers)
        assert rows_resp.status_code == 200
        rows_data = rows_resp.json()
        assert rows_data["total"] == 2
        assert rows_data["rows"][0]["date"] == "2024-01-02"

        execution_resp = await client.get("/api/v1/data/executions", headers=auth_headers)
        assert execution_resp.status_code == 200
        assert execution_resp.json()["total"] == 1
