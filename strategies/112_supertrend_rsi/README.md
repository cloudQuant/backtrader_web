# Supertrend RSI Strategy (超级趋势RSI策略)

## 策略简介

超级趋势RSI策略是一种结合SuperTrend趋势指标和RSI动量指标的趋势跟踪策略。该策略利用SuperTrend指标判断趋势方向，结合RSI指标确认入场时机，在趋势向上且动量充足时买入，在趋势反转时卖出。

## 策略原理

### SuperTrend指标

SuperTrend是一种基于ATR（平均真实波幅）的趋势跟踪指标，计算方法为：

1. **基础上限** = (最高价 + 最低价) / 2 - (ATR倍数 × ATR)
2. **基础下限** = (最高价 + 最低价) / 2 + (ATR倍数 × ATR)
3. **最终带**：根据前一日收盘价与带的关系进行平滑处理
4. **SuperTrend线**：根据价格与最终带的关系动态切换

### 入场条件
- 收盘价 > SuperTrend线（趋势向上）
- RSI > 阈值（默认40，确认动量）
- 两个条件同时满足时买入

### 出场条件
- 收盘价 < SuperTrend线（趋势转向下）

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| stake | 10 | 每次交易的股票数量 |
| atr_period | 14 | ATR计算周期 |
| atr_mult | 2 | ATR倍数 |
| rsi_period | 14 | RSI计算周期 |
| rsi_threshold | 40 | RSI入场阈值 |

## 适用场景

- **趋势市场**：在明显的上涨或下跌趋势中表现较好
- **波动率适中**：ATR能正确反映市场波动
- **中长线交易**：适合中长期持仓跟踪趋势

## 风险提示

1. **震荡亏损**：在横盘震荡中容易产生频繁交易
2. **滞后性**：指标具有滞后性，可能错过最佳买卖点
3. **假突破**：价格可能短暂突破SuperTrend线后回归
4. **参数敏感**：ATR倍数需要根据市场特性调整

## 回测结果

基于Oracle (ORCL) 2010-2014年数据回测：

| 指标 | 数值 |
|------|------|
| 初始资金 | $100,000 |
| 最终资金 | $100,085.04 |
| 夏普比率 | 0.899 |
| 年化收益率 | 0.017% |
| 最大回撤 | 7.72% |
| 处理K线数 | 1243 |

## 代码结构

```
112_supertrend_rsi/
├── config.yaml                # 策略配置文件
├── strategy_supertrend_rsi.py # 策略实现代码
└── README.md                  # 策略说明文档
```

## 使用方法

```python
import backtrader as bt
from strategy_supertrend_rsi import SupertrendRsiStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(SupertrendRsiStrategy,
                    stake=10,
                    atr_period=14,
                    atr_mult=2,
                    rsi_period=14,
                    rsi_threshold=40)
# ... 添加数据和运行回测
```

## 参考来源

- backtrader-strategies-compendium/strategies/SupertrendRSI.py
