#!/bin/bash
"""
运行测试脚本

使用系统 Python 运行所有测试，不依赖虚拟环境
"""

PROJECT_ROOT="/home/yun/Documents/backtrader_web"
BACKEND_DIR="$PROJECT_ROOT/backend"
TESTS_DIR="$BACKEND_DIR/tests"

echo "==================================="
echo "🚀 Backtrader Web - Running Tests"
echo "==================================="
echo ""

# 切换到后端目录
cd "$BACKEND_DIR" || exit 1

# 清理之前的测试进程
echo "📋 Cleaning up previous test processes..."
pkill -f "python" -9 2>/dev/null
pkill -f "pytest" -9 2>/dev/null
sleep 2

echo "✅ Cleanup complete"
echo ""

# 测试 1：快速导入检查
echo "📋 Test 1: Quick Import Check"
echo "-----------------------------------"
python3 -c "
import sys
import importlib.util

project_root = '/home/yun/Documents/backtrader_web'
sys.path.insert(0, project_root)

modules = [
    'app.models.paper_trading',
    'app.services.paper_trading_service',
    'app.api.paper_trading',
]

print('Testing module imports...')
for module_name in modules:
    try:
        module = importlib.import_module(module_name)
        print(f'  ✅ {module_name}')
    except Exception as e:
        print(f'  ✗ {module_name}: {e}')
        sys.exit(1)

print('✅ All modules imported successfully!')
" 2>&1

echo ""

# 测试 2：检查文件存在
echo "📋 Test 2: File Existence Check"
echo "-----------------------------------"
python3 -c "
import os
from pathlib import Path

backend_dir = '/home/yun/Documents/backtrader_web/backend'

files_to_check = [
    'app/models/paper_trading.py',
    'app/services/paper_trading_service.py',
    "app/api/paper_trading.py",
    "app/schemas/paper_trading.py",
]

print('Checking files...')
for file_path in files_to_check:
    full_path = os.path.join(backend_dir, file_path)
    if os.path.exists(full_path):
        size = os.path.getsize(full_path)
        print(f'  ✅ {file_path} ({size} bytes)')
    else:
        print(f'  ✗ {file_path} (NOT FOUND)')
        sys.exit(1)

print('✅ All files exist!')
" 2>&1

echo ""
echo "==================================="
echo "✅ Quick Tests Complete!"
echo "==================================="
echo ""

# 询问是否继续完整测试
read -p "是否运行完整测试套？ (y/n): " -r -n 1

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "🚀 Running Full Test Suite..."
    echo "==================================="
    echo ""

    # 测试 3：单元测试（模拟交易）
    echo "📋 Test 3: Paper Trading Unit Tests"
    echo "-----------------------------------"

    # 使用系统 Python 和 pytest
    python3 -m pytest tests/test_paper_trading_complete.py -v \
        --tb=short \
        --maxfail=1 \
        2>&1 | tee "$TESTS_DIR/test_results.log"

    TEST_EXIT_CODE=${PIPESTATUS[0]}

    echo ""
    if [ $TEST_EXIT_CODE -eq 0 ]; then
        echo "✅ All tests passed!"
        echo ""
        echo "📊 Test Results:"
        echo "-----------------------------------"
        echo "   See test_results.log for detailed output"
        echo "   Summary:"
        grep -E "(PASSED|FAILED|ERROR)" "$TESTS_DIR/test_results.log" | tail -20
    else
        echo "✗ Some tests failed!"
        echo ""
        echo "📊 Test Results:"
        echo "-----------------------------------"
        echo "   See test_results.log for detailed output"
        echo "   Summary:"
        grep -E "(PASSED|FAILED|ERROR)" "$TESTS_DIR/test_results.log" | tail -20
    fi

    echo ""
    echo "==================================="
    echo "✅ Test Suite Complete!"
    echo "==================================="
else
    echo "跳过完整测试"
fi

echo ""
echo "==================================="
echo "📋 Next Steps"
echo "==================================="
echo "1. If tests passed, you can start the backend:"
echo "   cd $BACKEND_DIR && python3 -m fastapi dev --host 0.0.0.0 --port 8000"
echo ""
echo "2. Access API documentation:"
echo "   http://0.0.0.0:8000/docs"
echo ""
echo "3. Start frontend:"
echo "   cd /home/yun/Documents/backtrader_web/frontend"
echo "   npm install && npm run dev"
echo ""
echo "==================================="
