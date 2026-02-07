# MACD + RSI + Bollinger Bands Strategy (多指标策略)

## 策略简介

MACD+RSI+布林带多指标策略是一种结合多个技术指标的均值回归策略。该策略通过布林带识别价格极端位置，结合RSI指标确认超买超卖状态，在价格从布林带下轨反弹且RSI超卖时买入，在价格触及上轨且RSI超买时卖出。

## 策略原理

### 技术指标

1. **布林带 (Bollinger Bands)**
   - 中轨：20日移动平均线
   - 上轨：中轨 + 2倍标准差
   - 下轨：中轨 - 2倍标准差

2. **相对强弱指数 (RSI)**
   - 14日周期
   - 超卖线：35
   - 超买线：65

3. **MACD**
   - 用于趋势确认（当前策略中暂未使用）

### 入场条件
- 前一日收盘价 < 布林带下轨
- 当前收盘价 > 布林带下轨（价格反弹）
- RSI < 35（确认超卖）

### 出场条件
- 当前收盘价 > 布林带上轨
- RSI > 65（确认超买）

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| stake | 10 | 每次交易的股票数量 |
| bb_period | 20 | 布林带周期 |
| bb_dev | 2.0 | 布林带标准差倍数 |
| rsi_period | 14 | RSI计算周期 |
| rsi_oversold | 35 | RSI超卖阈值（入场） |
| rsi_overbought | 65 | RSI超买阈值（出场） |

## 适用场景

- **震荡市场**：价格在区间内波动，有明显的均值回归特征
- **波动率适中**：布林带能正确反映价格波动范围
- **超跌反弹**：捕捉价格从极端位置回归均值的机会

## 风险提示

1. **趋势亏损**：在单边趋势中可能过早离场或持续亏损
2. **假突破**：价格可能短暂突破布林带后迅速回归
3. **参数敏感**：RSI和布林带参数需要针对不同品种调整
4. **交易频率**：可能产生较多小额交易

## 回测结果

基于Oracle (ORCL) 2010-2014年数据回测：

| 指标 | 数值 |
|------|------|
| 初始资金 | $100,000 |
| 最终资金 | $100,170.29 |
| 夏普比率 | 1.170 |
| 年化收益率 | 0.034% |
| 最大回撤 | 2.92% |
| 处理K线数 | 1224 |

## 代码结构

```
110_macd_rsi_bb/
├── config.yaml              # 策略配置文件
├── strategy_macd_rsi_bb.py  # 策略实现代码
└── README.md                # 策略说明文档
```

## 使用方法

```python
import backtrader as bt
from strategy_macd_rsi_bb import MacdRsiBbStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(MacdRsiBbStrategy,
                    stake=10,
                    bb_period=20,
                    bb_dev=2.0,
                    rsi_period=14,
                    rsi_oversold=35,
                    rsi_overbought=65)
# ... 添加数据和运行回测
```

## 参考来源

- backtrader_NUPL_strategy/hope/Hope_bbands.py
