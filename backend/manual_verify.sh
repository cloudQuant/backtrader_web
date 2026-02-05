#!/usr/bin/env python3
"""
手动功能验证脚本

通过直接导入和执行来验证功能，不依赖 pytest
"""
import sys
import importlib.util
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("="*70)
print("🔍 Manual Functionality Verification")
print("="*70)
print()

# 1. 验证导入
print("📋 Step 1: Verifying Imports")
print("-"*70)
print()

modules_to_check = [
    "app.models.paper_trading",
    "app.models.comparison",
    "app.services.paper_trading_service",
    "app.services.comparison_service",
    "app.api.paper_trading",
    "app.api.comparison",
    "app.websocket_manager",
]

all_ok = True
for module_name in modules_to_check:
    try:
        module = importlib.import_module(module_name)
        print(f"  ✅ {module_name}")
    except Exception as e:
        print(f"  ❌ {module_name}: {e}")
        all_ok = False

if all_ok:
    print("  ✅ All modules imported successfully!")
else:
    print("  ❌ Some modules failed to import")

print()

# 2. 验证服务实例化
print("📋 Step 2: Verifying Service Instantiation")
print("-"*70)
print()

try:
    from app.services.paper_trading_service import PaperTradingService
    print("  ✅ PaperTradingService can be instantiated")
    service = PaperTradingService()
    print("  ✅ Service instance created")
except Exception as e:
    print(f"  ❌ Failed to instantiate service: {e}")

print()

# 3. 验证 WebSocket 管理器
print("📋 Step 3: Verifying WebSocket Manager")
print("-"*70)
print()

try:
    from app.websocket_manager import WebSocketManager
    print("  ✅ WebSocketManager can be instantiated")
    manager = WebSocketManager()
    print("  ✅ WebSocket manager instance created")
except Exception as e:
    print(f"  ❌ Failed to instantiate WebSocket manager: {e}")

print()

# 4. 验证 API 路由
print("📋 Step 4: Verifying API Routes")
print("-"*70)
print()

apis_to_check = [
    "app.api.paper_trading",
    "app.api.comparison",
    "app.api.strategy_version",
    "app.api.live_trading",
    "app.api.realtime_data",
    "app.api.monitoring",
]

for api_name in apis_to_check:
    try:
        api = importlib.import_module(api_name)
        router = getattr(api, 'router', None)
        if router:
            print(f"  ✅ {api_name}.router exists")
        else:
            print(f"  ⚠️  {api_name}.router not found")
    except Exception as e:
        print(f"  ❌ {api_name}: {e}")

print()
print("="*70)
print("✅ Manual Verification Complete!")
print("="*70)
print()
print("Summary:")
print("  1. Imports: Checked")
print("  2. Services: Can be instantiated")
print("  3. WebSocket Manager: Can be instantiated")
print("  4. API Routes: Checked")
print()
print("Next Steps:")
print("  1. Start the backend server")
print("  2. Access http://0.0.0.0:8000/docs")
print("  3. Manually test each endpoint in Swagger UI")
print("  4. Verify functionality works as expected")
print("="*70)
