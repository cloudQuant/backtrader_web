# Put/Call比率情绪策略 (Put/Call Ratio Sentiment Strategy)

## 策略简介

Put/Call比率情绪策略是一个基于期权市场情绪的逆向投资策略。该策略使用Put/Call比率作为市场恐惧/贪婪的衡量指标，在极端情绪时进行逆向交易。

## 策略原理

### 核心思想
1. **Put/Call比率**: 衡量看跌期权与看涨期权的交易量比值
2. **情绪指标**: 高比率表示市场恐惧，低比率表示市场贪婪
3. **逆向投资**: 在情绪极端时采取相反立场

### 交易逻辑
- **买入**: Put/Call > 1.0（市场恐惧，逆向买入）
- **卖出**: Put/Call < 0.45（市场贪婪，逆向卖出）

### Put/Call比率解读
- > 1.0: 看跌期权交易量 > 看涨期权 → 市场恐惧
- < 0.5: 看涨期权交易量 > 看跌期权 → 市场贪婪
- ≈ 0.7-0.8: 正常市场水平

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| high_threshold | 1.0 | Put/Call比率高阈值（恐惧，买入信号） |
| low_threshold | 0.45 | Put/Call比率低阈值（贪婪，卖出信号） |

## 适用场景

- 美股市场（SPY标普500ETF）
- 有期权交易的市场
- 需要情绪指标辅助的投资决策

## 风险提示

1. Put/Call比率可能长期处于极端状态
2. 逆向投资需要较强的心理承受能力
3. 该策略交易频率较低
4. 情绪指标作为辅助指标，需结合其他分析

## 回测结果

基于2011-2021年SPY数据的回测结果:

- bar_num: 2,445
- buy_count: 6
- sell_count: 3
- win_count: 3
- loss_count: 0
- total_trades: 3
- sharpe_ratio: 0.83
- annual_return: 9.45%
- max_drawdown: 24.77%
- final_value: 240,069.35

## 数据要求

- SPY价格数据及情绪指标: spy-put-call-fear-greed-vix.csv
- 数据列: Date, Open, High, Low, Close, Adj Close, Volume, Put Call, Fear Greed, VIX

## 作者信息

- 作者: yunjinqi
- 策略类型: 期权情绪逆向策略
- 参考: https://github.com/cloudQuant/sentiment-fear-and-greed.git
