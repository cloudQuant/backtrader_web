import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_equity_research_api_returns_quote_history_and_technicals(client: AsyncClient):
    _, headers = await register_and_login(client, username="equity_user")

    search = await client.get("/api/v1/equity-research/search", headers=headers, params={"q": "RB"})
    quote = await client.get("/api/v1/equity-research/quote/RB2510", headers=headers)
    info = await client.get("/api/v1/equity-research/info/RB2510", headers=headers)
    history = await client.get("/api/v1/equity-research/history/RB2510", headers=headers)
    financials = await client.get("/api/v1/equity-research/financials/RB2510", headers=headers)
    technicals = await client.get("/api/v1/equity-research/technicals/RB2510", headers=headers)
    peers = await client.get("/api/v1/equity-research/peers/RB2510", headers=headers)

    assert search.status_code == 200
    assert search.json()["items"]
    assert quote.status_code == 200
    assert quote.json()["symbol"] == "RB2510"
    assert quote.json()["provider"] == "data_governance"
    assert info.status_code == 200
    assert info.json()["industry"]
    assert history.status_code == 200
    assert len(history.json()["rows"]) >= 5
    assert financials.status_code == 200
    assert financials.json()["annual"]
    assert technicals.status_code == 200
    assert "momentum_5" in technicals.json()["factors"]
    assert peers.status_code == 200
    assert peers.json()["items"]
