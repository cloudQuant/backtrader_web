# Writer输出测试策略

## 策略简介

本策略演示Backtrader中Writer功能的使用。Writer用于将回测结果输出到控制台或文件，便于分析和记录。

## 策略原理

### Writer功能

**Writer是Backtrader的输出工具，可以：**
- 将回测结果输出到控制台
- 保存为CSV文件
- 自定义输出格式和精度

**输出内容包括：**
- 交易日历
- 数据源信息
- 执行的交易记录
- 分析器结果
- 性能指标

### 交易逻辑

1. **买入信号**：价格上穿SMA（周期15）
2. **卖出信号**：价格下穿SMA
3. **持仓管理**：始终保持单边持仓（多头或现金）

## 策略参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| period | SMA周期 | 15 |

## Writer配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| output | 输出方式（console/csv/file） | console |
| csv | 是否输出CSV | false |
| rounding | 小数位数 | 4 |

## 适用场景

- 策略结果记录和存档
- 回测结果分析
- 策略对比报告
- 自动化报告生成

## 风险提示

1. 输出文件可能较大，注意存储空间
2. CSV输出会影响性能
3. 输出信息可能包含敏感数据
4. 建议定期清理输出文件

## 使用示例

### 输出到控制台

```python
import backtrader as bt
from strategy_writer import WriterTestStrategy, load_config, setup_writer

# 加载配置
config = load_config()
params = config['params']

# 创建Cerebro引擎
cerebro = bt.Cerebro()
cerebro.broker.setcash(100000)

# 添加数据
data = bt.feeds.BacktraderCSVData(dataname='data.csv')
cerebro.adddata(data)

# 添加策略
cerebro.addstrategy(WriterTestStrategy, **params)
cerebro.addsizer(bt.sizers.FixedSize, stake=10)

# 添加Writer（仅控制台输出）
cerebro.addwriter(bt.WriterFile, csv=False, rounding=4)

# 运行回测
results = cerebro.run()
```

### 输出到CSV文件

```python
# 输出到CSV文件
cerebro.addwriter(bt.WriterFile, csv=True, rounding=4,
                  out='backtest_results.csv')
```

### 自定义输出格式

```python
# 自定义输出
cerebro.addwriter(bt.WriterFile,
                  csv=True,
                  rounding=2,
                  out='results.csv')
```

### 多种Writer组合

```python
# 可以添加多个Writer
# 控制台输出
cerebro.addwriter(bt.WriterFile, csv=False)

# 同时保存到文件
cerebro.addwriter(bt.WriterFile, csv=True, out='results.csv')
```

## Writer输出内容

### 默认输出字段

```csv
datetime,data0,data0_open,data0_high,data0_low,data0_close,data0_volume,...
2005-01-03,....,....,....,....,....,....
```

### 包含Observer时的输出

```csv
datetime,data0,drawdown,sharperatio,...
2005-01-03,....,....,....
```

## 自定义Writer

### 创建自定义Writer

```python
class CustomWriter(bt.Writer):
    """自定义Writer类"""

    params = (
        ('filename', 'custom_output.csv'),
        ('sep', ','),
    )

    def start(self):
        """开始写入时调用"""
        self.file = open(self.p.filename, 'w')
        self.file.write('Date,Price,Position,Value\n')

    def next(self):
        """每个bar调用"""
        if self.strategy.position:
            pos = self.strategy.position.size
        else:
            pos = 0

        date = self.strategy.datetime.date(0)
        price = self.strategy.data.close[0]
        value = self.strategy.broker.getvalue()

        self.file.write(f'{date},{price},{pos},{value}\n')

    def stop(self):
        """结束时调用"""
        self.file.close()

# 使用自定义Writer
cerebro.addwriter(CustomWriter, filename='my_results.csv')
```

## 输出结果分析

### 解析CSV输出

```python
import pandas as pd

# 读取Writer输出的CSV
df = pd.read_csv('backtest_results.csv', parse_dates=['datetime'])

# 分析结果
print(f"总交易天数: {len(df)}")
print(f"最终价值: {df['value'].iloc[-1]}")
print(f"最大价值: {df['value'].max()}")
print(f"最小价值: {df['value'].min()}")

# 绘制资金曲线
import matplotlib.pyplot as plt
plt.figure(figsize=(12, 6))
plt.plot(df['datetime'], df['value'])
plt.title('Portfolio Value Over Time')
plt.xlabel('Date')
plt.ylabel('Value')
plt.grid(True)
plt.show()
```

## 输出最佳实践

### 结构化输出

```python
import json

def save_results(cerebro, results, filename='results.json'):
    """保存回测结果为JSON格式"""

    # 提取关键指标
    strat = results[0]
    broker_value = cerebro.broker.getvalue()

    output = {
        'initial_cash': 100000,
        'final_value': broker_value,
        'return': (broker_value - 100000) / 100000,
        'bars': strat.bar_num if hasattr(strat, 'bar_num') else None,
        'buy_count': strat.buy_count if hasattr(strat, 'buy_count') else None,
        'sell_count': strat.sell_count if hasattr(strat, 'sell_count') else None,
    }

    # 添加分析器结果
    if hasattr(strat, 'analyzers'):
        if hasattr(strat.analyzers, 'sharpe'):
            sharpe = strat.analyzers.sharpe.get_analysis()
            output['sharpe_ratio'] = sharpe.get('sharperatio')

    # 保存为JSON
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    return output

# 使用
results = cerebro.run()
save_results(cerebro, results, 'strategy_results.json')
```

## 参考

- 原始来源：backtrader-master2/samples/writer-test/
