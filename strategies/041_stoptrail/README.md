# 追踪止损策略 (Stop Trail Strategy)

## 策略简介

追踪止损策略使用移动平均线交叉作为入场信号，并通过追踪止损订单来保护已有利润。追踪止损会随着价格有利变动而调整，从而在锁定利润的同时给予价格继续波动的空间。

## 策略原理

### 什么是追踪止损

追踪止损（Trailing Stop）是一种动态止损方式：
- 止损价格随价格有利变动而调整
- 价格上涨时止损价跟随上调
- 价格下跌时止损价保持不变
- 触发止损价时自动平仓

### 技术指标

- **快速SMA**（默认5周期）：快速响应价格变化
- **慢速SMA**（默认20周期）：显示主要趋势
- **交叉信号**：金叉/死叉

### 交易逻辑

1. **入场条件**：快速SMA上穿慢速SMA（金叉）时买入
2. **止损设置**：设置追踪止损，距离当前价格一定百分比
3. **出场条件**：
   - 价格回调触及追踪止损价
   - 或快速SMA下穿慢速SMA（死叉）

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `p1` | 5 | 快速SMA周期 |
| `p2` | 20 | 慢速SMA周期 |
| `trailpercent` | 0.02 | 追踪止损百分比（2%） |

## 适用场景

1. **趋势市场**：在明显趋势中追踪止损效果最好
2. **波动市场**：能够捕捉大幅波动的同时限制损失
3. **保护利润**：防止盈利变成亏损

## 风险提示

1. **过早止损**：止损设置过紧可能被正常波动触发
2. **回撤损失**：从高点回撤到止损价之间的损失无法避免
3. **震荡市场**：在横盘震荡中容易被反复止损
4. **跳空风险**：价格跳空可能突破止损价

## 使用示例

```python
import backtrader as bt
from strategy_stoptrail import StopTrailStrategy, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎
cerebro = bt.Cerebro(stdstats=True)
cerebro.broker.setcash(100000)

# 添加策略
cerebro.addstrategy(StopTrailStrategy, **config['params'])

# 运行回测
results = cerebro.run()
```

## 参考来源

- Backtrader官方示例：backtrader-master2/samples/stoptrail/trail.py
