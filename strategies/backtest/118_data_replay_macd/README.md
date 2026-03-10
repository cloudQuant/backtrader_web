# Data Replay MACD Strategy (数据重放MACD策略)

## 策略简介

数据重放MACD策略展示了Backtrader的数据重放功能在经典MACD指标策略中的应用。该策略将日线数据重放为周线数据，然后应用MACD(12,26,9)交叉策略进行交易。

## 策略原理

### 数据重放功能

数据重放将原始日线数据压缩为周线：
- 开盘价：周一的开盘价
- 收盘价：周五的收盘价
- 最高价：周内最高价
- 最低价：周内最低价
- 成交量：周内成交量总和

### MACD指标

MACD（Moving Average Convergence Divergence）由三部分组成：
- **MACD线**：EMA(12) - EMA(26)
- **信号线**：MACD的9日EMA
- **柱状图**：MACD线 - 信号线

### 入场条件
- MACD线向上穿越信号线（金叉）
- 平掉原有仓位后开新多仓

### 出场条件
- MACD线向下跌破信号线（死叉）
- 平仓离场

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| fast_period | 12 | 快速EMA周期 |
| slow_period | 26 | 慢速EMA周期 |
| signal_period | 9 | 信号线周期 |
| stake | 10 | 每次交易的股票数量 |

## 数据配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| symbol | 2005-2006-day-001 | 数据文件名 |
| timeframe | Days | 原始数据周期 |
| replay_timeframe | Weeks | 重放目标周期 |

## 适用场景

- **趋势确认**：周线MACD信号更可靠
- **噪音过滤**：过滤掉日内虚假信号
- **中长线交易**：适合中长期持仓策略

## 风险提示

1. **信号滞后**：周线信号比日线更滞后
2. **错过反转**：可能错过趋势反转的最佳时机
3. **数据压缩**：丢失部分日内波动信息
4. **柱状图失真**：重放后MACD柱状图形态可能改变

## 回测结果

基于2005-2006年日线数据重放为周线回测：

| 指标 | 数值 |
|------|------|
| 初始资金 | $100,000 |
| 最终资金 | $106,870.40 |
| 夏普比率 | 1.323 |
| 年化收益率 | 3.38% |
| 最大回撤 | 1.66% |
| 处理K线数 | 344 |
| 总交易次数 | 9 |

## 代码结构

```
118_data_replay_macd/
├── config.yaml                      # 策略配置文件
├── strategy_data_replay_macd.py     # 策略实现代码
└── README.md                        # 策略说明文档
```

## 使用方法

```python
import backtrader as bt
from strategy_data_replay_macd import ReplayMACDStrategy

cerebro = bt.Cerebro()

# 添加数据并重放为周线
data = bt.feeds.BacktraderCSVData(dataname='2005-2006-day-001.txt')
cerebro.replaydata(data, timeframe=bt.TimeFrame.Weeks, compression=1)

cerebro.addstrategy(ReplayMACDStrategy, fast_period=12, slow_period=26, signal_period=9)
# ... 运行回测
```

## 参考来源

- backtrader test_58_data_replay.py
