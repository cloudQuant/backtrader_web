# 括号订单策略 (Bracket Order Strategy)

## 策略简介

括号订单策略是一种风险控制型交易策略，在开仓的同时设置止损和止盈订单。当移动平均线产生金叉信号时，策略会创建一组"括号订单"：

1. **主订单**：限价买入订单，价格略低于当前价格
2. **止损订单**：当价格不利时触发，限制损失
3. **止盈订单**：当价格有利时触发，锁定利润

这三个订单作为一个组执行，当主订单成交后，止损和止盈订单自动激活。

## 策略原理

### 技术指标

- **快速SMA**（默认5周期）：反应灵敏，跟随价格变化
- **慢速SMA**（默认15周期）：平滑波动，显示趋势
- **交叉信号**：快速SMA上穿慢速SMA产生买入信号

### 交易逻辑

1. **入场条件**：快速SMA上穿慢速SMA（金叉）
2. **订单结构**：
   - 主限价单：当前价 × (1 - 0.5%)
   - 止损单：主单价格 - 2%收盘价
   - 止盈单：主单价格 + 2%收盘价
3. **有效期**：主订单3天，止损/止盈订单1000天

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `p1` | 5 | 快速SMA周期 |
| `p2` | 15 | 慢速SMA周期 |
| `limit` | 0.005 | 限价订单偏移（0.5%） |
| `limdays` | 3 | 主订单有效期（天） |
| `limdays2` | 1000 | 止损/止盈有效期（天） |
| `hold` | 10 | 持仓周期 |

## 适用场景

1. **趋势跟踪**：适合有明显趋势的市场环境
2. **风险控制**：预先设定止损止盈，避免情绪化交易
3. **波段交易**：捕捉短期价格波动

## 风险提示

1. **震荡市场**：在横盘震荡中容易产生频繁交易
2. **滑点风险**：限价单可能无法成交
3. **止损风险**：市场剧烈波动时可能产生滑点
4. **参数敏感性**：SMA周期和止损止盈比例需要根据市场调整

## 使用示例

```python
import backtrader as bt
from strategy_bracket_order import BracketOrderStrategy, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎
cerebro = bt.Cerebro(stdstats=True)
cerebro.broker.setcash(100000)

# 添加策略
cerebro.addstrategy(BracketOrderStrategy, **config['params'])

# 运行回测
results = cerebro.run()
```

## 参考来源

- Backtrader官方示例：backtrader-master2/samples/bracket/bracket.py
