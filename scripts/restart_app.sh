#!/bin/bash

###############################################################################
# Backtrader Web - 重启脚本
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

# 获取脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${PURPLE}"
echo "======================================"
echo "  Backtrader Web - 重启项目"
echo "======================================"
echo -e "${NC}"

echo -e "${BLUE}[1/3]${NC} 停止服务..."
echo ""

# 先停止服务
bash "$SCRIPT_DIR/stop_app.sh"

echo ""
echo -e "${BLUE}[2/3]${NC} 等待端口释放..."
sleep 2

echo ""
echo -e "${BLUE}[3/3]${NC} 启动服务..."
echo ""

# 启动服务
bash "$SCRIPT_DIR/start_app.sh"
