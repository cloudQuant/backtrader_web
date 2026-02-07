# MACD+EMA期货趋势策略

## 策略简介

本策略结合MACD指标和EMA指标，构建了一个适用于期货交易的趋势跟踪系统。MACD金叉死叉作为入场信号，EMA作为止损过滤条件，有效过滤假突破并控制风险。

## 策略原理

### 技术指标

1. **MACD指标**：
   - DIF（快线）= EMA(收盘价, 10) - EMA(收盘价, 20)
   - DEA（信号线）= EMA(DIF, 9)
   - MACD柱 = 2 × (DIF - DEA)

2. **EMA指标**：10日指数移动平均线，作为止损过滤

### 交易规则

**平仓规则**：
- 多头持仓：当价格跌破EMA时平仓
- 空头持仓：当价格突破EMA时平仓

**开多仓**：
- DIF从负值变为正值（上穿0轴）
- 且MACD柱 > 0
- 且当前无持仓

**开空仓**：
- DIF从正值变为负值（下穿0轴）
- 且MACD柱 < 0
- 且当前无持仓

### 策略参数

| 参数名 | 类型 | 默认值 | 说明 |
|-------|-----|--------|------|
| period_me1 | int | 10 | MACD快线周期 |
| period_me2 | int | 20 | MACD慢线周期 |
| period_signal | int | 9 | MACD信号线周期 |

## 适用场景

1. **市场环境**：适合趋势明显的期货品种
2. **品种选择**：螺纹钢、铁矿石等波动性较大的商品期货
3. **时间周期**：日线级别交易
4. **交易方向**：双向交易，可做多可做空

## 风险提示

1. **趋势反转**：趋势快速反转时可能无法及时止损
2. **震荡亏损**：震荡市中MACD频繁产生假信号
3. **杠杆风险**：期货交易具有杠杆，亏损可能放大
4. **保证金追缴**：极端行情可能触发保证金追缴
5. **滑点成本**：期货交易存在滑点和手续费成本

## 回测示例

```python
import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent

# 加载策略
from strategies.macd_ema_fase.strategy import MacdEmaStrategy, RbPandasFeed

cerebro = bt.Cerebro()

# 加载数据
df = pd.read_csv('RB99.csv')
data = RbPandasFeed(dataname=df)
cerebro.adddata(data, name="RB99")

# 设置期货交易参数
comm = ComminfoFuturesPercent(commission=0.0002, margin=0.1, mult=10)
cerebro.broker.addcommissioninfo(comm, name="RB99")
cerebro.broker.setcash(50000)

# 添加策略
cerebro.addstrategy(MacdEmaStrategy, period_me1=10, period_me2=20, period_signal=9)

# 运行回测
results = cerebro.run()
```

## 参考资料

1. MACD指标原理与应用
2. EMA指数移动平均线
3. 期货交易基础知识
