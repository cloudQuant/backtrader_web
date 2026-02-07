# 目标仓位策略 (Order Target Strategy)

## 策略简介

目标仓位策略演示了Backtrader中`order_target_percent`的用法，该函数可以自动将仓位调整到目标比例。策略根据日期动态调整目标仓位比例，展示如何通过简单的规则实现动态仓位管理。

## 策略原理

### order_target_percent 函数

`order_target_percent(target=0.5)` 是Backtrader提供的仓位管理函数：
- 自动计算需要买入或卖出的数量
- 将仓位调整到目标百分比
- 无需手动计算股数

### 仓位计算规则

策略根据日期计算目标仓位：

| 月份类型 | 计算公式 | 说明 |
|----------|----------|------|
| 奇数月 | day / 100 | 1号=1%，15号=15%，31号=31% |
| 偶数月 | (31 - day) / 100 | 1号=30%，15号=16%，31号=0% |

这创造了仓位先增加后减少的周期性模式。

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `use_target_percent` | true | 是否使用order_target_percent |

## 适用场景

1. **仓位管理学习**：理解如何动态调整仓位
2. **定投策略**：根据时间调整投资比例
3. **趋势跟随**：根据信号强度调整仓位比例

## 风险提示

1. **演示性质**：本策略主要用于演示功能，非实战策略
2. **频繁调仓**：每日调整仓位会产生大量交易
3. **交易成本**：频繁交易会显著侵蚀收益
4. **滑点影响**：实际交易中滑点会增加成本

## 使用示例

```python
import backtrader as bt
from strategy_order_target import OrderTargetStrategy, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎
cerebro = bt.Cerebro(stdstats=True)
cerebro.broker.setcash(1000000)

# 添加策略
cerebro.addstrategy(OrderTargetStrategy, **config['params'])

# 运行回测
results = cerebro.run()
```

## 参考来源

- Backtrader官方示例：backtrader-master2/samples/order_target/order_target.py
