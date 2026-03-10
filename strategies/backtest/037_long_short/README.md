# 多空策略 (Long Short Strategy)

## 策略简介

多空策略是一个经典的趋势跟踪策略，通过价格与移动平均线的交叉信号来产生多空交易信号。该策略既可以从上涨趋势中获利，也可以从下跌趋势中获利。

## 策略原理

### 技术指标

- **SMA（简单移动平均线）**：计算指定周期内的平均价格
- **交叉信号**：价格与SMA的交叉点

### 交易逻辑

1. **做多信号**：当价格上穿SMA时
   - 如果当前持有空头仓位，先平仓
   - 开多头仓位

2. **做空信号**：当价格下穿SMA时
   - 如果当前持有多头仓位，先平仓
   - 开空头仓位（如果允许做空）

3. **只做多模式**：设置`onlylong=True`时，策略只在多头方向交易

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `period` | 15 | SMA周期 |
| `stake` | 1 | 每次交易数量 |
| `onlylong` | false | 是否只做多（true=仅做多） |

## 适用场景

1. **趋势市场**：在有明显趋势的市场中表现良好
2. **波动市场**：能够捕捉上升和下跌波段
3. **可做多空市场**：适合支持做空的市场（如期货、外汇）

## 风险提示

1. **震荡市场**：在横盘震荡中容易产生频繁交易和亏损
2. **滞后性**：SMA是滞后指标，信号可能在趋势后半段才出现
3. **做空风险**：做空理论上有无限损失风险
4. **滑点成本**：频繁交易会产生较高的交易成本

## 使用示例

```python
import backtrader as bt
from strategy_long_short import LongShortStrategy, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎
cerebro = bt.Cerebro(stdstats=True)
cerebro.broker.setcash(100000)

# 添加策略（允许做空）
cerebro.addstrategy(LongShortStrategy, **config['params'])

# 运行回测
results = cerebro.run()
```

## 参考来源

- Backtrader官方示例：backtrader-master2/samples/analyzer-annualreturn/analyzer-annualreturn.py
