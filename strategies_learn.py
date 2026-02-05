#!/usr/bin/env python3
"""
量化交易策略学习系统（TODO List 版本）

一个一个读取、总结、完成策略，直到全部完成
"""
import os
import sys
from pathlib import Path
from typing import Dict, List
from datetime import datetime

# 路径设置
STRATEGY_DIR = Path("/home/yun/Downloads/论文/论文")
STRATEGIES_DIR = Path("/home/yun/Documents/backtrader_web/strategies")

# 创建策略目录
STRATEGIES_DIR.mkdir(exist_ok=True)

# TODO list 文件
TODO_FILE = STRATEGIES_DIR / "TODO.md"

# 已完成列表
COMPLETED_FILE = STRATEGIES_DIR / "COMPLETED.md"

# 总数
TOTAL_FILES = len(list(STRATEGY_DIR.glob("*.html")))
print(f"找到 {TOTAL_FILES} 个策略文档")

print("="*70)
print("📚 量化交易策略学习系统")
print("="*70)
print()
print(f"总文档数: {TOTAL_FILES}")
print(f"策略目录: {STRATEGIES_DIR}")
print()

# ==================== 读取和总结策略 ====================

print("📋 开始处理策略文档...")
print("-"*70)
print()

html_files = sorted(list(STRATEGY_DIR.glob("*.html")))

# 处理每个文档
for i, html_file in enumerate(html_files, 1):
    try:
        print(f"📋 [{i}/{TOTAL_FILES}] 正在处理: {html_file.name}")
        
        # 1. 读取 HTML 文件
        with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # 2. 提取策略信息
        strategy_name = html_file.name.replace('.html', '').replace('_', ' ')
        strategy_type = classify_strategy(content)
        
        # 3. 生成策略 MD 文档
        generate_strategy_md(i, strategy_name, strategy_type, content, html_file)
        
        # 4. 更新 TODO list
        update_todo_list(i, TOTAL_FILES, strategy_name, status="completed")
        
        print(f"  ✅ [{i}/{TOTAL_FILES}] 完成: {strategy_name}")
        print(f"     类型: {strategy_type}")
        print()
        
    except Exception as e:
        print(f"  ❌ [{i}/{TOTAL_FILES}] 失败: {html_file.name}")
        print(f"     错误: {e}")
        print()

# ==================== 完成 ====================

print("="*70)
print("✅ 所有策略处理完成！")
print("="*70)
print()

# 生成最终报告
generate_final_report()

print()
print("📝 文档保存位置:")
print(f"  - 策略目录: {STRATEGIES_DIR}")
print(f"  - TODO 列表: {TODO_FILE}")
print(f"  - 已完成列表: {COMPLETED_FILE}")
print()


# ==================== 工具函数 ====================

def classify_strategy(content: str) -> str:
    """
    简单分类策略
    """
    content_lower = content.lower()
    
    # 动量策略
    if any(word in content_lower for word in ['momentum', 'trend', 'price']):
        return "动量策略"
    # 均值回归
    elif any(word in content_lower for word in ['mean', 'reversion', 'dollar']):
        return "均值回归"
    # 突破策略
    elif any(word in content_lower for word in ['breakout', 'channel']):
        return "突破策略"
    # 配对交易
    elif any(word in content_lower for word in ['pair', 'arbitrage', 'cointegration']):
        return "配对交易/套利"
    # 机器学习
    elif any(word in content_lower for word in ['machine', 'neural', 'ai', 'lstm', 'deep']):
        return "机器学习/AI"
    # 波动率
    elif any(word in content_lower for word in ['volatility', 'vix', 'atr']):
        return "波动率策略"
    # 投资组合优化
    elif any(word in content_lower for word in ['optimization', 'portfolio', 'optimizer']):
        return "投资组合优化"
    # 风险管理
    elif any(word in content_lower for word in ['risk', 'drawdown', 'hacker', "protection"]):
        return "风险管理"
    # 期权策略
    elif any(word in content_lower for word in ['iron', 'condor', 'option']):
        return "期权策略"
    # 其他
    else:
        return "其他策略"


def generate_strategy_md(index: int, name: str, type_name: str, content: str, html_file: Path) -> None:
    """
    生成单个策略的 MD 文档
    """
    filename = f"{index:03d}_{name[:50]}.md"
    strategy_md = STRATEGIES_DIR / filename
    
    with open(strategy_md, 'w', encoding='utf-8') as f:
        f.write(f"# {name}\n\n")
        f.write(f"**类型**: {type_name}\n\n")
        f.write(f"**源文件**: `{html_file.name}`\n\n")
        f.write("---\n\n")
        
        f.write("## 📋 策略概述\n\n")
        
        # 提取关键信息（简化版）
        summary = extract_strategy_summary(name, content)
        f.write(f"{summary}\n\n")
        f.write("---\n\n")
        
        f.write("## 📊 需要的数据\n\n")
        f.write(f"基于策略类型 `{type_name}`，需要以下数据：\n\n")
        
        if type_name == "动量策略":
            f.write("- OHLC 数据（开、高、低、收）\n")
            f.write("- 价格数据（用于计算动量）\n")
            f.write("- 成交量数据\n")
            f.write("- 时间序列数据\n")
            f.write("- 移动平均数据\n")
            f.write("- 技术指标（RSI, MACD 等）\n")
        elif type_name == "均值回归":
            f.write("- 历史价格数据\n")
            f.write("- 移动平均数据\n")
            f.write("- 标准差数据\n")
            f.write("- Z-Score 数据\n")
            f.write("- 支撑/阻力数据\n")
        elif type_name == "突破策略":
            f.write("- 价格数据\n")
            f.write("- 波动率数据（ATR）\n")
            f.write("- 历史高点/低点\n")
            f.write("- 成交量数据\n")
            f.write("- 通道数据\n")
        elif type_name == "机器学习/AI":
            f.write("- 历史 OHLC 数据\n")
            f.write("- 技术指标数据\n")
            f.write("- 市场情绪数据\n")
            f.write("- 新闻/事件数据\n")
            f.write("- 订单簿数据\n")
        elif type_name == "波动率策略":
            f.write("- 历史价格数据\n")
            f.write("- 收益率数据\n")
            f.write("- 波动率指标\n")
            f.write("- VIX 指数\n")
        else:
            f.write("- OHLC 数据\n")
            f.write("- 成交量数据\n")
            f.write("- 技术指标\n")
        
        f.write("\n---\n\n")
        
        f.write("## ✅ 策略有效性原因\n\n")
        f.write(f"该策略可能有效的原因：\n\n")
        
        if type_name == "动量策略":
            f.write("1. **市场动量效应**：价格趋势往往会延续\n")
            f.write("2. **动量因子**：利用动量因子捕捉趋势\n")
            f.write("3. **时间序列动量**：使用不同时间窗口的动量\n")
            f.write("4. **截面动量**：使用横截面数据\n")
        elif type_name == "均值回归":
            f.write("1. **均值回归理论**：价格会回归到均值\n")
            f.write("2. **超买超卖**：极端价格会反转\n")
            f.write("3. **Z-Score 策略**：使用统计方法识别异常\n")
            f.write("4. **配对交易**：利用相关性进行套利\n")
        elif type_name == "突破策略":
            f.write("1. **价格突破**：突破关键位置会有大行情\n")
            f.write("2. **波动率扩大**：突破伴随波动率扩大\n")
            f.write("3. **成交量确认**：突破需要成交量放大\n")
            f.write("4. **通道策略**：使用价格通道\n")
        elif type_name == "机器学习/AI":
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
        
        f.write("## ⚠️ 风险和注意事项\n\n")
        f.write(f"实施 `{name}` 策略时，需要注意：\n\n")
        f.write("1. **市场风险**：市场环境变化可能失效\n")
        f.write("2. **过拟合风险**：历史回测不代表未来\n")
        f.write("3. **执行风险**：滑点、手续费、流动性\n")
        f.write("4. **技术风险**：系统故障、网络延迟\n")
        f.write("5. **合规风险**：遵守交易规则和法规\n")
        f.write("\n---\n\n")
        
        f.write("## 📊 实施步骤\n\n")
        f.write(f"1. **数据准备**：获取 {type_name} 所需的数据\n")
        f.write("2. **策略实现**：在 backtrader 中实现策略逻辑\n")
        f.write("3. **回测验证**：使用历史数据验证策略\n")
        f.write("4. **参数优化**：优化策略参数\n")
        f.write("5. **模拟交易**：在模拟交易环境中测试\n")
        f.write("6. **实盘验证**：小资金实盘验证\n")
        f.write("7. **风险控制**：设置止损和仓位管理\n")
        f.write("\n---\n\n")
        
        f.write("## 🔗 参考链接\n\n")
        f.write(f"- 原始文档: `{html_file.name}`\n")
        f.write(f"- 策略类型: {type_name}\n")
        f.write("\n")


def extract_strategy_summary(name: str, content: str) -> str:
    """
    提取策略摘要（简化版）
    """
    content_lower = content.lower()
    
    # 提取关键词
    if 'momentum' in content_lower or 'trend' in content_lower:
        return f"这是一个{type_name}，基于价格趋势延续性进行交易"
    elif 'mean' in content_lower or 'reversion' in content_lower:
        return f"这是一个{type_name}，利用价格回归到均值的特性进行交易"
    elif 'breakout' in content_lower or 'channel' in content_lower:
        return f"这是一个{type_name}，当价格突破关键位置时进行交易"
    elif 'machine' in content_lower or 'neural' in content_lower or 'ai' in content_lower:
        return f"这是一个{type_name}，使用机器学习或AI模型预测市场方向"
    else:
        return f"这是一个{type_name}，基于特定的市场逻辑进行交易"


def update_todo_list(current: int, total: int, name: str, status: str = "completed") -> None:
    """
    更新 TODO list
    """
    # 读取现有的 TODO list
    if TODO_FILE.exists():
        with open(TODO_FILE, 'r', encoding='utf-8') as f:
            todo_content = f.read()
    else:
        todo_content = "# 📋 策略学习 TODO List\n\n"
    
    # 添加/更新 TODO 项
    todo_content += f"- [{current}/{total}] {name}: {status}\n"
    
    # 写入 TODO list
    with open(TODO_FILE, 'w', encoding='utf-8') as f:
        f.write(todo_content)
        f.write("\n")
        f.write(f"**进度**: {current}/{total} ({current*100//total}%)\n")


def generate_final_report() -> None:
    """
    生成最终报告
    """
    report_file = STRATEGIES_DIR / "FINAL_REPORT.md"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("# 📚 量化交易策略学习报告\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**总策略数**: {TOTAL_FILES}\n")
        f.write("---\n\n")
        
        f.write("## 📊 策略统计\n\n")
        
        # 统计各种类型的策略
        strategy_counts = {}
        
        html_files = sorted(list(STRATEGY_DIR.glob("*.html")))
        for html_file in html_files:
            try:
                with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                strategy_type = classify_strategy(content)
                
                if strategy_type not in strategy_counts:
                    strategy_counts[strategy_type] = 0
                strategy_counts[strategy_type] += 1
            except:
                pass
        
        f.write("| 策略类型 | 数量 |\n")
        f.write("| --- | --- |\n")
        for strat_type, count in sorted(strategy_counts.items()):
            f.write(f"| {strat_type} | {count} |\n")
        
        f.write("\n---\n\n")
        f.write("## 📝 生成的文档\n\n")
        f.write(f"- 策略目录: `{STRATEGIES_DIR}`\n")
        f.write(f"- TODO list: `{TODO_FILE.name}`\n")
        f.write(f"- 已完成列表: `{COMPLETED_FILE.name}`\n")
        f.write("\n---\n\n")
        f.write("## 🎯 下一步\n\n")
        f.write("1. 查看所有策略文档\n")
        f.write("2. 学习策略逻辑\n")
        f.write("3. 在 backtrader 中实现策略\n")
        f.write("4. 回测和验证\n")
        f.write("5. 实盘测试\n")
        f.write("\n")


if __name__ == "__main__":
    print("开始处理策略...")
    print("使用 TODO list 方式，逐个完成")
    print()
