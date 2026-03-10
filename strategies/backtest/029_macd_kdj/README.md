# MACD KDJ组合策略 (MACD + KDJ Strategy)

## 策略简介

MACD KDJ组合策略结合了MACD的趋势判断能力和KDJ的时机把握能力。MACD用于识别趋势方向，KDJ用于寻找入场时机。

## 策略原理

### 指标说明

- **MACD (Moving Average Convergence Divergence)**: 趋势跟踪指标
- **KDJ (Stochastic Oscillator)**: 随机振荡指标，用于超买超卖判断

### 交易规则

**开仓条件：**
- 做多：MACD金叉（MACD线上穿信号线）
- 做空：KDJ死叉（K线下穿D线）

**平仓条件：**
- 多头平仓：KDJ死叉
- 空头平仓：MACD金叉

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| macd_fast_period | 12 | MACD快线周期 |
| macd_slow_period | 26 | MACD慢线周期 |
| macd_signal_period | 9 | MACD信号线周期 |
| kdj_fast_period | 9 | KDJ周期 |
| kdj_slow_period | 3 | KDJ平滑周期 |

## 适用场景

- 趋势明确的市场
- 波动较大的品种
- 适合中短线交易

## 风险提示

1. 在震荡市场中表现不佳
2. MACD信号存在滞后性
3. 需要结合其他指标过滤假信号

## 回测表现

基于上海股票(sh600000) 2000-2022年数据回测：
- 总交易次数：212笔
- 胜率：较低
- 最终资金：5,870.49元（初始100,000元）
- 年化收益率：-12.36%（严重亏损）
- 最大回撤：98.63%

**注意**: 该策略在测试数据上表现极差，说明该参数配置不适合该股票。

## 文件说明

- `config.yaml`: 策略配置文件
- `strategy_macd_kdj.py`: 策略实现代码
- `README.md`: 策略说明文档
