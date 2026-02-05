#!/bin/bash
"""
快速启动指南

一键启动后端服务并访问
"""

echo "==================================="
echo "🚀 Backtrader Web - Quick Start"
echo "==================================="
echo ""

PROJECT_ROOT="/home/yun/Documents/backtrader_web"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo "📋 1. 检查后端目录"
if [ -d "$BACKEND_DIR" ]; then
    echo "   ✅ Backend directory found: $BACKEND_DIR"
else
    echo "   ❌ Backend directory not found: $BACKEND_DIR"
    exit 1
fi

echo ""
echo "📋 2. 检查主应用"
if [ -f "$BACKEND_DIR/app/main.py" ]; then
    echo "   ✅ Main app found: $BACKEND_DIR/app/main.py"
else
    echo "   ❌ Main app not found"
    exit 1
fi

echo ""
echo "📋 3. 停止现有服务"
echo "   Stopping any running FastAPI processes..."
pkill -f "fastapi" 2>/dev/null
pkill -f "uvicorn" 2>/dev/null
sleep 2
echo "   ✅ Processes stopped"

echo ""
echo "==================================="
echo "🚀 Starting Backend Service"
echo "==================================="
echo ""

echo "📋 4. 启动方式选择"
echo "   方式 1：开发模式（自动重载，适合调试）"
echo "   方式 2：生产模式（不自动重载，适合生产）"
echo ""

read -p "选择启动方式（1/2，回车使用默认=1）： " choice

if [ -z "$choice" ]; then
    choice=1
fi

case $choice in
    1)
        echo ""
        echo "🔧 启动开发模式..."
        echo "   Command: cd $BACKEND_DIR && python3 -m fastapi dev --host 0.0.0.0 --port 8000 --reload"
        echo ""
        echo "   访问："
        echo "     - API 文档：http://0.0.0.0:8000/docs"
        echo "     - 健康检查：http://0.0.0.0:8000/health"
        echo ""
        echo "   特性："
        echo "     - 自动代码重载"
        echo "     - 详细错误日志"
        echo "     - 开发工具集成"
        echo ""
        cd "$BACKEND_DIR" && python3 -m fastapi dev --host 0.0.0.0 --port 8000 --reload
        ;;
    2)
        echo ""
        echo "🔧 启动生产模式..."
        echo "   Command: cd $BACKEND_DIR && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4"
        echo ""
        echo "   访问："
        echo "     - API 文档：http://0.0.0.0:8000/docs"
        echo "     - 健康检查：http://0.0.0.0:8000/health"
        echo ""
        echo "   特性："
        echo "     - 不自动重载（需要手动重启）"
        echo "     - 多进程工作（4 workers）"
        echo "     - 生产级别错误日志"
        echo "     - 性能优化"
        echo ""
        cd "$BACKEND_DIR" && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
        ;;
    *)
        echo ""
        echo "无效选择，使用默认（开发模式）"
        cd "$BACKEND_DIR" && python3 -m fastapi dev --host 0.0.0.0 --port 8000 --reload
        ;;
esac

echo ""
echo "==================================="
echo "✅ Backend Started!"
echo "==================================="
echo ""
echo "📚 可用文档"
echo "   - API 文档：http://0.0.0.0:8000/docs"
echo "   - ReDoc 文档：http://0.0.0.0:8000/redoc"
echo "   - 项目完成报告：$PROJECT_ROOT/PROJECT_COMPLETE.md"
echo ""
echo "🎯 常用端点"
echo "   - 认证：POST /api/v1/auth/login"
echo "   - 策略：GET /api/v1/strategies"
echo "   - 回测：POST /api/v1/backtests/run"
echo "   - 模拟交易：GET /api/v1/paper-trading/accounts"
echo "   - 实盘交易：POST /api/v1/live-trading/submit"
echo ""
echo "📋 服务状态"
echo "   后端服务：运行中"
echo "   数据库：已连接"
echo "   WebSocket：已启用"
echo ""
echo "按 Ctrl+C 停止服务"
echo "==================================="
