#!/bin/bash
"""
启动脚本 - 使用 python3
"""

echo "==================================="
echo "🚀 Starting Backtrader Web API"
echo "==================================="
echo ""

PROJECT_ROOT="/home/yun/Documents/backtrader_web"
BACKEND_DIR="$PROJECT_ROOT/backend"

cd "$BACKEND_DIR" || exit 1

# 停止可能存在的进程
echo "📋 Stopping existing processes..."
pkill -f "fastapi" 2>/dev/null
pkill -f "uvicorn" 2>/dev/null
sleep 2

echo "✅ Processes stopped"
echo ""

# 检查 main.py
if [ -f "app/main.py" ]; then
    echo "✅ Found app/main.py"
else
    echo "❌ app/main.py not found!"
    exit 1
fi

# 启动服务器
echo "🚀 Starting FastAPI server with python3..."
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
echo "📋 Available Endpoints:"
echo "  - Authentication: /api/v1/auth/*"
echo "  - Strategies: /api/v1/strategies/*"
echo "  - Backtests: /api/v1/backtests/*"
echo "  - Paper Trading: /api/v1/paper-trading/*"
echo "  - Comparison: /api/v1/comparisons/*"
echo "  - Live Trading: /api/v1/live-trading/*"
echo "  - Strategy Versions: /api/v1/strategy-versions/*"
echo "  - Realtime Data: /api/v1/realtime/*"
echo "  - Monitoring: /api/v1/monitoring/*"
echo ""
echo "Press Ctrl+C to stop"
echo "==================================="
