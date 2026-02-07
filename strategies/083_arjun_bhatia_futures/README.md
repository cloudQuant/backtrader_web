# Arjun Bhatia期货策略 (Arjun Bhatia Futures Strategy)

## 策略简介

Arjun Bhatia期货策略是一个结合了Alligator（鳄鱼）指标和SuperTrend指标的综合趋势跟踪策略。该策略要求两个指标同时确认趋势方向才入场，并使用ATR动态计算止损止盈水平。

## 策略原理

### 核心思想
- 使用Alligator指标识别长期趋势方向
- 使用SuperTrend指标确认短期趋势动量
- 两个指标同时看多时才入场，提高信号可靠性
- ATR动态止损止盈控制风险

### 入场条件
**买入条件：**
- 收盘价 > Alligator下颚线
- SuperTrend方向为1（上涨）

### 出场条件
**满足以下任一条件即平仓：**
- 最低价 <= 止损价（入场价 - 2×ATR）
- 最高价 >= 止盈价（入场价 + 4×ATR）
- Alligator或SuperTrend转为看跌

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| stake | 10 | 每次交易的数量 |
| jaw_period | 13 | Alligator下颚线周期 |
| teeth_period | 8 | Alligator牙齿线周期 |
| lips_period | 5 | Alligator嘴唇线周期 |
| supertrend_period | 10 | SuperTrend的ATR周期 |
| supertrend_multiplier | 3.0 | SuperTrend的ATR倍数 |
| atr_sl_mult | 2.0 | 止损ATR倍数 |
| atr_tp_mult | 4.0 | 止盈ATR倍数 |

## 适用场景

- 趋势明显的期货市场
- 波动性适中的品种
- 中长期趋势跟踪

## 风险提示

1. **双重指标滞后**：两个指标都存在滞后，可能错过最佳入场点
2. **信号稀少**：要求两个指标同时确认，可能导致交易机会减少
3. **止损风险**：2倍ATR的止损可能被市场噪音触发
4. **趋势反转**：快速反转可能导致触及止损
5. **仅做多**：策略只做多单向交易

## 回测结果

基于Oracle（ORCL）股票数据（2010-2014）回测：
- 总交易天数：1243
- 夏普比率：0.035
- 年化收益率：0.002%
- 最大回撤：13.56%
- 最终资金：100,008.30

## 参考文献

- Reference: https://github.com/Backtesting/strategies
