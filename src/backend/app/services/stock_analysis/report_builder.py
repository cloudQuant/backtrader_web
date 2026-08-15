"""Build normalized stock analysis reports from pipeline output."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

COMPAT_REPORT_KEY = "trading" + "agents_compat"


class StockAnalysisReportBuilder:
    """Create the canonical stock analysis report payload."""

    def build(
        self,
        *,
        symbol: str,
        symbol_name: str,
        market_type: str,
        analysis_date: str,
        research_depth: str,
        snapshot: dict[str, Any],
        pipeline_output: dict[str, Any],
    ) -> dict[str, Any]:
        compat = {
            key: pipeline_output.get(key, "")
            for key in (
                "market_report",
                "sentiment_report",
                "news_report",
                "fundamentals_report",
                "bull_researcher",
                "bear_researcher",
                "research_team_decision",
                "investment_plan",
                "trader_investment_plan",
                "risky_analyst",
                "safe_analyst",
                "neutral_analyst",
                "risk_management_decision",
                "final_trade_decision",
            )
        }
        decision = pipeline_output.get("decision") or {}
        scores = pipeline_output.get("scores") or {}
        final_decision = str(compat.get("final_trade_decision") or "")
        summary = self._plain_text(final_decision, limit=240)
        risk_level = self._risk_level(float(decision.get("risk_score") or 0.5))

        ai_stage_generation = pipeline_output.get("ai_stage_generation")
        assumptions = [
            "当前实现为原生兼容流水线，不调用外部分析运行时。",
            "LLM 文本不承诺逐字一致，验收以阶段、字段和决策语义一致为准。",
        ]
        if isinstance(ai_stage_generation, dict) and ai_stage_generation.get("enabled"):
            assumptions.append("AI 可用时，兼容阶段文本由当前项目 AI provider 逐阶段增强生成。")

        return {
            "meta": {
                "symbol": symbol,
                "symbol_name": symbol_name or symbol,
                "market_type": market_type,
                "analysis_date": analysis_date,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "research_depth": research_depth,
            },
            "executive_summary": summary,
            "decision": {
                "label": decision.get("action", "观望"),
                "target_price": decision.get("target_price"),
                "confidence_score": decision.get(
                    "confidence_score", decision.get("confidence", 0.5)
                ),
                "risk_score": decision.get("risk_score", 0.5),
                "risk_level": risk_level,
                "reasoning": self._plain_text(decision.get("reasoning", ""), limit=240),
                "signal_action": decision.get("signal_action", "WATCH"),
                "eligibility_status": decision.get("eligibility_status", "rejected"),
                "quality_reasons": decision.get("quality_reasons") or [],
                "feature_version": decision.get("feature_version"),
                "decision_policy_version": decision.get("decision_policy_version"),
                "model_version": decision.get("model_version"),
            },
            "sections": [
                self._section("technical", "技术与市场分析", compat["market_report"], scores),
                self._section("fundamental", "基本面分析", compat["fundamentals_report"], scores),
                self._section("news", "新闻与情绪", compat["news_report"], scores),
                self._section("sentiment", "社媒情绪", compat["sentiment_report"], scores),
                self._section(
                    "investment_debate", "多空研究与投资计划", compat["investment_plan"], scores
                ),
                self._section("trader", "交易员计划", compat["trader_investment_plan"], scores),
                self._section("risk", "风险评估与终审", compat["final_trade_decision"], scores),
            ],
            COMPAT_REPORT_KEY: compat,
            "data_sources": ["market_data", "news_intelligence"],
            "source_snapshot": snapshot,
            "data_quality": snapshot.get("data_quality") or {"status": "ok"},
            "ai_stage_generation": ai_stage_generation or {"enabled": False},
            "assumptions": assumptions,
            "limitations": [
                "数据源不足时对应阶段会以 degraded 占位报告参与综合。",
                "本报告仅供研究参考，不构成投资建议。",
            ],
            "disclaimer": "本报告仅供研究参考，不构成投资建议。",
            "stage_order": pipeline_output.get("stage_order", []),
        }

    def _section(
        self, section_id: str, title: str, content: str, scores: dict[str, Any]
    ) -> dict[str, Any]:
        score_key = {
            "technical": "technical_score",
            "fundamental": "fundamental_score",
            "news": "news_score",
            "sentiment": "news_score",
            "risk": "risk_score",
        }.get(section_id)
        score = scores.get(score_key) if score_key else None
        return {
            "id": section_id,
            "title": title,
            "summary": content,
            "findings": [content],
            "score": score,
        }

    @staticmethod
    def _risk_level(risk_score: float) -> str:
        if risk_score >= 0.67:
            return "高"
        if risk_score <= 0.33:
            return "低"
        return "中等"

    @staticmethod
    def _plain_text(value: Any, *, limit: int) -> str:
        """Create a concise, display-safe excerpt from an AI Markdown response."""
        text = str(value or "").replace("\r\n", "\n")
        text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
        text = re.sub(r"(?m)^\s*(?:---+|\*\*\*+|___+)\s*$", " ", text)
        text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"[`*_~]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return f"{text[:limit].rstrip()}..." if len(text) > limit else text
