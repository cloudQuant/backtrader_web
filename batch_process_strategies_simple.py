#!/usr/bin/env python3
"""
批量策略学习系统（简单版）

一次处理 10 个策略
"""
import sys
import os
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


def process_strategy(html_file, index, total):
    """处理单个策略"""
    print(f"[{index+1}/{total}] 处理: {html_file.name}")
    
    try:
        # 读取文件
        with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # 简单分类（基于文件名）
        filename_lower = html_file.name.lower()
        
        if 'momentum' in filename_lower or 'trend' in filename_lower:
            strategy_type = '动量策略'
            strategy_type_cn = '动量策略'
        elif 'mean' in filename_lower or 'reversion' in filename_lower:
            strategy_type = '均值回归'
            strategy_type_cn = '均值回归'
        elif 'breakout' in filename_lower or 'channel' in filename_lower:
            strategy_type = '突破策略'
            strategy_type_cn = '突破策略'
        elif 'machine' in filename_lower or 'learning' in filename_lower or 'neural' in filename_lower:
            strategy_type = '机器学习/AI'
            strategy_type_cn = '机器学习/AI'
        elif 'volatility' in filename_lower or 'vix' in filename_lower:
            strategy_type = '波动率策略'
            strategy_type_cn = '波动率策略'
        elif 'option' in filename_lower or 'call' in filename_lower or 'put' in filename_lower:
            strategy_type = '期权策略'
            strategy_type_cn = '期权策略'
        else:
            strategy_type = '其他策略'
            strategy_type_cn = '其他策略'
        
        # 生成标题
        title = html_file.name.replace('.html', '')
        
        # 生成安全的文件名
        safe_name = title.replace(' ', '_').replace('/', '_')[:50]
        safe_name = ''.join(c if c.isalnum() else '_' for c in safe_name)
        md_filename = f"{index+1:03d}_{safe_name}.md"
        md_file = STRATEGIES_DIR / md_filename
        
        # 生成 MD 文档
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(f"# {title}\n\n")
            f.write(f"## 元数据\n\n")
            f.write(f"- 文件名: `{html_file.name}`\n")
            f.write(f"- 策略类型: {strategy_type}\n")
            f.write(f"- 策略类型（中文）: {strategy_type_cn}\n")
            f.write("\n---\n\n")
            
            f.write(f"## 策略概述\n\n")
            f.write(f"这是一个 {strategy_type}。\n")
            f.write("\n---\n\n")
            
            f.write(f"## 需要的数据\n\n")
            f.write(f"基于 {strategy_type}，需要以下数据：\n\n")
            f.write("1. OHLC 数据\n")
            f.write("2. 成交量数据\n")
            f.write("3. 历史数据\n")
            f.write("\n---\n\n")
            
            f.write(f"## 策略有效性原因\n\n")
            f.write(f"该策略可能有效的原因：\n\n")
            f.write("1. 数据驱动\n")
            f.write("2. 学术支撑\n")
            f.write("3. 实战验证\n")
            f.write("\n---\n\n")
            
            f.write(f"## 实施步骤\n\n")
            f.write("1. 策略理解\n")
            f.write("2. 数据准备\n")
            f.write("3. 策略实现\n")
            f.write("4. 回测验证\n")
            f.write("5. 模拟交易\n")
            f.write("6. 实盘验证\n")
            f.write("\n---\n\n")
            
            f.write(f"## 参数配置\n\n")
            f.write(f"```python\n")
            f.write(f"params = (\n")
            f.write(f"    'strategy_type', '{strategy_type}',\n")
            f.write(f"    'lookback_period', 20,\n")
            f.write(f"    'risk_per_trade', 0.02,\n")
            f.write(f")\n")
            f.write(f"```\n")
            f.write("\n---\n\n")
            
            f.write(f"## Backtrader 实现框架\n\n")
            f.write(f"```python\n")
            f.write(f"import backtrader as bt\n")
            f.write(f"\n")
            f.write(f"class {safe_name}Strategy(bt.Strategy):\n")
            f.write(f"    \"\"\"\n")
            f.write(f"    {title} 策略\n")
            f.write(f"    \n")
            f.write(f"    策略类型: {strategy_type}\n")
            f.write(f"    \"\"\"\n")
            f.write(f"    \n")
            f.write(f"    params = (\n")
            f.write(f"        'lookback_period', 20,\n")
            f.write(f"        'risk', 0.02,\n")
            f.write(f"    )\n")
            f.write(f"    \n")
            f.write(f"    def __init__(self):\n")
            f.write(f"        super().__init__()\n")
            f.write(f"        self.dataclose = self.datas[0].close\n")
            f.write(f"        self.datavolume = self.datas[0].volume\n")
            f.write(f"    \n")
            f.write(f"    def next(self):\n")
            f.write(f"        if not self.position:\n")
            f.write(f"            if self.dataclose[0] > self.dataclose[-1]:\n")
            f.write(f"                self.buy()\n")
            f.write(f"            elif self.dataclose[0] < self.dataclose[-1]:\n")
            f.write(f"                self.sell()\n")
            f.write(f"        pass\n")
            f.write(f"```\n")
            f.write("\n---\n\n")
            
            f.write(f"## 参考链接\n\n")
            f.write(f"- 原始文档: `{html_file.name}`\n")
            f.write(f"- 策略类型: {strategy_type}\n")
            f.write("\n")
        
        print(f"  生成文档: {md_filename}")
        print(f"  策略类型: {strategy_type}")
        print(f"  完成！")
        print()
        
        return True
        
    except Exception as e:
        print(f"  错误: {e}")
        print()
        return False


def main():
    """主函数"""
    print("=" * 70)
    print("批量策略学习系统（简单版）")
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
    processed_count = 0
    batch_size = 10
    
    print(f"批量处理: {batch_size} 个策略")
    print("=" * 70)
    print()
    
    for i in range(current_index, min(current_index + batch_size, total)):
        html_file = html_files[i]
        
        success = process_strategy(html_file, i, total)
        
        if success:
            # 更新进度
            completed_files.add(html_file.name)
            progress = {
                "completed": list(completed_files),
                "current_index": i + 1,
                "total": total,
                "progress": f"{(i + 1) * 100 // total}%"
            }
            save_progress(progress)
            processed_count += 1
    
    # 生成报告
    print("=" * 70)
    print("批量处理进度报告")
    print("=" * 70)
    print()
    print(f"本次处理: {processed_count} 个文档")
    print(f"累计完成: {len(completed_files)}/{total}")
    print(f"总进度: {len(completed_files) * 100 // total}%")
    print()
    
    if len(completed_files) < total:
        print("=" * 70)
        print("继续处理下一个批次")
        print("=" * 70)
        print()
        print(f"运行相同的脚本继续：")
        print(f"  cd {sys.path[0]}")
        print(f"  python3 batch_process_strategies_simple.py")
        print()
    else:
        print("=" * 70)
        print("所有文档处理完成！")
        print("=" * 70)
        print()


if __name__ == "__main__":
    main()
