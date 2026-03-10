# MACD+EMA多合约期货策略

## 策略简介

本策略在MACD+EMA策略基础上增加了多合约支持和自动换月功能。策略使用符合国内标准的MACD指标计算方法，并支持在主力合约切换时自动换仓，确保策略在期货合约到期前顺利完成换月。

## 策略原理

### 国内标准MACD

与标准MACD计算方法略有差异：
- 快线(DIF) = EMA(收盘价, 周期1) - EMA(收盘价, 周期2)
- 信号线(DEA) = EMA(DIF, 信号周期)
- MACD柱 = (DIF - DEA) × 2

### 主力合约识别

- 使用持仓量（openinterest）判断主力合约
- 持仓量最大的合约为主力合约
- 当主力合约发生变化时触发换月操作

### 换月逻辑

1. **检测主力合约变化**：每日对比当前持仓合约与主力合约
2. **平旧仓开新仓**：在主力合约上恢复原持仓方向和数量
3. **保持策略状态**：换月不影响策略的入场/出场逻辑

### 策略参数

| 参数名 | 类型 | 默认值 | 说明 |
|-------|-----|--------|------|
| period_me1 | int | 10 | 快线EMA周期 |
| period_me2 | int | 20 | 慢线EMA周期 |
| period_dif | int | 9 | DIF的EMA周期 |

## 适用场景

1. **市场环境**：适合趋势明显的期货品种
2. **品种选择**：螺纹钢、热卷等黑色系期货
3. **时间周期**：日线级别交易
4. **换月需求**：需要长期持有头寸的策略

## 风险提示

1. **换月风险**：主力合约切换时可能存在价差损失
2. **流动性风险**：非主力合约流动性不足
3. **趋势反转**：MACD信号滞后可能错过最佳出场点
4. **杠杆风险**：期货杠杆放大收益和亏损
5. **保证金风险**：极端行情可能触发强平

## 回测示例

```python
import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent

# 加载策略
from strategies.macd_ema_true.strategy import MacdEmaTrueStrategy, RbPandasFeed

cerebro = bt.Cerebro()

# 加载多合约数据
datas = load_rb_multi_data("rb")
for name, df in datas.items():
    feed = RbPandasFeed(dataname=df)
    cerebro.adddata(feed, name=name)
    comm = ComminfoFuturesPercent(commission=0.0002, margin=0.1, mult=10)
    cerebro.broker.addcommissioninfo(comm, name=name)

cerebro.broker.setcash(50000)
cerebro.addstrategy(MacdEmaTrueStrategy)

# 运行回测
results = cerebro.run()
```

## 参考资料

1. 国内MACD指标计算标准
2. 期货合约换月原理
3. 主力合约识别方法
