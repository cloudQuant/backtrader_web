import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login

MARKET_RETURNS = [0.01, 0.02, -0.01, 0.03, -0.02, 0.015]
SMB_RETURNS = [0.005, -0.004, 0.003, 0.002, -0.001, 0.006]
HML_RETURNS = [-0.002, 0.004, 0.001, -0.003, 0.005, -0.004]
STRATEGY_RETURNS = [
    0.001 + 1.2 * market + 0.5 * smb - 0.3 * hml
    for market, smb, hml in zip(MARKET_RETURNS, SMB_RETURNS, HML_RETURNS, strict=False)
]


@pytest.mark.asyncio
async def test_fama_french_service_calculates_three_factor_regression():
    from app.services.perf_attribution.fama_french import FamaFrenchAttributionService

    result = FamaFrenchAttributionService().calculate(
        strategy_returns=STRATEGY_RETURNS,
        market_returns=MARKET_RETURNS,
        smb_returns=SMB_RETURNS,
        hml_returns=HML_RETURNS,
    )

    assert result.status == "ok"
    assert result.observation_count == 6
    assert result.alpha == pytest.approx(0.001)
    assert result.market_beta == pytest.approx(1.2)
    assert result.smb_beta == pytest.approx(0.5)
    assert result.hml_beta == pytest.approx(-0.3)
    assert result.r_squared == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_fama_french_service_returns_degraded_for_insufficient_observations():
    from app.services.perf_attribution.fama_french import FamaFrenchAttributionService

    result = FamaFrenchAttributionService().calculate(
        strategy_returns=[0.01, 0.02],
        market_returns=[0.01, 0.02],
        smb_returns=[0.0, 0.0],
        hml_returns=[0.0, 0.0],
    )

    assert result.status == "degraded"
    assert result.reason == "insufficient_observations"


@pytest.mark.asyncio
async def test_fama_french_api_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/perf-attribution/fama-french",
        json={
            "strategy_returns": STRATEGY_RETURNS,
            "market_returns": MARKET_RETURNS,
            "smb_returns": SMB_RETURNS,
            "hml_returns": HML_RETURNS,
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_fama_french_api_returns_result(client: AsyncClient):
    _, headers = await register_and_login(client, username="fama_french_user")

    response = await client.post(
        "/api/v1/perf-attribution/fama-french",
        headers=headers,
        json={
            "strategy_returns": STRATEGY_RETURNS,
            "market_returns": MARKET_RETURNS,
            "smb_returns": SMB_RETURNS,
            "hml_returns": HML_RETURNS,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["market_beta"] == pytest.approx(1.2)
    assert payload["smb_beta"] == pytest.approx(0.5)
    assert payload["hml_beta"] == pytest.approx(-0.3)
    assert payload["r_squared"] == pytest.approx(1.0)
