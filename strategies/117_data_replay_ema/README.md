# Data Replay EMA Strategy (数据重放EMA双均线策略)

## 策略简介

数据重放EMA双均线策略展示了Backtrader的数据重放功能在经典双均线交叉策略中的应用。该策略将日线数据重放为周线数据，然后应用EMA(12,26)双均线交叉策略进行交易。

## 策略原理

### 数据重放功能

数据重放将原始日线数据压缩为周线：
- 开盘价：周一的开盘价
- 收盘价：周五的收盘价
- 最高价：周内最高价
- 最低价：周内最低价
- 成交量：周内成交量总和

### EMA双均线交叉策略

- **快速EMA**：12周期指数移动平均线
- **慢速EMA**：26周期指数移动平均线
- **交叉信号**：快速EMA穿越慢速EMA

### 入场条件
- 快速EMA向上穿越慢速EMA（金叉）
- 平掉原有仓位后开新多仓

### 出场条件
- 快速EMA向下跌破慢速EMA（死叉）
- 平仓离场

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| fast_period | 12 | 快速EMA周期 |
| slow_period | 26 | 慢速EMA周期 |
| stake | 10 | 每次交易的股票数量 |

## 数据配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| symbol | 2005-2006-day-001 | 数据文件名 |
| timeframe | Days | 原始数据周期 |
| replay_timeframe | Weeks | 重放目标周期 |

## 适用场景

- **趋势识别**：周线级别的趋势更可靠
- **噪音过滤**：重放后过滤掉日内波动
- **中长线交易**：适合中长期持仓策略

## 风险提示

1. **信号滞后**：周线信号比日线更滞后
2. **错过反转**：可能错过趋势反转的最佳时机
3. **数据压缩**：丢失部分日内信息
4. **交易次数少**：重放后交易信号大幅减少

## 回测结果

基于2005-2006年日线数据重放为周线回测：

| 指标 | 数值 |
|------|------|
| 初始资金 | $100,000 |
| 最终资金 | $104,553.50 |
| 夏普比率 | 0.887 |
| 年化收益率 | 2.25% |
| 最大回撤 | 1.79% |
| 处理K线数 | 384 |
| 总交易次数 | 9 |

## 代码结构

```
117_data_replay_ema/
├── config.yaml                      # 策略配置文件
├── strategy_data_replay_ema.py      # 策略实现代码
└── README.md                        # 策略说明文档
```

## 使用方法

```python
import backtrader as bt
from strategy_data_replay_ema import ReplayEMAStrategy

cerebro = bt.Cerebro()

# 添加数据并重放为周线
data = bt.feeds.BacktraderCSVData(dataname='2005-2006-day-001.txt')
cerebro.replaydata(data, timeframe=bt.TimeFrame.Weeks, compression=1)

cerebro.addstrategy(ReplayEMAStrategy, fast_period=12, slow_period=26)
# ... 运行回测
```

## 参考来源

- backtrader test_58_data_replay.py
