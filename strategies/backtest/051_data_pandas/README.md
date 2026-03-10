# Pandas数据加载策略

## 策略简介

本策略演示如何使用Pandas DataFrame作为数据源加载到Backtrader框架中。双移动平均线交叉策略作为测试案例。

## 策略原理

### Pandas数据加载

**Backtrader支持从Pandas DataFrame加载数据：**

```python
import pandas as pd
import backtrader as bt

# 读取CSV到DataFrame
dataframe = pd.read_csv('data.csv', index_col=0, parse_dates=True)

# 创建数据源
data = bt.feeds.PandasData(dataname=dataframe)
```

**DataFrame格式要求：**
- 必须包含日期索引（DatetimeIndex）
- 需要包含OHLCV列：open, high, low, close, volume
- 列名不区分大小写（设置nocase=True）

### 交易逻辑

1. **买入信号**：快速SMA（周期10）上穿慢速SMA（周期30）
2. **卖出信号**：快速SMA下穿慢速SMA
3. **持仓管理**：始终保持单边持仓（多头或现金）

## 策略参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| fast_period | 快速移动平均线周期 | 10 |
| slow_period | 慢速移动平均线周期 | 30 |

## 适用场景

- 数据已存储在Pandas DataFrame中
- 需要对数据进行预处理后再回测
- 从数据库或其他数据源加载的数据

## 风险提示

1. 确保DataFrame索引为DatetimeIndex
2. 检查数据列名是否正确
3. 注意数据的时间顺序和频率
4. 缺失值处理需要预先完成

## 使用示例

### 从CSV加载数据

```python
import pandas as pd
import backtrader as bt
from strategy_data_pandas import SimpleMAStrategy, load_config, load_data_from_pandas

# 加载配置
config = load_config()
params = config['params']

# 读取CSV到DataFrame
dataframe = pd.read_csv(
    'data.csv',
    header=0,
    parse_dates=True,
    index_col=0,
)

# 创建Cerebro引擎
cerebro = bt.Cerebro()
cerebro.broker.setcash(100000)

# 加载数据
data = load_data_from_pandas(dataframe, nocase=True)
cerebro.adddata(data)

# 添加策略
cerebro.addstrategy(SimpleMAStrategy, **params)

# 运行回测
results = cerebro.run()
```

### 从数据库加载数据

```python
import pandas as pd
import backtrader as bt
from strategy_data_pandas import SimpleMAStrategy, load_data_from_pandas

# 从SQL数据库读取
import sqlite3
conn = sqlite3.connect('database.db')
query = "SELECT date, open, high, low, close, volume FROM prices"
dataframe = pd.read_sql(query, conn, index_col='date', parse_dates=['date'])

# 创建数据源
data = load_data_from_pandas(dataframe)

# 添加到Cerebro
cerebro = bt.Cerebro()
cerebro.adddata(data)
# ...
```

### 自定义DataFrame

```python
import pandas as pd
import backtrader as bt

# 手动创建DataFrame
data = {
    'open': [100, 101, 102, 103, 104],
    'high': [102, 103, 104, 105, 106],
    'low': [99, 100, 101, 102, 103],
    'close': [101, 102, 103, 104, 105],
    'volume': [1000, 1100, 1200, 1300, 1400],
}
index = pd.date_range('2023-01-01', periods=5, freq='D')
dataframe = pd.DataFrame(data, index=index)

# 加载到Backtrader
data = bt.feeds.PandasData(dataname=dataframe)
```

## PandasData参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| dataname | DataFrame对象 | 必填 |
| nocase | 列名不区分大小写 | False |
| datetime | 日期列名 | None |
| open | 开盘价列名 | 'open' |
| high | 最高价列名 | 'high' |
| low | 最低价列名 | 'low' |
| close | 收盘价列名 | 'close' |
| volume | 成交量列名 | 'volume' |
| openinterest | 持仓量列名 | None |

## 数据预处理建议

```python
import pandas as pd

# 读取数据
df = pd.read_csv('data.csv', parse_dates=['date'], index_col='date')

# 检查缺失值
print(df.isnull().sum())

# 删除缺失值
df = df.dropna()

# 或填充缺失值
df = df.fillna(method='ffill')

# 排序
df = df.sort_index()

# 确保列名正确
df.columns = df.columns.str.lower()

# 检查数据类型
print(df.dtypes)
```

## 参考

- 原始来源：backtrader-master2/samples/data-pandas/data-pandas.py
