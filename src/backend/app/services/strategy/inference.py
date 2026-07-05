"""Heuristic inference helpers used by the AI strategy copilot draft builder."""

from __future__ import annotations

import re

from app.schemas.strategy import ParamSpec


def infer_category(name: str, description: str) -> str:
    """Infer strategy category from name and description.

    Args:
        name: Strategy name.
        description: Strategy description.

    Returns:
        Inferred category string (trend, mean_reversion, volatility, etc.).
    """
    text = (name + description).lower()
    if any(
        k in text
        for k in ["ma", "trend", "supertrend", "turtle", "breakout", "momentum", "crossover"]
    ):
        return "trend"
    if any(
        k in text
        for k in [
            "rsi",
            "mean_reversion",
            "reversal",
            "oscillator",
            "overbought",
            "oversold",
            "kdj",
            "stochastic",
        ]
    ):
        return "mean_reversion"
    if any(k in text for k in ["boll", "bollinger", "atr", "volatility", "vix", "chandelier"]):
        return "volatility"
    if any(k in text for k in ["arbitrage", "hedge", "long_short", "pair"]):
        return "arbitrage"
    if any(k in text for k in ["macd", "ema", "signal", "indicator"]):
        return "indicator"
    return "custom"


def strategy_name_from_prompt(prompt: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(prompt or "")).strip(" \n\t，。,.!?！？")
    if not cleaned:
        return "AI Generated Strategy"
    return f"AI策略 - {cleaned[:24]}"


def class_name_from_prompt(prompt: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", str(prompt or ""))
    tokens = [token for token in tokens if re.search(r"[A-Za-z]", token)]
    if not tokens:
        return "AIGeneratedStrategy"
    class_name = "".join(token[:1].upper() + token[1:] for token in tokens[:4])
    if not re.match(r"^[A-Za-z_]", class_name):
        class_name = f"AI{class_name}"
    if not class_name.endswith("Strategy"):
        class_name = f"{class_name}Strategy"
    return class_name


def infer_timeframe(prompt: str) -> str | None:
    text = str(prompt or "").lower()
    if any(token in text for token in ["1m", "5m", "15m", "30m", "60m", "分钟"]):
        return "15m"
    if any(token in text for token in ["1h", "4h", "hour", "小时"]):
        return "1h"
    if any(token in text for token in ["日线", "daily", "1d"]):
        return "1d"
    if any(token in text for token in ["周线", "weekly", "1w"]):
        return "1w"
    return None


def infer_data_source_type(prompt: str) -> str:
    text = str(prompt or "").lower()
    if any(token in text for token in ["akshare", "a股", "沪深", "基金", "期货"]):
        return "csv"
    if any(token in text for token in ["yfinance", "yahoo", "美股", "us stock"]):
        return "csv"
    return "csv"


def build_ai_param_specs(prompt: str) -> dict[str, ParamSpec]:
    text = str(prompt or "").lower()
    params: dict[str, ParamSpec] = {}

    def add_param(name: str, spec: ParamSpec) -> None:
        if name not in params:
            params[name] = spec

    if any(token in text for token in ["ma", "均线", "crossover", "cross", "trend", "趋势"]):
        add_param(
            "fast_period",
            ParamSpec(
                type="int",
                default=10,
                min=2,
                max=60,
                description="Fast moving average period",
            ),
        )
        add_param(
            "slow_period",
            ParamSpec(
                type="int",
                default=30,
                min=10,
                max=240,
                description="Slow moving average period",
            ),
        )
    if any(token in text for token in ["rsi", "超卖", "超买"]):
        add_param(
            "rsi_period",
            ParamSpec(type="int", default=14, min=2, max=60, description="RSI lookback period"),
        )
        add_param(
            "oversold",
            ParamSpec(
                type="float",
                default=30,
                min=5,
                max=50,
                description="RSI oversold threshold",
            ),
        )
        add_param(
            "overbought",
            ParamSpec(
                type="float",
                default=70,
                min=50,
                max=95,
                description="RSI overbought threshold",
            ),
        )
    if any(token in text for token in ["atr", "止损", "volatility", "波动"]):
        add_param(
            "atr_period",
            ParamSpec(
                type="int",
                default=14,
                min=5,
                max=60,
                description="ATR calculation period",
            ),
        )
        add_param(
            "atr_stop_multiplier",
            ParamSpec(
                type="float",
                default=2.0,
                min=0.5,
                max=10.0,
                description="ATR stop multiplier",
            ),
        )
    if any(token in text for token in ["breakout", "突破", "channel", "唐奇安"]):
        add_param(
            "breakout_period",
            ParamSpec(
                type="int",
                default=20,
                min=5,
                max=120,
                description="Breakout lookback period",
            ),
        )
    if not params:
        add_param(
            "lookback_period",
            ParamSpec(
                type="int",
                default=20,
                min=2,
                max=200,
                description="Generic lookback period",
            ),
        )
        add_param(
            "signal_threshold",
            ParamSpec(
                type="float",
                default=0.0,
                min=-10.0,
                max=10.0,
                description="Generic signal threshold",
            ),
        )

    add_param(
        "risk_pct",
        ParamSpec(
            type="float",
            default=0.02,
            min=0.001,
            max=0.2,
            description="Risk budget per trade",
        ),
    )
    add_param(
        "contract_multiplier",
        ParamSpec(
            type="float",
            default=1.0,
            min=0.000001,
            max=1000000.0,
            description="Contract multiplier used for asset-aware position sizing",
        ),
    )
    add_param(
        "margin_rate",
        ParamSpec(
            type="float",
            default=1.0,
            min=0.0,
            max=10.0,
            description="Initial margin rate used to cap position size",
        ),
    )
    add_param(
        "stop_loss_pct",
        ParamSpec(
            type="float",
            default=0.03,
            min=0.001,
            max=0.5,
            description="Fallback stop-loss percentage when ATR is unavailable",
        ),
    )
    add_param(
        "take_profit_pct",
        ParamSpec(
            type="float",
            default=0.08,
            min=0.005,
            max=1.0,
            description="Take-profit percentage for the default template",
        ),
    )
    add_param(
        "max_hold_bars",
        ParamSpec(
            type="int",
            default=72,
            min=1,
            max=2000,
            description="Maximum bars to hold a position before forcing an exit",
        ),
    )
    return params


def render_param_default(value: object) -> str:
    if isinstance(value, str):
        return repr(value)
    return str(value)
