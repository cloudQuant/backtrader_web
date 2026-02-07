# Pinkfish挑战策略 (Pinkfish Challenge Strategy)

## 策略简介

Pinkfish挑战策略是一个基于价格突破动量的简单策略：当价格创N日新高时买入，持有固定天数后无条件卖出。这是一个典型的"突破买入、时间止损"策略。

## 策略原理

### 策略逻辑

1. **入场条件**：当日最高价 >= 过去N天的最高价
   - 表示价格正在创阶段新高
   - 显示上升动能

2. **出场条件**：持仓达到设定天数后卖出
   - 不考虑价格表现
   - 纯时间基础的出场

### 技术指标

- **Highest指标**：追踪过去N天的最高价
- 当当前价格突破该指标时产生买入信号

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `highperiod` | 20 | 创新高判断周期（天） |
| `sellafter` | 2 | 持有天数后卖出 |

## 适用场景

1. **趋势市场**：在有明显趋势的市场表现较好
2. **动量交易**：捕捉价格突破的短期动量
3. **快速交易**：持仓时间短，资金利用率高

## 风险提示

1. **假突破**：价格创新高后可能迅速回落
2. **固定持仓期**：不考虑市场状况的机械出场
3. **震荡市场**：在横盘震荡中容易被套
4. **频繁交易**：突破信号较多时交易频繁

## 策略特点

| 特点 | 说明 |
|------|------|
| 简单性 | 只有入场和固定时间出场两个规则 |
| 动量导向 | 买入强势，不依赖技术指标 |
| 时间止损 | 避免长期持有不利仓位 |
| 无止损 | 入场后不设止损，依赖时间出场 |

## 使用示例

```python
import backtrader as bt
from strategy_pinkfish import PinkfishStrategy, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎
cerebro = bt.Cerebro(stdstats=True)
cerebro.broker.setcash(50000)

# 添加策略
cerebro.addstrategy(PinkfishStrategy, **config['params'])

# 运行回测
results = cerebro.run()
```

## 参考来源

- Backtrader官方示例：backtrader-master2/samples/pinkfish-challenge/pinkfish-challenge.py
