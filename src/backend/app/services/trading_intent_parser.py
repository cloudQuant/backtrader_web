"""Trading intent parser: converts natural language to structured trading intents.

Uses LLM to parse user's natural language trading instructions into
structured TradingIntent objects that can be validated and executed.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.schemas.ai_trading import (
    OrderType,
    RiskLevel,
    TradeAction,
    TradingIntent,
)

logger = logging.getLogger(__name__)


async def _call_llm(question: str, system_prompt: str) -> str:
    """Call the AI provider for intent parsing.

    Uses the same AI chat infrastructure as the KB Copilot.
    Builds messages directly and calls the provider.
    """
    import asyncio

    from app.services.ai_chat_service import AIChatService

    service = AIChatService()
    if not service.is_enabled():
        raise RuntimeError("AI chat is not enabled (AI_CHAT_ENABLED=false)")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    try:
        result = await asyncio.to_thread(service._call_provider, messages, "knowledge_qa")
        return result.get("answer", "")
    except Exception as e:
        raise RuntimeError(f"AI provider call failed: {e}") from e

_INTENT_PARSE_PROMPT = """你是一个交易指令解析器。将用户的自然语言交易指令解析为结构化 JSON。

你必须返回一个 JSON 对象，不要使用 Markdown 代码块，不要输出 JSON 以外的内容。

JSON 结构：
{
  "action": "buy|sell|close|cancel|query|modify",
  "symbol": "交易品种代码（如 rb2501, BTCUSDT, AAPL）",
  "exchange": "交易所（ctp|binance|okx|ib|null）",
  "quantity": 数量（数字或null）,
  "price": 价格（数字或null，null表示市价）,
  "order_type": "market|limit|stop|stop_limit",
  "stop_loss": 止损价（数字或null）,
  "take_profit": 止盈价（数字或null）,
  "reason": "解析理由说明",
  "confidence": 0.0-1.0的置信度,
  "risk_level": "low|medium|high|critical"
}

解析规则：
1. "买入"/"做多"/"开多" → action: "buy"
2. "卖出"/"做空"/"开空" → action: "sell"
3. "平仓"/"了结"/"清仓" → action: "close"
4. "撤单"/"取消" → action: "cancel"
5. "查询"/"看看"/"持仓" → action: "query"
6. 没有明确价格 → order_type: "market"
7. 有明确价格 → order_type: "limit"
8. "手" 在期货中通常是合约数量单位
9. 如果无法确定品种，symbol 设为 null，confidence 降低
10. 如果指令模糊或有歧义，confidence 应低于 0.5

品种识别：
- 螺纹钢/螺纹 → rb（主力合约自动匹配）
- 铁矿石/铁矿 → i
- BTC/比特币 → BTCUSDT
- ETH/以太坊 → ETHUSDT
- 中文股票名需要转换为代码

当前市场上下文：
{market_context}
"""


async def parse_trading_intent(
    user_input: str,
    market_context: str = "无额外市场上下文",
) -> TradingIntent:
    """Parse natural language input into a structured trading intent.

    Args:
        user_input: The user's natural language trading instruction.
        market_context: Optional market context for better parsing.

    Returns:
        A TradingIntent object with parsed fields.
    """
    system_prompt = _INTENT_PARSE_PROMPT.replace("{market_context}", market_context)

    try:
        response_text = await _call_llm(
            question=user_input,
            system_prompt=system_prompt,
        )
    except Exception as e:
        logger.warning("AI intent parsing failed, returning low-confidence intent: %s", e)
        return TradingIntent(
            action=TradeAction.QUERY,
            reason=f"AI 解析失败: {e}",
            confidence=0.0,
            risk_level=RiskLevel.HIGH,
            raw_input=user_input,
        )

    # Parse JSON response
    intent_data = _extract_json(response_text)
    if intent_data is None:
        logger.warning("Failed to parse JSON from AI response: %s", response_text[:200])
        return TradingIntent(
            action=TradeAction.QUERY,
            reason="无法解析 AI 响应为有效 JSON",
            confidence=0.0,
            risk_level=RiskLevel.HIGH,
            raw_input=user_input,
        )

    # Build TradingIntent from parsed data
    try:
        return TradingIntent(
            action=_parse_action(intent_data.get("action", "query")),
            symbol=intent_data.get("symbol"),
            exchange=intent_data.get("exchange"),
            quantity=_safe_float(intent_data.get("quantity")),
            price=_safe_float(intent_data.get("price")),
            order_type=_parse_order_type(intent_data.get("order_type", "market")),
            stop_loss=_safe_float(intent_data.get("stop_loss")),
            take_profit=_safe_float(intent_data.get("take_profit")),
            reason=intent_data.get("reason", ""),
            confidence=min(1.0, max(0.0, float(intent_data.get("confidence", 0.5)))),
            risk_level=_parse_risk_level(intent_data.get("risk_level", "medium")),
            raw_input=user_input,
            additional_params={
                k: v
                for k, v in intent_data.items()
                if k not in {
                    "action", "symbol", "exchange", "quantity", "price",
                    "order_type", "stop_loss", "take_profit", "reason",
                    "confidence", "risk_level",
                }
            },
        )
    except Exception as e:
        logger.warning("Failed to construct TradingIntent: %s", e)
        return TradingIntent(
            action=TradeAction.QUERY,
            reason=f"构建交易意图失败: {e}",
            confidence=0.0,
            risk_level=RiskLevel.HIGH,
            raw_input=user_input,
        )


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract JSON object from text, handling markdown code blocks."""
    text = text.strip()
    # Remove markdown code block if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None


def _parse_action(value: str) -> TradeAction:
    """Parse action string to TradeAction enum."""
    mapping = {
        "buy": TradeAction.BUY,
        "sell": TradeAction.SELL,
        "close": TradeAction.CLOSE,
        "cancel": TradeAction.CANCEL,
        "query": TradeAction.QUERY,
        "modify": TradeAction.MODIFY,
    }
    return mapping.get(value.lower(), TradeAction.QUERY)


def _parse_order_type(value: str) -> OrderType:
    """Parse order type string to OrderType enum."""
    mapping = {
        "market": OrderType.MARKET,
        "limit": OrderType.LIMIT,
        "stop": OrderType.STOP,
        "stop_limit": OrderType.STOP_LIMIT,
    }
    return mapping.get(value.lower(), OrderType.MARKET)


def _parse_risk_level(value: str) -> RiskLevel:
    """Parse risk level string to RiskLevel enum."""
    mapping = {
        "low": RiskLevel.LOW,
        "medium": RiskLevel.MEDIUM,
        "high": RiskLevel.HIGH,
        "critical": RiskLevel.CRITICAL,
    }
    return mapping.get(value.lower(), RiskLevel.MEDIUM)


def _safe_float(value: Any) -> float | None:
    """Safely convert value to float, returning None on failure."""
    if value is None:
        return None
    try:
        result = float(value)
        return result if result > 0 else None
    except (ValueError, TypeError):
        return None
