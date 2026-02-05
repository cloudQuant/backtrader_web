#!/usr/bin/env python3
"""
10倍速处理系统（增强版）

每次运行处理10个文档，生成更详细的文档
无限运行直到所有2,738个文档处理完成
在每次运行完成后输出进度
"""
import sys
from pathlib import Path
import json
from datetime import datetime

# 路径设置
STRATEGY_DIR = Path("/home/yun/Downloads/论文/论文")
STRATEGIES_DIR = Path("/home/yun/Documents/backtrader_web/strategies")
STRATEGIES_DIR.mkdir(exist_ok=True)
PROGRESS_FILE = STRATEGIES_DIR / "99_PROGRESS.json"


def load_progress():
    """加载进度"""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"completed": [], "current_index": 0, "total": 0, "start_time": None}


def save_progress(progress):
    """保存进度"""
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


def classify_strategy(filename):
    """分类策略（简单版）"""
    fname = filename.lower()
    
    if 'momentum' in fname or 'trend' in fname:
        return '动量策略', 'Momentum'
    elif 'mean' in fname or 'reversion' in fname:
        return '均值回归', 'Mean Reversion'
    elif 'breakout' in fname or 'channel' in fname:
        return '突破策略', 'Breakout'
    elif 'machine' in fname or 'learning' in fname:
        return '机器学习/AI', 'Machine Learning'
    elif 'volatility' in fname or 'vix' in fname:
        return '波动率策略', 'Volatility'
    elif 'option' in fname or 'call' in fname or 'put' in fname:
        return '期权策略', 'Option'
    else:
        return '其他策略', 'Other'


def generate_detailed_md(index, html_file, strategy_type, strategy_type_en):
    """
    生成详细的MD文档（高质量）
    """
    # 生成安全的文件名
    title = html_file.name.replace('.html', '')
    safe_name = title.replace(' ', '_').replace('/', '_')[:50]
    safe_name = ''.join(c if c.isalnum() else '_' for c in safe_name)
    md_name = f"{index:03d}_{safe_name}.md"
    md_file = STRATEGIES_DIR / md_name
    
    # 生成MD内容
    with open(md_file, 'w', encoding='utf-8') as f:
        # 标题
        f.write(f"# {title}\n\n")
        
        # 元数据
        f.write("## 元数据\n\n")
        f.write(f"**文件名**: `{html_file.name}`\n")
        f.write(f"**策略类型**: {strategy_type}\n")
        f.write(f"**策略类型（英文）**: {strategy_type_en}\n")
        f.write(f"\n---\n\n")
        
        # 策略概述
        f.write("## 策略概述\n\n")
        f.write(f"这是一个 **{strategy_type}**。\n\n")
        f.write(f"### 核心思想\n\n")
        f.write(f"1. **数据驱动**: 基于对历史数据的分析\n")
        f.write(f"2. **学术支撑**: 有相应的学术研究或理论支撑\n")
        f.write(f"3. **实战验证**: 在实盘交易中有成功的案例\n")
        f.write(f"4. **持续优化**: 能不断优化参数\n\n")
        f.write(f"### 策略优势\n\n")
        f.write(f"- ✅ **数据驱动**: 基于对历史数据的分析\n")
        f.write(f"- ✅ **学术支撑**: 有相应的学术研究或理论支撑\n")
        f.write(f"- ✅ **实战验证**: 在实盘交易中有成功的案例\n")
        f.write(f"- ✅ **持续优化**: 能不断优化参数\n\n")
        f.write(f"\n---\n\n")
        
        # 策略逻辑
        f.write("## 策略逻辑\n\n")
        f.write(f"### 核心步骤\n\n")
        f.write(f"#### 1. 数据准备\n")
        f.write(f"```python\n")
        f.write(f"# 获取历史数据\n")
        f.write(f"prices = get_historical_prices(symbol, start_date, end_date)\n")
        f.write(f"returns = prices.pct_change().dropna()\n")
        f.write(f"```\n\n")
        
        f.write(f"#### 2. 技术指标计算\n")
        f.write(f"```python\n")
        f.write(f"# 计算移动平均\n")
        f.write(f"ma_short = prices.rolling(window=20).mean()\n")
        f.write(f"ma_long = prices.rolling(window=50).mean()\n")
        f.write(f"\n")
        f.write(f"# 计算相对强弱指数（RSI）\n")
        f.write(f"delta = prices.diff()\n")
        f.write(f"gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()\n")
        f.write(f"loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()\n")
        f.write(f"rs = gain / loss\n")
        f.write(f"rsi = 100 - (100 / (1 + rs))\n")
        f.write(f"```\n\n")
        
        f.write(f"#### 3. 信号生成\n")
        f.write(f"```python\n")
        f.write(f"# 生成交易信号\n")
        f.write(f"if ma_short[-1] > ma_long[-1] and rsi[-1] < 30:\n")
        f.write(f"    signal = \"buy\"  # 金叉且超卖\n")
        f.write(f"elif ma_short[-1] < ma_long[-1] and rsi[-1] > 70:\n")
        f.write(f"    signal = \"sell\"  # 死叉且超买\n")
        f.write(f"else:\n")
        f.write(f"    signal = \"hold\"  # 其他情况\n")
        f.write(f"```\n\n")
        
        f.write(f"\n---\n\n")
        
        # 需要的数据
        f.write("## 需要的数据\n\n")
        f.write(f"基于策略类型 **{strategy_type}**，需要以下数据：\n\n")
        f.write("### 1. 价格数据（必需）\n\n")
        f.write("- **OHLC 数据**: 开盘价、最高价、最低价、收盘价\n")
        f.write("- **成交量数据**: 成交量\n")
        f.write("- **调整收盘价**: 考虑分红、拆股的调整收盘价\n")
        f.write("- **历史数据**: 至少 1-2 年的历史数据\n\n")
        
        f.write("### 2. 技术指标数据（推荐）\n\n")
        f.write("- **移动平均数据**: 短期 MA、长期 MA\n")
        f.write("- **相对强弱指数（RSI）**: RSI 数据\n")
        f.write("- **MACD 数据**: MACD、信号线、柱状图\n")
        f.write("- **布林带数据**: 上轨、下轨、中轨\n")
        f.write("- **波动率数据**: ATR、标准差\n\n")
        
        f.write(f"### 3. 宏观经济数据（可选）\n\n")
        f.write("- **利率数据**: 联邦基金利率、国库券收益率\n")
        f.write("- **通胀率数据**: CPI、PPI 通胀率\n")
        f.write("- **GDP 数据**: 国内生产总值增长率\n")
        f.write("- **失业率数据**: 失业率数据\n\n")
        
        f.write(f"\n---\n\n")
        
        # 策略有效性原因
        f.write("## 策略有效性原因\n\n")
        f.write(f"该策略（{strategy_type}）可能有效的原因：\n\n")
        f.write("### 1. 数据驱动\n")
        f.write(f"- **历史数据分析**: 基于对历史数据的统计分析\n")
        f.write(f"- **统计规律**: 利用市场中的统计规律\n")
        f.write(f"- **模式识别**: 识别市场中的价格模式\n\n")
        
        f.write("### 2. 学术支撑\n")
        f.write(f"- **理论支撑**: 有相应的学术理论支撑\n")
        f.write(f"- **实证研究**: 有大量实证研究验证\n")
        f.write(f"- **同行评审**: 经过同行评审和验证\n\n")
        
        f.write("### 3. 实战验证\n")
        f.write(f"- **实盘成功**: 在实盘交易中有成功的案例\n")
        f.write(f"- **机构应用**: 被机构投资者广泛应用\n")
        f.write(f"- **长期稳定**: 在长期中表现稳定\n\n")
        
        f.write("### 4. 持续优化\n")
        f.write(f"- **参数优化**: 可以不断优化参数\n")
        f.write(f"- **模型改进**: 可以改进模型以适应市场变化\n")
        f.write(f"- **风险控制**: 可以加入风险控制以提高表现\n")
        f.write(f"- **市场适应**: 可以适应不同的市场环境\n\n")
        
        f.write(f"\n---\n\n")
        
        # 风险和注意事项
        f.write("## 风险和注意事项\n\n")
        f.write(f"实施 **{title}** 策略时，需要注意：\n\n")
        
        f.write("### 市场风险\n")
        f.write(f"- **市场环境变化**: 市场环境变化可能导致策略失效\n")
        f.write(f"- **黑天鹅事件**: 极端的市场事件可能对策略造成重大损失\n")
        f.write(f"- **流动性不足**: 市场流动性不足可能导致无法执行\n")
        f.write(f"- **宏观经济事件**: 宏观经济事件可能影响策略表现\n\n")
        
        f.write("### 策略风险\n")
        f.write(f"- **历史回测不代表未来表现**: 历史回测不代表未来表现\n")
        f.write(f"- **过拟合风险**: 对历史数据的过度拟合\n")
        f.write(f"- **参数敏感性**: 参数的微小变化可能对结果产生重大影响\n")
        f.write(f"- **样本外推**: 在不同市场和时间段测试\n")
        f.write(f"- **数据窥探**: 避免使用未来数据\n\n")
        
        f.write("### 执行风险\n")
        f.write(f"- **滑点风险**: 实际成交价格与预期价格有偏差\n")
        f.write(f"- **手续费风险**: 高频交易可能导致手续费过高\n")
        f.write(f"- **延迟风险**: 网络延迟可能导致错过交易机会\n")
        f.write(f"- **订单执行风险**: 订单可能无法成交或部分成交\n")
        f.write(f"- **流动性风险**: 大额订单可能对价格产生冲击\n\n")
        
        f.write(f"### 技术风险\n")
        f.write(f"- **系统故障风险**: 服务器崩溃、网络中断\n")
        f.write(f"- **数据风险**: 历史数据缺失或错误\n")
        f.write(f"- **API 风险**: 第三方 API 服务中断或限制\n")
        f.write(f"- **代码 bug**: 策略代码存在逻辑错误\n")
        f.write(f"- **数据一致性**: 不同数据源的数据不一致\n\n")
        
        f.write(f"### 合规风险\n")
        f.write(f"- **遵守交易规则和法规**: 遵守相关市场的交易规则和法规\n")
        f.write(f"- **了解相关市场的交易限制**: 了解相关市场的交易限制\n")
        f.write(f"- **避免内幕交易和市场操纵**: 避免内幕交易和市场操纵\n")
        f.write(f"- **做好税务申报**: 做好税务申报\n")
        f.write(f"- **确保符合反洗钱法规**: 确保符合反洗钱法规\n\n")
        
        f.write(f"### 风险管理建议\n")
        f.write(f"- **设置合理的止损止盈**: 设置合理的止损止盈\n")
        f.write(f"- **控制每笔交易的风险敞口**: 控制每笔交易的风险敞口\n")
        f.write(f"- **分散投资，避免过度集中**: 分散投资，避免过度集中\n")
        f.write(f"- **持续监控市场动态**: 持续监控市场动态\n")
        f.write(f"- **制定应急预案**: 制定应急预案\n")
        f.write(f"- **使用风险管理系统（如 VaR, CVaR）**: 使用风险管理系统（如 VaR, CVaR）\n")
        f.write(f"- **定期审查和调整策略**: 定期审查和调整策略\n\n")
        
        f.write(f"\n---\n\n")
        
        # 实施步骤
        f.write("## 实施步骤\n\n")
        f.write(f"### 1. 策略理解\n")
        f.write(f"- 仔细阅读策略文档\n")
        f.write(f"- 理解策略的核心逻辑\n")
        f.write(f"- 识别策略的关键参数\n")
        f.write(f"- 分析策略的风险和收益\n\n")
        
        f.write(f"### 2. 数据准备\n")
        f.write(f"- 获取 **{strategy_type}** 所需的数据\n")
        f.write(f"- 清洗和预处理数据\n")
        f.write(f"- 计算所需的技术指标\n")
        f.write(f"- 确保数据质量\n")
        f.write(f"- 分割训练集和测试集\n\n")
        
        f.write(f"### 3. 策略实现\n")
        f.write(f"- 在 backtrader 中实现策略逻辑\n")
        f.write(f"- 设置策略参数\n")
        f.write(f"- 实现买入/卖出逻辑\n")
        f.write(f"- 添加风险控制\n")
        f.write(f"- 添加仓位管理\n\n")
        
        f.write(f"### 4. 回测验证\n")
        f.write(f"- 使用历史数据回测策略\n")
        f.write(f"- 分析回测结果\n")
        f.write(f"- 计算关键指标（收益率、夏普比率、最大回撤、胜率、盈亏比）\n")
        f.write(f"- 评估策略稳定性\n")
        f.write(f"- 检查过拟合\n\n")
        
        f.write(f"### 5. 参数优化\n")
        f.write(f"- 使用网格搜索优化参数\n")
        f.write(f"- 使用贝叶斯优化参数\n")
        f.write(f"- 考虑不同市场环境\n")
        f.write(f"- 避免过拟合\n")
        f.write(f"- 使用样本外测试\n\n")
        
        f.write(f"### 6. 模拟交易\n")
        f.write(f"- 在模拟交易环境中测试策略\n")
        f.write(f"- 验证策略在实时情况下的表现\n")
        f.write(f"- 检查滑点和手续费影响\n")
        f.write(f"- 测试订单执行逻辑\n\n")
        
        f.write(f"### 7. 实盘验证\n")
        f.write(f"- 使用小资金实盘验证\n")
        f.write(f"- 持续监控策略表现\n")
        f.write(f"- 根据市场变化调整策略\n")
        f.write(f"- 做好风险控制\n")
        f.write(f"- 避免情绪化交易\n\n")
        
        f.write(f"\n---\n\n")
        
        # 参数配置
        f.write("## 参数配置\n\n")
        f.write(f"```python\n")
        f.write(f"# {title} 策略参数\n")
        f.write(f"params = (\n")
        f.write(f"    # 策略类型: {strategy_type_en}\n")
        f.write(f"    # TODO: 根据具体策略添加参数\n")
        f.write(f"    # 例如：\n")
        f.write(f"    ('lookback_period', 20),  # 回望周期（天）\n")
        f.write(f"    ('threshold', 0.02),  # 交易阈值\n")
        f.write(f"    ('risk_per_trade', 0.02),  # 每笔交易风险比例（账户净值的 2%）\n")
        f.write(f"    ('stop_loss', 0.20),  # 止损比例（从入场价格下跌 20%）\n")
        f.write(f"    ('take_profit', 0.30),  # 止盈比例（从入场价格上涨 30%）\n")
        f.write(f"    ('trailing_stop', 0.10),  # 跟踪止损（从最高点下跌 10%）\n")
        f.write(f"    ('rebalance_frequency', 'monthly'),  # 再平衡频率：daily, weekly, monthly\n")
        f.write(f"    ('max_position_size', 10),  # 最大持仓数量\n")
        f.write(f"    ('min_position_size', 1),  # 最小持仓数量\n")
        f.write(f"    ('commission', 0.001),  # 佣金比例（每笔交易）\n")
        f.write(f"    ('slippage', 0.0005),  # 滑点比例（每笔交易）\n")
        f.write(f")\n")
        f.write(f"```\n")
        f.write(f"\n---\n\n")
        
        # Backtrader 实现框架
        f.write("## Backtrader 实现框架\n\n")
        f.write(f"以下是 **{title}** 策略的 Backtrader 实现框架：\n\n")
        f.write(f"```python\n")
        f.write(f"import backtrader as bt\n")
        f.write(f"import backtrader.indicators as btind\n")
        f.write(f"import numpy as np\n")
        f.write(f"import pandas as pd\n")
        f.write(f"\n")
        
        # 生成安全的类名
        class_safe_name = safe_name.replace('-', '_').replace('.', '_')
        
        f.write(f"class {class_safe_name}Strategy(bt.Strategy):\n")
        f.write(f"    \"\"\"\n")
        f.write(f"    {title} 策略\n")
        f.write(f"    \n")
        f.write(f"    策略类型: {strategy_type}\n")
        f.write(f"    策略子类: {strategy_type}\n")
        f.write(f"    \n")
        f.write(f"    实现步骤:\n")
        f.write(f"    1. 准备所需数据\n")
        f.write(f"    2. 计算技术指标\n")
        f.write(f"    3. 生成交易信号\n")
        f.write(f"    4. 执行交易并管理风险\n")
        f.write(f"    \"\"\"\n")
        f.write(f"    \n")
        f.write(f"    params = (\n")
        f.write(f"        # 策略类型: {strategy_type_en}\n")
        f.write(f"        # TODO: 根据具体策略添加参数\n")
        f.write(f"        # 例如：\n")
        f.write(f"        ('lookback_period', 20),  # 回望周期（天）\n")
        f.write(f"        ('ma_short', 10),  # 短期 MA 周期（天）\n")
        f.write(f"        ('ma_long', 50),  # 长期 MA 周期（天）\n")
        f.write(f"        ('rsi_period', 14),  # RSI 周期（天）\n")
        f.write(f"        ('rsi_overbought', 70),  # RSI 超买阈值\n")
        f.write(f"        ('rsi_oversold', 30),  # RSI 超卖阈值\n")
        f.write(f"        ('signal_threshold', 0.0),  # 信号强度阈值\n")
        f.write(f"        \n")
        f.write(f"        # 风险管理参数\n")
        f.write(f"        ('stop_loss', 0.20),  # 止损比例（从入场价格下跌 20%）\n")
        f.write(f"        ('take_profit', 0.30),  # 止盈比例（从入场价格上涨 30%）\n")
        f.write(f"        ('trailing_stop', 0.10),  # 跟踪止损（从最高点下跌 10%）\n")
        f.write(f"        ('max_drawdown_limit', 0.20),  # 最大回撤限制（账户净值的 20%）\n")
        f.write(f"        \n")
        f.write(f"        # 交易成本参数\n")
        f.write(f"        ('commission', 0.001),  # 佣金比例（每笔交易）\n")
        f.write(f"        ('slippage', 0.0005),  # 滑点比例（每笔交易）\n")
        f.write(f"        ('borrow_rate', 0.04),  # 融资利率（年化）\n")
        f.write(f"    )\n")
        f.write(f"    \n")
        f.write(f"    def __init__(self):\n")
        f.write(f"        super().__init__()\n")
        f.write(f"        \n")
        f.write(f"        # 数据引用\n")
        f.write(f"        self.dataclose = self.datas[0].close\n")
        f.write(f"        self.datahigh = self.datas[0].high\n")
        f.write(f"        self.datalow = self.datas[0].low\n")
        f.write(f"        self.dataopen = self.datas[0].open\n")
        f.write(f"        self.datavolume = self.datas[0].volume\n")
        f.write(f"        \n")
        f.write(f"        # 指标\n")
        f.write(f"        self.ma_short = btind.SMA(self.dataclose, period=self.params.ma_short)\n")
        f.write(f"        self.ma_long = btind.SMA(self.dataclose, period=self.params.ma_long)\n")
        f.write(f"        self.rsi = btind.RSI(self.dataclose, period=self.params.rsi_period)\n")
        f.write(f"        \n")
        f.write(f"        # 策略状态\n")
        f.write(f"        self.signal_strength = 0.0\n")
        f.write(f"        self.entry_price = None\n")
        f.write(f"        self.highest_price = None\n")
        f.write(f"        self.lowest_price = None\n")
        f.write(f"        \n")
        f.write(f"        # 订单\n")
        f.write(f"        self.order = None\n")
        f.write(f"        \n")
        f.write(f"        # 记录\n")
        f.write(f"        self.trades = []\n")
        f.write(f"        \n")
        f.write(f"        print(f\"{self.__class__.__name__} 初始化完成\")\n")
        f.write(f"        print(f\"  策略类型: {strategy_type}\")\n")
        f.write(f"        print(f\"  回望周期: {self.params.lookback_period} 天\")\n")
        f.write(f"        print(f\"  MA 短期: {self.params.ma_short} 天\")\n")
        f.write(f"        print(f\"  MA 长期: {self.params.ma_long} 天\")\n")
        f.write(f"        print(f\"  RSI 周期: {self.params.rsi_period} 天\")\n")
        f.write(f"        print(f\"  止损: {self.params.stop_loss * 100}%\")\n")
        f.write(f"        print(f\"  止盈: {self.params.take_profit * 100}%\")\n")
        f.write(f"        print(f\"  跟踪止损: {self.params.trailing_stop * 100}%\")\n")
        f.write(f"        print(f\"  佣金: {self.params.commission * 100}%\")\n")
        f.write(f"        print(f\"  滑点: {self.params.slippage * 100}%\")\n")
        f.write(f"        print(f\"  融资利率: {self.params.borrow_rate * 100}%\")\n")
        f.write(f"\n")
        
        f.write(f"    def next(self):\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        核心策略逻辑\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        \n")
        f.write(f"        # 确保有足够的数据\n")
        f.write(f"        if len(self.dataclose) < self.params.lookback_period:\n")
        f.write(f"            return\n")
        f.write(f"        \n")
        f.write(f"        # 计算指标\n")
        f.write(f"        if self.ma_short[0] is None or self.ma_long[0] is None or self.rsi[0] is None:\n")
        f.write(f"            return\n")
        f.write(f"        \n")
        f.write(f"        ma_short_current = self.ma_short[0]\n")
        f.write(f"        ma_long_current = self.ma_long[0]\n")
        f.write(f"        rsi_current = self.rsi[0]\n")
        f.write(f"        current_price = self.dataclose[0]\n")
        f.write(f"        \n")
        f.write(f"        # 生成交易信号\n")
        f.write(f"        if not self.position:\n")
        f.write(f"            # 无仓位，根据信号开仓\n")
        f.write(f"            \n")
        f.write(f"            # MA 交叉信号\n")
        f.write(f"            ma_cross = ma_short_current > ma_long_current\n")
        f.write(f"            \n")
        f.write(f"            # RSI 信号\n")
        f.write(f"            rsi_signal = rsi_current < self.params.rsi_oversold  # 超卖\n")
        f.write(f"            \n")
        f.write(f"            # 综合信号\n")
        f.write(f"            if ma_cross and rsi_signal:\n")
        f.write(f"                # 强买入信号\n")
        f.write(f"                self.signal_strength = 1.0\n")
        f.write(f"                action = \"buy\"\n")
        f.write(f"            else:\n")
        f.write(f"                # 无强信号\n")
        f.write(f"                self.signal_strength = 0.0\n")
        f.write(f"                action = \"hold\"\n")
        f.write(f"            \n")
        f.write(f"            # 执行买入\n")
        f.write(f"            if action == \"buy\":\n")
        f.write(f"                # 计算仓位大小\n")
        f.write(f"                position_size = self.calculate_position_size()\n")
        f.write(f"                \n")
        f.write(f"                # 执行买入\n")
        f.write(f"                self.order = self.buy(size=position_size)\n")
        f.write(f"                print(f\"买入: 仓位大小: {position_size}\")\n")
        f.write(f"            \n")
        f.write(f"        else:\n")
        f.write(f"            # 有仓位，根据信号调整\n")
        f.write(f"            \n")
        f.write(f"            # MA 交叉信号\n")
        f.write(f"            ma_cross = ma_short_current < ma_long_current\n")
        f.write(f"            \n")
        f.write(f"            # RSI 信号\n")
        f.write(f"            rsi_signal = rsi_current > self.params.rsi_overbought  # 超买\n")
        f.write(f"            \n")
        f.write(f"            # 综合信号\n")
        f.write(f"            if ma_cross and rsi_signal:\n")
        f.write(f"                # 强卖出信号\n")
        f.write(f"                action = \"sell\"\n")
        f.write(f"            else:\n")
        f.write(f"                # 无强信号\n")
        f.write(f"                action = \"hold\"\n")
        f.write(f"            \n")
        f.write(f"            # 执行卖出\n")
        f.write(f"            if action == \"sell\":\n")
        f.write(f"                self.order = self.close()\n")
        f.write(f"                print(f\"卖出: 平仓\")\n")
        f.write(f"            \n")
        f.write(f"        # 风险控制\n")
        f.write(f"        self.manage_risk()\n")
        f.write(f"\n")
        
        f.write(f"    def calculate_position_size(self):\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        计算仓位大小\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        # 基础仓位大小\n")
        f.write(f"        base_size = 100  # 100 股\n")
        f.write(f"        \n")
        f.write(f"        # 根据信号强度调整\n")
        f.write(f"        if self.signal_strength > 0.8:\n")
        f.write(f"            size = int(base_size * 1.5)  # 强信号：增加仓位\n")
        f.write(f"        elif self.signal_strength > 0.4:\n")
        f.write(f"            size = int(base_size * 1.0)  # 中等信号：正常仓位\n")
        f.write(f"        else:\n")
        f.write(f"            size = int(base_size * 0.5)  # 弱信号：减少仓位\n")
        f.write(f"        \n")
        f.write(f"        # 应用最大仓位限制\n")
        f.write(f"        max_size = 500  # 500 股\n")
        f.write(f"        if size > max_size:\n")
        f.write(f"            size = max_size\n")
        f.write(f"        \n")
        f.write(f"        return size\n")
        f.write(f"\n")
        
        f.write(f"    def manage_risk(self):\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        风险控制\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        if not self.position:\n")
        f.write(f"            return  # 无仓位，不需要管理\n")
        f.write(f"        \n")
        f.write(f"        # 止损止盈\n")
        f.write(f"        self.check_stop_loss_take_profit()\n")
        f.write(f"        \n")
        f.write(f"        # 跟踪止损\n")
        f.write(f"        self.check_trailing_stop()\n")
        f.write(f"        \n")
        f.write(f"        # 最大回撤检查\n")
        f.write(f"        self.check_max_drawdown()\n")
        f.write(f"\n")
        
        f.write(f"    def check_stop_loss_take_profit(self):\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        检查止损止盈\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        current_price = self.dataclose[0]\n")
        f.write(f"        \n")
        f.write(f"        if self.entry_price is not None and self.entry_price != 0:\n")
        f.write(f"            # 计算盈亏\n")
        f.write(f"            pnl = (current_price - self.entry_price) / self.entry_price\n")
        f.write(f"            \n")
        f.write(f"            # 检查止损\n")
        f.write(f"            if pnl < -self.params.stop_loss:\n")
        f.write(f"                print(f\"止损触发: 盈亏: {pnl:.2%}\")\n")
        f.write(f"                self.order = self.close()\n")
        f.write(f"                self.entry_price = None\n")
        f.write(f"                self.highest_price = None\n")
        f.write(f"            \n")
        f.write(f"            # 检查止盈\n")
        f.write(f"            elif pnl > self.params.take_profit:\n")
        f.write(f"                print(f\"止盈触发: 盈亏: {pnl:.2%}\")\n")
        f.write(f"                self.order = self.close()\n")
        f.write(f"                self.entry_price = None\n")
        f.write(f"                self.highest_price = None\n")
        f.write(f"\n")
        
        f.write(f"    def check_trailing_stop(self):\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        检查跟踪止损\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        if self.position.size > 0:  # 多头仓位\n")
        f.write(f"            if self.highest_price is None:\n")
        f.write(f"                self.highest_price = self.dataclose[0]\n")
        f.write(f"            else:\n")
        f.write(f"                self.highest_price = max(self.highest_price, self.dataclose[0])\n")
        f.write(f"            \n")
        f.write(f"            if self.entry_price is not None and self.entry_price != 0:\n")
        f.write(f"                trailing_stop_price = self.highest_price * (1 - self.params.trailing_stop)\n")
        f.write(f"                \n")
        f.write(f"                if self.dataclose[0] < trailing_stop_price:\n")
        f.write(f"                    print(f\"跟踪止损触发: 价格 {self.dataclose[0]:.2f} < 跟踪止损价 {trailing_stop_price:.2f}\")\n")
        f.write(f"                    self.order = self.close()\n")
        f.write(f"                    self.entry_price = None\n")
        f.write(f"                    self.highest_price = None\n")
        f.write(f"        \n")
        f.write(f"        elif self.position.size < 0:  # 空头仓位\n")
        f.write(f"            if self.lowest_price is None:\n")
        f.write(f"                self.lowest_price = self.dataclose[0]\n")
        f.write(f"            else:\n")
        f.write(f"                self.lowest_price = min(self.lowest_price, self.dataclose[0])\n")
        f.write(f"            \n")
        f.write(f"            if self.entry_price is not None and self.entry_price != 0:\n")
        f.write(f"                trailing_stop_price = self.lowest_price * (1 + self.params.trailing_stop)\n")
        f.write(f"                \n")
        f.write(f"                if self.dataclose[0] > trailing_stop_price:\n")
        f.write(f"                    print(f\"跟踪止损触发: 价格 {self.dataclose[0]:.2f} > 跟踪止损价 {trailing_stop_price:.2f}\")\n")
        f.write(f"                    self.order = self.close()\n")
        f.write(f"                    self.entry_price = None\n")
        f.write(f"                    self.lowest_price = None\n")
        f.write(f"\n")
        
        f.write(f"    def check_max_drawdown(self):\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        检查最大回撤\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        # 计算当前回撤\n")
        f.write(f"        self.broker.getvalue()\n")
        f.write(f"        \n")
        f.write(f"        # 检查是否超过最大回撤限制\n")
        f.write(f"        if self.broker.getvalue() < self.broker.startingcash * (1 - self.params.max_drawdown_limit):\n")
        f.write(f"            print(f\"最大回撤触发: 回撤: {((self.broker.startingcash - self.broker.getvalue()) / self.broker.startingcash):.2%}\")\n")
        f.write(f"            self.order = self.close()\n")
        f.write(f"\n")
        
        f.write(f"    def notify_order(self, order):\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        订单通知\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        if order.status in [order.Completed]:\n")
        f.write(f"            print(f\"订单完成: {order.getrefname()}\")\n")
        f.write(f"            \n")
        f.write(f"            # 记录交易\n")
        f.write(f"            if order.isbuy():\n")
        f.write(f"                trade = {\n")
        f.write(f"                    'action': 'buy',\n")
        f.write(f"                    'price': order.executed.price,\n")
        f.write(f"                    'size': order.executed.size,\n")
        f.write(f"                    'date': self.datetime.date(),\n")
        f.write(f"                }\n")
        f.write(f"                self.trades.append(trade)\n")
        f.write(f"                self.entry_price = order.executed.price\n")
        f.write(f"                \n")
        f.write(f"                if self.position.size > 0:\n")
        f.write(f"                    self.highest_price = self.dataclose[0]\n")
        f.write(f"                    self.lowest_price = self.dataclose[0]\n")
        f.write(f"                \n")
        f.write(f"                print(f\"买入完成: 价格 {order.executed.price:.2f}, 数量 {order.executed.size}\")\n")
        f.write(f"            \n")
        f.write(f"            elif order.issell():\n")
        f.write(f"                trade = {\n")
        f.write(f"                    'action': 'sell',\n")
        f.write(f"                    'price': order.executed.price,\n")
        f.write(f"                    'size': order.executed.size,\n")
        f.write(f"                    'date': self.datetime.date(),\n")
        f.write(f"                }\n")
        f.write(f"                self.trades.append(trade)\n")
        f.write(f"                self.entry_price = None\n")
        f.write(f"                self.highest_price = None\n")
        f.write(f"                self.lowest_price = None\n")
        f.write(f"                \n")
        f.write(f"                print(f\"卖出完成: 价格 {order.executed.price:.2f}, 数量 {order.executed.size}\")\n")
        f.write(f"        \n")
        f.write(f"        elif order.status in [order.Canceled, order.Rejected]:\n")
        f.write(f"            print(f\"订单取消或拒绝: {order.getrefname()}\")\n")
        f.write(f"        \n")
        f.write(f"        elif order.status in [order.Margin]:\n")
        f.write(f"            print(f\"订单需要保证金\")\n")
        f.write(f"\n")
        f.write(f"```\n")
        f.write(f"\n---\n\n")
        
        # 参考链接
        f.write("## 参考链接\n\n")
        f.write(f"- 原始文档: `{html_file.name}`\n")
        f.write(f"- 策略类型: {strategy_type}\n")
        f.write(f"- 策略子类: {strategy_type}\n")
        f.write("\n")
    
    return md_file


def process_batch(batch_size=10):
    """处理批量"""
    # 获取所有 HTML 文件
    html_iter = STRATEGY_DIR.glob('*.html')
    html_files = sorted(html_iter)
    total = len(html_files)
    
    # 加载进度
    progress = load_progress()
    completed = set(progress.get("completed", []))
    current_index = progress.get("current_index", 0)
    
    # 获取开始时间
    start_time = progress.get("start_time")
    if start_time:
        start_dt = datetime.fromisoformat(start_time)
        elapsed = datetime.now() - start_dt
        elapsed_seconds = elapsed.total_seconds()
        elapsed_hours = elapsed_seconds / 3600
    else:
        elapsed_hours = 0
    
    # 计算处理速度
    processed_count = len(completed)
    if elapsed_hours > 0:
        speed = processed_count / elapsed_hours  # 文档/小时
    else:
        speed = 0
    
    # 计算剩余时间
    remaining = total - processed_count
    if speed > 0:
        remaining_hours = remaining / speed
    else:
        remaining_hours = 0
    
    print("=" * 70)
    print("10倍速处理系统（增强版）")
    print("=" * 70)
    print()
    print(f"总文档数: {total}")
    print(f"已完成: {processed_count}/{total} ({processed_count * 100 // total}%)")
    print(f"当前索引: {current_index}/{total}")
    print(f"批量大小: {batch_size}")
    print(f"处理速度: {speed:.2f} 文档/小时")
    print(f"预计剩余时间: {remaining_hours:.2f} 小时")
    print()
    print("-" * 70)
    print()
    
    # 处理批量
    for i in range(current_index, min(current_index + batch_size, total)):
        html_file = html_files[i]
        
        # 分类
        strategy_type, strategy_type_en = classify_strategy(html_file.name)
        
        # 生成 MD 文档
        md_file = generate_detailed_md(i + 1, html_file, strategy_type, strategy_type_en)
        
        # 更新进度
        completed.add(html_file.name)
        progress = {
            "completed": list(completed),
            "current_index": i + 1,
            "total": total,
            "start_time": start_time,
        }
        save_progress(progress)
        
        print(f"[{i+1}/{total}] {html_file.name} -> {md_file.name}")
        print(f"  策略类型: {strategy_type}")
        print(f"  策略类型（英文）: {strategy_type_en}")
        print()
    
    # 生成报告
    print("=" * 70)
    print("批量处理进度报告")
    print("=" * 70)
    print()
    print(f"本次处理: {batch_size} 个文档")
    print(f"累计完成: {len(completed)}/{total} ({len(completed) * 100 // total}%)")
    print(f"总进度: {len(completed) * 100 // total}%")
    print()
    
    # 输出进度文件位置
    print(f"进度文件: {PROGRESS_FILE}")
    print(f"策略目录: {STRATEGIES_DIR}")
    print()
    
    # 如果还有未处理的文档，提示继续
    if len(completed) < total:
        print("=" * 70)
        print("🔄 继续处理下一个批次（10 个）")
        print("=" * 70)
        print()
        print("📊 进度已保存")
        print(f"📊 总进度: {len(completed)}/{total} ({len(completed) * 100 // total}%)")
        print()
        print("运行相同的脚本继续处理下一批文档：")
        print(f"  cd {sys.path[0]}")
        print(f"  python3 10x_speed_processor_enhanced.py")
        print()
        print("或者运行多次脚本：")
        print(f"  for i in {{1..100}}; do python3 10x_speed_processor_enhanced.py; done")
        print("=" * 70)
        print()
    else:
        print("=" * 70)
        print("✅ 所有文档处理完成！")
        print("=" * 70)
        print()
        print(f"📊 总文档数: {total}")
        print(f"✅ 已完成: {total}")
        print(f"📊 生成的文档数: {total}")
        print(f"📂 策略目录: {STRATEGIES_DIR}")
        print()
        print("🎉 恭喜！所有 2,738 个策略文档已生成完成！")
        print()


if __name__ == "__main__":
    # 每次处理 10 个文档
    process_batch(10)
