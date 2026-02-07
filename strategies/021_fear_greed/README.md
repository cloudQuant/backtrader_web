# 恐惧贪婪情绪指标策略 (Fear & Greed Sentiment Strategy)

## 策略简介

恐惧贪婪情绪指标策略是一个基于市场情绪的逆向投资策略。该策略使用Fear & Greed指数衡量市场情绪，在极端恐惧时买入（市场超卖），在极端贪婪时卖出（市场超买）。

## 策略原理

### 核心思想
1. **情绪极端化**: 市场情绪极端时往往预示反转
2. **逆向投资**: 在别人恐惧时贪婪，在别人贪婪时恐惧
3. **均值回归**: 情绪指标会向中性水平回归

### 交易逻辑
- **买入**: Fear & Greed < 10（极端恐惧）
- **卖出**: Fear & Greed > 94（极端贪婪）

### Fear & Greed指数
- 0 = 极端恐惧
- 50 = 中性
- 100 = 极端贪婪

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| fear_threshold | 10 | 恐惧阈值（低于此值买入） |
| greed_threshold | 94 | 贪婪阈值（高于此值卖出） |

## 适用场景

- 美股市场（SPY标普500ETF）
- 长期投资
- 市场情绪极端波动时期

## 风险提示

1. 情绪指标可能长期处于极端状态
2. 逆向投资需要较强的风险承受能力
3. 该策略交易频率较低，需要耐心等待
4. 情绪指数滞后于市场，可能错过最佳时机

## 回测结果

基于2011-2021年SPY数据的回测结果:

- bar_num: 2,445
- buy_count: 6
- sell_count: 2
- win_count: 2
- loss_count: 0
- total_trades: 3
- sharpe_ratio: 0.89
- annual_return: 11.23%
- max_drawdown: 24.28%
- final_value: 280,859.60

## 数据要求

- SPY价格数据及情绪指标: spy-put-call-fear-greed-vix.csv
- 数据列: Date, Open, High, Low, Close, Adj Close, Volume, Put Call, Fear Greed, VIX

## 作者信息

- 作者: yunjinqi
- 策略类型: 情绪指标逆向策略
- 参考: https://github.com/cloudQuant/sentiment-fear-and-greed.git
