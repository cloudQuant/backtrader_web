"""Regression coverage for the stock-analysis data collection boundary."""

from __future__ import annotations

import json
import sys
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services.stock_analysis.analysis_engine import StockAnalysisEngine
from app.services.stock_analysis.data_collector import StockAnalysisDataCollector
from app.services.stock_analysis.pipeline import StockAnalysisPipeline


class _RefreshAwareMarketService:
    """Expose whether the collector asks an explicit analysis request to refresh."""

    async def lookup(self, **kwargs):
        if kwargs["refresh_online"]:
            history_date = "2026-07-30"
            price = 11.61
        else:
            history_date = "2026-07-03"
            price = 10.88
        return {
            "symbol": "000001",
            "name": "平安银行",
            "provider": "akshare",
            "snapshot": {
                "symbol": "000001",
                "name": "平安银行",
                "price": price,
                "update_time": history_date,
            },
            "history": {
                "rows": [
                    {
                        "date": history_date,
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                        "volume": 100,
                    }
                ]
            },
            "indicators": {},
        }


class _EmptyNewsLibrary:
    async def list_articles(self, _user_id: str, *, ticker: str):
        assert ticker in {"000001.SZ", "000001"}
        return {"items": [], "total": 0}


class _NoNewsLibrary:
    """Return an empty local library without constraining the test ticker."""

    async def list_articles(self, _user_id: str, *, ticker: str):
        return {"items": [], "total": 0}


class _CompanyProfileMarketService:
    """Supply the sparse quote payload that previously caused the warning."""

    async def lookup(self, **kwargs):
        assert kwargs["refresh_online"] is True
        return {
            "symbol": "601398.SH",
            "name": "601398.SH",
            "provider": "akshare",
            "snapshot": {
                "symbol": "601398.SH",
                "name": "601398.SH",
                "price": 8.15,
                "update_time": "2026-07-30",
            },
            "history": {
                "rows": [
                    {
                        "date": "2026-07-30",
                        "open": 8.0,
                        "high": 8.2,
                        "low": 7.9,
                        "close": 8.15,
                        "volume": 100,
                    }
                ]
            },
            "indicators": {},
        }


@pytest.mark.asyncio
async def test_collect_uses_current_cn_market_financial_and_news_data(
    monkeypatch: pytest.MonkeyPatch,
):
    """An explicit stock analysis must not silently reuse stale or empty local data."""
    financial_abstract = pd.DataFrame(
        [
            {"选项": "常用指标", "指标": "营业总收入", "20260331": 35.0, "20251231": 130.0},
            {"选项": "常用指标", "指标": "归母净利润", "20260331": 14.0, "20251231": 42.0},
            {"选项": "常用指标", "指标": "基本每股收益", "20260331": 0.67, "20251231": 2.07},
            {"选项": "常用指标", "指标": "净资产收益率(ROE)", "20260331": 2.83, "20251231": 9.15},
        ]
    )
    financial_indicators = pd.DataFrame(
        [
            {
                "日期": "2026-03-31",
                "主营业务收入增长率(%)": 4.65,
                "净利润增长率(%)": 3.03,
            },
            {
                "日期": "2025-12-31",
                "主营业务收入增长率(%)": -10.4,
                "净利润增长率(%)": -4.21,
            },
        ]
    )
    stock_news = pd.DataFrame(
        [
            {
                "新闻标题": "平安银行发布最新经营数据",
                "新闻内容": "测试新闻正文",
                "发布时间": "2026-07-30 10:00:00",
                "文章来源": "证券时报网",
                "新闻链接": "https://example.test/news/1",
            }
        ]
    )
    monkeypatch.setitem(
        sys.modules,
        "akshare",
        SimpleNamespace(
            stock_financial_abstract=lambda *, symbol: financial_abstract,
            stock_financial_analysis_indicator=lambda *, symbol, start_year: financial_indicators,
            stock_news_em=lambda *, symbol: stock_news,
        ),
    )
    monkeypatch.setattr(
        "app.services.stock_analysis.data_collector.get_news_intelligence_service",
        lambda _db: _EmptyNewsLibrary(),
    )

    collector = StockAnalysisDataCollector(db=SimpleNamespace())
    collector.market_service = _RefreshAwareMarketService()

    snapshot = await collector.collect(
        user_id="collector-test-user",
        symbol="000001.SZ",
        market_type="A股",
        analysis_date=date(2026, 7, 30),
    )

    assert snapshot["history"]["rows"][-1]["date"] == "2026-07-30"
    assert snapshot["financials"]["annual"] == [
        {
            "report_date": "2025-12-31",
            "revenue": 130.0,
            "net_income": 42.0,
            "eps": 2.07,
            "roe": 9.15,
            "revenue_growth": -10.4,
            "profit_growth": -4.21,
        }
    ]
    assert snapshot["financials"]["quarterly"] == [
        {
            "report_date": "2026-03-31",
            "revenue": 35.0,
            "net_income": 14.0,
            "eps": 0.67,
            "roe": 2.83,
            "revenue_growth": 4.65,
            "profit_growth": 3.03,
        }
    ]
    assert snapshot["news"]["total"] == 1
    assert snapshot["news"]["items"][0]["headline"] == "平安银行发布最新经营数据"
    assert snapshot["news"]["items"][0]["sentiment"] == "UNKNOWN"
    assert snapshot["data_quality"]["degraded_reasons"] == []


def test_cn_news_normalization_marks_unsupported_headlines_unknown_not_neutral() -> None:
    news = pd.DataFrame(
        [
            {"新闻标题": "公司公告", "新闻内容": "例行信息披露"},
            {"新闻标题": "业绩增长并获批新业务", "新闻内容": ""},
            {"新闻标题": "收到监管处罚", "新闻内容": ""},
        ]
    )

    items = StockAnalysisDataCollector._normalize_cn_news(news, "000001.SZ")

    assert [item["sentiment"] for item in items] == ["UNKNOWN", "BULLISH", "BEARISH"]


@pytest.mark.asyncio
async def test_collect_enriches_cn_company_profile_and_industry_peers(
    monkeypatch: pytest.MonkeyPatch,
):
    """A-share reports must carry real company context rather than an empty info shell."""
    company_profile = pd.DataFrame(
        [
            {"item": "org_short_name_cn", "value": "中国工商银行"},
            {
                "item": "main_operation_business",
                "value": "从事公司和个人金融业务、资金业务、投资银行业务，并提供资产管理等金融服务。",
            },
            {"item": "affiliate_industry", "value": {"ind_name": "银行"}},
        ]
    )
    industry_members = pd.DataFrame(
        [
            {"代码": "601398", "名称": "工商银行"},
            {"代码": "601939", "名称": "建设银行"},
            {"代码": "601288", "名称": "农业银行"},
            {"代码": "601988", "名称": "中国银行"},
        ]
    )
    monkeypatch.setitem(
        sys.modules,
        "akshare",
        SimpleNamespace(
            stock_financial_abstract=lambda *, symbol: pd.DataFrame(),
            stock_financial_analysis_indicator=lambda *, symbol, start_year: pd.DataFrame(),
            stock_news_em=lambda *, symbol: pd.DataFrame(),
            stock_individual_basic_info_xq=lambda *, symbol: company_profile,
            stock_board_industry_cons_em=lambda *, symbol: industry_members,
        ),
    )
    monkeypatch.setattr(
        "app.services.stock_analysis.data_collector.get_news_intelligence_service",
        lambda _db: _NoNewsLibrary(),
    )
    collector = StockAnalysisDataCollector(db=SimpleNamespace())
    collector.market_service = _CompanyProfileMarketService()

    snapshot = await collector.collect(
        user_id="company-profile-test-user",
        symbol="601398.SH",
        market_type="A股",
        analysis_date=date(2026, 7, 30),
    )

    assert snapshot["info"]["name"] == "中国工商银行"
    assert snapshot["info"]["sector"] == "金融业"
    assert snapshot["info"]["industry"] == "银行"
    assert snapshot["info"]["description"] == (
        "从事公司和个人金融业务、资金业务、投资银行业务，并提供资产管理等金融服务。"
    )
    assert snapshot["peers"] == {
        "items": [
            {"symbol": "601939.SH", "name": "建设银行", "industry": "银行"},
            {"symbol": "601288.SH", "name": "农业银行", "industry": "银行"},
            {"symbol": "601988.SH", "name": "中国银行", "industry": "银行"},
        ],
        "total": 3,
        "provider": "akshare",
    }


def test_ai_source_context_includes_company_profile_and_industry_peers():
    """AI stages need the enriched context, not just the rule-based report."""
    engine = StockAnalysisEngine(
        SimpleNamespace(),
        ai_router=SimpleNamespace(),
        model_preference_service=SimpleNamespace(),
        settings=SimpleNamespace(),
    )

    source_context = json.loads(
        engine._source_context(
            {
                "info": {
                    "name": "中国工商银行",
                    "industry": "银行",
                    "description": "从事公司和个人金融业务。",
                },
                "peers": {
                    "items": [{"symbol": "601939.SH", "name": "建设银行", "industry": "银行"}],
                    "total": 1,
                    "provider": "akshare",
                },
            }
        )
    )

    assert source_context["info"]["description"] == "从事公司和个人金融业务。"
    assert source_context["peers"]["items"][0]["symbol"] == "601939.SH"


@pytest.mark.asyncio
async def test_pipeline_uses_the_most_recent_financial_disclosure_not_only_annual_data():
    """The fundamentals narrative must expose the newest available financial period."""
    output = await StockAnalysisPipeline().run(
        symbol="000001.SZ",
        market_type="A股",
        research_depth="标准",
        selected_modules=["market", "fundamentals", "news", "risk"],
        snapshot={
            "analysis_date": "2026-07-30",
            "quote": {"symbol": "000001.SZ", "name": "平安银行", "price": 11.61},
            "info": {"symbol": "000001.SZ", "name": "平安银行"},
            "history": {
                "rows": [
                    {
                        "date": "2026-07-30",
                        "open": 11.28,
                        "high": 11.62,
                        "low": 11.18,
                        "close": 11.61,
                        "volume": 100,
                    }
                ]
            },
            "technicals": {"factors": {}},
            "financials": {
                "annual": [
                    {
                        "report_date": "2025-12-31",
                        "revenue": 130.0,
                        "net_income": 42.0,
                        "eps": 2.07,
                        "roe": 9.15,
                    }
                ],
                "quarterly": [
                    {
                        "report_date": "2026-03-31",
                        "revenue": 35.0,
                        "net_income": 14.0,
                        "eps": 0.67,
                        "roe": 2.83,
                    }
                ],
            },
            "news": {"items": [], "total": 0},
        },
    )

    assert "最新披露日期：2026-03-31" in output["fundamentals_report"]
    assert "最新披露收入：35.0" in output["fundamentals_report"]


@pytest.mark.asyncio
async def test_pipeline_marks_missing_market_and_financial_data_unavailable_without_defaults() -> (
    None
):
    output = await StockAnalysisPipeline().run(
        symbol="601398.SH",
        market_type="A股",
        research_depth="标准",
        selected_modules=["market", "fundamentals", "news", "risk"],
        snapshot={
            "analysis_date": "2026-07-30",
            "quote": {},
            "info": {"symbol": "601398.SH", "name": "中国工商银行"},
            "history": {"rows": []},
            "technicals": {"factors": {}},
            "financials": {"annual": [], "quarterly": []},
            "news": {"items": [], "total": 0},
        },
    )

    assert output["decision"]["action"] == "观望"
    assert "技术维度不可用" in output["market_report"]
    assert "基本面维度不可用" in output["fundamentals_report"]
    assert "¥100.00" not in output["market_report"]
    assert "财务数据不可用" in output["bull_researcher"]
