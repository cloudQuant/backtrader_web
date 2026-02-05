#!/usr/bin/env python3
"""
检查后端代码导入
"""
import sys
import importlib.util
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 检查核心模块
modules_to_check = [
    'app.models.user',
    'app.models.permission',
    'app.models.paper_trading',
    'app.models.comparison',
    'app.models.strategy_version',
    'app.models.alerts',
    'app.schemas.comparison',
    'app.schemas.strategy_version',
    'app.schemas.live_trading',
    'app.schemas.realtime_data',
    'app.schemas.monitoring',
    'app.services.paper_trading_service',
    'app.services.comparison_service',
    'app.services.strategy_version_service',
    'app.services.live_trading_service',
    'app.services.monitoring_service',
    'app.api.paper_trading',
    'app.api.comparison',
    'app.api.strategy_version',
    'app.api.live_trading',
    'app.api.realtime_data',
    'app.api.monitoring',
    'app.websocket_manager',
    'app.config',
    'app.db.database',
    'app.utils.logger',
]

print("="*70)
print("Checking Backend Modules")
print("="*70)
print()

all_ok = True
for module_name in modules_to_check:
    try:
        module = importlib.import_module(module_name)
        print(f"✓ {module_name}")
    except Exception as e:
        print(f"✗ {module_name}: {e}")
        all_ok = False

print()
print("="*70)
if all_ok:
    print("✅ All modules imported successfully!")
    print("="*70)
else:
    print("✗ Some modules failed to import")
    print("="*70)

print()
print("Python Path:")
for path in sys.path[:10]:  # 只显示前10个
    print(f"  {path}")
print(f"  ... ({len(sys.path) - 10} more)")
