from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestStrategyExplainerApi:
    async def test_explain_strategy_requires_auth(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/strategy/explain",
            json={"code": "class Demo: pass"},
        )

        assert response.status_code == 401

    async def test_explain_strategy_from_code(self, client: AsyncClient, auth_headers: dict):
        with patch(
            "app.api.strategy_explainer.StrategyExplainerService.explain",
            new_callable=AsyncMock,
        ) as mock_explain:
            mock_explain.return_value = {
                "code_hash": "abc123",
                "strategy_name": "双均线策略",
                "summary": "双均线策略通过快慢均线交叉识别趋势。",
                "indicators_explanation": "使用 SMA 和 CrossOver。",
                "entry_explanation": "快线上穿慢线时买入。",
                "exit_explanation": "快线下穿慢线时卖出。",
                "params_explanation": "fast_period 控制快线周期。",
                "market_fit": "适合趋势市场。",
                "risk_notes": ["震荡市场可能频繁假突破"],
                "ast": {
                    "parsable": True,
                    "indicators": [],
                    "entry_signals": [],
                    "exit_signals": [],
                    "risk_controls": [],
                    "params": [],
                    "data_sources": [],
                    "raw_code": None,
                    "parse_error": None,
                },
                "reason_code": "static_fallback",
                "model_id": None,
                "cached": False,
                "disclaimer": "解释仅供研究参考，不构成投资建议。",
            }

            response = await client.post(
                "/api/v1/strategy/explain",
                headers=auth_headers,
                json={"code": "class Demo: pass", "strategy_name": "双均线策略"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["code_hash"] == "abc123"
        assert payload["reason_code"] == "static_fallback"
        assert "双均线" in payload["summary"]

    async def test_get_cached_explanation(self, client: AsyncClient, auth_headers: dict):
        with patch(
            "app.api.strategy_explainer.StrategyExplainerService.get_cached_explanation",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = {
                "code_hash": "abc123",
                "strategy_name": "双均线策略",
                "summary": "缓存解释。",
                "indicators_explanation": "使用 SMA。",
                "entry_explanation": "买入说明。",
                "exit_explanation": "卖出说明。",
                "params_explanation": "参数说明。",
                "market_fit": "市场适配。",
                "risk_notes": [],
                "ast": {
                    "parsable": True,
                    "indicators": [],
                    "entry_signals": [],
                    "exit_signals": [],
                    "risk_controls": [],
                    "params": [],
                    "data_sources": [],
                    "raw_code": None,
                    "parse_error": None,
                },
                "reason_code": "cache_hit",
                "model_id": None,
                "cached": True,
                "disclaimer": "解释仅供研究参考，不构成投资建议。",
            }

            response = await client.get(
                "/api/v1/strategy/explain/cached/abc123",
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json()["cached"] is True
