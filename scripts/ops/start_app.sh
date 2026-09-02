#!/bin/bash

###############################################################################
# AI for Investor - 启动脚本
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
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/src/backend"
FRONTEND_DIR="$PROJECT_ROOT/src/frontend"
PID_DIR="$PROJECT_ROOT/.pids"
LOG_DIR="$PROJECT_ROOT/logs"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python || true)}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
BACKEND_HEALTH_URL="${BACKEND_HEALTH_URL:-http://127.0.0.1:${BACKEND_PORT}/health}"
# 首次冷启动需加载本地嵌入模型（含 PyTorch/MPS 初始化），30 秒常不够用。
BACKEND_STARTUP_TIMEOUT_SECONDS="${BACKEND_STARTUP_TIMEOUT_SECONDS:-120}"

# PID 文件
BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"

# 日志文件
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

# 创建必要目录
mkdir -p "$PID_DIR"
mkdir -p "$LOG_DIR"

start_background() {
    local log_file="$1"
    shift

    if command -v setsid >/dev/null 2>&1; then
        setsid "$@" > "$log_file" 2>&1 &
    else
        nohup "$@" > "$log_file" 2>&1 &
    fi
    echo $!
}

backend_is_running() {
    ps -p "$BACKEND_PID" > /dev/null 2>&1
}

backend_is_healthy() {
    local response
    response=$(curl --fail --silent --max-time 2 "$BACKEND_HEALTH_URL" 2>/dev/null) || return 1
    printf '%s\n' "$response" | grep -Eq '"database"[[:space:]]*:[[:space:]]*"connected"'
}

wait_for_backend_ready() {
    local elapsed=0

    while [ "$elapsed" -lt "$BACKEND_STARTUP_TIMEOUT_SECONDS" ]; do
        if ! backend_is_running; then
            return 1
        fi
        if backend_is_healthy; then
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    return 1
}

show_backend_startup_failure() {
    echo -e "${RED}后端服务启动失败或健康检查未通过: $BACKEND_HEALTH_URL${NC}"
    echo -e "${YELLOW}请确认数据库服务已启动，并查看日志: $BACKEND_LOG${NC}"
    tail -20 "$BACKEND_LOG" || true
}

stop_started_backend() {
    # 启动失败时回收本次拉起的后端进程，避免残留进程继续占用端口，
    # 导致下一次重启误判“端口被占用”或健康检查打到旧进程。
    if [ -n "${BACKEND_PID:-}" ] && ps -p "$BACKEND_PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}正在停止本次启动的后端进程 (PID: $BACKEND_PID)...${NC}"
        kill "$BACKEND_PID" 2>/dev/null || true
        for _ in 1 2 3 4 5; do
            ps -p "$BACKEND_PID" > /dev/null 2>&1 || break
            sleep 1
        done
        kill -9 "$BACKEND_PID" 2>/dev/null || true
    fi
}

echo -e "${CYAN}"
echo "======================================"
echo "  AI for Investor - 启动项目"
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
if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
    echo -e "${RED}错误: 未找到 Python，请先激活项目 Python 环境或设置 PYTHON_BIN${NC}"
    exit 1
fi
if ! [[ "$BACKEND_STARTUP_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
    echo -e "${RED}错误: BACKEND_STARTUP_TIMEOUT_SECONDS 必须是正整数${NC}"
    exit 1
fi
PYTHON_VERSION=$("$PYTHON_BIN" --version | awk '{print $2}')
echo -e "  Python 版本: ${GREEN}$PYTHON_VERSION${NC}"

# 检查 Python 依赖
echo -e "  ${BLUE}检查 Python 依赖...${NC}"
MISSING_DEPS=0
for pkg in fastapi uvicorn sqlalchemy pydantic; do
    if ! "$PYTHON_BIN" -c "import $pkg" 2>/dev/null; then
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
if ! command -v curl &> /dev/null; then
    echo -e "${RED}错误: 未找到 curl，无法验证后端健康状态${NC}"
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

# 启动后端
BACKEND_HOST="${HOST:-0.0.0.0}"
BACKEND_DEBUG="${DEBUG:-true}"
echo -e "  ${GREEN}启动 FastAPI 服务 (端口 ${BACKEND_PORT}, 地址 ${BACKEND_HOST})...${NC}"
BACKEND_PID=$(start_background "$BACKEND_LOG" env DEBUG="$BACKEND_DEBUG" HOST="$BACKEND_HOST" "$PYTHON_BIN" -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT")
echo $BACKEND_PID > "$BACKEND_PID_FILE"

# 等待后端启动并验证应用完成生命周期初始化。
if wait_for_backend_ready; then
    echo -e "  ${GREEN}后端服务启动成功 (PID: $BACKEND_PID)${NC}"
else
    show_backend_startup_failure
    stop_started_backend
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
    FRONTEND_PID=$(start_background "$FRONTEND_LOG" npm run dev)
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
if backend_is_running && backend_is_healthy; then
    echo -e "  ${GREEN}✓${NC} 后端服务运行中 (${BACKEND_HEALTH_URL})"
else
    echo -e "  ${RED}✗${NC} 后端服务未运行或健康检查失败"
    show_backend_startup_failure
    stop_started_backend
    rm -f "$BACKEND_PID_FILE"
    exit 1
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
echo -e "=====================================${NC}"
echo ""
echo -e "  ${CYAN}前端地址:${NC} http://localhost:3000"
echo -e "  ${CYAN}后端地址:${NC} http://localhost:${BACKEND_PORT}"
echo -e "  ${CYAN}API文档:${NC}  http://localhost:${BACKEND_PORT}/docs"
echo -e "  ${CYAN}WebSocket:${NC} ws://localhost:${BACKEND_PORT}/ws"
echo ""
echo -e "  ${YELLOW}日志目录:${NC} $LOG_DIR"
echo -e "  ${YELLOW}PID目录:${NC} $PID_DIR"
echo ""
echo -e "  ${GREEN}停止服务:${NC} ./scripts/stop_app.sh"
echo -e "  ${GREEN}重启服务:${NC} ./scripts/restart_app.sh"
echo -e "  ${GREEN}查看日志:${NC} tail -f logs/*.log"
echo ""
