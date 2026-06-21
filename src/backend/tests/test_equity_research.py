import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_equity_research_api_leaves_empty_when_no_real_data(client: AsyncClient):
    _, headers = await register_and_login(client, username="equity_user")

    search = await client.get("/api/v1/equity-research/search", headers=headers, params={"q": "RB"})
    quote = await client.get("/api/v1/equity-research/quote/RB2510", headers=headers)
    info = await client.get("/api/v1/equity-research/info/RB2510", headers=headers)
    history = await client.get("/api/v1/equity-research/history/RB2510", headers=headers)
    financials = await client.get("/api/v1/equity-research/financials/RB2510", headers=headers)
    technicals = await client.get("/api/v1/equity-research/technicals/RB2510", headers=headers)
    peers = await client.get("/api/v1/equity-research/peers/RB2510", headers=headers)

    assert search.status_code == 200
    assert search.json() == {"items": [], "total": 0}
    assert quote.status_code == 200
    assert quote.json()["symbol"] == "RB2510"
    assert quote.json()["price"] is None
    assert quote.json()["provider"] is None
    assert info.status_code == 200
    assert info.json()["industry"] is None
    assert history.status_code == 200
    assert history.json()["rows"] == []
    assert financials.status_code == 200
    assert financials.json()["annual"] == []
    assert financials.json()["quarterly"] == []
    assert technicals.status_code == 200
    assert technicals.json()["factors"] == {}
    assert peers.status_code == 200
    assert peers.json()["items"] == []
