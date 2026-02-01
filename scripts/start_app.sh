#!/bin/bash

###############################################################################
# Backtrader Web - 启动脚本
###############################################################################

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
PID_DIR="$PROJECT_ROOT/.pids"
LOG_DIR="$PROJECT_ROOT/logs"

# PID 文件
BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"

# 日志文件
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

# 创建必要目录
mkdir -p "$PID_DIR"
mkdir -p "$LOG_DIR"

echo -e "${CYAN}"
echo "======================================"
echo "  Backtrader Web - 启动项目"
echo "======================================"
echo -e "${NC}"

# 检查是否已启动
if [ -f "$BACKEND_PID_FILE" ]; then
    BACKEND_PID=$(cat "$BACKEND_PID_FILE")
    if ps -p "$BACKEND_PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}后端服务已在运行 (PID: $BACKEND_PID)${NC}"
        echo -e "如需重启，请先运行: ${CYAN}./scripts/stop_app.sh${NC}"
        exit 1
    fi
    rm -f "$BACKEND_PID_FILE"
fi

if [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
    if ps -p "$FRONTEND_PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}前端服务已在运行 (PID: $FRONTEND_PID)${NC}"
        echo -e "如需重启，请先运行: ${CYAN}./scripts/stop_app.sh${NC}"
        exit 1
    fi
    rm -f "$FRONTEND_PID_FILE"
fi

###############################################################################
# 检查依赖
###############################################################################

echo -e "${BLUE}[1/4]${NC} 检查环境依赖..."

# 检查 Python
if ! command -v python &> /dev/null; then
    echo -e "${RED}错误: 未找到 Python，请先安装 Python 3.10+${NC}"
    exit 1
fi
PYTHON_VERSION=$(python --version | awk '{print $2}')
echo -e "  Python 版本: ${GREEN}$PYTHON_VERSION${NC}"

# 检查 Python 依赖
echo -e "  ${BLUE}检查 Python 依赖...${NC}"
MISSING_DEPS=0
for pkg in fastapi uvicorn sqlalchemy pydantic; do
    if ! python -c "import $pkg" 2>/dev/null; then
        echo -e "  ${YELLOW}✗${NC} $pkg 未安装"
        MISSING_DEPS=1
    fi
done

if [ $MISSING_DEPS -eq 1 ]; then
    echo -e "${RED}错误: 缺少 Python 依赖，请先安装:${NC}"
    echo -e "  ${YELLOW}pip install -r requirements.txt${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Python 依赖完整"

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}错误: 未找到 Node.js，请先安装 Node.js 18+${NC}"
    exit 1
fi
NODE_VERSION=$(node --version)
echo -e "  Node.js 版本: ${GREEN}$NODE_VERSION${NC}"

# 检查 npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}错误: 未找到 npm${NC}"
    exit 1
fi

###############################################################################
# 后端启动
###############################################################################

echo ""
echo -e "${BLUE}[2/4]${NC} 启动后端服务..."

cd "$BACKEND_DIR"

# 复制环境变量文件
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "  ${YELLOW}已创建 .env 文件${NC}"
    else
        echo -e "  ${YELLOW}警告: .env.example 不存在，跳过创建${NC}"
    fi
fi

# 启动后端（使用系统Python）
echo -e "  ${GREEN}启动 FastAPI 服务 (端口 8000)...${NC}"
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$BACKEND_PID_FILE"

# 等待后端启动
sleep 3

if ps -p "$BACKEND_PID" > /dev/null 2>&1; then
    echo -e "  ${GREEN}后端服务启动成功 (PID: $BACKEND_PID)${NC}"
else
    echo -e "${RED}后端服务启动失败，请查看日志: $BACKEND_LOG${NC}"
    cat "$BACKEND_LOG" | tail -20
    rm -f "$BACKEND_PID_FILE"
    exit 1
fi

###############################################################################
# 前端启动
###############################################################################

echo ""
echo -e "${BLUE}[3/4]${NC} 启动前端服务..."

cd "$FRONTEND_DIR"

# 检查前端目录是否存在
if [ ! -d "$FRONTEND_DIR" ]; then
    echo -e "${YELLOW}警告: 前端目录不存在，跳过前端启动${NC}"
else
    # 安装依赖
    if [ ! -d "node_modules" ]; then
        echo -e "  ${YELLOW}安装 NPM 依赖...${NC}"
        npm install --silent
    fi

    # 启动前端
    echo -e "  ${GREEN}启动 Vite 开发服务器 (端口 3000)...${NC}"
    nohup npm run dev > "$FRONTEND_LOG" 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > "$FRONTEND_PID_FILE"

    # 等待前端启动
    sleep 3

    if ps -p "$FRONTEND_PID" > /dev/null 2>&1; then
        echo -e "  ${GREEN}前端服务启动成功 (PID: $FRONTEND_PID)${NC}"
    else
        echo -e "${YELLOW}前端服务启动失败，请查看日志: $FRONTEND_LOG${NC}"
        cat "$FRONTEND_LOG" | tail -10
        rm -f "$FRONTEND_PID_FILE"
    fi
fi

###############################################################################
# 服务状态
###############################################################################

echo ""
echo -e "${BLUE}[4/4]${NC} 服务状态检查..."

sleep 2

# 检查后端
if ps -p "$BACKEND_PID" > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} 后端服务运行中 (http://localhost:8000)"
else
    echo -e "  ${RED}✗${NC} 后端服务未运行"
fi

# 检查前端
if [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
    if ps -p "$FRONTEND_PID" > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} 前端服务运行中 (http://localhost:3000)"
    else
        echo -e "  ${YELLOW}!${NC} 前端服务未运行"
    fi
fi

###############################################################################
# 完成
###############################################################################

echo ""
echo -e "${PURPLE}====================================="
echo "  服务启动完成！"
echo "=====================================${NC}"
echo ""
echo -e "  ${CYAN}前端地址:${NC} http://localhost:3000"
echo -e "  ${CYAN}后端地址:${NC} http://localhost:8000"
echo -e "  ${CYAN}API文档:${NC}  http://localhost:8000/docs"
echo -e "  ${CYAN}WebSocket:${NC} ws://localhost:8000/ws"
echo ""
echo -e "  ${YELLOW}日志目录:${NC} $LOG_DIR"
echo -e "  ${YELLOW}PID目录:${NC} $PID_DIR"
echo ""
echo -e "  ${GREEN}停止服务:${NC} ./scripts/stop_app.sh"
echo -e "  ${GREEN}重启服务:${NC} ./scripts/restart_app.sh"
echo -e "  ${GREEN}查看日志:${NC} tail -f logs/*.log"
echo ""
