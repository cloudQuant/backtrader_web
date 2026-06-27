"""AI strategy draft builder used by the strategy copilot flow."""

from __future__ import annotations

import re

from app.schemas.strategy import (
    AIStrategyBacktestSpec,
    AIStrategyDataSourceSpec,
    AIStrategyDraft,
    AIStrategyExecutionPlan,
    ParamSpec,
)
from app.services.strategy.inference import (
    build_ai_param_specs,
    class_name_from_prompt,
    infer_category,
    infer_data_source_type,
    infer_timeframe,
    render_param_default,
    strategy_name_from_prompt,
)


def build_ai_strategy_draft(prompt: str, references: list[str] | None = None) -> AIStrategyDraft:
    """Build a deterministic fallback strategy draft from natural language input."""
    name = strategy_name_from_prompt(prompt)
    category = infer_category(name, prompt)
    class_name = class_name_from_prompt(prompt)
    params = build_ai_param_specs(prompt)
    timeframe = infer_timeframe(prompt)
    prompt_comment = re.sub(r"\s+", " ", str(prompt or "")).strip()
    prompt_comment = prompt_comment.replace('"""', "'''")
    reference_note = ""
    if references:
        reference_note = "\n".join(f"- {title}" for title in references[:3])
    param_lines = "\n".join(
        f"        ('{key}', {render_param_default(spec.default)})," for key, spec in params.items()
    )
    setup_lines = [
        "        self.close = self.datas[0].close",
        "        self.entry_price = None",
        "        self.stop_price = None",
        "        self.take_profit_price = None",
    ]
    if "fast_period" in params:
        setup_lines.extend(
            [
                "        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.p.fast_period)",
                "        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.p.slow_period)",
                "        self.ma_crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)",
            ]
        )
    if "rsi_period" in params:
        setup_lines.append(
            "        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)"
        )
    if "atr_period" in params:
        setup_lines.append(
            "        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)"
        )
    setup_block = "\n".join(setup_lines)

    code = f'''import backtrader as bt


class {class_name}(bt.Strategy):
    """
    Auto-generated draft from AI for Trader AI Copilot.
    Original prompt: {prompt_comment}
    """

    params = (
{param_lines}
    )

    def __init__(self):
{setup_block}

    def _entry_signal(self):
        if hasattr(self, 'ma_crossover'):
            return self.ma_crossover[0] > 0
        if hasattr(self, 'rsi'):
            return self.rsi[0] < self.p.oversold
        return len(self) == 1

    def _exit_signal(self):
        if hasattr(self, 'ma_crossover'):
            return self.ma_crossover[0] < 0
        if hasattr(self, 'rsi'):
            return self.rsi[0] > self.p.overbought
        return False

    def next(self):
        if not self.position:
            if self._entry_signal():
                entry_price = float(self.close[0])
                risk_budget = max(float(self.broker.getvalue()) * self.p.risk_pct, 0.0)
                contract_multiplier = max(float(self.p.contract_multiplier or 1.0), 0.000001)
                margin_rate = max(float(self.p.margin_rate or 1.0), 0.0)
                if hasattr(self, 'atr'):
                    atr_stop = float(self.atr[0]) * self.p.atr_stop_multiplier
                    self.stop_price = entry_price - atr_stop
                    price_risk = atr_stop
                else:
                    self.stop_price = entry_price * (1.0 - self.p.stop_loss_pct)
                    price_risk = entry_price * self.p.stop_loss_pct
                self.take_profit_price = entry_price * (1.0 + self.p.take_profit_pct)
                risk_per_unit = max(price_risk * contract_multiplier, 0.000001)
                risk_size = int(risk_budget / risk_per_unit) if risk_budget > 0 else 0
                margin_per_unit = max(entry_price * contract_multiplier * margin_rate, 0.000001)
                affordable_size = int(max(float(self.broker.getcash()), 0.0) / margin_per_unit)
                size = min(risk_size, affordable_size)
                if size <= 0:
                    return
                self.entry_price = entry_price
                self.buy(size=size)
        else:
            should_exit = self._exit_signal()
            if self.stop_price is not None and self.close[0] <= self.stop_price:
                should_exit = True
            if self.take_profit_price is not None and self.close[0] >= self.take_profit_price:
                should_exit = True
            if should_exit:
                self.close()
                self.entry_price = None
                self.stop_price = None
                self.take_profit_price = None
'''

    rationale = f"该草案基于自然语言需求“{prompt_comment[:80]}”生成，已按 {category} 类策略补齐常见参数和 Backtrader 类骨架。"
    if reference_note:
        rationale += f"\n参考过的知识库文档：\n{reference_note}"

    return AIStrategyDraft(
        name=name,
        description=f"AI Copilot 根据自然语言需求生成的 {category} 策略草案。",
        code=code,
        params=params,
        category=category,
        assumptions=[
            "默认使用标准 OHLCV K 线数据，并按信号所在 bar 后续执行。",
            "默认未加入滑点、停牌、涨跌停和撮合冲击等市场微观结构约束。",
        ],
        risk_points=[
            "需要验证参数稳定性，避免仅在样本内表现良好。",
            "需要结合交易成本与回撤约束评估真实可执行性。",
        ],
        data_source=AIStrategyDataSourceSpec(
            type=infer_data_source_type(prompt_comment),
            symbol=None,
            symbol_name=None,
            timeframe=timeframe or "1d",
            timeframe_n=1,
            start_date=None,
            end_date=None,
            adjustment=None,
        ),
        backtest_defaults=AIStrategyBacktestSpec(
            initial_cash=100000.0,
            commission=0.001,
            annual_days=252,
            calc_method="simple",
            weight_mode="equal",
        ),
        execution_plan=AIStrategyExecutionPlan(
            workspace_type="research",
            group_name=name,
            run_parallel=False,
        ),
        rationale=rationale,
        next_steps=[
            "补充 entry / exit 条件与风险控制逻辑",
            "根据目标市场调整默认参数与时间框架",
            "在回测工作区中创建单元并验证收益/回撤/交易频率",
        ],
        suggested_symbol=None,
        suggested_timeframe=timeframe,
    )


def render_ai_strategy_draft_answer(draft: AIStrategyDraft) -> str:
    """Render a human-readable chat answer from a strategy draft."""
    params_summary = (
        ", ".join(f"{name}={spec.default}" for name, spec in draft.params.items()) or "无"
    )
    next_steps = "\n".join(f"- {step}" for step in draft.next_steps) or "- 无"
    timeframe = draft.suggested_timeframe or "待确认"
    rationale = draft.rationale or "基于自然语言需求自动生成。"
    data_source_type = draft.data_source.type if draft.data_source else "待确认"
    initial_cash = draft.backtest_defaults.initial_cash if draft.backtest_defaults else 100000.0
    commission = draft.backtest_defaults.commission if draft.backtest_defaults else 0.001
    return (
        f"已为你生成一个可继续完善的 Backtrader 策略草案。\n\n"
        f"策略名称：{draft.name}\n"
        f"策略分类：{draft.category}\n"
        f"建议周期：{timeframe}\n"
        f"建议数据源：{data_source_type}\n"
        f"默认回测：初始资金 {initial_cash:.2f} / 手续费 {commission}\n"
        f"关键参数：{params_summary}\n\n"
        f"说明：{rationale}\n\n"
        "代码骨架：\n"
        f"```python\n{draft.code}\n```\n\n"
        f"下一步建议：\n{next_steps}"
    )


def strategy_param_defaults(params: dict[str, ParamSpec]) -> dict[str, object]:
    return {name: spec.default for name, spec in params.items()}
