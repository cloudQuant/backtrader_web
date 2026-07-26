import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_iter170_keeps_legacy_data_portfolio_and_quote_routes(
    client: AsyncClient, monkeypatch
):
    _, headers = await register_and_login(client, username="compat_user")

    class DummyAk:
        @staticmethod
        def stock_zh_a_hist(**kwargs):
            import pandas as pd

            return pd.DataFrame(
                [
                    {
                        "日期": "2026-05-26",
                        "开盘": 1,
                        "最高": 2,
                        "最低": 1,
                        "收盘": 2,
                        "成交量": 100,
                        "涨跌幅": 1.0,
                    }
                ]
            )

    import sys

    monkeypatch.setitem(sys.modules, "akshare", DummyAk)

    data = await client.get(
        "/api/v1/data/kline",
        headers=headers,
        params={"symbol": "000001.SZ", "start_date": "2026-05-26", "end_date": "2026-05-26"},
    )
    portfolio = await client.get("/api/v1/portfolio/overview", headers=headers)
    quote = await client.get("/api/v1/quote/sources", headers=headers)

    assert data.status_code == 200
    assert {"symbol", "count", "kline", "records"}.issubset(data.json().keys())
    assert portfolio.status_code == 200
    assert {"total_assets", "strategy_count"}.issubset(portfolio.json().keys())
    assert quote.status_code == 200
    assert "sources" in quote.json()
