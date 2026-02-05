#!/bin/bash
"""
直接启动后端

使用系统 Python，不依赖虚拟环境
"""

echo "==================================="
echo "🚀 Starting Backtrader Web API"
echo "==================================="
echo ""

PROJECT_ROOT="/home/yun/Documents/backtrader_web"
BACKEND_DIR="$PROJECT_ROOT/backend"

# 停止可能存在的进程
echo "📋 Stopping existing processes..."
pkill -f "uvicorn app.main" 2>/dev/null
pkill -f "python -m uvicorn" 2>/dev/null
pkill -f "fastapi" 2>/dev/null

sleep 2

# 切换到后端目录
cd "$BACKEND_DIR" || exit 1

# 检查 main.py
if [ -f "app/main.py" ]; then
    echo "✅ Found app/main.py"
else
    echo "❌ app/main.py not found!"
    exit 1

# 使用系统 Python 直接启动
echo "🚀 Starting with system Python..."
python3 -m fastapi dev --host 0.0.0.0 --port 8000 --reload &

sleep 3

echo ""
echo "==================================="
echo "✅ Server Started!"
echo "==================================="
echo ""
echo "📋 API Documentation: http://0.0.0.0:8000/docs"
echo "📋 Health Check: http://0.0.0.0:8000/health"
echo "📋 Root Route: http://0.0.0.0:8000/"
echo ""
echo "Press Ctrl+C to stop"
echo "==================================="
