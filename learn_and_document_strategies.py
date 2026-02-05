#!/usr/bin/env python3
"""
量化交易策略学习和文档生成系统

从 /home/yun/Downloads/论文 文件夹中学习并总结所有量化交易策略，
生成完整的 MD 文档，并添加到 backtrader_web 项目中
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

# 论文文件夹路径
PAPERS_DIR = Path("/home/yun/Downloads/论文")
PAPERS_SUBDIR = Path("/home/yun/Downloads/论文/论文")

# backtrader_web 项目路径
BACKTRADER_WEB_DIR = Path("/home/yun/Documents/backtrader_web")
STRATEGIES_DIR = BACKTRADER_WEB_DIR / "strategies"

# 创建策略目录
STRATEGIES_DIR.mkdir(exist_ok=True)

# 存储所有找到的策略
strategies_found = []

print("="*70)
print("📚 Learning and Documenting Quant Trading Strategies")
print("="*70)
print()

# 第1步：扫描 HTML 策略文档
print("📋 Step 1: Scanning HTML Strategy Documents")
print("-"*70)
print()

html_files = list(PAPERS_SUBDIR.glob("*.html"))

print(f"Found {len(html_files)} HTML strategy documents")
print()

for html_file in html_files:
    try:
        with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # 提取策略信息
        strategy_info = extract_strategy_info(html_file.name, content)
        if strategy_info:
            strategies_found.append(strategy_info)
            print(f"  ✅ {html_file.name}")
            print(f"     Strategy: {strategy_info['name']}")
            print(f"     Type: {strategy_info['type']}")
            print(f"     Source: {strategy_info['source']}")
            print(f"     Summary: {strategy_info['summary']}")
            print()
    except Exception as e:
        print(f"  ❌ Failed to read {html_file.name}: {e}")
        print()

print(f"Total strategies found: {len(strategies_found)}")
print()

# 第2步：分析策略模式
print("📋 Step 2: Analyzing Strategy Patterns")
print("-"*70)
print()

strategy_types = {}
for strategy in strategies_found:
    strategy_type = strategy['type']
    if strategy_type not in strategy_types:
        strategy_types[strategy_type] = []
    strategy_types[strategy_type].append(strategy)

print("Strategy Types:")
for strat_type, strategies in strategy_types.items():
    print(f"  {strat_type}: {len(strategies)} strategies")
    for strategy in strategies[:3]:  # 只显示前3个
        print(f"    - {strategy['name']}")
print()

# 第3步：生成策略总览
print("📋 Step 3: Generating Strategy Overview")
print("-"*70)
print()

generate_strategy_overview(strategies_found, strategy_types)

# 第4步：生成详细策略文档
print("📋 Step 4: Generating Detailed Strategy Documentation")
print("-"*70)
print()

for i, strategy in enumerate(strategies_found):
    generate_strategy_md(strategy, i + 1)
    print(f"  ✅ Generated: {strategy['name']}.md")
print()

# 第5步：生成 backtrader 策略模板
print("📋 Step 5: Generating Backtrader Strategy Templates")
print("-"*70)
print()

for strategy in strategies_found:
    generate_backtrader_template(strategy)
    print(f"  ✅ Generated: {strategy['name']}_backtrader.py")
print()

print("="*70)
print("✅ All Strategy Documentation Generated!")
print("="*70)
print()

print(f"Total strategies documented: {len(strategies_found)}")
print(f"Documentation saved to: {STRATEGIES_DIR}")
print(f"Backtrader templates saved to: {STRATEGIES_DIR}")
print()
print("Next steps:")
print("  1. Review strategy documentation")
print("  2. Implement strategies in backtrader")
print("  3. Test strategies in paper trading")
print("  4. Deploy to live trading")
print()
print("="*70)


def extract_strategy_info(filename: str, content: str) -> Dict[str, Any]:
    """
    从 HTML 文件中提取策略信息
    """
    # 清理文件名
    clean_name = filename.replace('.html', '').replace('_', ' ')
    
    # 提取来源
    source = "Unknown"
    if 'QuantStrat' in clean_name or 'AlphaArchitect' in clean_name:
        source = "QuantStrat TradeR / Alpha Architect"
    elif 'CapitalSpectator' in clean_name:
        source = "CapitalSpectator"
    elif 'Quantified' in clean_name:
        source = "Quantified Trading"
    else:
        source = "Other"
    
    # 提取策略类型
    strategy_type = classify_strategy(clean_name, content)
    
    # 提取策略摘要
    summary = extract_strategy_summary(clean_name, content)
    
    return {
        'name': clean_name,
        'filename': filename,
        'source': source,
        'type': strategy_type,
        'summary': summary,
        'content': content,
    }


def extract_strategy_summary(name: str, content: str) -> str:
    """
    提取策略摘要
    """
    content_lower = content.lower()
    
    # 基于关键词分类
    if any(word in name.lower() for word in ['momentum', 'trend', 'price']):
        return "Momentum / Trend Strategy"
    elif any(word in name.lower() for word in ['mean', 'reversion', 'dollar cost']):
        return "Mean Reversion Strategy"
    elif any(word in name.lower() for word in ['breakout', 'channel', 'donchian']):
        return "Breakout Strategy"
    elif any(word in name.lower() for word in ['pair', 'cointegration', 'arbitrage']):
        return "Pair Trading / Arbitrage Strategy"
    elif any(word in name.lower() for word in ['machine', 'neural', 'ai', 'lstm']):
        return "Machine Learning / AI Strategy"
    elif any(word in name.lower() for word in ['volatility', 'vix', 'atr']):
        return "Volatility Strategy"
    elif any(word in name.lower() for word in ['rotation', 'rebalancing']):
        return "Portfolio Rotation Strategy"
    elif any(word in name.lower() for word in ['iron', 'condor']):
        return "Iron Condor Strategy"
    elif any(word in name.lower() for word in ['crash', 'hacker', 'protection']):
        return "Crash Protection Strategy"
    elif any(word in name.lower() for word in ['optimization', 'portfolio', 'optimizer']):
        return "Portfolio Optimization Strategy"
    elif any(word in name.lower() for word in ['timing', 'intraday', 'day']):
        return "Timing Strategy"
    elif any(word in name.lower() for word in ['pattern', 'month', 'weekend']):
        return "Pattern Recognition Strategy"
    elif any(word in name.lower() for word in ['risk', 'drawdown', 'sharpe']):
        return "Risk Management Strategy"
    elif any(word in name.lower() for word in ['index', 'beta', 'smart']):
        return "Indexing / Smart Beta Strategy"
    else:
        return "Other Trading Strategy"


def classify_strategy(name: str, content: str) -> str:
    """
    分类策略类型
    """
    name_lower = name.lower()
    
    # 基于关键词分类
    if any(word in name_lower for word in ['momentum', 'trend', 'price']):
        return "Momentum"
    elif any(word in name_lower for word in ['mean', 'reversion', 'dollar']):
        return "Mean Reversion"
    elif any(word in name_lower for word in ['breakout', 'channel']):
        return "Breakout"
    elif any(word in name_lower for word in ['pair', 'arbitrage']):
        return "Pair Trading"
    elif any(word in name_lower for word in ['machine', 'neural', 'ai', 'lstm']):
        return "Machine Learning"
    elif any(word in name_lower for word in ['volatility', 'vix', 'atr']):
        return "Volatility"
    elif any(word in name_lower for word in ['optimization', 'portfolio']):
        return "Portfolio Optimization"
    elif any(word in name_lower for word in ['risk', 'drawdown', 'sharpe']):
        return "Risk Management"
    else:
        return "Other"


def generate_strategy_overview(strategies: List[Dict], types: Dict) -> None:
    """
    生成策略总览文档
    """
    overview_md = STRATEGIES_DIR / "00_STRATEGY_OVERVIEW.md"
    
    with open(overview_md, 'w', encoding='utf-8') as f:
        f.write("# 📚 量化交易策略学习文档\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")
        f.write("## 📊 策略总览\n\n")
        f.write(f"**总策略数**: {len(strategies)}\n\n")
        f.write("---\n\n")
        f.write("## 📂 策略分类\n\n")
        
        # 按类型分组
        for strat_type, strat_list in types.items():
            f.write(f"### {strat_type} ({len(strat_list)} 策略)\n\n")
            for strategy in strat_list:
                f.write(f"- {strategy['name']}\n")
                f.write(f"  - 来源: {strategy['source']}\n")
                f.write(f"  - 摘要: {strategy['summary']}\n")
            f.write("---\n\n")
    
        print(f"  ✅ Generated: {overview_md}")


def generate_strategy_md(strategy: Dict, index: int) -> None:
    """
    生成单个策略的详细文档
    """
    filename = f"{index:03d}_{strategy['name'][:50]}.md"
    strategy_md = STRATEGIES_DIR / filename
    
    with open(strategy_md, 'w', encoding='utf-8') as f:
        # 标题
        f.write(f"# {strategy['name']}\n\n")
        f.write(f"**来源**: {strategy['source']}\n")
        f.write(f"**类型**: {strategy['type']}\n")
        f.write(f"**文件**: `{strategy['filename']}`\n\n")
        f.write("---\n\n")
        
        # 策略概述
        f.write("## 📋 策略概述\n\n")
        f.write(f"{strategy['summary']}\n\n")
        f.write("---\n\n")
        
        # 策略逻辑
        f.write("## 🧠 策略逻辑\n\n")
        
        # 提取关键内容（前 5000 字符）
        content = strategy['content'][:5000]
        f.write(f"```html\n{content}\n```\n\n")
        f.write("---\n\n")
        
        # 需要的数据
        f.write("## 📊 需要的数据\n\n")
        f.write(f"基于策略类型 {strategy['type']}，需要以下数据：\n\n")
        
        if strategy['type'] == "Momentum":
            f.write("- OHLC 数据（开、高、低、收）\n")
            f.write("- 价格数据（用于计算动量）\n")
            f.write("- 成交量数据\n")
            f.write("- 时间序列数据\n")
        elif strategy['type'] == "Mean Reversion":
            f.write("- 历史价格数据\n")
            f.write("- 均值计算数据\n")
            f.write("- 统计指标（如移动平均）\n")
            f.write("- Z-Score 数据\n")
        elif strategy['type'] == "Breakout":
            f.write("- 价格通道数据\n")
            f.write("- 波动率数据（如 ATR）\n")
            f.write("- 历史高点/低点\n")
            f.write("- 成交量数据\n")
        elif strategy['type'] == "Machine Learning":
            f.write("- 历史 OHLC 数据\n")
            f.write("- 技术指标数据\n")
            f.write("- 市场情绪数据\n")
            f.write("- 新闻/事件数据\n")
            f.write("- 订单簿数据\n")
        elif strategy['type'] == "Volatility":
            f.write("- 历史价格数据\n")
            f.write("- 收益率数据\n")
            f.write("- 波动率指标\n")
            f.write("- VIX 指数\n")
        else:
            f.write("- 基础 OHLC 数据\n")
            f.write("- 成交量数据\n")
            f.write("- 技术指标\n")
        
        f.write("\n---\n\n")
        
        # 策略有效性原因
        f.write("## ✅ 策略有效性原因\n\n")
        f.write(f"该策略可能有效的原因：\n\n")
        
        if strategy['type'] == "Momentum":
            f.write("1. **市场动量效应**：价格趋势往往会延续\n")
            f.write("2. **动量因子**：利用动量因子捕捉趋势\n")
            f.write("3. **时间序列动量**：使用不同时间窗口的动量\n")
            f.write("4. **截面动量**：使用横截面数据\n")
        elif strategy['type'] == "Mean Reversion":
            f.write("1. **均值回归**：价格会回归到均值\n")
            f.write("2. **超买超卖**：极端价格会反转\n")
            f.write("3. **Z-Score 策略**：使用统计方法识别异常\n")
            f.write("4. **配对交易**：利用相关性进行套利\n")
        elif strategy['type'] == "Breakout":
            f.write("1. **价格突破**：突破关键位置会有大行情\n")
            f.write("2. **波动率扩大**：突破伴随波动率扩大\n")
            f.write("3. **成交量确认**：突破需要成交量放大\n")
            f.write("4. **通道策略**：使用价格通道\n")
        elif strategy['type'] == "Machine Learning":
            f.write("1. **模式识别**：AI 能发现人类无法发现模式\n")
            f.write("2. **非线性关系**：神经网络能捕捉非线性关系\n")
            f.write("3. **适应性强**：模型能适应市场变化\n")
            f.write("4. **多因子融合**：能融合多种数据源\n")
        else:
            f.write("1. **数据驱动**：基于历史数据验证\n")
            f.write("2. **学术研究**：有理论支撑\n")
            f.write("3. **实战验证**：在实盘中有成功案例\n")
            f.write("4. **持续优化**：能不断优化参数\n")
        
        f.write("\n---\n\n")
        
        # 风险和注意事项
        f.write("## ⚠️ 风险和注意事项\n\n")
        f.write(f"实施 {strategy['name']} 策略时，需要注意：\n\n")
        f.write("1. **市场风险**：市场环境变化可能失效\n")
        f.write("2. **过拟合风险**：历史回测不代表未来\n")
        f.write("3. **执行风险**：滑点、手续费、流动性\n")
        f.write("4. **技术风险**：系统故障、网络延迟\n")
        f.write("5. **合规风险**：遵守交易规则和法规\n")
        f.write("\n---\n\n")
        
        # 参考链接
        f.write("## 🔗 参考链接\n\n")
        f.write(f"- 原始文档: {strategy['filename']}\n")
        f.write("- 来源网站: {strategy['source']}\n")
        f.write("\n")


def generate_backtrader_template(strategy: Dict) -> None:
    """
    生成 Backtrader 策略模板
    """
    # 生成文件名
    safe_name = strategy['name'].replace(' ', '_').replace(')', '').replace('(', '')
    filename = f"{safe_name}_backtrader.py"
    template_file = STRATEGIES_DIR / filename
    
    with open(template_file, 'w', encoding='utf-8') as f:
        # Backtrader 模板
        f.write(f'"""\n')
        f.write(f'"""\n')
        f.write(f"\"\"\"\n")
        f.write(f'{strategy["name"]} - Backtrader 策略实现\n')
        f.write(f"\"\"\"\n")
        f.write(f"\n")
        f.write(f"import backtrader as bt\n")
        f.write(f"\n")
        f.write(f"class {safe_name}Strategy(bt.Strategy):\n")
        f.write(f"    \"\"\"\n")
        f.write(f"    {strategy["name"]} 策略\n")
        f.write(f"    \n")
        f.write(f"    策略逻辑: {strategy["summary"]}\n")
        f.write(f"    \"\"\"\n")
        f.write(f"\n")
        f.write(f"    params = (\n")
        f.write(f"        # 策略参数（根据具体策略调整）\n")
        f.write(f"        ('period', 20),  # 周期\n")
        f.write(f"        ('risk', 0.02),  # 风险比例\n")
        f.write(f"    )\n")
        f.write(f"\n")
        f.write(f"    def __init__(self):\n")
        f.write(f"        super().__init__()\n")
        f.write(f"\n")
        f.write(f"    def next(self):\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        核心策略逻辑\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        \n")
        f.write(f"        # TODO: 实现 {strategy["name"]} 的具体逻辑\n")
        f.write(f"        # 这里应该根据 {strategy["type"]} 策略的具体规则实现\n")
        f.write(f"        \n")
        f.write(f"        # 示例框架（需要根据具体策略调整）\n")
        f.write(f"        if len(self.data.close) > self.params.period:\n")
        f.write(f"            # 计算指标\n")
        f.write(f"            close = self.data.close[-1]\n")
        f.write(f"            \n")
        f.write(f"            # 策略信号\n")
        f.write(f"            if self.data.close[0] > close:  # 买入信号\n")
        f.write(f"                self.buy()\n")
        f.write(f"            elif self.data.close[0] < close:  # 卖出信号\n")
        f.write(f"                self.sell()\n")
        f.write(f"\n")


if __name__ == "__main__":
    print("Starting strategy learning and documentation...")
    print(f"Strategies directory: {STRATEGIES_DIR}")
    print(f"Total strategies to process: {len(strategies_found)}")
    print()
