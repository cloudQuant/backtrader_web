#!/usr/bin/env python3
"""
从论文文件夹中学习并总结量化交易策略

读取 PDF 和 HTML 文档，提取量化交易策略信息
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Any

# 论文文件夹路径
PAPERS_DIR = Path("/home/yun/Downloads/论文")

# 策略文档文件夹路径
STRATEGY_DIR = Path("/home/yun/Documents/论文/论文")

# 存储所有找到的策略
strategies_found = []

print("="*70)
print("📚 Learning and Summarizing Quant Trading Strategies")
print("="*70)
print()

# 1. 扫描 HTML 策略文档
print("📋 Step 1: Scanning HTML Strategy Documents")
print("-"*70)
print()

if STRATEGY_DIR.exists():
    # 查找所有 HTML 文件
    html_files = list(STRATEGY_DIR.glob("*.html"))
    
    print(f"Found {len(html_files)} HTML files")
    print()
    
    for html_file in html_files:
        try:
            # 读取 HTML 文件
            with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 提取策略信息
            strategy_info = extract_strategy_info(html_file.name, content)
            if strategy_info:
                strategies_found.append(strategy_info)
                print(f"  ✅ {html_file.name}")
                print(f"     Strategy: {strategy_info['name']}")
                print(f"     Source: {strategy_info['source']}")
                print(f"     Summary: {strategy_info['summary']}")
                print()
        
        except Exception as e:
            print(f"  ❌ Failed to read {html_file.name}: {e}")
            print()

print(f"Total strategies found: {len(strategies_found)}")
print()

# 2. 分析策略模式
print("="*70)
print("📊 Step 2: Analyzing Strategy Patterns")
print("="*70)
print()

strategy_types = {}
for strategy in strategies_found:
    strategy_type = classify_strategy(strategy)
    if strategy_type not in strategy_types:
        strategy_types[strategy_type] = []
    strategy_types[strategy_type].append(strategy['name'])

print("Strategy Types Found:")
for strat_type, names in strategy_types.items():
    print(f"  {strat_type}: {len(names)} strategies")
    for name in names[:3]:  # 只显示前3个
        print(f"    - {name}")

print()

# 3. 生成 MD 文档
print("="*70)
print("📝 Step 3: Generating MD Documentation")
print("="*70)
print()

generate_strategy_md(strategies_found, strategy_types)

print()
print("="*70)
print("✅ Documentation Generation Complete!")
print("="*70)
print()
print(f"Markdown files saved to: /home/yun/Documents/backtrader_web/strategies/")
print()


def extract_strategy_info(filename: str, content: str) -> Dict[str, Any]:
    """
    从 HTML 内容中提取策略信息
    
    Args:
        filename: 文件名
        content: HTML 内容
    
    Returns:
        Dict: 策略信息字典
    """
    # 从文件名提取策略名称
    # 格式示例：006_Day_of_month_pattern_or_luck_for_a_monthly_ETF_rotation_strategy_Alvarez_Quant_Trading.html
    
    # 清理文件名
    clean_name = filename.replace('.html', '').replace('_', ' ')
    
    # 提取来源
    source = "Unknown"
    if 'QuantStrat' in clean_name or 'AlphaArchitect' in clean_name:
        source = "QuantStrat TradeR / Alpha Architect"
    elif 'Quantified' in clean_name:
        source = "Quantified Trading"
    elif 'CapitalSpectator' in clean_name:
        source = "CapitalSpectator"
    else:
        source = "Other"
    
    # 提取策略摘要
    summary = extract_strategy_summary(clean_name, content)
    
    return {
        'name': clean_name,
        'filename': filename,
        'source': source,
        'summary': summary,
        'content': content[:1000],  # 保存前 1000 个字符
    }


def extract_strategy_summary(name: str, content: str) -> str:
    """
    提取策略摘要
    
    Args:
        name: 策略名称
        content: HTML 内容
    
    Returns:
        str: 策略摘要
    """
    # 简单的基于关键词的摘要提取
    keywords = {
        'momentum': ['momentum', 'trend', 'price action'],
        'mean_reversion': ['reversion', 'mean', 'dollar cost'],
        'breakout': ['breakout', 'channel', 'donchian'],
        'volatility': ['volatility', 'atr', 'std', 'vix'],
        'pair_trading': ['pairs', 'cointegration', 'arbitrage'],
        'machine_learning': ['machine learning', 'neural', 'ai', 'lstm'],
        'risk': ['risk', 'drawdown', 'sharpe', 'max drawdown'],
    }
    
    content_lower = content.lower()
    strategy_type = "Unknown"
    
    for type_key, type_keywords in keywords.items():
        for keyword in type_keywords:
            if keyword in content_lower:
                strategy_type = type_key.replace('_', ' ').title()
                break
    
    return f"{strategy_type} Strategy"


def classify_strategy(strategy: Dict[str, Any]) -> str:
    """
    分类策略类型
    
    Args:
        strategy: 策略信息字典
    
    Returns:
        str: 策略类型
    """
    name = strategy['name'].lower()
    summary = strategy['summary'].lower()
    
    # 基于关键词分类
    if 'momentum' in name or 'momentum' in summary:
        return "Momentum"
    elif 'reversion' in name or 'reversion' in summary:
        return "Mean Reversion"
    elif 'breakout' in name or 'breakout' in summary:
        return "Breakout"
    elif 'pair' in name or 'cointegration' in name or 'arbitrage' in name:
        return "Pair Trading / Arbitrage"
    elif 'machine' in name or 'neural' in name or 'ai' in name:
        return "Machine Learning / AI"
    elif 'risk' in name or 'drawdown' in name:
        return "Risk Management"
    elif 'rotation' in name or 'rebalancing' in name:
        return "Portfolio Rotation"
    elif 'index' in name or 'smart beta' in name:
        return "Indexing / Smart Beta"
    else:
        return "Other"


def generate_strategy_md(strategies: List[Dict], types: Dict[str, List]) -> None:
    """
    生成策略 MD 文档
    
    Args:
        strategies: 策略列表
        types: 策略类型分类
    """
    # 创建输出目录
    output_dir = Path("/home/yun/Documents/backtrader_web/strategies")
    output_dir.mkdir(exist_ok=True)
    
    # 生成索引文件
    index_md = output_dir / "00_STRATEGY_INDEX.md"
    
    with open(index_md, 'w', encoding='utf-8') as f:
        f.write("# 📚 量化交易策略学习文档\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")
        f.write("## 📊 策略总览\n\n")
        f.write(f"**总策略数**: {len(strategies)}\n\n")
        f.write("---\n\n")
        f.write("## 📂 策略分类\n\n")
        
        for strat_type, names in types.items():
            f.write(f"### {strat_type}\n\n")
            f.write(f"策略数量: {len(names)}\n\n")
            for name in names:
                f.write(f"- {name}\n")
            f.write("---\n\n")
        
        f.write("---\n\n")
        f.write("## 📝 详细策略列表\n\n")
        f.write(f"以下是所有策略的详细信息：\n\n")
        f.write("---\n\n")
        
        # 按字母顺序排序
        sorted_strategies = sorted(strategies, key=lambda x: x['name'])
        
        for i, strategy in enumerate(sorted_strategies, 1):
            f.write(f"### {i}. {strategy['name']}\n\n")
            f.write(f"**来源**: {strategy['source']}\n\n")
            f.write(f"**类型**: {strategy['summary']}\n\n")
            f.write(f"**文件**: `{strategy['filename']}`\n\n")
            
            # 保存到单独的 MD 文件
            strategy_md = output_dir / f"{i:03d}_{strategy['name'][:50]}.md"
            with open(strategy_md, 'w', encoding='utf-8') as f_strat:
                f_strat.write(f"# {strategy['name']}\n\n")
                f_strat.write(f"**来源**: {strategy['source']}\n\n")
                f_strat.write(f"**类型**: {strategy['summary']}\n\n")
                f_strat.write(f"**文件**: `{strategy['filename']}`\n\n")
                f_strat.write("---\n\n")
                f_strat.write("## 📋 策略概述\n\n")
                f_strat.write(f"{strategy['summary']}\n\n")
                f_strat.write("---\n\n")
                f_strat.write("## 📄 策略逻辑\n\n")
                # 只保存前 2000 个字符作为示例
                f_strat.write(f"```html\n{strategy['content'][:2000]}\n```\n\n")
            
            f.write(f"**详细文档**: [{i:03d}_{strategy['name'][:50]}]({strategy_md.name})\n\n")
            f.write("---\n\n")
    
    print(f"  ✅ Generated index: {index_md}")
    print(f"  ✅ Generated {len(sorted_strategies)} strategy MD files")


    if __name__ == "__main__":
        import datetime
        main()
