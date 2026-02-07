# ATR动量策略 (ATR Momentum Strategy)

## 策略简介

本策略结合多个技术指标来识别趋势跟踪入场机会，并使用ATR(平均真实波幅)实现基于波动率的风险管理。

## 策略原理

1. **趋势过滤**：价格必须位于200日SMA上方(做多)或下方(做空)
2. **动量信号**：RSI穿越50作为入场信号
3. **风险管理**：使用ATR计算动态止损和止盈位
   - 止损：2倍ATR
   - 止盈：5倍ATR
4. **仓位管理**：根据ATR波动率调整仓位大小

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| bet | 100 | 基础仓位大小 |
| stop_atr_multiplier | 2 | 止损ATR倍数 |
| target_atr_multiplier | 5 | 止盈ATR倍数 |
| rsi_period | 14 | RSI周期 |
| sma_period | 200 | 趋势过滤SMA周期 |
| atr_period | 14 | ATR周期 |

## 适用场景

- 趋势明显的市场
- 波动率较大的品种
- 需要动态风险管理的策略

## 风险提示

- 在震荡市场中表现不佳
- ATR计算需要足够的历史数据
- 杠杆使用需要谨慎

## 参考资料

- https://github.com/papodetrader/backtest
