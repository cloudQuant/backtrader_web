#!/bin/bash

###############################################################################
# Backtrader Web - 停止脚本
###############################################################################

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$PROJECT_ROOT/.pids"

# PID 文件
BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"

echo -e "${CYAN}"
echo "======================================"
echo "  Backtrader Web - 停止项目"
echo "======================================"
echo -e "${NC}"

STOPPED_BACKEND=false
STOPPED_FRONTEND=false

###############################################################################
# 停止后端
###############################################################################

if [ -f "$BACKEND_PID_FILE" ]; then
    BACKEND_PID=$(cat "$BACKEND_PID_FILE")
    echo -e "${BLUE}停止后端服务...${NC}"

    if ps -p "$BACKEND_PID" > /dev/null 2>&1; then
        kill "$BACKEND_PID"
        sleep 1

        # 如果还没停止，强制杀死
        if ps -p "$BACKEND_PID" > /dev/null 2>&1; then
            echo -e "  ${YELLOW}强制停止后端服务...${NC}"
            kill -9 "$BACKEND_PID" 2>/dev/null || true
        fi

        echo -e "  ${GREEN}后端服务已停止 (PID: $BACKEND_PID)${NC}"
        STOPPED_BACKEND=true
    else
        echo -e "  ${YELLOW}后端服务未运行 (PID: $BACKEND_PID)${NC}"
    fi

    rm -f "$BACKEND_PID_FILE"
else
    echo -e "${YELLOW}后端 PID 文件不存在${NC}"
fi

###############################################################################
# 停止前端
###############################################################################

if [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
    echo -e "${BLUE}停止前端服务...${NC}"

    if ps -p "$FRONTEND_PID" > /dev/null 2>&1; then
        kill "$FRONTEND_PID"
        sleep 1

        # 如果还没停止，强制杀死
        if ps -p "$FRONTEND_PID" > /dev/null 2>&1; then
            echo -e "  ${YELLOW}强制停止前端服务...${NC}"
            kill -9 "$FRONTEND_PID" 2>/dev/null || true
        fi

        echo -e "  ${GREEN}前端服务已停止 (PID: $FRONTEND_PID)${NC}"
        STOPPED_FRONTEND=true
    else
        echo -e "  ${YELLOW}前端服务未运行 (PID: $FRONTEND_PID)${NC}"
    fi

    rm -f "$FRONTEND_PID_FILE"
else
    echo -e "${YELLOW}前端 PID 文件不存在${NC}"
fi

###############################################################################
# 清理可能残留的进程
###############################################################################

echo ""
echo -e "${BLUE}清理残留进程...${NC}"

# 查找并停止可能残留的 uvicorn 进程
REMAINING_BACKEND=$(ps aux | grep -v grep | grep "uvicorn app.main:app" | awk '{print $2}' || true)
if [ -n "$REMAINING_BACKEND" ]; then
    echo -e "  ${YELLOW}停止残留的后端进程...${NC}"
    echo "$REMAINING_BACKEND" | xargs kill -9 2>/dev/null || true
fi

# 查找并停止可能残留的 vite 进程
REMAINING_FRONTEND=$(ps aux | grep -v grep | grep "vite.*backtrader" | awk '{print $2}' || true)
if [ -n "$REMAINING_FRONTEND" ]; then
    echo -e "  ${YELLOW}停止残留的前端进程...${NC}"
    echo "$REMAINING_FRONTEND" | xargs kill -9 2>/dev/null || true
fi

# 查找并停止占用端口的进程
# 端口 8000
OCCUPIED_8000=$(lsof -ti:8000 2>/dev/null || true)
if [ -n "$OCCUPIED_8000" ]; then
    echo -e "  ${YELLOW}停止占用端口 8000 的进程...${NC}"
    echo "$OCCUPIED_8000" | xargs kill -9 2>/dev/null || true
fi

# 端口 3000
OCCUPIED_3000=$(lsof -ti:3000 2>/dev/null || true)
if [ -n "$OCCUPIED_3000" ]; then
    echo -e "  ${YELLOW}停止占用端口 3000 的进程...${NC}"
    echo "$OCCUPIED_3000" | xargs kill -9 2>/dev/null || true
fi

###############################################################################
# 完成
###############################################################################

echo ""
if [ "$STOPPED_BACKEND" = true ] || [ "$STOPPED_FRONTEND" = true ]; then
    echo -e "${GREEN}======================================"
    echo "  服务已停止"
    echo "======================================${NC}"
else
    echo -e "${YELLOW}======================================"
    echo "  没有运行中的服务"
    echo "======================================${NC}"
fi
echo ""
echo -e "  ${CYAN}启动服务:${NC} ./scripts/start_app.sh"
echo ""
