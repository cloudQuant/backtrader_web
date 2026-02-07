# 抄底策略 (Buy The F* Dip Strategy)

## 策略简介

BTFD（Buy The F* Dip）即"逢低买入"策略，是一个利用短期价格下跌机会进行交易的逆向投资策略。当日内价格下跌超过预设阈值时买入，持有固定天数后卖出。

## 策略原理

### 价格下跌计算方式

策略支持4种不同的价格下跌计算方式：

| 方式 | 计算公式 | 说明 |
|------|----------|------|
| `closeclose` | (今日收盘 - 昨日收盘) / 昨日收盘 | 日间下跌 |
| `openclose` | (今日收盘 - 今日开盘) / 今日开盘 | 日内从开盘到收盘 |
| `highclose` | (今日收盘 - 今日最高) / 今日最高 | 从最高点到收盘 |
| `highlow` | (今日最低 - 今日最高) / 今日最高 | 日内振幅 |

### 交易逻辑

1. **买入条件**：当日价格下跌幅度 >= 设定阈值（默认-1%）
2. **卖出条件**：持仓达到设定天数后无条件卖出
3. **仓位管理**：使用目标百分比分配仓位

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `fall` | -0.01 | 价格下跌阈值（-1%） |
| `hold` | 2 | 持有天数 |
| `approach` | "highlow" | 价格下跌计算方式 |
| `target` | 1.0 | 目标仓位比例（100%） |

## 适用场景

1. **均值回归市场**：价格下跌后倾向于反弹的市场
2. **波动市场**：有一定日内波动但总体稳定
3. **短期交易**：适合日内或短线交易

## 风险提示

1. **持续下跌**：在持续下跌趋势中容易"抄底在山腰"
2. **固定持仓期**：不考虑市场情况的固定持仓可能不灵活
3. **频繁交易**：在波动大的市场可能产生过多交易
4. **滑点影响**：实际交易中可能难以获得理想价格

## 使用示例

```python
import backtrader as bt
from strategy_btfd import BTFDStrategy, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎
cerebro = bt.Cerebro(stdstats=True)
cerebro.broker.setcash(100000)
cerebro.broker.set_coc(True)  # 收盘时下单

# 添加策略
cerebro.addstrategy(BTFDStrategy, **config['params'])

# 运行回测
results = cerebro.run()
```

## 参考来源

- Backtrader官方示例：backtrader-master2/samples/btfd/btfd.py
