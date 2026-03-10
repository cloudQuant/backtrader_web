# VIX波动率指数策略 (VIX Volatility Index Strategy)

## 策略简介

VIX波动率指数策略是一个基于市场波动率的逆向投资策略。该策略使用CBOE波动率指数（VIX）作为市场恐惧指标，在波动率极端高时买入（市场恐慌），在波动率极端低时卖出（市场自满）。

## 策略原理

### 核心思想
1. **VIX指数**: 衡量标普500指数未来30天的预期波动率
2. **恐惧指标**: VIX被称为"恐惧指标"，高值表示市场恐慌
3. **均值回归**: 波动率会向长期均值回归

### 交易逻辑
- **买入**: VIX > 35（市场极度恐慌，逆向买入）
- **卖出**: VIX < 10（市场过度平静，卖出信号）

### VIX指数解读
- < 12: 市场平静，可能自满
- 12-20: 正常波动水平
- 20-30: 市场担忧增加
- > 30: 高波动，市场恐慌
- > 40: 极端恐慌（如金融危机期间）

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| high_threshold | 35 | VIX高阈值（恐惧，买入信号） |
| low_threshold | 10 | VIX低阈值（平静，卖出信号） |

## 适用场景

- 美股市场（SPY标普500ETF）
- 市场极端波动时期
- 长期价值投资

## 风险提示

1. VIX可能长期维持高位（如2008金融危机）
2. 极端低波动率可能持续很长时间
3. 该策略交易频率非常低，需要极大耐心
4. VIX与股市呈负相关，但相关性并非绝对

## 回测结果

基于2011-2021年SPY数据的回测结果:

- bar_num: 2,445
- buy_count: 3
- sell_count: 1
- win_count: 1
- loss_count: 0
- total_trades: 2
- sharpe_ratio: 0.92
- annual_return: 10.41%
- max_drawdown: 33.68%
- final_value: 261,273.50

## 数据要求

- SPY价格数据及VIX指标: spy-put-call-fear-greed-vix.csv
- 数据列: Date, Open, High, Low, Close, Adj Close, Volume, Put Call, Fear Greed, VIX

## 作者信息

- 作者: yunjinqi
- 策略类型: VIX波动率逆向策略
- 参考: https://github.com/cloudQuant/sentiment-fear-and-greed.git
