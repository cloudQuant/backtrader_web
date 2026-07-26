"""LLM-backed strategy explanation generation."""

from __future__ import annotations

import json
from typing import Any

from app.schemas.strategy_explanation import StrategyStructure
from app.services.ai_chat_service import AIChatService


class StrategyLLMExplainer:
    """Generate structured strategy explanations with the configured AI chat provider."""

    def __init__(self, ai_chat_service: AIChatService | None = None) -> None:
        self.ai_chat_service = ai_chat_service or AIChatService()

    async def generate(
        self,
        *,
        structure: StrategyStructure,
        source_code: str,
        strategy_name: str,
        category: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.ai_chat_service.is_enabled():
            return None
        prompt = self._build_prompt(
            structure=structure,
            source_code=source_code,
            strategy_name=strategy_name,
            category=category,
        )
        response = await self.ai_chat_service.generate_answer(
            question=prompt,
            citations=[],
            assistant_mode="strategy_review",
            thinking_mode=False,
            knowledge_base_settings={"quant_focus": "strategy_review"},
        )
        if not response:
            return None
        answer = str(response.get("answer") or "").strip()
        parsed = self._parse_payload(answer)
        if parsed is None:
            return None
        parsed["model_id"] = response.get("model_id")
        return parsed

    @staticmethod
    def _build_prompt(
        *,
        structure: StrategyStructure,
        source_code: str,
        strategy_name: str,
        category: str | None,
    ) -> str:
        return "\n".join(
            [
                "请基于以下 Backtrader 策略源码和结构化 AST，只返回 JSON 对象，不要 Markdown。",
                "JSON 字段必须包含：summary, indicators_explanation, entry_explanation, exit_explanation, params_explanation, market_fit, risk_notes。",
                f"策略名称：{strategy_name}",
                f"策略分类：{category or 'unknown'}",
                "结构化 AST：",
                json.dumps(structure.model_dump(mode="json"), ensure_ascii=False),
                "源码：",
                source_code[:12000],
            ]
        )

    @staticmethod
    def _parse_payload(content: str) -> dict[str, Any] | None:
        json_text = AIChatService._extract_json_object(content)
        if not json_text:
            return None
        try:
            payload = json.loads(json_text)
        except json.JSONDecodeError:
            return None
        required = [
            "summary",
            "indicators_explanation",
            "entry_explanation",
            "exit_explanation",
            "params_explanation",
            "market_fit",
        ]
        if not all(isinstance(payload.get(key), str) and payload[key].strip() for key in required):
            return None
        risk_notes = payload.get("risk_notes")
        if not isinstance(risk_notes, list):
            payload["risk_notes"] = []
        else:
            payload["risk_notes"] = [str(item) for item in risk_notes]
        return payload
