#!/usr/bin/env python3
import sys
from pathlib import Path
import json

STRATEGY_DIR = Path("/home/yun/Downloads/论文/论文")
STRATEGIES_DIR = Path("/home/yun/Documents/backtrader_web/strategies")
STRATEGIES_DIR.mkdir(exist_ok=True)
PROGRESS_FILE = STRATEGIES_DIR / "99_PROGRESS.json"

def main():
    html_files = sorted(list(STRATEGY_DIR.glob("*.html"))))
    total = len(html_files)
    
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r') as f:
            progress = json.load(f)
    else:
        progress = {"completed": [], "current_index": 0}
    
    current_index = progress.get("current_index", 0)
    completed = set(progress.get("completed", []))
    
    for i in range(current_index, min(current_index + 10, total)):
        html_file = html_files[i]
        fname = html_file.name.lower()
        
        if 'momentum' in fname or 'trend' in fname:
            stype = '动量策略'
        elif 'mean' in fname:
            stype = '均值回归'
        elif 'breakout' in fname or 'channel' in fname:
            stype = '突破策略'
        elif 'option' in fname or 'call' in fname or 'put' in fname:
            stype = '期权策略'
        else:
            stype = '其他策略'
        
        title = html_file.name.replace('.html', '')
        safe_name = title.replace(' ', '_')[:50]
        safe_name = ''.join(c if c.isalnum() else '_' for c in safe_name)
        md_name = f"{i+1:03d}_{safe_name}.md"
        
        md_path = STRATEGIES_DIR / md_name
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# {title}\n\n")
            f.write(f"## 策略类型\n\n{stype}\n\n")
            f.write(f"## 文件\n\n{html_file.name}\n\n")
        
        completed.add(html_file.name)
        progress = {
            "completed": list(completed),
            "current_index": i + 1,
            "total": total
        }
        
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(progress, f, indent=2)
        
        print(f"[{i+1}/{total}] {html_file.name} -> {md_name}")
    
    print(f"\n完成: 10")
    print(f"累计: {len(completed)}")
    print("\n继续运行")

if __name__ == '__main__':
    main()
