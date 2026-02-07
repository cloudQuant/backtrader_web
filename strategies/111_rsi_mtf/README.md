# RSI MTF Strategy (RSI多周期策略)

## 策略简介

RSI多周期策略是一种使用不同周期RSI指标组合来识别交易机会的策略。通过结合长周期RSI（趋势过滤）和短周期RSI（动量触发），该策略旨在趋势和动量对齐时入场，在动量反转时离场。

## 策略原理

### 多时间框架概念

多时间框架（Multiple Time Frame, MTF）分析的核心思想是：
- **长周期指标**：用于判断整体趋势方向
- **短周期指标**：用于捕捉入场时机

### 入场条件
- 长周期RSI(14) > 50：表示趋势偏多
- 短周期RSI(3) > 70：表示短期动量强劲
- 两个条件同时满足时买入

### 出场条件
- 短周期RSI(3) < 35：表示短期动量丧失，可能反转

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| stake | 10 | 每次交易的股票数量 |
| period_long | 14 | 长周期RSI计算周期 |
| period_short | 3 | 短周期RSI计算周期 |
| buy_rsi_long | 50 | 长周期RSI买入阈值 |
| buy_rsi_short | 70 | 短周期RSI买入阈值 |
| sell_rsi_short | 35 | 短周期RSI卖出阈值 |

## 适用场景

- **趋势确认**：需要确认趋势方向后再入场
- **动量捕捉**：捕捉短期动量爆发机会
- **快进快出**：适合短线交易

## 风险提示

1. **假突破**：短周期RSI容易产生假信号
2. **趋势反转**：在趋势反转时可能持续亏损
3. **过度交易**：短周期指标可能导致频繁交易
4. **参数敏感**：不同市场需要调整参数组合

## 回测结果

基于Oracle (ORCL) 2010-2014年数据回测：

| 指标 | 数值 |
|------|------|
| 初始资金 | $100,000 |
| 最终资金 | $99,944.33 |
| 夏普比率 | -0.293 |
| 年化收益率 | -0.011% |
| 最大回撤 | 14.51% |
| 处理K线数 | 1243 |

## 代码结构

```
111_rsi_mtf/
├── config.yaml           # 策略配置文件
├── strategy_rsi_mtf.py   # 策略实现代码
└── README.md             # 策略说明文档
```

## 使用方法

```python
import backtrader as bt
from strategy_rsi_mtf import RsiMtfStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(RsiMtfStrategy,
                    stake=10,
                    period_long=14,
                    period_short=3,
                    buy_rsi_long=50,
                    buy_rsi_short=70,
                    sell_rsi_short=35)
# ... 添加数据和运行回测
```

## 参考来源

- backtrader-strategies-compendium/strategies/RsiMtf.py
