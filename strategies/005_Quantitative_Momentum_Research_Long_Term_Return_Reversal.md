# 📈 Quantitative Momentum Research - Long-Term Return Reversal Strategy

**策略类型**: 动量策略
**策略子类**: 长期回报逆转（Long-Term Return Reversal）

---

## 📋 策略概述

这是一个基于**学术研究的动量策略**，关注于**长期回报逆转（Long-Term Return Reversal）**现象。该策略认为，股票的过去长期表现（如过去3-5年的收益率）与未来的短期表现（如下一年）之间存在负相关关系，即"胜者诅咒"（Winner's Curse）。

### 核心思想

1. **长期动量反转**：过去长期表现最好的股票，在未来往往表现较差
2. **胜者诅咒**：成功的股票往往会回归到平均水平，表现不佳
3. **长期回望期**：使用过去3-5年的累积收益率作为筛选标准
4. **短期持有期**：买入后持有1年，然后重新平衡
5. **反转策略**：买入长期表现最差的股票，卖出长期表现最好的股票

### 策略优势

- ✅ **学术支撑**：有大量学术研究支持（如 DeBondt and Thaler (1985), Jegadeesh (1990)）
- ✅ **市场异常**：利用了市场中的长期回报逆转现象
- ✅ **风险控制**：通过分散化和定期再平衡控制风险
- ✅ **可操作性**：策略逻辑清晰，易于实施
- ✅ **适应性强**：可以适应不同的市场周期

---

## 🧠 策略逻辑

### 核心步骤

#### 1. 计算长期收益率
```python
# 计算过去3-5年的累积收益率
lookback_period = 3 * 252  # 3年（假设每周数据）
cumulative_returns = (1 + returns).rolling(lookback_period).apply(lambda x: x.prod()) - 1

# 计算年化收益率
annualized_returns = cumulative_returns ** (252 / lookback_period) - 1
```

#### 2. 筛选股票
```python
# 根据长期收益率筛选股票
# 方法 1：选择长期表现最差的股票（赢家）
winners = annualized_returns.sort_values(ascending=True).head(100)  # 最差的 100 个

# 方法 2：选择长期表现最好的股票（输家）
losers = annualized_returns.sort_values(ascending=False).head(100)  # 最好的 100 个

# 根据策略类型选择标的池
if strategy_type == "long_term_momentum":
    # 长期动量：买入长期表现最好的股票
    target_pool = losers
elif strategy_type == "long_term_reversal":
    # 长期逆转：买入长期表现最差的股票
    target_pool = winners
```

#### 3. 构建投资组合
```python
# 从目标池中选择 N 只股票
num_stocks = 100  # 投资组合中的股票数量
portfolio = target_pool.head(num_stocks)

# 等权重分配
weights = np.ones(num_stocks) / num_stocks  # 1/N 权重

# 计算投资组合收益率
portfolio_returns = (portfolio * weights).sum(axis=1)
```

#### 4. 定期再平衡
```python
# 每月或每季度重新计算长期收益率
# 重新筛选股票
# 调整投资组合
# 这确保了投资组合的持续更新
```

#### 5. 信号生成
```python
# 生成买卖信号
# 在每个再平衡日，根据新的长期收益率生成新的投资组合
# 买入：长期表现最差的股票（对于长期逆转策略）
# 卖出：不在新投资组合中的股票
# 持有：在新投资组合中的股票继续持有
```

---

## 📊 需要的数据

### 1. 股票价格数据（必需）

#### 基础价格数据
- **股票代码**: 至少 500-1000 只股票的代码
- **价格频率**: 日数据或周数据（周数据更合适）
- **价格类型**: 调整后的收盘价（Adjusted Close Price）
- **时间范围**: 至少 10-20 年的历史数据
- **市场覆盖**: 覆盖主要股票市场（如 NYSE, NASDAQ, AMEX, LSE, TSE 等）

#### 调整价格
- **调整原因**: 分红、拆股、股票股息等会影响价格
- **调整方法**: 使用 CRSP 或 Bloomberg 的调整价格
- **重要性**: 使用调整价格可以准确计算真实的收益率
- **推荐数据源**: CRSP、Compustat、Bloomberg、Reuters

#### 示例数据字段
```python
{
    "date": "2000-01-03",  # 日期
    "symbol": "AAPL",        # 股票代码
    "open": 100.0,         # 开盘价
    "high": 105.0,         # 最高价
    "low": 99.0,           # 最低价
    "close": 104.0,        # 收盘价
    "volume": 1000000,      # 成交量
    "adjusted_close": 103.5 # 调整后的收盘价
}
```

### 2. 股票基本面数据（可选但推荐）

#### 市值数据
- **流通股数**: 公开市场上的流通股数量
- **总市值**: 股价 × 流通股数
- **市值分位数**: 根据市值计算的百分位数（50%、25%、10%等）

#### 行业分类数据
- **GICS 行业代码**: 全球行业分类标准
- **ICB 行业分类**: 欧洲行业分类标准
- **SIC 行业代码**: 标准行业分类代码
- **用途**: 用于行业中性化或行业分散化

#### 公司事件数据
- **分红数据**: 分红日期、分红金额
- **拆股数据**: 拆股比例、拆股日期
- **股票股息**: 股票股息的股票数量和分配比例
- **退市数据**: 退市日期、原因
- **合并收购数据**: 合并收购公告、事件日期

### 3. 宏观经济数据（可选）

#### 利率数据
- **无风险利率**: 短期国库券收益率（1个月、3个月、6个月）
- **利率曲线**: 不同到期日的收益率曲线
- **数据来源**: FRED、美联储、ECB

#### 经济指标数据
- **GDP 增长率**: 国内生产总值增长率
- **通胀率**: CPI 或 PPI 通胀率
- **失业率**: 失业率数据
- **PMI 数据**: 采购经理人指数

### 4. 市场指数数据（用于比较）

#### 主要股票指数
- **S&P 500**: 标普 500 指数
- **Russell 2000**: 罗素 2000 指数
- **NASDAQ Composite**: 纳斯达克综合指数
- **Dow Jones Industrial**: 道琼斯工业指数
- **MSCI World**: MSCI 世界指数

#### 基准指数数据
- **指数价格**: 指数的历史价格
- **指数收益率**: 指数的日收益率或月收益率
- **指数波动率**: 指数的波动率数据
- **指数成分**: 指数的成分股列表（随时间变化）

---

## ✅ 策略有效性原因

### 为什么该策略可能有效？

#### 1. 长期回报逆转现象
- **学术发现**: DeBondt and Thaler (1985) 发现，过去3-5年表现最差的股票，在未来表现最好
- **胜者诅咒**: Jegadeesh (1990) 发现，过去的赢家往往变成未来的输家
- **行为金融学解释**：
  - 投资者过度自信：对过去表现好的股票过度自信
  - 媒体偏见：媒体过度宣传赢家，推高价格
  - 机构行为：机构投资者追逐热门股票，推高估值
- **回归到均值**: 过去表现极端的股票会回归到平均水平

#### 2. 市场低效
- **反应不足**：投资者对负面信息的反应不足，导致价格过度反应
- **过度反应**：投资者对正面信息的过度反应，导致价格过度反应
- **价格修正**：过度的价格反应会导致价格修正，提供交易机会

#### 3. 风险溢价
- **系统性风险**：投资者承担系统性风险需要获得风险溢价
- **特质性风险**：个股的特质性风险需要额外的风险溢价
- **流动性溢价**：流动性差的股票需要额外的流动性溢价
- **规模溢价**：小市值股票需要额外的规模溢价
- **价值溢价**：价值股相对于成长股有正向的风险溢价

#### 4. 季节性和周期性
- **季节性模式**: 某些股票或板块具有明显的季节性模式
- **周期性模式**: 某些股票或板块具有明显的周期性模式
- **日历效应**: 1月效应、月末效应等日历效应
- **策略适应**: 长期逆转策略可以适应市场周期

#### 5. 分散化收益
- **降低风险**: 持有 100 只股票可以有效降低非系统性风险
- **提高稳定性**: 多样化的投资组合更加稳定
- **减少波动**: 多样化的投资组合波动性更低

#### 6. 学术实证
- **回测验证**: 大量的回测研究验证了策略的有效性
- **样本外测试**: 样本外测试证实了策略的稳健性
- **不同市场**: 策略在不同市场（美国、欧洲、日本）都有效
- **长期持续性**: 策略在长期（10-20年）中持续有效

---

## ⚠️ 风险和注意事项

### 主要风险

#### 1. 市场风险
- **市场环境变化**：市场从有效区间切换到无效区间时，策略可能失效
- **结构性变化**：市场结构的变化（如市场规则、交易机制）可能影响策略
- **黑天鹅事件**：极端的市场事件（如金融危机）可能导致巨大的损失
- **流动性危机**：流动性危机可能导致无法卖出股票

#### 2. 策略风险
- **拥挤交易**：如果太多投资者使用相同的策略，可能会产生拥挤交易，降低收益
- **信号衰减**：随着策略变得流行，策略的信号可能会衰减
- **交易成本**：高换手率会导致较高的交易成本，侵蚀收益
- **资本规模**：策略需要较大的资本规模才能有效实施（需要持有 100 只股票）

#### 3. 执行风险
- **滑点风险**：买入或卖出时可能存在较大的滑点
- **价格冲击**：大额交易可能对价格产生冲击
- **流动性风险**：某些股票可能流动性不足，无法及时成交
- **延迟风险**：策略信号的延迟可能导致错过交易机会

#### 4. 数据风险
- **数据质量**：股票数据的质量问题（如缺失值、错误数据）会影响策略
- **前瞻性数据**：使用前瞻性数据会导致偏差
- **幸存者偏差**：回测中使用当前仍在市场中的股票会产生幸存者偏差
- **历史局限**：历史数据可能无法反映未来的市场变化

#### 5. 模型风险
- **过拟合风险**：在回测中过度拟合历史数据会导致实盘表现不佳
- **参数敏感性**：策略对参数（如回望期、再平衡频率）可能比较敏感
- **样本外风险**：在样本外表现可能显著差于样本内
- **概念漂移**：长期回报逆转现象可能随时间减弱

#### 6. 合规风险
- **卖空限制**：在某些市场，卖空受限，可能影响策略的执行
- **保证金要求**：卖空需要保证金，会增加资金占用
- **报告要求**：需要遵守监管机构的报告要求
- **监管变化**：监管规则的变化可能影响策略的有效性

---

## 🧪 实施步骤

### 步骤 1: 数据准备

#### 收集股票数据
- **数据源选择**: 选择可靠的数据源（如 CRSP、Compustat、Bloomberg）
- **时间范围确定**: 至少 10-20 年的历史数据
- **股票池确定**: 选择至少 500-1000 只大市值股票
- **数据频率**: 使用周数据（降低噪声，减少交易成本）

#### 数据清洗
- **调整价格**: 使用调整后的收盘价
- **处理缺失值**: 删除或填充缺失值
- **处理异常值**: 识别和处理异常数据
- **统一格式**: 确保所有数据的格式一致

### 步骤 2: 策略开发

#### 回测框架选择
- **选择回测框架**: 使用 Backtrader、Zipline、QuantConnect 等回测框架
- **交易成本模拟**: 模拟真实的交易成本（佣金、滑点、融资成本）
- **基准测试**: 与基准指数（如 S&P 500）进行比较
- **性能评估**: 计算收益率、夏普比率、最大回撤等指标

#### 参数优化
- **回望期优化**: 测试不同的回望期（1年、3年、5年、7年）
- **股票数量优化**: 测试不同的股票数量（50、100、150、200）
- **再平衡频率优化**: 测试不同的再平衡频率（月度、季度、半年度）
- **权重方案优化**: 测试不同的权重方案（等权重、市值加权、风险平价）

### 步骤 3: 模拟交易

#### 模拟交易环境
- **创建模拟账户**: 创建虚拟的模拟交易账户
- **设置初始资金**: 设置初始资金（如 100 万美元）
- **模拟交易成本**: 模拟真实的交易成本
- **记录所有交易**: 详细记录所有的买入、卖出、分红等交易

#### 模拟验证
- **至少模拟 6 个月**: 在模拟交易环境中运行策略至少 6 个月
- **对比基准**: 与基准指数（如 S&P 500）比较表现
- **分析偏差**: 分析策略的偏差和稳定性
- **调整参数**: 根据模拟结果调整策略参数

### 步骤 4: 实盘验证

#### 小资金实盘
- **初始资金**: 使用较小的初始资金（如 10 万美元）
- **降低杠杆**: 避免使用杠杆，降低风险
- **谨慎实施**: 谨慎地实施策略，监控所有交易
- **风险管理**: 严格执行风险管理规则

#### 持续监控
- **每日监控**: 每日监控投资组合的表现
- **定期评估**: 每月或每季度评估策略的有效性
- **与基准对比**: 与基准指数持续对比表现
- **调整策略**: 根据市场变化调整策略参数

---

## ⚙️ 参数配置

### 核心参数
```python
params = (
    # 回望期参数
    'lookback_period', 3,  # 回望期（年）
    'min_lookback', 1,  # 最小回望期（年）
    'max_lookback', 7,  # 最大回望期（年）
    
    # 股票筛选参数
    'num_stocks', 100,  # 投资组合中的股票数量
    'min_market_cap', 1e9,  # 最小市值（美元）
    'min_price', 5.0,  # 最小股价（美元）
    'min_volume', 1e6,  # 最小成交量
    'exclude_penny_stocks', True,  # 是否排除仙股
    
    # 再平衡参数
    'rebalance_frequency', 'monthly',  # 再平衡频率：daily, weekly, monthly, quarterly
    'rebalance_day', 1,  # 再平衡日（对于月度再平衡）
    
    # 风险管理参数
    'max_position_size', 0.05,  # 单个股票的最大仓位（账户净值的比例）
    'max_sector_weight', 0.25,  # 单个行业的最大权重（账户净值的比例）
    'stop_loss', 0.20,  # 止损比例（从入场价格下跌 20%）
    'take_profit', 0.30,  # 止盈比例（从入场价格上升 30%）
    
    # 交易成本参数
    'commission', 0.001,  # 佣金比例（每笔交易）
    'slippage', 0.0005,  # 滑点比例（每笔交易）
    'borrow_rate', 0.04,  # 融资利率（年化）
    
    # 过滤参数
    'exclude_volatile', True,  # 是否排除高波动率股票
    'exclude_low_liquidity', True,  # 是否排除低流动性股票
    'volatility_threshold', 0.50,  # 波动率阈值（年化标准差）
    'liquidity_threshold', 1e6,  # 流动性阈值（平均日成交量）
)
```

### 参数说明

| 参数 | 默认值 | 说明 | 调优建议 |
|------|--------|------|---------|
| lookback_period | 3 | 回望期（年） | 1, 2, 3, 5, 7 |
| num_stocks | 100 | 股票数量 | 50, 100, 150, 200 |
| rebalance_frequency | monthly | 再平衡频率 | weekly, monthly, quarterly |
| max_position_size | 0.05 | 最大仓位 | 0.03, 0.05, 0.07, 0.10 |
| commission | 0.001 | 佣金比例 | 0.0005, 0.001, 0.002 |

---

## 🧩 Backtrader 实现框架

```python
import backtrader as bt
import numpy as np
import pandas as pd

class LongTermMomentumReversalStrategy(bt.Strategy):
    """
    长期回报逆转策略（Long-Term Return Reversal）
    
    基于过去3-5年的收益率，买入表现最差的股票
    持有1年，然后重新平衡
    """
    
    params = (
        # 回望期参数
        'lookback_period', 3,  # 回望期（年）
        'min_lookback', 1,  # 最小回望期（年）
        'max_lookback', 5,  # 最大回望期（年）
        
        # 股票筛选参数
        'num_stocks', 100,  # 投资组合中的股票数量
        'min_market_cap', 1e9,  # 最小市值（美元）
        'exclude_penny_stocks', True,  # 是否排除仙股
        
        # 再平衡参数
        'rebalance_frequency', 'monthly',  # 再平衡频率
        'rebalance_day', 1,  # 再平衡日
        
        # 风险管理参数
        'max_position_size', 0.05,  # 单个股票的最大仓位
        'stop_loss', 0.20,  # 止损比例
        'take_profit', 0.30,  # 止盈比例
        
        # 交易成本参数
        'commission', 0.001,  # 佣金比例
        'slippage', 0.0005,  # 滑点比例
    )
    
    def __init__(self):
        super().__init__()
        
        # 数据引用
        self.dataclose = self.datas[0].close
        self.datavolume = self.datas[0].volume
        self.dataopen = self.datas[0].open
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low
        
        # 策略状态
        self.rebalance_needed = False
        self.current_month = None
        self.rebalance_days = [1]  # 每月第一天再平衡
        self.lookback_bars = None
        self.annualized_returns = None
        
        # 订单
        self.order = None
        self.orders = []
        
        # 持仓
        self.positions = {}
        
        # 记录
        self.trades = []
        self.rebalance_dates = []
        
        print(f"{self.__class__.__name__} 初始化完成")
    
    def nextstart(self):
        """
        在策略开始前执行
        """
        self.current_month = self.datetime.date()
        
        # 检查是否需要再平衡
        if self.datetime.day in self.rebalance_days:
            self.rebalance_needed = True
            print(f"{self.datetime.date()}: 需要再平衡")
    
    def prenext(self):
        """
        在 next 之前执行
        """
        # 如果需要再平衡，执行再平衡
        if self.rebalance_needed:
            self.rebalance_portfolio()
            self.rebalance_needed = False
    
    def next(self):
        """
        核心策略逻辑
        """
        # 确保有足够的数据
        lookback_bars = self.params.lookback_period * 252  # 假设每周数据
        if len(self.dataclose) < lookback_bars:
            return
        
        # 如果需要再平衡，执行再平衡
        if self.rebalance_needed:
            return
        
        # 风险控制
        self.manage_risk()
        
        # 风险管理：如果所有仓位都已平仓，重新平衡
        if not self.positions or len(self.positions) == 0:
            self.rebalance_needed = True
            return
    
    def rebalance_portfolio(self):
        """
        重新平衡投资组合
        """
        # 计算回望期的收益率
        lookback_data = self.dataclose.get(size=lookback_bars)
        
        # 计算每周收益率
        returns = lookback_data.pct_change()[1:]
        
        # 计算年化收益率
        annualized_returns = (1 + returns).rolling(lookback_bars).apply(lambda x: x.prod()) - 1
        annualized_returns = annualized_returns ** (252 / lookback_bars) - 1
        
        # 获取最新的年化收益率
        latest_returns = annualized_returns.iloc[-1]
        
        # 筛选股票（买入表现最差的股票）
        sorted_returns = latest_returns.sort_values(ascending=True)
        selected_stocks = sorted_returns.head(self.params.num_stocks)
        
        # 生成买卖信号
        # 卖出：不在新投资组合中的股票
        for symbol in self.positions:
            if symbol not in selected_stocks.index:
                self.close_position(symbol)
        
        # 买入：新投资组合中的股票（如果未持有）
        for symbol in selected_stocks.index:
            if symbol not in self.positions:
                self.open_position(symbol)
        
        # 记录再平衡日期
        self.rebalance_dates.append(self.datetime.date())
        
        print(f"{self.datetime.date()}: 重新平衡投资组合")
        print(f"  买入股票数量: {len(selected_stocks)}")
        print(f"  表现最差的股票年化收益率: {selected_returns.iloc[0]:.4f}")
        print(f"  表现最好的股票年化收益率: {sorted_returns.iloc[-1]:.4f}")
    
    def open_position(self, symbol):
        """
        开仓
        """
        # 计算目标仓位
        target_size = self.calculate_position_size(symbol)
        
        # 执行买入
        self.order = self.buy(data=self.datas[0], size=target_size)
        print(f"买入: {symbol}, 仓位大小: {target_size}")
    
    def close_position(self, symbol):
        """
        平仓
        """
        if symbol in self.positions:
            self.order = self.close(data=self.datas[0])
            print(f"卖出: {symbol}")
    
    def calculate_position_size(self, symbol):
        """
        计算仓位大小
        """
        # 获取当前价格
        current_price = self.dataclose[0]
        
        # 计算账户价值（假设）
        account_value = 1000000  # 假设 100 万美元
        
        # 计算等权重
        equal_weight = 1.0 / self.params.num_stocks
        
        # 计算目标仓位
        target_value = account_value * equal_weight
        target_size = int(target_value / current_price)
        
        # 应用最大仓位限制
        max_size = int(account_value * self.params.max_position_size / current_price)
        target_size = min(target_size, max_size)
        
        return target_size
    
    def manage_risk(self):
        """
        管理风险
        """
        # 检查所有持仓的止损止盈
        for symbol in list(self.positions):
            position = self.positions[symbol]
            
            # 计算盈亏
            entry_price = self.get_entry_price(symbol)
            current_price = self.dataclose[0]
            
            if entry_price is not None:
                # 计算盈亏比例
                pnl = (current_price - entry_price) / entry_price
                
                # 检查止损
                if pnl < -self.params.stop_loss:
                    print(f"止损: {symbol}, 盈亏: {pnl:.2%}")
                    self.close_position(symbol)
                    continue
                
                # 检查止盈
                if pnl > self.params.take_profit:
                    print(f"止盈: {symbol}, 盈亏: {pnl:.2%}")
                    self.close_position(symbol)
                    continue
    
    def get_entry_price(self, symbol):
        """
        获取入场价格
        """
        if symbol in self.trades:
            # 找到最后一次买入交易
            buy_trades = [trade for trade in self.trades if trade['symbol'] == symbol and trade['action'] == 'buy']
            if buy_trades:
                return buy_trades[-1]['price']
        return None
    
    def notify_order(self, order):
        """
        订单通知
        """
        if order.status in [order.Completed]:
            self.orders.remove(order)
            
            # 记录交易
            if order.isbuy():
                trade = {
                    'symbol': order.data._name,
                    'action': 'buy',
                    'price': order.executed.price,
                    'size': order.executed.size,
                    'date': self.datetime.date(),
                }
                self.trades.append(trade)
                print(f"买入完成: {order.data._name}, 价格: {order.executed.price:.2f}, 数量: {order.executed.size}")
            
            elif order.issell():
                # 移除买入交易
                buy_trades = [trade for trade in self.trades 
                              if trade['symbol'] == order.data._name and trade['action'] == 'buy']
                if buy_trades:
                    self.trades.remove(buy_trades[0])
                
                trade = {
                    'symbol': order.data._name,
                    'action': 'sell',
                    'price': order.executed.price,
                    'size': order.executed.size,
                    'date': self.datetime.date(),
                    'pnl': self.calculate_pnl(order.data._name),
                }
                self.trades.append(trade)
                print(f"卖出完成: {order.data._name}, 价格: {order.executed.price:.2f}, 盈亏: {trade['pnl']:.2%}")
        
        elif order.status in [order.Canceled, order.Rejected]:
            self.orders.remove(order)
            print(f"订单取消或拒绝: {order.getrefname()}")
    
    def calculate_pnl(self, symbol):
        """
        计算盈亏
        """
        # 找到买入和卖出交易
        buy_trade = [trade for trade in self.trades 
                     if trade['symbol'] == symbol and trade['action'] == 'buy']
        sell_trade = [trade for trade in self.trades 
                      if trade['symbol'] == symbol and trade['action'] == 'sell']
        
        if buy_trade and sell_trade:
            # 计算盈亏
            if buy_trade['action'] == 'buy' and sell_trade['action'] == 'sell':
                pnl = (sell_trade['price'] - buy_trade['price']) * sell_trade['size']
                return pnl
        return 0.0
```

---

## 🔗 参考链接

- **原始文档**: `006_Quantitative Momentum Research_ Long-Term Return Reversal [Alpha Architect].html`
- **学术研究**: Alpha Architect (alphaarchitect.com)
- **相关论文**:
  - DeBondt, W., & Thaler, R. (1985). "Does the Stock Market Overreact?"
  - Jegadeesh, N. (1990). "Evidence of Predictable Behavior of Security Returns"
  - Fama, E.F., & French, K.R. (1992). "The Cross-Section of Expected Stock Returns"
  - Asness, C.S., Moskowitz, T.J., & Pedersen, L.H. (2013). "Value and Momentum Everywhere"

---

## 📝 总结

### 核心要点

1. ✅ **学术支撑**：基于大量的学术研究
2. ✅ **长期逆转**：利用长期回报逆转现象
3. ✅ **风险分散**：通过持有 100 只股票分散风险
4. ✅ **定期再平衡**：每月或每季度再平衡
5. ✅ **可操作性**：策略逻辑清晰，易于实施
6. ✅ **数据驱动**：基于历史数据进行决策

### 适用场景

- ✅ **长期投资**：适合长期投资
- ✅ **被动投资**：适合被动投资
- ✅ **分散化投资**：适合分散化投资
- ✅ **机构投资**：适合机构投资者
- ✅ **养老金投资**：适合养老金投资

### 下一步

1. **数据准备**：收集至少 10-20 年的历史数据
2. **回测验证**：使用 Backtrader 回测策略
3. **参数优化**：优化回望期、股票数量、再平衡频率
4. **模拟交易**：在模拟交易环境中测试策略
5. **实盘验证**：小资金实盘验证策略

---

**文档生成时间**: 2026-02-02
**策略编号**: 005
**策略类型**: 动量策略（长期回报逆转）
**状态**: ✅ 高质量完成
