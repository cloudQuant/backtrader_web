#!/usr/bin/env python3
"""
Quick backend test script.

Tests core functionality without dependencies on all modules.
"""
import importlib.util
import sys
from pathlib import Path

# Add project path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("="*70)
print("🚀 Quick Backend Test")
print("="*70)
print()

# Test 1: Python version
print(f"✅ Python Version: {sys.version}")
print()

# Test 2: Project path
print(f"✅ Project Root: {project_root}")
print(f"✅ Working Directory: {Path.cwd()}")
print()

# Test 3: Check file existence
files_to_check = [
    "app/models/paper_trading.py",
    "app/services/paper_trading_service.py",
    "app/api/paper_trading.py",
    "app/schemas/paper_trading.py",
    "app/main.py",
]

print("📋 Checking Files...")
for file_path in files_to_check:
    full_path = project_root / file_path
    if full_path.exists():
        print(f"  ✅ {file_path}")
    else:
        print(f"  ✗ {file_path} (NOT FOUND)")

print()

# Test 4: Check core module imports
print("📋 Testing Core Imports...")
modules_to_import = [
    "app.models.paper_trading",
    "app.services.paper_trading_service",
]

for module_name in modules_to_import:
    try:
        module = importlib.import_module(module_name)
        print(f"  ✅ {module_name}")
    except Exception as e:
        print(f"  ✗ {module_name}: {e}")

print()
print("="*70)
print("✅ Quick Test Complete!")
print("="*70)
print()
print("Next Steps:")
print("1. If files are missing, create them")
print("2. If imports fail, check syntax")
print("3. Then run full pytest with dependencies")
