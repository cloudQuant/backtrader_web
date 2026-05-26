import pytest

from app.schemas.strategy_explanation import StrategyExplainRequest
from app.services.strategy_explainer.ast_extractor import extract_strategy_structure
from app.services.strategy_explainer.llm_explainer import StrategyLLMExplainer
from app.services.strategy_explainer.service import StrategyExplainerService

SAMPLE_STRATEGY = """
import backtrader as bt

class DualMaStrategy(bt.Strategy):
    params = (
        ('fast_period', 5),
        ('slow_period', 20),
        ('risk_pct', 0.02),
    )

    def __init__(self):
        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.p.fast_period)
        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.p.slow_period)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)

    def next(self):
        if not self.position and self.crossover[0] > 0:
            self.buy(size=10)
        elif self.position and self.crossover[0] < 0:
            self.sell(size=self.position.size)
"""


def test_extract_strategy_structure_detects_indicators_params_and_signals() -> None:
    structure = extract_strategy_structure(SAMPLE_STRATEGY)

    assert structure.parsable is True
    assert {item.name for item in structure.indicators} >= {'SMA', 'CrossOver'}
    assert {item.name for item in structure.params} >= {'fast_period', 'slow_period', 'risk_pct'}
    assert any(signal.side == 'buy' for signal in structure.entry_signals)
    assert any(signal.side == 'sell' for signal in structure.exit_signals)
    assert any(control.type == 'position_size' for control in structure.risk_controls)


def test_extract_strategy_structure_gracefully_degrades_on_invalid_code() -> None:
    structure = extract_strategy_structure('class Broken(:\n    pass')

    assert structure.parsable is False
    assert structure.raw_code.startswith('class Broken')
    assert structure.parse_error


def test_extract_strategy_structure_detects_dict_params_and_target_percent_controls() -> None:
    code = """
import backtrader as bt

class RsiRebalance(bt.Strategy):
    params = dict(rsi_period=14, target_pct=0.8, stop_loss=0.05)

    def __init__(self):
        self.rsi = bt.ind.RSI(self.data.close, period=self.p.rsi_period)

    def next(self):
        if self.rsi[0] < 30:
            self.order_target_percent(target=self.p.target_pct)
        if self.position and self.rsi[0] > 70:
            self.close()
"""
    structure = extract_strategy_structure(code)

    assert {item.name for item in structure.params} >= {"rsi_period", "target_pct", "stop_loss"}
    assert any(item.name == "RSI" for item in structure.indicators)
    assert any(control.type == "target_percent" for control in structure.risk_controls)
    assert any(control.type == "stop_loss_param" for control in structure.risk_controls)
    assert any(signal.side == "buy" for signal in structure.entry_signals)
    assert any(signal.side == "close" for signal in structure.exit_signals)


@pytest.mark.asyncio
async def test_strategy_explainer_returns_static_fallback_when_ai_disabled() -> None:
    service = StrategyExplainerService(ai_chat_service=None)

    result = await service.explain(
        StrategyExplainRequest(code=SAMPLE_STRATEGY, strategy_name='双均线策略')
    )

    assert result.reason_code == 'static_fallback'
    assert result.ast.parsable is True
    assert '双均线策略' in result.summary
    assert 'SMA' in result.indicators_explanation
    assert '买入' in result.entry_explanation
    assert '卖出' in result.exit_explanation
    assert result.code_hash


@pytest.mark.asyncio
async def test_strategy_explainer_uses_llm_explanation_when_available() -> None:
    class FakeLLMExplainer:
        async def generate(self, **kwargs):
            return {
                'summary': 'AI 总结：双均线策略识别趋势。',
                'indicators_explanation': 'AI 指标说明：SMA 衡量趋势。',
                'entry_explanation': 'AI 买入说明：金叉买入。',
                'exit_explanation': 'AI 卖出说明：死叉卖出。',
                'params_explanation': 'AI 参数说明：fast_period 控制快线。',
                'market_fit': 'AI 市场适配：趋势市场。',
                'risk_notes': ['AI 风险：震荡市假信号'],
                'model_id': 'fake-model',
            }

    service = StrategyExplainerService(ai_chat_service=None, llm_explainer=FakeLLMExplainer())

    result = await service.explain(
        StrategyExplainRequest(code=SAMPLE_STRATEGY, strategy_name='双均线策略')
    )

    assert result.reason_code == 'ai_generated'
    assert result.model_id == 'fake-model'
    assert result.summary.startswith('AI 总结')
    assert result.ast.parsable is True


def test_strategy_llm_explainer_parses_json_code_fence_and_normalizes_risks() -> None:
    payload = StrategyLLMExplainer._parse_payload(
        """```json
{
  "summary": "AI 总结",
  "indicators_explanation": "指标",
  "entry_explanation": "买入",
  "exit_explanation": "卖出",
  "params_explanation": "参数",
  "market_fit": "市场",
  "risk_notes": ["风险1", 2]
}
```"""
    )

    assert payload is not None
    assert payload["summary"] == "AI 总结"
    assert payload["risk_notes"] == ["风险1", "2"]


def test_strategy_llm_explainer_returns_none_on_invalid_json() -> None:
    assert StrategyLLMExplainer._parse_payload("{not-json") is None
