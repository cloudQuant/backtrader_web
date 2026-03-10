# 信号策略 (Signals Strategy)

## 策略简介

信号策略演示了Backtrader的`cerebro.add_signal()`功能，提供了一种无需编写完整Strategy类即可实现基于指标的交易的声明式方法。

## 策略原理

### 什么是信号策略

与传统Strategy类不同，信号策略：
- **声明式**：定义信号指标，让Backtrader处理执行
- **简化代码**：无需编写完整的next()方法
- **指标驱动**：交易决策基于指标值

### 信号类型

| 信号类型 | 说明 |
|----------|------|
| `SIGNAL_LONG` | 信号为正时做多 |
| `SIGNAL_LONGSHORT` | 根据信号正负做多或做空 |
| `SIGNAL_SHORT` | 信号为负时做空 |
| `SIGNAL_LONGEXIT` | 信号变负时退出多头 |

### SMACloseSignal指标

```
信号值 = 当前价格 - SMA(30周期)
```

- **信号 > 0**：价格在均线上方（看涨）→ 持有多头仓位
- **信号 < 0**：价格在均线下方（看跌）→ 平仓

仓位大小与信号强度成正比。

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `period` | 30 | SMA周期 |

## 适用场景

1. **快速原型**：快速测试指标组合
2. **简单策略**：基于单一指标的简单规则
3. **投资组合**：多资产信号聚合
4. **因子策略**：基于因子评分的仓位分配

## 信号vs策略类对比

| 方面 | 信号策略 | 策略类 |
|------|----------|--------|
| 代码量 | 少 | 多 |
| 灵活性 | 有限 | 高 |
| 适用场景 | 简单指标策略 | 复杂多阶段逻辑 |
| 订单管理 | 自动 | 手动控制 |
| 状态管理 | 简单 | 可自定义 |

## 风险提示

1. **灵活性限制**：无法实现复杂的多阶段逻辑
2. **订单控制**：高级订单类型（OCO、Bracket）支持有限
3. **仓位大小**：由信号值自动决定，可能不符合预期
4. **学习曲线**：需要理解信号值与仓位的关系

## 使用示例

```python
import backtrader as bt
from strategy_signals import SMACloseSignal, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎
cerebro = bt.Cerebro(stdstats=True)
cerebro.broker.setcash(50000)

# 添加信号（无需Strategy类）
cerebro.add_signal(bt.SIGNAL_LONG, SMACloseSignal, period=30)

# 运行回测
results = cerebro.run()
```

## 参考来源

- Backtrader官方示例：backtrader-master2/samples/signals-strategy/signals-strategy.py
