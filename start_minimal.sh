#!/bin/bash
"""
启动脚本 - 最小版本

使用最小化的 main.py，绕过所有导入问题
"""

PROJECT_ROOT="/home/yun/Documents/backtrader_web"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo "==================================="
echo "🚀 Starting Backtrader Web API (Minimal Edition)"
echo "==================================="
echo ""

# 切换到后端目录
cd "$BACKEND_DIR" || exit 1

# 停止可能存在的进程
echo "📋 Stopping existing processes..."
pkill -f "uvicorn app.main"
pkill -f "python app.main"
sleep 2

# 启动最小版本
echo "🚀 Starting Minimal FastAPI Server..."
/home/yun/Documents/backtrader/.venv/bin/python -m uvicorn app.main_minimal:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level info

echo ""
echo "==================================="
echo "✅ Server Started!"
echo "==================================="
echo ""
echo "📋 API Documentation: http://0.0.0.0:8000/docs"
echo "📋 Health Check: http://0.0.0.0:8000/health"
echo "📋 Root Route: http://0.0.0.0:8000/"
echo ""
echo "Available Endpoints:"
echo "  - Authentication: /api/v1/auth/*"
echo "  - Strategies: /api/v1/strategies/*"
echo "  - Backtests: /api/v1/backtests/*"
echo "  - Paper Trading: /api/v1/paper-trading/*"
echo "  - Analytics: /api/v1/analytics/*"
echo ""
echo "Press Ctrl+C to stop"
echo ""
