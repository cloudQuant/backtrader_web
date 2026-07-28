"""AI-backed stock analysis stage generation."""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.ai_call_log import AICallLog
from app.schemas.ai_observability import AICallStatus
from app.services.ai_observability.budget import AIBudgetService
from app.services.ai_observability.cost_calculator import calculate_estimated_cost_usd
from app.services.ai_observability.logger import hash_prompt
from app.services.ai_router.preferences import AIModelPreferenceService, ResolvedAIModelPreference
from app.services.ai_router.router import AIChatRouter, ChatCompletionResponse, get_ai_chat_router
from app.services.stock_analysis.signal import StockSignalExtractor

_BudgetChecker = Callable[..., Awaitable[None]]


@dataclass(frozen=True)
class StockAnalysisStageSpec:
    """Prompt metadata for one clean-room compatible analysis stage."""

    stage_id: str
    output_key: str
    title: str
    role_instruction: str
    dependencies: tuple[str, ...] = ()


_STAGES: tuple[StockAnalysisStageSpec, ...] = (
    StockAnalysisStageSpec(
        "market",
        "market_report",
        "市场/技术分析师",
        "从行情、历史价格和技术因子出发，生成市场与技术分析报告。",
    ),
    StockAnalysisStageSpec(
        "sentiment",
        "sentiment_report",
        "社媒情绪分析师",
        "从情绪样本和信息不足风险出发，生成社媒情绪分析报告；样本不足时明确 degraded。",
    ),
    StockAnalysisStageSpec(
        "news",
        "news_report",
        "新闻分析师",
        "从新闻条目、事件冲击和持续性出发，生成新闻分析报告。",
    ),
    StockAnalysisStageSpec(
        "fundamentals",
        "fundamentals_report",
        "基本面分析师",
        "从公司信息、财务、行业和可比标的出发，生成基本面分析报告。",
    ),
    StockAnalysisStageSpec(
        "bull_researcher",
        "bull_researcher",
        "多头研究员",
        "基于分析师报告提炼买入或增持论据，但不得承诺收益。",
        ("market_report", "sentiment_report", "news_report", "fundamentals_report"),
    ),
    StockAnalysisStageSpec(
        "bear_researcher",
        "bear_researcher",
        "空头研究员",
        "基于分析师报告提炼卖出、减持或观望论据，强调数据和执行风险。",
        ("market_report", "sentiment_report", "news_report", "fundamentals_report"),
    ),
    StockAnalysisStageSpec(
        "research_manager",
        "research_team_decision",
        "研究经理",
        "综合多空观点，给出研究团队结论和投资计划。",
        ("bull_researcher", "bear_researcher"),
    ),
    StockAnalysisStageSpec(
        "trader",
        "trader_investment_plan",
        "交易员",
        "把研究团队结论转成可执行交易计划，包含方向、触发条件和风控。",
        ("investment_plan", "market_report", "fundamentals_report", "news_report"),
    ),
    StockAnalysisStageSpec(
        "risky_analyst",
        "risky_analyst",
        "激进风险分析师",
        "从机会优先角度评估交易员计划，但必须注明可能承受的波动。",
        ("trader_investment_plan",),
    ),
    StockAnalysisStageSpec(
        "safe_analyst",
        "safe_analyst",
        "保守风险分析师",
        "从资本保护角度评估交易员计划，强调仓位、止损和不可交易条件。",
        ("trader_investment_plan",),
    ),
    StockAnalysisStageSpec(
        "neutral_analyst",
        "neutral_analyst",
        "中性风险分析师",
        "从风险收益平衡角度评估交易员计划，给出继续观察或执行的条件。",
        ("trader_investment_plan",),
    ),
    StockAnalysisStageSpec(
        "risk_manager",
        "risk_management_decision",
        "风险经理",
        "综合三类风险观点，形成风险管理结论。",
        ("risky_analyst", "safe_analyst", "neutral_analyst", "trader_investment_plan"),
    ),
    StockAnalysisStageSpec(
        "final_trade_decision",
        "final_trade_decision",
        "最终交易决策",
        "输出最终交易决策，必须包含最终交易建议、目标价位、置信度和风险评分。",
        ("risk_management_decision", "trader_investment_plan"),
    ),
)


class StockAnalysisEngine:
    """Generate compatible stage text with the current AI provider."""

    TEMPLATE_VERSION = "v1"

    def __init__(
        self,
        db: AsyncSession,
        *,
        ai_router: AIChatRouter | None = None,
        model_preference_service: AIModelPreferenceService | None = None,
        budget_checker: _BudgetChecker | None = None,
        settings: Any | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.ai_router = ai_router or get_ai_chat_router()
        self.model_preference_service = model_preference_service or AIModelPreferenceService()
        self.budget_checker = budget_checker or AIBudgetService().ensure_budget_available
        self.signal_extractor = StockSignalExtractor()

    async def can_generate(self, *, user_id: str | None, model_id: str | None = None) -> bool:
        if not bool(getattr(self.settings, "AI_CHAT_ENABLED", False)):
            return False
        preference = self.model_preference_service.resolve_model_key(model_id)
        if preference is None:
            preference = await self.model_preference_service.resolve_for_user(user_id)
        if preference is not None:
            return preference.configured
        return bool(
            str(getattr(self.settings, "AI_CHAT_BASE_URL", "") or "").strip()
            and str(getattr(self.settings, "AI_CHAT_API_KEY", "") or "").strip()
            and str(getattr(self.settings, "AI_CHAT_MODEL", "") or "").strip()
        )

    async def enhance(
        self,
        *,
        task_id: str,
        user_id: str,
        model_id: str | None,
        symbol: str,
        market_type: str,
        research_depth: str,
        selected_modules: list[str],
        snapshot: dict[str, Any],
        pipeline_output: dict[str, Any],
    ) -> dict[str, Any]:
        output = dict(pipeline_output)
        preference = self.model_preference_service.resolve_model_key(model_id)
        if preference is None:
            preference = await self.model_preference_service.resolve_for_user(user_id)
        stage_results: list[dict[str, Any]] = []
        source_context = self._source_context(snapshot)

        for stage in _STAGES:
            prompt = self._build_prompt(
                stage=stage,
                symbol=symbol,
                market_type=market_type,
                research_depth=research_depth,
                selected_modules=selected_modules,
                source_context=source_context,
                output=output,
            )
            result = await self._call_stage(
                task_id=task_id,
                user_id=user_id,
                stage=stage,
                prompt=prompt,
                preference=preference,
            )
            stage_results.append(result)
            if result.get("status") == "success" and result.get("content"):
                output[stage.output_key] = str(result["content"]).strip()
                if stage.output_key == "research_team_decision":
                    output["investment_plan"] = output[stage.output_key]
            if result.get("error_code") == "TimeoutError":
                # A provider that does not answer must not multiply one stuck
                # request across every remaining analysis stage.  Keep the
                # rule-based pipeline output and finish the report as degraded.
                break

        output["decision"] = self.signal_extractor.extract(
            str(output.get("final_trade_decision") or ""),
            symbol=symbol,
        )
        output["ai_stage_generation"] = {
            "enabled": True,
            "degraded": any(result.get("status") == "failed" for result in stage_results),
            "template_version": self.TEMPLATE_VERSION,
            "stages": stage_results,
        }
        return output

    async def _call_stage(
        self,
        *,
        task_id: str,
        user_id: str,
        stage: StockAnalysisStageSpec,
        prompt: str,
        preference: ResolvedAIModelPreference | None,
    ) -> dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 AI for Investor 的原生股票分析引擎。"
                    "你按兼容阶段职责生成中文研究文本，"
                    "但不得复制或引用外部分析项目源码。"
                    "所有结论仅供研究参考，不构成投资建议。"
                ),
            },
            {"role": "user", "content": prompt},
        ]
        started = time.perf_counter()
        try:
            await self.budget_checker(user_id=user_id)
            response = await self.ai_router.chat_completion(
                messages=messages,
                model=preference.model if preference else str(self.settings.AI_CHAT_MODEL),
                provider=preference.provider if preference else "openai_compatible",
                base_url=preference.base_url if preference else str(self.settings.AI_CHAT_BASE_URL),
                api_key=preference.api_key if preference else str(self.settings.AI_CHAT_API_KEY),
                timeout=float(getattr(self.settings, "AI_CHAT_TIMEOUT", 60.0) or 60.0),
                temperature=min(
                    float(getattr(self.settings, "AI_CHAT_TEMPERATURE", 0.2) or 0.2), 0.2
                ),
            )
            if not response.content:
                raise ValueError("AI provider returned empty stock analysis stage")
            await self._record_call(
                task_id=task_id,
                user_id=user_id,
                stage=stage,
                prompt=prompt,
                status=AICallStatus.SUCCESS,
                response=response,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            return {
                "stage": stage.stage_id,
                "status": "success",
                "model": response.model,
                "provider": response.provider,
                "content": response.content,
            }
        except Exception as exc:
            await self._record_call(
                task_id=task_id,
                user_id=user_id,
                stage=stage,
                prompt=prompt,
                status=AICallStatus.FAILED,
                response=None,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=exc,
                preference=preference,
            )
            return {
                "stage": stage.stage_id,
                "status": "failed",
                "error_code": type(exc).__name__,
                "message": str(exc)[:300],
            }

    async def _record_call(
        self,
        *,
        task_id: str,
        user_id: str,
        stage: StockAnalysisStageSpec,
        prompt: str,
        status: AICallStatus,
        response: ChatCompletionResponse | None,
        latency_ms: int,
        error: BaseException | None = None,
        preference: ResolvedAIModelPreference | None = None,
    ) -> None:
        model_name = (
            response.model
            if response is not None
            else preference.model
            if preference is not None
            else str(getattr(self.settings, "AI_CHAT_MODEL", "unknown") or "unknown")
        )
        provider = (
            response.provider
            if response is not None
            else preference.provider
            if preference is not None
            else "openai_compatible"
        )
        prompt_tokens = response.prompt_tokens if response is not None else 0
        completion_tokens = response.completion_tokens if response is not None else 0
        total_tokens = response.total_tokens if response is not None else 0
        self.db.add(
            AICallLog(
                user_id=user_id,
                request_id=task_id,
                service_name="stock_analysis",
                mode=f"ai_stage:{stage.stage_id}",
                model_name=model_name,
                provider=provider,
                prompt_template_id=f"stock_analysis.{stage.stage_id}",
                prompt_template_version=self.TEMPLATE_VERSION,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=calculate_estimated_cost_usd(
                    model_name,
                    prompt_tokens,
                    completion_tokens,
                ),
                latency_ms=latency_ms,
                status=status.value,
                error_code=type(error).__name__ if error else None,
                error_message=str(error)[:1000] if error else None,
                response_chars=len(response.content) if response is not None else 0,
                prompt_hash=hash_prompt(prompt),
            )
        )

    def _build_prompt(
        self,
        *,
        stage: StockAnalysisStageSpec,
        symbol: str,
        market_type: str,
        research_depth: str,
        selected_modules: list[str],
        source_context: str,
        output: dict[str, Any],
    ) -> str:
        dependencies = "\n\n".join(
            f"【{key}】\n{str(output.get(key) or '').strip()}"
            for key in stage.dependencies
            if output.get(key)
        )
        current_draft = str(output.get(stage.output_key) or "").strip()
        final_constraints = ""
        if stage.stage_id == "final_trade_decision":
            final_constraints = (
                "\n最终交易决策必须显式包含以下字段："
                "\n- 最终交易建议: **买入/持有/卖出**"
                "\n- 目标价位: 数字"
                "\n- 置信度: 0-1"
                "\n- 风险评分: 0-1"
            )
        return "\n".join(
            [
                f"阶段：{stage.title}",
                f"股票：{symbol}",
                f"市场：{market_type}",
                f"研究深度：{research_depth}",
                f"用户选择模块：{', '.join(selected_modules) or '未指定'}",
                "",
                "阶段职责：",
                stage.role_instruction,
                "",
                "数据快照摘要：",
                source_context,
                "",
                "前序阶段输出：",
                dependencies or "无",
                "",
                "规则流水线草稿：",
                current_draft or "无",
                "",
                "输出要求：",
                "- 使用中文，长度控制在 250-500 字。",
                "- 只基于给定数据和前序阶段输出，不编造缺失数据。",
                "- 数据不足时明确说明 degraded 和原因。",
                "- 不承诺收益，不构成投资建议。",
                final_constraints,
            ]
        ).strip()

    def _source_context(self, snapshot: dict[str, Any]) -> str:
        financials = snapshot.get("financials") or {}
        annual = financials.get("annual") or []
        news_items = (snapshot.get("news") or {}).get("items") or []
        compact = {
            "quote": snapshot.get("quote") or {},
            "info": snapshot.get("info") or {},
            "technicals": snapshot.get("technicals") or {},
            "latest_financial": annual[-1] if annual else {},
            "news_items": news_items[:5],
            "data_quality": snapshot.get("data_quality") or {},
        }
        return json.dumps(compact, ensure_ascii=False, default=str)[:6000]
