from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestStrategyScoreApi:
    async def test_create_strategy_score_requires_auth(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/strategy/score",
            json={"backtest_id": "bt-001"},
        )

        assert response.status_code == 401

    async def test_create_strategy_score_for_backtest_id(self, client: AsyncClient, auth_headers: dict):
        with patch(
            "app.api.strategy_score.StrategyScoreService.score_backtest",
            new_callable=AsyncMock,
        ) as mock_score:
            mock_score.return_value = {
                "backtest_id": "bt-001",
                "total_score": 78.0,
                "level": "A",
                "model_version": "v1",
                "disclaimer": "评分仅供研究参考，不构成投资建议。",
                "dimensions": [
                    {
                        "key": "profitability",
                        "label": "收益质量",
                        "score": 80.0,
                        "weight": 0.2,
                        "explanation": "收益与夏普表现较好。",
                        "sub_metrics": {"annual_return": 18.4},
                        "degraded": False,
                    },
                    {
                        "key": "risk_control",
                        "label": "风险控制",
                        "score": 72.0,
                        "weight": 0.2,
                        "explanation": "回撤可控。",
                        "sub_metrics": {"max_drawdown": -12.8},
                        "degraded": False,
                    },
                    {
                        "key": "stability",
                        "label": "稳定性",
                        "score": 76.0,
                        "weight": 0.2,
                        "explanation": "稳定性中上。",
                        "sub_metrics": {"trade_count": 42},
                        "degraded": False,
                    },
                    {
                        "key": "overfitting_risk",
                        "label": "过拟合风险",
                        "score": 50.0,
                        "weight": 0.15,
                        "explanation": "尚未完成过拟合检测，暂按中位分处理。",
                        "sub_metrics": {},
                        "degraded": True,
                    },
                    {
                        "key": "executability",
                        "label": "可执行性",
                        "score": 74.0,
                        "weight": 0.15,
                        "explanation": "交易频率和样本量基本可执行。",
                        "sub_metrics": {"total_trades": 42},
                        "degraded": False,
                    },
                    {
                        "key": "benchmark_comparison",
                        "label": "基准对比",
                        "score": 70.0,
                        "weight": 0.1,
                        "explanation": "当前版本尚未接入真实 benchmark，先按中性偏上处理。",
                        "sub_metrics": {},
                        "degraded": True,
                    },
                ],
            }

            response = await client.post(
                "/api/v1/strategy/score",
                headers=auth_headers,
                json={"backtest_id": "bt-001"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["backtest_id"] == "bt-001"
        assert payload["level"] == "A"
        assert len(payload["dimensions"]) == 6

    async def test_get_strategy_score_history(self, client: AsyncClient, auth_headers: dict):
        with patch(
            "app.api.strategy_score.StrategyScoreService.get_score_by_backtest_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = {
                "backtest_id": "bt-001",
                "total_score": 78.0,
                "level": "A",
                "model_version": "v1",
                "disclaimer": "评分仅供研究参考，不构成投资建议。",
                "dimensions": [],
            }

            response = await client.get(
                "/api/v1/strategy/score/bt-001",
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json()["backtest_id"] == "bt-001"
