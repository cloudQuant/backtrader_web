# Data Replay Bollinger Bands Strategy (数据重放布林带策略)

## 策略简介

数据重放布林带策略展示了Backtrader的数据重放（Data Replay）功能。该策略将日线数据重放为周线数据，然后应用布林带突破策略进行交易。数据重放功能允许在不同时间周期上测试策略，而无需重新准备数据。

## 策略原理

### 数据重放功能

Backtrader的数据重放功能可以将原始数据（如日线）压缩成更大周期的数据（如周线）：
- 原始周期：日线
- 重放周期：周线
- 压缩方式：开盘价取第一日，收盘价取最后一日，最高价取期间最大值，最低价取期间最小值

### 布林带突破策略

- **上轨**：中轨 + 2倍标准差
- **中轨**：20周期移动平均线
- **下轨**：中轨 - 2倍标准差

### 入场条件
- 周线收盘价突破布林带上轨
- 开仓做多

### 出场条件
- 周线收盘价跌破布林带中轨
- 平仓离场

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| period | 20 | 布林带周期 |
| devfactor | 2.0 | 标准差倍数 |
| stake | 10 | 每次交易的股票数量 |

## 数据配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| symbol | 2005-2006-day-001 | 数据文件名 |
| timeframe | Days | 原始数据周期 |
| replay_timeframe | Weeks | 重放目标周期 |

## 适用场景

- **多周期分析**：在不同时间周期上测试策略
- **数据复用**：使用同一数据源测试不同周期的策略
- **趋势跟踪**：周线级别过滤日线噪音

## 风险提示

1. **数据压缩损失**：重放过程会丢失部分日内波动信息
2. **信号延迟**：周线级别信号比日线更滞后
3. **样本减少**：重放后数据量大幅减少
4. **成交量失真**：重放后的成交量是期间总和

## 回测结果

基于2005-2006年日线数据重放为周线回测：

| 指标 | 数值 |
|------|------|
| 初始资金 | $100,000 |
| 最终资金 | $103,822.30 |
| 夏普比率 | 0.717 |
| 年化收益率 | 1.89% |
| 最大回撤 | 1.98% |
| 处理K线数 | 419 |
| 总交易次数 | 2 |

## 代码结构

```
116_data_replay_bollinger/
├── config.yaml                         # 策略配置文件
├── strategy_data_replay_bollinger.py   # 策略实现代码
└── README.md                           # 策略说明文档
```

## 使用方法

```python
import backtrader as bt
from strategy_data_replay_bollinger import ReplayBollingerStrategy

cerebro = bt.Cerebro()

# 添加数据并重放为周线
data = bt.feeds.BacktraderCSVData(dataname='2005-2006-day-001.txt')
cerebro.replaydata(data, timeframe=bt.TimeFrame.Weeks, compression=1)

cerebro.addstrategy(ReplayBollingerStrategy, period=20, devfactor=2.0)
# ... 运行回测
```

## 参考来源

- backtrader test_58_data_replay.py
