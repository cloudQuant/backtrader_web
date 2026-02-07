# 多交易ID策略 (MultiTrades Strategy)

## 策略简介

多交易ID策略演示了如何使用交易ID（trade ID）来管理多个并发的独立交易。每个交易ID可以单独跟踪和管理，这对于分批建仓、金字塔加仓等场景非常有用。

## 策略原理

### 什么是交易ID

Backtrader支持通过`tradeid`参数来标识不同的交易：
- 每个tradeid代表一个独立的交易流
- 同一tradeid的交易会自动合并仓位
- 不同tradeid的交易可以并存

### 策略逻辑

1. **交易ID循环**：在ID [0, 1, 2] 之间循环
2. **信号生成**：价格与SMA交叉
3. **新交易**：每次信号使用新的tradeid
4. **独立管理**：每个tradeid可以单独平仓

### 技术指标

- **SMA**（默认15周期）：移动平均线
- **交叉信号**：价格上穿/下穿SMA

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `period` | 15 | SMA周期 |
| `stake` | 1 | 每次交易数量 |
| `onlylong` | false | 是否只做多 |
| `mtrade` | true | 是否启用多交易ID模式 |

## 适用场景

1. **分批建仓**：在不同价位分批入场
2. **金字塔加仓**：盈利后逐步加仓
3. **多策略并行**：同一策略实例运行多个独立版本
4. **风险管理**：对不同入场点分别管理

## 风险提示

1. **仓位管理**：多个并发交易会增加总仓位
2. **复杂性增加**：需要跟踪多个tradeid的状态
3. **平仓顺序**：需要明确知道要平哪个tradeid
4. **资金管理**：并发交易可能占用更多保证金

## 使用示例

```python
import backtrader as bt
from strategy_multitrades import MultiTradesStrategy, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎
cerebro = bt.Cerebro(stdstats=True)
cerebro.broker.setcash(100000)

# 添加策略（启用多交易ID模式）
cerebro.addstrategy(MultiTradesStrategy, **config['params'])

# 运行回测
results = cerebro.run()
```

## 参考来源

- Backtrader官方示例：backtrader-master2/samples/multitrades/multitrades.py
