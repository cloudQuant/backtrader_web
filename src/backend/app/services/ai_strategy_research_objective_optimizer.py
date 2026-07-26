"""LLM-assisted refinement for deterministic AI strategy research objectives."""

from __future__ import annotations

import json
from typing import Any

from app.config import get_settings
from app.schemas.ai_strategy_research import (
    AIStrategyResearchObjectiveOptimizeRequest,
    AIStrategyResearchObjectiveOptimizeResponse,
)
from app.services.ai_router.preferences import (
    AIModelPreferenceService,
    ResolvedAIModelPreference,
)
from app.services.ai_router.router import AIChatRouter, get_ai_chat_router

_SENSITIVE_CONFIG_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "gateway",
    "password",
    "secret",
    "token",
)


class AIStrategyResearchObjectiveOptimizer:
    """Refine an existing objective while retaining every supplied hard constraint."""

    def __init__(
        self,
        *,
        ai_router: AIChatRouter | None = None,
        preference_service: AIModelPreferenceService | None = None,
        settings: Any | None = None,
    ) -> None:
        self.ai_router = ai_router or get_ai_chat_router()
        self.preference_service = preference_service or AIModelPreferenceService()
        self.settings = settings or get_settings()

    async def optimize(
        self,
        user_id: str | None,
        request: AIStrategyResearchObjectiveOptimizeRequest,
    ) -> AIStrategyResearchObjectiveOptimizeResponse:
        """Return a clearer, executable objective using the user's configured model."""
        preference = await self._resolve_preference(user_id)
        if preference is None:
            raise ValueError("未配置可用的大模型，已保留默认投研目标。")

        try:
            response = await self.ai_router.chat_completion(
                messages=_build_objective_optimization_messages(request),
                model=preference.model,
                provider=preference.provider,
                base_url=preference.base_url,
                api_key=preference.api_key,
                timeout=float(getattr(self.settings, "AI_CHAT_TIMEOUT", 120.0) or 120.0),
                max_tokens=min(
                    int(getattr(self.settings, "AI_CHAT_MAX_TOKENS", 4000) or 4000),
                    6000,
                ),
                temperature=min(
                    float(getattr(self.settings, "AI_CHAT_TEMPERATURE", 0.2) or 0.2),
                    0.3,
                ),
            )
        except Exception as exc:
            raise ValueError("大模型优化投研目标失败，已保留默认投研目标。") from exc

        prompt = _normalize_objective(response.content)
        if not prompt:
            raise ValueError("大模型未返回可用的投研目标，已保留默认投研目标。")
        return AIStrategyResearchObjectiveOptimizeResponse(
            prompt=prompt,
            model=response.model or preference.model,
            provider=response.provider or preference.provider,
        )

    async def _resolve_preference(
        self,
        user_id: str | None,
    ) -> ResolvedAIModelPreference | None:
        preference = await self.preference_service.resolve_for_user(user_id)
        if preference is not None:
            return preference if preference.configured else None

        if not bool(getattr(self.settings, "AI_CHAT_ENABLED", False)):
            return None
        model = str(getattr(self.settings, "AI_CHAT_MODEL", "") or "").strip()
        base_url = str(getattr(self.settings, "AI_CHAT_BASE_URL", "") or "").strip()
        api_key = str(getattr(self.settings, "AI_CHAT_API_KEY", "") or "").strip()
        if not (model and base_url and api_key):
            return None
        return ResolvedAIModelPreference(
            provider="openai_compatible",
            model=model,
            base_url=base_url,
            api_key=api_key,
            configured=True,
        )


def _build_objective_optimization_messages(
    request: AIStrategyResearchObjectiveOptimizeRequest,
) -> list[dict[str, str]]:
    """Build a constrained editor prompt instead of asking the model to invent a plan."""
    config = json.dumps(
        _safe_research_config(request.research_config),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return [
        {
            "role": "system",
            "content": (
                "你是量化投研目标编辑器。只输出优化后的中文投研目标原文，不要标题、"
                "Markdown 代码块、解释、免责声明或寒暄。必须保留原目标与配置快照中的"
                "标的、周期、回测区间、质量门槛、验证、资金和模拟交易等硬约束；"
                "只能提升结构、清晰度和可执行性，不能放宽、删除或编造约束。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请优化下面的投研目标。\n\n"
                f"原始投研目标：\n{request.prompt.strip()}\n\n"
                f"必须保留的表单配置快照：\n{config}"
            ),
        },
    ]


def _normalize_objective(content: str) -> str:
    """Accept plain model output while rejecting empty or unsafe-size responses."""
    prompt = str(content or "").strip()
    if prompt.startswith("```") and prompt.endswith("```"):
        prompt = prompt.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return prompt[:12000].strip()


def _safe_research_config(value: Any) -> Any:
    """Remove credentials before a free-form client payload reaches an external model."""
    if isinstance(value, dict):
        return {
            str(key): _safe_research_config(item)
            for key, item in value.items()
            if not any(part in str(key).lower() for part in _SENSITIVE_CONFIG_KEY_PARTS)
        }
    if isinstance(value, list):
        return [_safe_research_config(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_research_config(item) for item in value]
    return value
