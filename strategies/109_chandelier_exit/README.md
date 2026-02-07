# Chandelier Exit Strategy (吊灯止损策略)

## 策略简介

吊灯止损策略是一种结合移动平均线交叉和吊灯止损指标的趋势跟踪策略。该策略利用移动平均线判断趋势方向，使用吊灯止损指标作为动态止损位，以保护利润并跟踪趋势。

## 策略原理

### 吊灯止损指标

吊灯止损（Chandelier Exit）是一种基于波动率的动态止损指标，由Chuck LeBeau开发。其计算方法为：

- **多头止损位** = 最高价 - ATR × 倍数
- **空头止损位** = 最低价 + ATR × 倍数

其中ATR（Average True Range）用于衡量市场波动率。

### 入场条件
- 快速移动平均线(SMA8) > 慢速移动平均线(SMA15)
- 收盘价 > 吊灯止损空头位

### 出场条件
- 快速移动平均线(SMA8) < 慢速移动平均线(SMA15)
- 收盘价 < 吊灯止损多头位

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| stake | 10 | 每次交易的股票数量 |
| sma_fast | 8 | 快速移动平均线周期 |
| sma_slow | 15 | 慢速移动平均线周期 |
| ce_period | 22 | 吊灯止损计算周期 |
| ce_mult | 3 | ATR倍数 |

## 适用场景

- **趋势市场**：在明显的趋势行情中表现较好
- **波动率适中**：ATR能正确反映市场波动
- **中长线交易**：适合中长期持仓策略

## 风险提示

1. **震荡市亏损**：在横盘震荡市场中容易产生频繁交易
2. **滞后性**：移动平均线具有滞后性，可能错过最佳买卖点
3. **参数敏感**：策略表现对参数设置较为敏感
4. **止损风险**：止损位可能被假突破触发

## 回测结果

基于Oracle (ORCL) 2010-2014年数据回测：

| 指标 | 数值 |
|------|------|
| 初始资金 | $100,000 |
| 最终资金 | $100,018.36 |
| 夏普比率 | 0.143 |
| 年化收益率 | 0.0037% |
| 最大回撤 | 8.41% |
| 处理K线数 | 1235 |

## 代码结构

```
109_chandelier_exit/
├── config.yaml                # 策略配置文件
├── strategy_chandelier_exit.py # 策略实现代码
└── README.md                  # 策略说明文档
```

## 使用方法

```python
import backtrader as bt
from strategy_chandelier_exit import ChandelierExitStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(ChandelierExitStrategy,
                    stake=10,
                    sma_fast=8,
                    sma_slow=15,
                    ce_period=22,
                    ce_mult=3)
# ... 添加数据和运行回测
```

## 参考来源

- backtrader-strategies-compendium/strategies/MA_Chandelier.py
- Chuck LeBeau的吊灯止损技术
