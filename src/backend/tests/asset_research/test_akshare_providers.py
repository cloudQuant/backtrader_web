"""Deterministic tests for the approved AkShare pilot providers."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from app.schemas.asset_research import (
    BondIdentityDetails,
    FuturesIdentityDetails,
    InstrumentIdentity,
)
from app.services.asset_research.providers import akshare as akshare_providers

CUTOFF = datetime(2026, 8, 7, 11, 10, tzinfo=timezone.utc)


def _futures_identity() -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="futures",
        identity_level="CONTRACT",
        canonical_id="futures:CFFEX:IF2609:CNY",
        display_symbol="IF2609",
        name="沪深300期货2609",
        venue="CFFEX",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="CONTRACT_CODE",
        identifier_value="IF2609",
        product_type="FUTURE",
        metadata_version="akshare-test-v1",
        details=FuturesIdentityDetails(
            product_code="IF",
            contract_month="2609",
            underlying_id="CN:000300",
            expiry_at=datetime(2026, 9, 18, 7, 15, tzinfo=timezone.utc),
            contract_multiplier="300",
            trading_calendar_id="CFFEX",
        ),
    )


def _bond_identity() -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="bond",
        identity_level="PRODUCT",
        canonical_id="bond:SSE:sh110085:CNY",
        display_symbol="sh110085",
        name="通22转债",
        venue="SSE",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="SECURITY_CODE",
        identifier_value="110085",
        product_type="CONVERTIBLE_BOND",
        metadata_version="akshare-test-v1",
        details=BondIdentityDetails(
            bond_identity_kind="LISTING",
            issuer_id="CN600438",
            maturity_date="2028-02-24",
            is_perpetual=False,
            settlement_calendar_id="SSE_BOND",
        ),
    )


class _FakeAk:
    @staticmethod
    def tool_trade_date_hist_sina():
        return pd.DataFrame(
            {
                "trade_date": [
                    "2026-08-06",
                    "2026-08-07",
                    "2026-08-10",
                    "2026-08-11",
                ]
            }
        )

    @staticmethod
    def futures_zh_daily_sina(symbol: str):
        assert symbol == "IF2609"
        return pd.DataFrame(
            [
                {
                    "date": "2026-08-06",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 10,
                    "hold": 100,
                    "settle": 100.4,
                }
            ]
        )

    @staticmethod
    def futures_zh_realtime(symbol: str):
        assert symbol == "沪深300指数期货"
        return pd.DataFrame(
            [
                {
                    "symbol": "IF2609",
                    "exchange": "cffex",
                    "trade": 100.5,
                    "bidprice1": 100.4,
                    "askprice1": 100.6,
                    "bidvol1": 2,
                    "askvol1": 3,
                    "ticktime": "15:00:00",
                    "tradedate": "2026-08-07",
                    "volume": 10,
                    "position": 100,
                }
            ]
        )

    @staticmethod
    def futures_rule(date: str):
        assert date == "20260807"
        return pd.DataFrame(
            [
                {
                    "交易所": "中金所",
                    "品种": "沪深300股指期货",
                    "代码": "IF",
                    "交易保证金比例": 14.0,
                    "涨跌停板幅度": 10.0,
                    "合约乘数": 300,
                    "最小变动价位": 0.2,
                }
            ]
        )

    @staticmethod
    def futures_contract_info_cffex(date: str):
        assert date == "20260807"
        return pd.DataFrame(
            [
                {
                    "合约代码": "IF2609",
                    "合约月份": "2609",
                    "上市日": "2026-03-16",
                    "最后交易日": "2026-09-18",
                    "持仓限额": 2000,
                    "品种": "IF",
                    "查询交易日": "2026-08-07",
                }
            ]
        )

    @staticmethod
    def bond_zh_hs_cov_spot():
        return pd.DataFrame(
            [
                {
                    "symbol": "sh110085",
                    "name": "通22转债",
                    "trade": 118.15,
                    "buy": 118.172,
                    "sell": 118.183,
                    "ticktime": "15:00:02",
                    "volume": 1000,
                    "amount": 100000,
                }
            ]
        )

    @staticmethod
    def bond_cb_profile_sina(symbol: str):
        assert symbol == "sh110085"
        return pd.DataFrame(
            {
                "item": [
                    "债券面值（元）",
                    "起息日期",
                    "到期日",
                    "付息日期",
                    "年付息次数",
                    "利率说明",
                    "信用等级",
                    "全价（元）",
                ],
                "value": [
                    "100",
                    "2022-02-24",
                    "2028-02-24",
                    "02-24",
                    "1",
                    "第一年0.2%、第二年0.4%、第三年0.6%、第四年1.5%、第五年1.8%、第六年2.0%。",
                    "AAA",
                    "118.15",
                ],
            }
        )

    @staticmethod
    def bond_zh_hs_daily(symbol: str):
        assert symbol == "sh110085"
        return pd.DataFrame(
            [
                {
                    "date": "2026-08-07",
                    "open": 118.0,
                    "high": 118.3,
                    "low": 117.8,
                    "close": 118.15,
                    "volume": 1000,
                }
            ]
        )

    @staticmethod
    def bond_china_yield(start_date: str, end_date: str):
        assert start_date <= end_date
        return pd.DataFrame(
            [
                {
                    "曲线名称": "中债国债收益率曲线",
                    "日期": "2026-08-07",
                    "3月": 1.10,
                    "6月": 1.20,
                    "1年": 1.30,
                    "3年": 1.40,
                    "5年": 1.50,
                    "7年": 1.60,
                    "10年": 1.70,
                    "30年": 2.10,
                }
            ]
        )


@pytest.mark.asyncio
async def test_futures_provider_builds_executable_quote_and_calendar(monkeypatch) -> None:
    monkeypatch.setattr(akshare_providers, "_akshare_module", lambda: _FakeAk())

    snapshot = await akshare_providers.AkShareFuturesProvider().collect(
        _futures_identity(),
        cutoff_at=CUTOFF,
    )

    assert snapshot.raw_fields["snapshot"]["bid"] == 100.4
    assert snapshot.raw_fields["snapshot"]["ask"] == 100.6
    assert snapshot.raw_fields["calendar"]["calendar_id"] == "CFFEX"
    assert len(snapshot.raw_fields["calendar"]["sessions"]) == 2
    assert snapshot.raw_fields["futures"]["margin_ratio"] == 14.0
    assert snapshot.source_manifest["capabilities"] == ["price", "contract_calendar"]
    assert len(snapshot.history_rows) == 1
    assert snapshot.content_hash


@pytest.mark.asyncio
async def test_bond_provider_builds_cashflows_curve_benchmark_and_quote(monkeypatch) -> None:
    monkeypatch.setattr(akshare_providers, "_akshare_module", lambda: _FakeAk())
    monkeypatch.setattr(akshare_providers, "_now_utc", lambda: CUTOFF)

    snapshot = await akshare_providers.AkShareBondProvider().collect(
        _bond_identity(),
        cutoff_at=CUTOFF,
    )

    assert snapshot.raw_fields["snapshot"]["bid"] == 118.172
    assert snapshot.raw_fields["snapshot"]["ask"] == 118.183
    assert snapshot.raw_fields["calendar"]["calendar_id"] == "SSE_BOND"
    bond = snapshot.raw_fields["bond"]
    assert len(bond["cashflows"]) == 2
    assert bond["cashflows"][-1]["is_maturity_redemption"] is True
    assert len(bond["curve"]) == 8
    assert bond["benchmark"]["benchmark_id"] == "CN_TREASURY_10Y"
    assert snapshot.source_manifest["capabilities"] == [
        "price",
        "official_valuation",
        "curve",
        "cashflows",
    ]


@pytest.mark.asyncio
async def test_composite_provider_rejects_unsupported_asset(monkeypatch) -> None:
    monkeypatch.setattr(akshare_providers, "_akshare_module", lambda: _FakeAk())
    provider = akshare_providers.AkShareCompositeProvider()

    with pytest.raises(ValueError, match="AKSHARE_PROVIDER_ASSET_UNSUPPORTED"):
        await provider.collect(
            _futures_identity().model_copy(
                update={
                    "asset_type": "stock",
                    "identity_level": "PRODUCT",
                    "canonical_id": "stock:test",
                    "display_symbol": "TEST",
                    "identifier_value": "TEST",
                    "details": {
                        "kind": "STOCK",
                    },
                }
            ),
            cutoff_at=CUTOFF,
        )


def test_akshare_provider_registered_by_orchestrator_only_when_enabled(monkeypatch) -> None:
    from app.services.asset_research import orchestrator

    calls: list[str] = []

    class _Settings:
        ASSET_RESEARCH_AKSHARE_PROVIDER_ENABLED = True

    def fake_factory():
        calls.append("provider")
        return object()

    monkeypatch.setattr(orchestrator, "get_settings", lambda: _Settings())
    monkeypatch.setattr(
        akshare_providers,
        "AkShareCompositeProvider",
        fake_factory,
    )

    orchestrator.AssetResearchOrchestrator(object())  # type: ignore[arg-type]
    assert calls == ["provider"]
