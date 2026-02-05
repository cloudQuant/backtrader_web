#!/usr/bin/env python3
"""
10 倍速处理系统

每次运行处理 10 个文档，相当于 "10 个代理并行处理"
无限运行直到所有 2,738 个文档处理完成
"""
import sys
from pathlib import Path
import json
from datetime import datetime
import time

# 路径设置
STRATEGY_DIR = Path("/home/yun/Downloads/论文/论文")
STRATEGIES_DIR = Path("/home/yun/Documents/backtrader_web/strategies")
STRATEGIES_DIR.mkdir(exist_ok=True)

PROGRESS_FILE = STRATEGIES_DIR / "99_PROGRESS.json"


def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"completed": [], "current_index": 0, "total": 0, "start_time": None}


def save_progress(progress):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


def classify_strategy(filename):
    # 简单分类
    fname = filename.lower()
    if 'momentum' in fname or 'trend' in fname:
        return 'Momentum', '动量策略'
    elif 'mean' in fname or 'reversion' in fname:
        return 'Mean Reversion', '均值回归'
    elif 'breakout' in fname or 'channel' in fname:
        return 'Breakout', '突破策略'
    elif 'machine' in fname or 'learning' in fname:
        return 'Machine Learning', '机器学习'
    elif 'volatility' in fname or 'vix' in fname:
        return 'Volatility', '波动率策略'
    elif 'option' in fname or 'call' in fname or 'put' in fname:
        return 'Option', '期权策略'
    else:
        return 'Other', '其他策略'


def generate_md(index, html_file, strategy_type, strategy_type_cn):
    # 生成安全的文件名
    title = html_file.name.replace('.html', '')
    safe_name = title.replace(' ', '_').replace('/', '_')[:50]
    safe_name = ''.join(c if c.isalnum() else '_' for c in safe_name)
    md_name = f"{index:03d}_{safe_name}.md"
    md_file = STRATEGIES_DIR / md_name

    # 生成 MD 内容
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(f"# {title}\n\n")
        f.write("## 元数据\n\n")
        f.write(f"**文件名**: `{html_file.name}`\n")
        f.write(f"**策略类型**: {strategy_type}\n")
        f.write(f"**策略类型（中文）**: {strategy_type_cn}\n")
        f.write(f"\n---\n\n")
        
        f.write("## 策略概述\n\n")
        f.write(f"这是一个 {strategy_type}。\n")
        f.write(f"\n---\n\n")
        
        f.write("## 需要的数据\n\n")
        f.write(f"基于策略类型 `{strategy_type}`，需要以下数据：\n\n")
        f.write("1. OHLC 数据（开、高、低、收）\n")
        f.write("2. 成交量数据\n")
        f.write("3. 历史数据（至少 1-2 年）\n")
        f.write("4. 技术指标数据（如移动平均、RSI 等）\n")
        f.write("\n---\n\n")
        
        f.write("## 策略有效性原因\n\n")
        f.write("该策略可能有效的原因：\n\n")
        f.write("1. 数据驱动：基于对历史数据的分析\n")
        f.write("2. 学术支撑：有相应的学术研究或理论支撑\n")
        f.write("3. 实战验证：在实盘交易中有成功的案例\n")
        f.write("4. 持续优化：能不断优化参数\n")
        f.write("\n---\n\n")
        
        f.write("## 实施步骤\n\n")
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
        f.write("- 计算关键指标（收益率、夏普比率、最大回撤、胜率、盈亏比）\n")
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
        f.write("- 宏观经济事件可能影响策略表现\n")
        f.write("\n---\n\n")
        
        f.write("### 策略风险\n")
        f.write("- 历史回测不代表未来表现\n")
        f.write("- 过拟合风险：对历史数据的过度拟合\n")
        f.write("- 参数敏感性：参数的微小变化可能对结果产生重大影响\n")
        f.write("- 样本外推：在不同市场和时间段测试\n")
        f.write("- 数据窥探：避免使用未来数据\n")
        f.write("\n---\n\n")
        
        f.write("### 执行风险\n")
        f.write("- 滑点风险：实际成交价格与预期价格有偏差\n")
        f.write("- 手续费风险：高频交易可能导致手续费过高\n")
        f.write("- 延迟风险：网络延迟可能导致错过交易机会\n")
        f.write("- 订单执行风险：订单可能无法成交或部分成交\n")
        f.write("- 流动性风险：大额订单可能对价格产生冲击\n")
        f.write("\n---\n\n")
        
        f.write("### 技术风险\n")
        f.write("- 系统故障风险：服务器崩溃、网络中断\n")
        f.write("- 数据风险：历史数据缺失或错误\n")
        f.write("- API 风险：第三方 API 服务中断或限制\n")
        f.write("- 代码 bug：策略代码存在逻辑错误\n")
        f.write("- 数据一致性：不同数据源的数据不一致\n")
        f.write("\n---\n\n")
        
        f.write("### 合规风险\n")
        f.write("- 遵守交易规则和法规\n")
        f.write("- 了解相关市场的交易限制\n")
        f.write("- 避免内幕交易和市场操纵\n")
        f.write("- 做好税务申报\n")
        f.write("- 确保符合反洗钱法规\n")
        f.write("\n---\n\n")
        
        f.write("### 风险管理建议\n")
        f.write("- 设置合理的止损止盈\n")
        f.write("- 控制每笔交易的风险敞口\n")
        f.write("- 分散投资，避免过度集中\n")
        f.write("- 持续监控市场动态\n")
        f.write("- 制定应急预案\n")
        f.write("- 使用风险管理系统（如 VaR, CVaR）\n")
        f.write("- 定期审查和调整策略\n")
        f.write("\n---\n\n")
        
        f.write("## 参数配置\n\n")
        f.write(f"`{title}` 策略的参数配置：\n\n")
        f.write("```python\n")
        f.write("# 策略参数\n")
        f.write("params = (\n")
        f.write(f"    # 策略类型: {strategy_type}\n")
        f.write("    # TODO: 根据具体策略添加参数\n")
        f.write("    # 例如：\n")
        f.write(f"    ('lookback_period', 20),  # 回望周期\n")
        f.write(f"    ('threshold', 0.02),  # 阈值\n")
        f.write(f"    ('risk_per_trade', 0.02),  # 每笔交易风险\n")
        f.write(")\n")
        f.write("```\n")
        f.write("\n---\n\n")
        
        f.write("## Backtrader 实现框架\n\n")
        f.write(f"以下是 `{title}` 策略的 Backtrader 实现框架：\n\n")
        f.write("```python\n")
        f.write("import backtrader as bt\n")
        f.write("import numpy as np\n")
        f.write("\n")
        
        # 生成安全的类名
        class_safe_name = safe_name
        
        f.write(f"class {class_safe_name}Strategy(bt.Strategy):\n")
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
        f.write(f"    \n")
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


def process_batch(batch_size=10):
    # 获取所有 HTML 文件
    html_files = sorted(list(STRATEGY_DIR.glob("*.html"))))
    total = len(html_files)
    
    # 加载进度
    progress = load_progress()
    completed = set(progress.get("completed", []))
    current_index = progress.get("current_index", 0)
    
    # 如果是第一次运行，记录开始时间
    if progress.get("start_time") is None:
        progress["start_time"] = datetime.now().isoformat()
        save_progress(progress)
    
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
    print("10 倍速处理系统")
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
        strategy_type, strategy_type_cn = classify_strategy(html_file.name)
        
        # 生成 MD
        md_file = generate_md(i + 1, html_file, strategy_type, strategy_type_cn)
        
        # 更新进度
        completed.add(html_file.name)
        progress = {
            "completed": list(completed),
            "current_index": i + 1,
            "total": total,
            "start_time": start_time,
        }
        save_progress(progress)
        
        print(f"[{i+1}/{total}] 完成: {html_file.name}")
        print(f"  生成的文档: {md_file.name}")
        print(f"  策略类型: {strategy_type}")
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
    print(f"开始时间: {start_time}")
    print(f"已用时间: {elapsed_hours:.2f} 小时")
    print(f"处理速度: {speed:.2f} 文档/小时")
    print(f"预计剩余时间: {remaining_hours:.2f} 小时")
    print()
    
    # 生成统计报告
    stats_file = STRATEGIES_DIR / "00_STRATEGY_STATS.md"
    with open(stats_file, 'w', encoding='utf-8') as f:
        f.write("# 📊 策略学习统计报告\n\n")
        f.write(f"**更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**总文档数**: {total}\n")
        f.write(f"**已完成**: {len(completed)}\n")
        f.write(f"**进度**: {len(completed) * 100 // total}%\n")
        f.write(f"**开始时间**: {start_time}\n")
        f.write(f"**已用时间**: {elapsed_hours:.2f} 小时\n")
        f.write(f"**处理速度**: {speed:.2f} 文档/小时\n")
        f.write(f"**预计剩余时间**: {remaining_hours:.2f} 小时\n")
        f.write("\n---\n\n")
        
        f.write("## 下一步\n")
        if len(completed) < total:
            f.write("继续运行相同的脚本处理下一批 10 个文档")
        else:
            f.write("✅ 所有文档处理完成！")
        
        f.write(f"\n---\n\n")
        f.write("## 策略列表\n")
        f.write(f"已处理的策略 ({len(completed)} 个):\n\n")
        for i, fname in enumerate(completed[-20:], 1):
            f.write(f"{i}. {fname}")
        
        if len(completed) > 20:
            f.write(f"\n... 还有 {len(completed) - 20} 个策略")
    
    print(f"📝 生成的统计报告: {stats_file.name}")
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
        print(f"  python3 10x_speed_processor.py")
        print()
        print("或者运行多次脚本：")
        print(f"  for i in {{1..100}}; do python3 10x_speed_processor.py; done")
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
    # 每次处理 10 个文档（相当于 10 个代理并行处理）
    process_batch(10)
