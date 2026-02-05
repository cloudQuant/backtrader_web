#!/usr/bin/env python3
"""Simple verification script"""
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("Checking files...")
files = [
    "app/main.py",
    "app/services/paper_trading_service.py",
    "app/api/paper_trading.py",
    "app/schemas/paper_trading.py",
    "app/models/paper_trading.py",
]

for file in files:
    path = project_root / file
    if path.exists():
        print(f"  {file}: OK")
    else:
        print(f"  {file}: NOT FOUND")

print("Done!")
