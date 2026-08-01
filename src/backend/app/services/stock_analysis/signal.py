"""Compatible signal extraction for stock analysis."""

from __future__ import annotations

import re
from typing import Any


class StockSignalExtractor:
    """Extract a structured decision from a final trade decision text."""

    ACTION_MAP = {
        "buy": "买入",
        "BUY": "买入",
        "买入": "买入",
        "购买": "买入",
        "增持": "买入",
        "hold": "观望",
        "HOLD": "观望",
        "持有": "观望",
        "观望": "观望",
        "WATCH": "观望",
        "watch": "观望",
        "中性": "观望",
        "sell": "卖出",
        "SELL": "卖出",
        "卖出": "卖出",
        "减持": "卖出",
        "出售": "卖出",
    }

    def extract(self, final_trade_decision: str, *, symbol: str = "") -> dict[str, Any]:
        text = str(final_trade_decision or "").strip()
        if not text:
            return self._default_decision("最终交易决策为空，默认观望。")

        action = self._extract_action(text)
        target_price = self._extract_target_price(text)
        confidence = self._extract_ratio(text, ("置信度", "信心", "confidence"), default=0.7)
        risk_score = self._extract_ratio(text, ("风险评分", "风险", "risk_score"), default=0.5)
        reasoning = self._extract_reasoning(text)

        return {
            "action": action,
            "target_price": target_price,
            "confidence": max(0.0, min(1.0, confidence)),
            "risk_score": max(0.0, min(1.0, risk_score)),
            "reasoning": reasoning or f"基于{symbol or '该标的'}综合分析的投资建议。",
        }

    def _extract_action(self, text: str) -> str:
        preferred_patterns = [
            r"最终交易建议[：:\s*]*(买入|卖出|持有|观望|增持|减持|BUY|SELL|HOLD|WATCH)",
            r"投资建议[：:\s*]*(买入|卖出|持有|观望|增持|减持|BUY|SELL|HOLD|WATCH)",
            r"建议[：:\s*]*(买入|持有|观望|卖出|增持|减持|BUY|HOLD|WATCH|SELL|buy|hold|watch|sell)",
        ]
        for pattern in preferred_patterns:
            match = re.search(pattern, text)
            if match:
                return self.ACTION_MAP.get(match.group(1), "观望")
        for token, normalized in self.ACTION_MAP.items():
            if token in text:
                return normalized
        return "观望"

    def _extract_target_price(self, text: str) -> float | None:
        patterns = [
            r"目标价[位格]?[：:\s]*[¥￥$]?(\d+(?:\.\d+)?)",
            r"目标[：:\s]*[¥￥$]?(\d+(?:\.\d+)?)",
            r"合理价格[区间]*[：:\s]*[¥￥$]?(\d+(?:\.\d+)?)",
            r"看[到至][：:\s]*[¥￥$]?(\d+(?:\.\d+)?)",
            r"[¥￥$](\d+(?:\.\d+)?)",
            r"(\d+(?:\.\d+)?)\s*(?:元|美元|港元)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            try:
                return float(match.group(1))
            except ValueError:
                continue
        return None

    def _extract_ratio(self, text: str, labels: tuple[str, ...], *, default: float) -> float:
        for label in labels:
            match = re.search(rf"{label}[：:\s]*(\d+(?:\.\d+)?)\s*%?", text, flags=re.IGNORECASE)
            if not match:
                continue
            try:
                value = float(match.group(1))
            except ValueError:
                continue
            return value / 100 if value > 1 else value
        return default

    def _extract_reasoning(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if len(cleaned) <= 240:
            return cleaned
        return f"{cleaned[:240]}..."

    def _default_decision(self, reasoning: str) -> dict[str, Any]:
        return {
            "action": "观望",
            "target_price": None,
            "confidence": 0.5,
            "risk_score": 0.5,
            "reasoning": reasoning,
        }
