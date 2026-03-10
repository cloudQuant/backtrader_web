# OCO订单策略 (One Cancels Other Order Strategy)

## 策略简介

OCO（One Cancels Other，一单取消另一单）订单策略允许同时提交多个订单，当其中一个订单成交时，其他订单自动取消。这策略演示了如何使用OCO订单在多个价格水平尝试入场。

## 策略原理

### 什么是OCO订单

OCO订单是一组关联订单，具有以下特点：
- 任一订单成交，其他订单自动取消
- 确保只有一个订单会执行
- 避免过度暴露风险

### 交易逻辑

1. **入场条件**：快速SMA上穿慢速SMA（金叉）
2. **OCO订单设置**：
   - 订单1：接近当前价格（-0.5%），有效期3天
   - 订单2：较深价格（-2%），有效期1000天
   - 订单3：更深价格（-4.5%），有效期1000天
3. **执行**：任一订单成交后，其他自动取消
4. **出场**：持有固定天数后平仓

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `p1` | 5 | 快速SMA周期 |
| `p2` | 15 | 慢速SMA周期 |
| `limit` | 0.005 | 限价偏移比例（0.5%） |
| `limdays` | 3 | 主订单有效期（天） |
| `limdays2` | 1000 | 次级订单有效期（天） |
| `hold` | 10 | 持仓周期 |

## 适用场景

1. **回撤交易**：在价格回撤到不同水平时尝试入场
2. **突破交易**：设置多个入场点，避免错过机会
3. **风险管理**：自动管理多个待入场订单

## 风险提示

1. **成交不确定性**：可能没有任何订单成交
2. **价格跳跃**：价格可能直接跳过所有限价单
3. **持仓时间固定**：不考虑市场状况的固定持仓
4. **滑点风险**：实际成交价可能与限价不同

## 使用示例

```python
import backtrader as bt
from strategy_oco_order import OCOOrderStrategy, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎
cerebro = bt.Cerebro(stdstats=True)
cerebro.broker.setcash(100000)

# 添加策略
cerebro.addstrategy(OCOOrderStrategy, **config['params'])

# 运行回测
results = cerebro.run()
```

## 参考来源

- Backtrader官方示例：backtrader-master2/samples/oco/oco.py
