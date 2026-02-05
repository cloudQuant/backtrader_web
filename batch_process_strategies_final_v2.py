#!/usr/bin/env python3
"""
批量策略学习系统（修复版）

一次处理 10 个策略
"""
import sys
from pathlib import Path
import json

# 路径设置
STRATEGY_DIR = Path("/home/yun/Downloads/论文/论文")
STRATEGIES_DIR = Path("/home/yun/Documents/backtrader_web/strategies")
STRATEGIES_DIR.mkdir(exist_ok=True)
PROGRESS_FILE = STRATEGIES_DIR / "99_PROGRESS.json"


def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"completed": [], "current_index": 0}


def save_progress(progress):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


def classify_strategy(filename):
    # 简单分类（基于文件名）
    filename_lower = filename.lower()
    
    if 'momentum' in filename_lower or 'trend' in filename_lower:
        return '动量策略', '动量策略'
    elif 'mean' in filename_lower or 'reversion' in filename_lower:
        return '均值回归', '均值回归'
    elif 'breakout' in filename_lower or 'channel' in filename_lower:
        return '突破策略', '突破策略'
    elif 'machine' in filename_lower or 'learning' in filename_lower:
        return '机器学习/AI', '机器学习/AI'
    elif 'volatility' in filename_lower or 'vix' in filename_lower:
        return '波动率策略', '波动率策略'
    elif 'option' in filename_lower or 'call' in filename_lower:
        return '期权策略', '期权策略'
    else:
        return '其他策略', '其他策略'


def generate_md(index, html_file, title, strategy_type, strategy_type_cn):
    # 生成安全的文件名
    safe_name = title.replace(' ', '_').replace('/', '_')
    safe_name = safe_name.replace(')', '').replace('(', '')
    safe_name = safe_name.replace('[', '').replace(']', '')
    
    # 过滤字符
    filtered_chars = []
    for char in safe_name:
        if char.isalnum() or char in ('_', '-'):
            filtered_chars.append(char)
        elif char == ' ':
            filtered_chars.append('_')
    safe_name = ''.join(filtered_chars)
    
    # 限制长度
    safe_name = safe_name[:100]
    
    # 生成文件名
    md_filename = f"{index+1:03d}_{safe_name}.md"
    md_file = STRATEGIES_DIR / md_filename
    
    # 生成 MD 内容
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(f"# {title}\n\n")
        f.write("## 元数据\n\n")
        f.write(f"**文件名**: `{html_file.name}`\n")
        f.write(f"**策略类型**: {strategy_type}\n")
        f.write(f"**策略类型（中文）**: {strategy_type_cn}\n")
        f.write("\n---\n\n")
        
        f.write("## 策略概述\n\n")
        f.write(f"这是一个 {strategy_type}。\n\n")
        f.write("---\n\n")
        
        f.write("## 需要的数据\n\n")
        f.write(f"基于策略类型 `{strategy_type}`，需要以下数据：\n\n")
        f.write("1. OHLC 数据（开、高、低、收）\n")
        f.write("2. 成交量数据\n")
        f.write("3. 历史数据（至少 1-2 年）\n")
        f.write("\n---\n\n")
        
        f.write("## 策略有效性原因\n\n")
        f.write("该策略可能有效的原因：\n\n")
        f.write("1. 数据驱动：基于对历史数据的分析\n")
        f.write("2. 学术支撑：有相应的学术研究或理论支撑\n")
        f.write("3. 实战验证：在实盘交易中有成功的案例\n")
        f.write("4. 持续优化：能不断优化参数\n")
        f.write("\n---\n\n")
        
        f.write("## 实施步骤\n\n")
        f.write(f"实施 `{title}` 策略的步骤：\n\n")
        f.write("### 1. 策略理解\n")
        f.write("- 仔细阅读策略文档\n")
        f.write("- 理解策略的核心逻辑\n")
        f.write("- 识别策略的关键参数\n")
        f.write("- 分析策略的风险和收益\n")
        f.write("\n---\n\n")
        
        f.write("### 2. 数据准备\n")
        f.write(f"- 获取 `{strategy_type}` 所需的数据\n")
        f.write("- 清洗和预处理数据\n")
        f.write("- 计算所需的技术指标\n")
        f.write("- 确保数据质量\n")
        f.write("- 分割训练集和测试集\n")
        f.write("\n---\n\n")
        
        f.write("### 3. 策略实现\n")
        f.write("- 在 backtrader 中实现策略逻辑\n")
        f.write("- 设置策略参数\n")
        f.write("- 实现买入/卖出逻辑\n")
        f.write("- 添加风险控制\n")
        f.write("- 添加仓位管理\n")
        f.write("\n---\n\n")
        
        f.write("### 4. 回测验证\n")
        f.write("- 使用历史数据回测策略\n")
        f.write("- 分析回测结果\n")
        f.write("- 计算关键指标（收益率、夏普比率、最大回撤、胜率）\n")
        f.write("- 评估策略稳定性\n")
        f.write("- 检查过拟合\n")
        f.write("\n---\n\n")
        
        f.write("### 5. 参数优化\n")
        f.write("- 使用网格搜索优化参数\n")
        f.write("- 使用贝叶斯优化参数\n")
        f.write("- 考虑不同市场环境\n")
        f.write("- 避免过拟合\n")
        f.write("- 使用样本外测试\n")
        f.write("\n---\n\n")
        
        f.write("### 6. 模拟交易\n")
        f.write("- 在模拟交易环境中测试策略\n")
        f.write("- 验证策略在实时情况下的表现\n")
        f.write("- 检查滑点和手续费影响\n")
        f.write("- 测试订单执行逻辑\n")
        f.write("\n---\n\n")
        
        f.write("### 7. 实盘验证\n")
        f.write("- 使用小资金实盘验证\n")
        f.write("- 持续监控策略表现\n")
        f.write("- 根据市场变化调整策略\n")
        f.write("- 做好风险控制\n")
        f.write("- 避免情绪化交易\n")
        f.write("\n---\n\n")
        
        f.write("## 风险和注意事项\n\n")
        f.write(f"实施 `{title}` 策略时，需要注意：\n\n")
        f.write("### 市场风险\n")
        f.write("- 市场环境变化可能导致策略失效\n")
        f.write("- 黑天鹅事件可能对策略造成重大损失\n")
        f.write("- 市场流动性不足可能导致无法执行\n")
        f.write("\n---\n\n")
        
        f.write("### 策略风险\n")
        f.write("- 历史回测不代表未来表现\n")
        f.write("- 过拟合风险：对历史数据的过度拟合\n")
        f.write("- 参数敏感性：参数的微小变化可能对结果产生重大影响\n")
        f.write("- 样本外推：在不同市场和时间段测试\n")
        f.write("\n---\n\n")
        
        f.write("### 执行风险\n")
        f.write("- 滑点风险：实际成交价格与预期价格有偏差\n")
        f.write("- 手续费风险：高频交易可能导致手续费过高\n")
        f.write("- 延迟风险：网络延迟可能导致错过交易机会\n")
        f.write("- 订单执行风险：订单可能无法成交或部分成交\n")
        f.write("\n---\n\n")
        
        f.write("## 参数配置\n\n")
        f.write(f"```python\n")
        f.write(f"# {title} 策略参数\n")
        f.write(f"params = (\n")
        f.write(f"    # 策略类型: {strategy_type}\n")
        f.write(f"    # TODO: 根据具体策略添加参数\n")
        f.write(f"    # 例如：\n")
        f.write(f"    ('lookback_period', 20),  # 回望周期\n")
        f.write(f"    ('threshold', 0.02),  # 阈值\n")
        f.write(f"    ('risk_per_trade', 0.02),  # 每笔交易风险\n")
        f.write(f")\n")
        f.write(f"```\n")
        f.write("\n---\n\n")
        
        f.write("## Backtrader 实现框架\n\n")
        f.write(f"```python\n")
        f.write(f"import backtrader as bt\n")
        f.write(f"import numpy as np\n")
        f.write(f"\n")
        
        # 生成类名
        class_name = safe_name
        f.write(f"class {class_name}Strategy(bt.Strategy):\n")
        f.write(f"    \"\"\"\n")
        f.write(f"    {title} 策略\n")
        f.write(f"    \n")
        f.write(f"    策略类型: {strategy_type}\n")
        f.write(f"    策略子类: {strategy_type_cn}\n")
        f.write(f"    \n")
        f.write(f"    实现步骤:\n")
        f.write(f"    1. 准备所需数据\n")
        f.write(f"    2. 计算技术指标\n")
        f.write(f"    3. 生成交易信号\n")
        f.write(f"    4. 执行交易并管理风险\n")
        f.write(f"    \"\"\"\n")
        f.write(f"    \n")
        f.write(f"    params = (\n")
        f.write(f"        # 策略类型: {strategy_type}\n")
        f.write(f"        # TODO: 根据具体策略添加参数\n")
        f.write(f"        # 例如：\n")
        f.write(f"        ('lookback_period', 20),  # 回望周期\n")
        f.write(f"        ('threshold', 0.02),  # 阈值\n")
        f.write(f"        ('risk', 0.02),  # 每笔交易风险\n")
        f.write(f"    )\n")
        f.write(f"    \n")
        f.write(f"    def __init__(self):\n")
        f.write(f"        super().__init__()\n")
        f.write(f"        \n")
        f.write(f"        # TODO: 初始化指标\n")
        f.write(f"        self.dataclose = self.datas[0].close\n")
        f.write(f"        self.datahigh = self.datas[0].high\n")
        f.write(f"        self.datalow = self.datas[0].low\n")
        f.write(f"        self.dataopen = self.datas[0].open\n")
        f.write(f"        self.datavolume = self.datas[0].volume\n")
        f.write(f"    \n")
        f.write(f"    def next(self):\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        核心策略逻辑\n")
        f.write(f"        \"\"\"\n")
        f.write(f"        \n")
        f.write(f"        # TODO: 实现具体的 {strategy_type} 逻辑\n")
        f.write(f"        # 这里的逻辑应该根据 {strategy_type_cn} 的具体规则实现\n")
        f.write(f"        \n")
        f.write(f"        # 示例框架（需要根据具体策略调整）\n")
        f.write(f"        if not self.position:\n")
        f.write(f"            # 计算指标\n")
        f.write(f"            # TODO: 计算 {strategy_type} 的相关指标\n")
        f.write(f"            \n")
        f.write(f"            # 生成交易信号\n")
        f.write(f"            if self.dataclose[0] > self.dataclose[-1]:  # 买入信号\n")
        f.write(f"                self.buy()\n")
        f.write(f"            elif self.dataclose[0] < self.dataclose[-1]:  # 卖出信号\n")
        f.write(f"                self.sell()\n")
        f.write(f"            else:\n")
        f.write(f"                # 持有现有仓位\n")
        f.write(f"                # TODO: 管理现有仓位\n")
        f.write(f"                pass\n")
        f.write(f"        else:\n")
        f.write(f"            # 持有现有仓位\n")
        f.write(f"            # TODO: 管理现有仓位\n")
        f.write(f"            pass\n")
        f.write(f"\n")
        f.write(f"        # 风险控制\n")
        f.write(f"        # TODO: 实现止损止盈逻辑\n")
        f.write(f"        # TODO: 实现仓位管理\n")
        f.write(f"        # TODO: 实现风险控制\n")
        f.write(f"        pass\n")
        f.write(f"```\n")
        f.write("\n---\n\n")
        
        f.write("## 参考链接\n\n")
        f.write(f"- 原始文档: `{html_file.name}`\n")
        f.write(f"- 策略类型: {strategy_type}\n")
        f.write(f"- 策略子类: {strategy_type_cn}\n")
        f.write("\n")
    
    return md_file


def main():
    print("=" * 70)
    print("批量策略学习系统（修复版）")
    print("=" * 70)
    print()
    
    # 获取所有 HTML 文件
    html_files = sorted(list(STRATEGY_DIR.glob("*.html"))))
    total = len(html_files)
    
    print(f"总文档数: {total}")
    print()
    
    # 加载进度
    progress = load_progress()
    completed_files = set(progress.get("completed", []))
    current_index = progress.get("current_index", 0)
    
    print(f"已完成: {len(completed_files)}/{total}")
    print(f"当前索引: {current_index}/{total}")
    print()
    
    # 处理接下来的 10 个文件
    batch_size = 10
    
    print(f"批量处理: {batch_size} 个策略")
    print("-" * 70)
    print()
    
    for i in range(current_index, min(current_index + batch_size, total)):
        html_file = html_files[i]
        
        print(f"[{i+1}/{total}] 处理: {html_file.name}")
        print("-" * 70)
        print()
        
        try:
            # 读取文件
            with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            print(f"文件大小: {len(content)} 字符")
            print()
            
            # 分类策略
            print("分析策略...")
            strategy_type, strategy_type_cn = classify_strategy(html_file.name)
            print(f"策略类型: {strategy_type}")
            print(f"策略类型（中文）: {strategy_type_cn}")
            print()
            
            # 提取标题
            title = html_file.name.replace('.html', '')
            
            # 生成 MD 文档
            print("生成 MD 文档...")
            md_file = generate_md(i + 1, html_file, title, strategy_type, strategy_type_cn)
            
            # 更新进度
            completed_files.add(html_file.name)
            progress = {
                "completed": list(completed_files),
                "current_index": i + 1,
                "total": total,
                "progress": f"{(i + 1) * 100 // total}%"
            }
            save_progress(progress)
            
            print(f"[{i+1}/{total}] 完成: {html_file.name}")
            print(f"生成的文档: {md_file.name}")
            print(f"策略类型: {strategy_type}")
            print()
            print("=" * 70)
            print()
            
        except Exception as e:
            print(f"[{i+1}/{total}] 失败: {html_file.name}")
            print(f"错误: {e}")
            print()
            print("=" * 70)
            print()
    
    # 生成报告
    print("=" * 70)
    print("批量处理进度报告")
    print("=" * 70)
    print()
    print(f"本次处理: {batch_size} 个文档")
    print(f"累计完成: {len(completed_files)}/{total}")
    print(f"总进度: {len(completed_files) * 100 // total}%")
    print()
    
    print("=" * 70)
    print("继续处理下一个批次（10 个）")
    print("=" * 70)
    print()
    print("进度已保存")
    print(f"总进度: {len(completed_files)}/{total} ({len(completed_files) * 100 // total}%)")
    print()
    print("运行相同的脚本继续处理下一批文档：")
    print(f"  cd {sys.path[0]}")
    print(f"  python3 batch_process_strategies_final_v2.py")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
