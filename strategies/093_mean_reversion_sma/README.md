# 均值回归SMA策略 (Mean Reversion SMA Strategy)

## 策略简介

均值回归SMA策略是一种经典的均值回归交易策略。它基于一个简单的前提：价格会围绕其均值（此处为简单移动平均线SMA）波动，当价格偏离均值过远时，倾向于回归均值。

## 策略原理

### 均值回归理论

均值回归理论认为：
- 价格上涨过快后会回调
- 价格下跌过快后会反弹
- 价格围绕价值（均线）波动

### 交易逻辑

**买入条件**:
```
价格 < SMA × (1 - dip_size)
```
当价格跌破SMA一定幅度（默认2.5%）时买入

**卖出条件**:
```
价格 >= SMA
```
当价格回归至SMA或以上时卖出

### 仓位管理

使用可用资金的一定比例（默认95%）进行交易，计算可买入股数：
```
买入股数 = floor(可用资金 × order_percentage / 当前价格)
```

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `period` | 20 | SMA周期 |
| `order_percentage` | 0.95 | 每次使用资金的百分比 |
| `dip_size` | 0.025 | 下跌阈值(2.5%) |

## 适用场景

1. **震荡市场**: 在价格围绕均值波动的市场中表现最佳
2. **股票/指数**: 适合波动较大的品种
3. **日线级别**: 适合中短线交易

## 风险提示

1. **趋势市场风险**: 强趋势中可能持续亏损
2. **抄底风险**: 价格可能持续下跌
3. **资金管理**: 需要合理控制仓位比例

## 回测结果

基于ORCL(Oracle)股票2010-2014年历史数据回测：

- **初始资金**: $100,000
- **最终资金**: $172,375.61
- **夏普比率**: 1.27
- **年化收益率**: 11.53%
- **最大回撤**: 18.97%

## 使用示例

```python
import backtrader as bt
from strategy_mean_reversion_sma import MeanReversionSmaStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(MeanReversionSmaStrategy,
                    period=20,
                    order_percentage=0.95,
                    dip_size=0.025)
```

## 参考文献

- Reference: backtrader-strategies-compendium/strategies/MeanReversion.py
