# MT5 MACD趋势跟踪策略

基于MACD指标的趋势跟踪策略，适用于MT5外汇及贵金属品种。

## 策略逻辑

- **MACD金叉做多**：MACD线上穿信号线且柱状图为正时买入
- **MACD死叉平仓**：MACD线下穿信号线时平仓

## 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| fast_period | 12 | 快线EMA周期 |
| slow_period | 26 | 慢线EMA周期 |
| signal_period | 9 | 信号线周期 |
| volume | 0.01 | 交易手数 |

## 适用品种

XAUUSD（黄金）、EURUSD 等趋势性品种，推荐H1周期。
