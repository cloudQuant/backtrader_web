from types import ModuleType

import pandas as pd
import pytest


@pytest.fixture
def dummy_akshare(monkeypatch) -> ModuleType:
    module = ModuleType("akshare")

    def stock_zh_a_spot_em() -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "代码": "000001",
                    "名称": "平安银行",
                    "最新价": 12.34,
                    "涨跌额": 0.12,
                    "涨跌幅": 0.98,
                    "今开": 12.1,
                    "最高": 12.4,
                    "最低": 12.0,
                    "昨收": 12.22,
                    "成交量": 1000,
                    "成交额": 1234000,
                    "总市值": 100000000,
                    "流通市值": 80000000,
                    "市盈率-动态": 8.1,
                    "市净率": 0.9,
                }
            ]
        )

    def stock_zh_a_hist(**_: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "日期": "2026-06-17",
                    "开盘": 12.0,
                    "最高": 12.3,
                    "最低": 11.9,
                    "收盘": 12.2,
                    "成交量": 100,
                    "成交额": 1200,
                    "涨跌幅": 1.2,
                },
                {
                    "日期": "2026-06-18",
                    "开盘": 12.2,
                    "最高": 12.5,
                    "最低": 12.1,
                    "收盘": 12.4,
                    "成交量": 200,
                    "成交额": 2400,
                    "涨跌幅": 1.6,
                },
            ]
        )

    def futures_zh_spot(**_: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "symbol": "螺纹钢2510",
                    "time": "150000",
                    "open": 2969,
                    "high": 2969,
                    "low": 2940,
                    "current_price": 2950,
                    "bid_price": 2941,
                    "ask_price": 2951,
                    "hold": 7620,
                    "volume": 3060,
                    "avg_price": 2954,
                    "last_close": 2950,
                    "last_settle_price": 2975,
                }
            ]
        )

    def futures_zh_daily_sina(**_: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "date": "2026-06-17",
                    "open": 3000,
                    "high": 3001,
                    "low": 2962,
                    "close": 2970,
                    "volume": 2220,
                    "hold": 9570,
                    "settle": 2975,
                },
                {
                    "date": "2026-06-18",
                    "open": 2969,
                    "high": 2969,
                    "low": 2940,
                    "close": 2950,
                    "volume": 3060,
                    "hold": 7620,
                    "settle": 2954,
                },
            ]
        )

    def bond_zh_hs_cov_spot() -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "symbol": "sh113527",
                    "code": "113527",
                    "name": "维格转债",
                    "trade": 120.5,
                    "pricechange": 0.8,
                    "changepercent": 0.67,
                    "buy": 120.4,
                    "sell": 120.6,
                    "settlement": 119.7,
                    "open": 119.9,
                    "high": 121.0,
                    "low": 119.5,
                    "volume": 500,
                    "amount": 60250,
                    "ticktime": "15:00:00",
                }
            ]
        )

    def bond_zh_hs_cov_daily(**_: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "date": "2026-06-17",
                    "open": 119.5,
                    "high": 120.0,
                    "low": 119.2,
                    "close": 119.7,
                    "volume": 300,
                },
                {
                    "date": "2026-06-18",
                    "open": 119.9,
                    "high": 121.0,
                    "low": 119.5,
                    "close": 120.5,
                    "volume": 500,
                },
            ]
        )

    def fund_etf_spot_em() -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "代码": "159915",
                    "名称": "创业板ETF",
                    "最新价": 1.234,
                    "涨跌额": 0.01,
                    "涨跌幅": 0.82,
                    "开盘价": 1.22,
                    "最高价": 1.24,
                    "最低价": 1.21,
                    "昨收": 1.224,
                    "成交量": 10000,
                    "成交额": 12340,
                    "更新时间": "2026-06-18 15:00:00",
                }
            ]
        )

    def fund_etf_hist_em(**_: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "日期": "2026-06-17",
                    "开盘": 1.20,
                    "最高": 1.23,
                    "最低": 1.19,
                    "收盘": 1.224,
                    "成交量": 9000,
                    "成交额": 11016,
                    "涨跌幅": 0.41,
                },
                {
                    "日期": "2026-06-18",
                    "开盘": 1.22,
                    "最高": 1.24,
                    "最低": 1.21,
                    "收盘": 1.234,
                    "成交量": 10000,
                    "成交额": 12340,
                    "涨跌幅": 0.82,
                },
            ]
        )

    def option_sse_daily_sina(**_: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "日期": "2026-06-17",
                    "开盘": 0.101,
                    "最高": 0.123,
                    "最低": 0.095,
                    "收盘": 0.118,
                    "成交量": 120,
                },
                {
                    "日期": "2026-06-18",
                    "开盘": 0.118,
                    "最高": 0.13,
                    "最低": 0.11,
                    "收盘": 0.126,
                    "成交量": 180,
                },
            ]
        )

    def option_cffex_hs300_daily_sina(**_: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "date": "2026-06-17",
                    "open": 80,
                    "high": 88,
                    "low": 76,
                    "close": 85,
                    "volume": 600,
                },
                {
                    "date": "2026-06-18",
                    "open": 85,
                    "high": 91,
                    "low": 82,
                    "close": 89,
                    "volume": 700,
                },
            ]
        )

    def forex_spot_em() -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "代码": "USDCNH",
                    "名称": "美元离岸人民币",
                    "最新价": 7.18,
                    "涨跌额": -0.01,
                    "涨跌幅": -0.14,
                    "今开": 7.19,
                    "最高": 7.2,
                    "最低": 7.17,
                    "昨收": 7.19,
                    "更新时间": "2026-06-18 15:00:00",
                }
            ]
        )

    def forex_hist_em(**_: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "date": "2026-06-17",
                    "open": 7.20,
                    "high": 7.21,
                    "low": 7.18,
                    "close": 7.19,
                    "volume": 100,
                },
                {
                    "date": "2026-06-18",
                    "open": 7.19,
                    "high": 7.20,
                    "low": 7.17,
                    "close": 7.18,
                    "volume": 110,
                },
            ]
        )

    def crypto_js_spot() -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "市场": "Bitstamp",
                    "交易品种": "BTCJPY",
                    "最近报价": 10000000,
                    "涨跌额": 1000,
                    "涨跌幅": 0.01,
                    "24小时最高": 10100000,
                    "24小时最低": 9900000,
                    "24小时成交量": 123,
                    "更新时间": "2026-06-18 15:00:00",
                }
            ]
        )

    def crypto_bitcoin_cme(**_: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "商品": "BTC",
                    "类型": "Asset Manager",
                    "成交量": 2000,
                    "未平仓合约": 8000,
                    "持仓变化": 120,
                },
                {
                    "商品": "BTC",
                    "类型": "Dealer",
                    "成交量": 1500,
                    "未平仓合约": 6000,
                    "持仓变化": -80,
                },
            ]
        )

    module.stock_zh_a_spot_em = stock_zh_a_spot_em
    module.stock_zh_a_hist = stock_zh_a_hist
    module.futures_zh_spot = futures_zh_spot
    module.futures_zh_daily_sina = futures_zh_daily_sina
    module.bond_zh_hs_cov_spot = bond_zh_hs_cov_spot
    module.bond_zh_hs_cov_daily = bond_zh_hs_cov_daily
    module.fund_etf_spot_em = fund_etf_spot_em
    module.fund_etf_hist_em = fund_etf_hist_em
    module.option_sse_daily_sina = option_sse_daily_sina
    module.option_cffex_hs300_daily_sina = option_cffex_hs300_daily_sina
    module.forex_spot_em = forex_spot_em
    module.forex_hist_em = forex_hist_em
    module.crypto_js_spot = crypto_js_spot
    module.crypto_bitcoin_cme = crypto_bitcoin_cme
    monkeypatch.setitem(__import__("sys").modules, "akshare", module)
    return module


@pytest.fixture(autouse=True)
def disable_market_instrument_warehouse(monkeypatch):
    from app.services.market_instrument import MarketInstrumentService

    async def empty_warehouse_lookup(
        self,
        *,
        asset_type,
        symbol,
        start_date,
        end_date,
        period,
        market,
        warnings,
    ):
        return self._payload(
            asset_type=asset_type,
            symbol=symbol,
            name=symbol,
            market=market or "CN",
            snapshot={},
            rows=[],
            period=period,
            provider="akshare_data",
        )

    monkeypatch.setattr(MarketInstrumentService, "_lookup_warehouse", empty_warehouse_lookup)


@pytest.mark.asyncio
async def test_market_instrument_lookup_returns_stock_snapshot_and_history(
    client,
    auth_headers,
    dummy_akshare,
):
    response = await client.get(
        "/api/v1/data/market-instruments/lookup",
        headers=auth_headers,
        params={
            "asset_type": "stock",
            "symbol": "000001.SZ",
            "start_date": "2026-06-01",
            "end_date": "2026-06-19",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["asset_type"] == "stock"
    assert data["name"] == "平安银行"
    assert data["snapshot"]["price"] == 12.34
    assert data["history"]["total"] == 2
    assert data["indicators"]["latest_close"] == 12.4
    assert data["warnings"] == []


@pytest.mark.asyncio
async def test_market_instrument_lookup_returns_futures_snapshot_and_history(
    client,
    auth_headers,
    dummy_akshare,
):
    response = await client.get(
        "/api/v1/data/market-instruments/lookup",
        headers=auth_headers,
        params={
            "asset_type": "futures",
            "symbol": "RB2510",
            "start_date": "2026-06-01",
            "end_date": "2026-06-19",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["asset_type"] == "futures"
    assert data["snapshot"]["price"] == 2950
    assert data["snapshot"]["open_interest"] == 7620
    assert data["history"]["total"] == 2
    assert data["indicators"]["return_pct"] < 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("asset_type", "symbol", "expected_price"),
    [
        ("bond", "sh113527", 120.5),
        ("fund", "159915", 1.234),
        ("option", "10003889", 0.126),
        ("fx", "USDCNH", 7.18),
        ("crypto", "BTCJPY", 10000000),
    ],
)
async def test_market_instrument_lookup_returns_extended_asset_types(
    client,
    auth_headers,
    dummy_akshare,
    asset_type,
    symbol,
    expected_price,
):
    response = await client.get(
        "/api/v1/data/market-instruments/lookup",
        headers=auth_headers,
        params={
            "asset_type": asset_type,
            "symbol": symbol,
            "start_date": "2026-06-01",
            "end_date": "2026-06-19",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["asset_type"] == asset_type
    assert data["snapshot"]["price"] == expected_price
    assert data["history"]["total"] == 2
    assert data["warnings"] == []
