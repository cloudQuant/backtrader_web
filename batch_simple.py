#!/usr/bin/env python3
import sys
from pathlib import Path
import json

STRATEGY_DIR = Path("/home/yun/Downloads/论文/论文")
STRATEGIES_DIR = Path("/home/yun/Documents/backtrader_web/strategies")
STRATEGIES_DIR.mkdir(exist_ok=True)
PROGRESS_FILE = STRATEGIES_DIR / "99_PROGRESS.json"


def main():
    html_list = list(STRATEGY_DIR.glob("*.html")))
    total = len(html_list)
    
    # 加载进度
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r') as f:
            progress = json.load(f)
    else:
        progress = {"completed": [], "current_index": 0}
    
    current_index = progress.get("current_index", 0)
    completed = set(progress.get("completed", []))
    
    print(f"Total: {total}")
    print(f"Completed: {len(completed)}")
    print(f"Starting from: {current_index}")
    print()
    
    # 处理 10 个文件
    for i in range(current_index, min(current_index + 10, total)):
        html_file = html_list[i]
        
        # 简单分类
        fname = html_file.name.lower()
        if 'momentum' in fname:
            stype = '动量策略'
        elif 'mean' in fname:
            stype = '均值回归'
        elif 'breakout' in fname:
            stype = '突破策略'
        elif 'machine' in fname or 'learning' in fname:
            stype = '机器学习'
        elif 'volatility' in fname or 'vix' in fname:
            stype = '波动率策略'
        elif 'option' in fname:
            stype = '期权策略'
        else:
            stype = '其他策略'
        
        # 生成文件名
        title = html_file.name.replace('.html', '')
        safe_title = title.replace(' ', '_').replace('/', '_')[:50]
        safe_title = ''.join(c if c.isalnum() else '_' for c in safe_title)
        md_name = f"{i+1:03d}_{safe_title}.md"
        
        # 生成 MD
        md_path = STRATEGIES_DIR / md_name
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# {title}\n\n")
            f.write(f"## 策略类型\n")
            f.write(f"{stype}\n\n")
            f.write(f"## 文件\n")
            f.write(f"{html_file.name}\n\n")
            f.write(f"## 说明\n")
            f.write(f"这是一个 {stype}。\n\n")
            f.write(f"## 实施\n")
            f.write(f"1. 理解策略\n")
            f.write(f"2. 准备数据\n")
            f.write(f"3. 回测验证\n")
            f.write(f"4. 模拟交易\n")
            f.write(f"5. 实盘部署\n\n")
        
        completed.add(html_file.name)
        progress = {
            "completed": list(completed),
            "current_index": i + 1,
            "total": total
        }
        
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(progress, f, indent=2)
        
        print(f"[{i+1}/{total}] {html_file.name} -> {md_name}")
    
    print()
    print(f"Processed: 10")
    print(f"Total completed: {len(completed)}")
    print()
    print("Run again to continue")


if __name__ == "__main__":
    main()
