"""Strategy explanation orchestration service."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.db.sql_repository import SQLRepository
from app.models.backtest import BacktestTask
from app.models.strategy import Strategy
from app.models.strategy_explanation import StrategyExplanationModel
from app.schemas.strategy_explanation import (
    StrategyExplainRequest,
    StrategyExplanation,
    StrategyStructure,
)
from app.services.ai_chat_service import AIChatService
from app.services.strategy_explainer.ast_extractor import extract_strategy_structure
from app.services.strategy_explainer.llm_explainer import StrategyLLMExplainer

DEFAULT_EXPLANATION_DISCLAIMER = "解释仅供研究参考，不构成投资建议。"


class StrategyExplainerService:
    """Create and cache strategy explanations."""

    def __init__(
        self,
        ai_chat_service: AIChatService | None = None,
        llm_explainer: StrategyLLMExplainer | None = None,
    ) -> None:
        self.ai_chat_service = ai_chat_service or AIChatService()
        self.llm_explainer = llm_explainer or StrategyLLMExplainer(self.ai_chat_service)
        self.explanation_repo = SQLRepository(StrategyExplanationModel)
        self.strategy_repo = SQLRepository(Strategy)
        self.backtest_repo = SQLRepository(BacktestTask)

    async def explain(
        self,
        request: StrategyExplainRequest,
        *,
        user_id: str | None = None,
    ) -> StrategyExplanation:
        source = await self._resolve_source(request, user_id=user_id)
        code_hash = self._hash_code(source["code"])
        cached = await self.get_cached_explanation(code_hash)
        if cached is not None:
            cached.cached = True
            cached.reason_code = "cache_hit"
            return cached

        structure = extract_strategy_structure(source["code"])
        response = await self._build_ai_explanation(
            code_hash=code_hash,
            source_code=source["code"],
            structure=structure,
            strategy_name=source["strategy_name"],
            category=source.get("category"),
        )
        if response is None:
            response = self._build_static_explanation(
                code_hash=code_hash,
                structure=structure,
                strategy_name=source["strategy_name"],
                category=source.get("category"),
            )
        await self._persist_explanation(response)
        return response

    async def _build_ai_explanation(
        self,
        *,
        code_hash: str,
        source_code: str,
        structure: StrategyStructure,
        strategy_name: str,
        category: str | None,
    ) -> StrategyExplanation | None:
        payload = await self.llm_explainer.generate(
            structure=structure,
            source_code=source_code,
            strategy_name=strategy_name,
            category=category,
        )
        if not payload:
            return None
        return StrategyExplanation(
            code_hash=code_hash,
            strategy_name=strategy_name,
            summary=str(payload["summary"]),
            indicators_explanation=str(payload["indicators_explanation"]),
            entry_explanation=str(payload["entry_explanation"]),
            exit_explanation=str(payload["exit_explanation"]),
            params_explanation=str(payload["params_explanation"]),
            market_fit=str(payload["market_fit"]),
            risk_notes=[str(item) for item in payload.get("risk_notes", [])],
            ast=structure,
            reason_code="ai_generated",
            model_id=str(payload["model_id"]) if payload.get("model_id") else None,
            cached=False,
            disclaimer=DEFAULT_EXPLANATION_DISCLAIMER,
        )

    async def get_cached_explanation(self, code_hash: str) -> StrategyExplanation | None:
        model = await self.explanation_repo.get_by_field("code_hash", code_hash)
        if model is None:
            return None
        return self._to_response(model, cached=True, reason_code="cache_hit")

    async def _resolve_source(
        self,
        request: StrategyExplainRequest,
        *,
        user_id: str | None,
    ) -> dict[str, Any]:
        if request.code:
            return {
                "code": request.code,
                "strategy_name": request.strategy_name or "未命名策略",
                "category": request.category,
                "params": request.params or {},
            }
        if request.strategy_id:
            strategy = await self.strategy_repo.get_by_id(request.strategy_id)
            if strategy is None or (user_id and str(strategy.user_id) != str(user_id)):
                raise ValueError("Strategy not found")
            return {
                "code": str(strategy.code),
                "strategy_name": str(strategy.name),
                "category": str(strategy.category or request.category or "custom"),
                "params": dict(strategy.params or {}),
            }
        if request.backtest_id:
            task = await self.backtest_repo.get_by_id(request.backtest_id)
            if task is None or (user_id and str(task.user_id) != str(user_id)):
                raise ValueError("Backtest task not found")
            strategy_id = str(task.strategy_id or "")
            strategy = await self.strategy_repo.get_by_id(strategy_id) if strategy_id else None
            if strategy is None:
                raise ValueError("Strategy not found")
            return {
                "code": str(strategy.code),
                "strategy_name": str(strategy.name),
                "category": str(strategy.category or request.category or "custom"),
                "params": dict(strategy.params or {}),
            }
        raise ValueError("one of code, strategy_id, or backtest_id is required")

    @staticmethod
    def _hash_code(code: str) -> str:
        normalized = code.strip().encode("utf-8")
        return hashlib.sha256(normalized).hexdigest()

    def _build_static_explanation(
        self,
        *,
        code_hash: str,
        structure: StrategyStructure,
        strategy_name: str,
        category: str | None,
    ) -> StrategyExplanation:
        indicators = ", ".join(item.name for item in structure.indicators) or "未识别到明确技术指标"
        entry_text = self._signals_text(structure.entry_signals, "买入")
        exit_text = self._signals_text(structure.exit_signals, "卖出/退出")
        params_text = self._params_text(structure)
        risk_notes = self._risk_notes(structure)
        market_fit = self._market_fit(indicators, category)
        return StrategyExplanation(
            code_hash=code_hash,
            strategy_name=strategy_name,
            summary=f"{strategy_name} 主要通过 {indicators} 和条件分支生成交易信号。",
            indicators_explanation=f"策略使用的核心指标包括：{indicators}。这些指标用于刻画趋势、动量或价格状态。",
            entry_explanation=entry_text,
            exit_explanation=exit_text,
            params_explanation=params_text,
            market_fit=market_fit,
            risk_notes=risk_notes,
            ast=structure,
            reason_code="static_fallback",
            model_id=None,
            cached=False,
            disclaimer=DEFAULT_EXPLANATION_DISCLAIMER,
        )

    @staticmethod
    def _signals_text(signals, action_label: str) -> str:
        if not signals:
            return f"未从源码中识别到明确{action_label}条件，需要人工复核 next() 逻辑。"
        conditions = "；".join(f"{action_label}条件：{signal.condition}" for signal in signals[:4])
        return conditions

    @staticmethod
    def _params_text(structure: StrategyStructure) -> str:
        if not structure.params:
            return "未识别到显式 params 配置，参数可能写在代码常量或外部配置中。"
        parts = [f"{item.name}={item.default}" for item in structure.params[:8]]
        return "关键参数包括：" + "，".join(parts) + "。"

    @staticmethod
    def _risk_notes(structure: StrategyStructure) -> list[str]:
        notes = ["解释来自静态代码分析，无法替代样本外验证和真实成交成本评估。"]
        if structure.risk_controls:
            notes.append("源码中识别到仓位或订单 size 控制，但仍需确认资金占用和滑点假设。")
        else:
            notes.append("未识别到明确仓位控制，需重点检查单笔风险敞口。")
        if not structure.exit_signals:
            notes.append("未识别到明确退出逻辑，需检查止损、止盈或平仓规则。")
        return notes

    @staticmethod
    def _market_fit(indicators: str, category: str | None) -> str:
        text = f"{indicators} {category or ''}".lower()
        if any(token in text for token in ["sma", "ema", "crossover", "macd", "trend"]):
            return "更适合趋势较清晰、噪声较低的市场环境；震荡市中可能出现频繁假信号。"
        if any(token in text for token in ["rsi", "mean", "reversion"]):
            return "更适合区间震荡或均值回归特征较强的市场环境；单边趋势中需控制逆势风险。"
        return "适用市场环境需要结合回测分段、样本外验证和交易成本进一步判断。"

    async def _persist_explanation(self, response: StrategyExplanation) -> None:
        payload = {
            "strategy_name": response.strategy_name,
            "summary": response.summary,
            "indicators_explanation": response.indicators_explanation,
            "entry_explanation": response.entry_explanation,
            "exit_explanation": response.exit_explanation,
            "params_explanation": response.params_explanation,
            "market_fit": response.market_fit,
            "risk_notes": response.risk_notes,
            "ast_payload": response.ast.model_dump(mode="json"),
            "reason_code": response.reason_code,
            "model_id": response.model_id,
            "disclaimer": response.disclaimer,
        }
        existing = await self.explanation_repo.get_by_field("code_hash", response.code_hash)
        if existing is not None:
            await self.explanation_repo.update(existing.id, payload)
            return
        await self.explanation_repo.create(
            StrategyExplanationModel(
                code_hash=response.code_hash,
                **payload,
            )
        )

    def _to_response(
        self,
        model: StrategyExplanationModel,
        *,
        cached: bool,
        reason_code: str | None = None,
    ) -> StrategyExplanation:
        ast_payload = dict(model.ast_payload or {})
        return StrategyExplanation(
            code_hash=str(model.code_hash),
            strategy_name=str(model.strategy_name),
            summary=str(model.summary),
            indicators_explanation=str(model.indicators_explanation),
            entry_explanation=str(model.entry_explanation),
            exit_explanation=str(model.exit_explanation),
            params_explanation=str(model.params_explanation),
            market_fit=str(model.market_fit),
            risk_notes=list(model.risk_notes or []),
            ast=StrategyStructure.model_validate(ast_payload),
            reason_code=reason_code or str(model.reason_code or "static_fallback"),
            model_id=str(model.model_id) if model.model_id else None,
            cached=cached,
            disclaimer=str(model.disclaimer or DEFAULT_EXPLANATION_DISCLAIMER),
        )


def build_strategy_explainer_prompt(
    *,
    structure: StrategyStructure,
    strategy_name: str,
    category: str | None = None,
) -> str:
    """Build a deterministic prompt for future AI-backed explanation."""
    return "\n".join(
        [
            "请基于以下结构化分析，用 6 段话向非编程用户解释这个量化策略。",
            f"策略名称：{strategy_name}",
            f"策略分类：{category or 'unknown'}",
            "结构化 AST：",
            json.dumps(structure.model_dump(mode="json"), ensure_ascii=False),
        ]
    )
