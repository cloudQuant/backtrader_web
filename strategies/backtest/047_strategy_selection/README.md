# 策略选择 (Strategy Selection)

## 策略简介

策略选择模块演示了如何在运行时动态选择不同的策略进行比较和测试。该模块包含两个示例策略，展示了策略选择和比较的最佳实践。

## 策略说明

### StrategyA：双均线交叉

- **原理**：快速SMA上穿慢速SMA时买入，下穿时卖出
- **参数**：
  - `p1`：快速SMA周期（默认10）
  - `p2`：慢速SMA周期（默认30）
- **特点**：经典的趋势跟踪策略

### StrategyB：价格SMA交叉

- **原理**：价格上穿SMA时买入，下穿时卖出
- **参数**：
  - `period`：SMA周期（默认10）
- **特点**：更敏感的信号，交易频率更高

## 策略对比

| 特点 | StrategyA | StrategyB |
|------|-----------|-----------|
| 信号类型 | 双均线交叉 | 价格-均线交叉 |
| 交易频率 | 较低 | 较高 |
| 敏感性 | 中等 | 高 |
| 趋势跟踪 | 好 | 非常好 |

## 使用场景

1. **策略选择**：在多个策略中选择表现最好的
2. **参数优化**：同一策略不同参数的对比
3. **A/B测试**：比较不同策略思路的效果
4. **投资组合**：组合多个策略分散风险

## 使用示例

### 运行单个策略

```python
from strategy_selection import StrategyA, run_strategy, load_config

# 加载配置
config = load_config()

# 运行StrategyA
result = run_strategy(StrategyA, config, "MyStrategy")
```

### 比较多个策略

```python
from strategy_selection import compare_strategies, load_config

# 加载配置
config = load_config()

# 比较两个策略
results = compare_strategies(config)
```

### 添加自定义策略

```python
# 定义新策略
class MyStrategy(bt.Strategy):
    params = (('period', 20),)

    def __init__(self):
        self.sma = bt.ind.SMA(period=self.p.period)

    def next(self):
        if self.data.close[0] > self.sma[0]:
            self.buy()
        elif self.data.close[0] < self.sma[0]:
            self.sell()

# 运行比较
from strategy_selection import run_strategy, load_config

config = load_config()
result = run_strategy(MyStrategy, config, "MyStrategy")
```

## 评估指标

| 指标 | 说明 | 越高越好 |
|------|------|----------|
| Final Value | 最终资产价值 | 是 |
| Sharpe Ratio | 风险调整后收益 | 是 |
| Annual Return | 年化收益率 | 是 |
| Max Drawdown | 最大回撤 | 否 |
| Total Trades | 总交易次数 | 视情况 |

## 风险提示

1. **过拟合风险**：历史表现不代表未来
2. **数据窥探**：避免用同一数据集多次优化
3. **交易成本**：高频交易策略需考虑手续费
4. **市场变化**：市场环境变化可能影响策略效果

## 参考来源

- Backtrader官方示例：backtrader-master2/samples/strategy-selection/strategy-selection.py
