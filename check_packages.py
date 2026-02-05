#!/usr/bin/env python3
"""
检查依赖是否已安装
"""
import sys

packages = [
    "fastapi",
    "uvicorn",
    "pydantic",
    "pytest",
    "sqlalchemy",
    "httpx",
    "websockets",
    "pandas",
    "backtrader",
    "ccxt",
]

print("="*70)
print("🔍 Checking Installed Packages")
print("="*70)
print()

installed = []
not_installed = []

for package in packages:
    try:
        module = __import__(package, fromlist=["__version__"])
        version = getattr(module, "__version__", "unknown")
        print(f"  ✅ {package: {version}")
        installed.append(package)
    except ImportError:
        print(f"  ❌ {package}: NOT INSTALLED")
        not_installed.append(package)

print()
print("="*70)
if not_installed:
    print(f"⚠️  {len(not_installed)} packages not installed:")
    for pkg in not_installed:
        print(f"     - {pkg}")
    print()
    print("To install packages, run:")
    print("  cd /home/yun/Documents/backtrader_web")
    print("  bash install_with_pip.sh")
else:
    print(f"✅ All {len(packages)} packages installed!")
print("="*70)
print()
print("Summary:")
print(f"  Installed: {len(installed)}/{len(packages)}")
print(f"  Not Installed: {len(not_installed)}/{len(packages)}")
