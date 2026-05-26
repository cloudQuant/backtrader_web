import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_factor_evaluator_calculates_ic_ir_and_long_short_return():
    from app.services.factor_lib.evaluator import FactorEvaluator

    result = FactorEvaluator().evaluate(
        factor_values=[1.0, 2.0, 3.0, 4.0, 5.0],
        future_returns=[0.01, 0.02, 0.03, 0.04, 0.05],
        quantiles=5,
    )

    assert result.status == "ok"
    assert result.observation_count == 5
    assert result.ic_mean == pytest.approx(1.0)
    assert result.ic_ir is None
    assert result.ic_t_stat is None
    assert result.long_short_return == pytest.approx(0.04)


@pytest.mark.asyncio
async def test_factor_evaluator_returns_degraded_for_insufficient_observations():
    from app.services.factor_lib.evaluator import FactorEvaluator

    result = FactorEvaluator().evaluate(factor_values=[1.0], future_returns=[0.01])

    assert result.status == "degraded"
    assert result.reason == "insufficient_observations"
    assert result.observation_count == 1


@pytest.mark.asyncio
async def test_factor_evaluator_ignores_missing_values():
    from app.services.factor_lib.evaluator import FactorEvaluator

    result = FactorEvaluator().evaluate(
        factor_values=[1.0, None, 3.0, 4.0],
        future_returns=[0.01, 0.02, None, 0.04],
    )

    assert result.status == "ok"
    assert result.observation_count == 2
    assert result.ic_mean == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_factor_evaluate_api_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/factor-lib/evaluate",
        json={"factor_values": [1, 2, 3], "future_returns": [0.01, 0.02, 0.03]},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_factor_evaluate_api_returns_result(client: AsyncClient):
    _, headers = await register_and_login(client, username="factor_eval_user")

    response = await client.post(
        "/api/v1/factor-lib/evaluate",
        headers=headers,
        json={"factor_values": [1, 2, 3, 4, 5], "future_returns": [0.01, 0.02, 0.03, 0.04, 0.05]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["observation_count"] == 5
    assert payload["ic_mean"] == pytest.approx(1.0)
    assert payload["long_short_return"] == pytest.approx(0.04)
