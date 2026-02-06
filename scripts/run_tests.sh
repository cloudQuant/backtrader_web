#!/bin/bash

###############################################################################
# Backtrader Web - 测试运行脚本
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
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]})/.." )" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/src/backend"

echo -e "${CYAN}"
echo "======================================"
echo "  Backtrader Web - 运行测试"
echo "======================================"
echo -e "${NC}"

# 默认选项
TEST_TYPE="unit"
HEADED=""
VERBOSE=""
COVERAGE=""

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        unit|unit-test)
            TEST_TYPE="unit"
            shift
            ;;
        e2e|end-to-end)
            TEST_TYPE="e2e"
            shift
            ;;
        all)
            TEST_TYPE="all"
            shift
            ;;
        --headed)
            HEADED="--headed"
            shift
            ;;
        -v|--verbose)
            VERBOSE="-v -s"
            shift
            ;;
        --cov|--coverage)
            COVERAGE="--cov=app --cov-report=html --cov-report=term"
            shift
            ;;
        --help)
            echo "用法: ./scripts/run_tests.sh [选项]"
            echo ""
            echo "选项:"
            echo "  unit, unit-test  运行单元测试 (默认)"
            echo "  e2e             运行E2E测试 (需要应用运行)"
            echo "  all             运行所有测试"
            echo "  --headed        E2E测试显示浏览器窗口"
            echo "  -v, --verbose   详细输出"
            echo "  --cov           生成覆盖率报告"
            echo "  --help          显示帮助"
            exit 0
            ;;
        *)
            echo -e "${RED}未知参数: $1${NC}"
            exit 1
            ;;
    esac
done

cd "$BACKEND_DIR"

# 检查虚拟环境
if [ -d "venv" ]; then
    echo -e "${BLUE}激活虚拟环境...${NC}"
    source venv/bin/activate
fi

# 检查依赖
echo -e "${BLUE}检查测试依赖...${NC}"

if ! python -c "import pytest" 2>/dev/null; then
    echo -e "${YELLOW}安装测试依赖...${NC}"
    pip install -q pytest pytest-asyncio httpx
fi

###############################################################################
# 运行单元测试
###############################################################################

run_unit_tests() {
    echo ""
    echo -e "${BLUE}[1/2]${NC} 运行单元测试..."
    echo ""

    pytest tests/ -m "not e2e" $VERBOSE $COVERAGE \
        --tb=short \
        -W ignore::DeprecationWarning

    local exit_code=$?

    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}单元测试通过!${NC}"
    else
        echo -e "${RED}单元测试失败!${NC}"
    fi

    return $exit_code
}

###############################################################################
# 运行E2E测试
###############################################################################

run_e2e_tests() {
    echo ""
    echo -e "${BLUE}[2/2]${NC} 运行E2E测试..."
    echo ""

    # 检查服务是否运行
    echo -e "${CYAN}检查服务状态...${NC}"

    BACKEND_RUNNING=false
    FRONTEND_RUNNING=false

    if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} 后端服务运行中"
        BACKEND_RUNNING=true
    else
        echo -e "  ${RED}✗${NC} 后端服务未运行 (需要启动: ./scripts/start_app.sh)"
    fi

    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} 前端服务运行中"
        FRONTEND_RUNNING=true
    else
        echo -e "  ${YELLOW}!${NC} 前端服务未运行 (部分E2E测试可能失败)"
    fi

    if [ "$BACKEND_RUNNING" = false ]; then
        echo -e "${RED}错误: E2E测试需要后端服务运行${NC}"
        echo -e "${YELLOW}请先启动服务: ./scripts/start_app.sh${NC}"
        return 1
    fi

    echo ""
    echo -e "${CYAN}安装Playwright浏览器...${NC}"

    # 安装playwright浏览器
    if ! python -c "import playwright" 2>/dev/null; then
        pip install -q playwright pytest-playwright
    fi

    playwright install chromium --quiet 2>/dev/null || true

    echo ""
    echo -e "${CYAN}运行E2E测试...${NC}"

    pytest tests/test_e2e.py $VERBOSE $HEADED \
        --tb=short \
        -W ignore::DeprecationWarning \
        --timeout=60

    local exit_code=$?

    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}E2E测试通过!${NC}"
    else
        echo -e "${RED}E2E测试失败!${NC}"
    fi

    return $exit_code
}

###############################################################################
# 主执行流程
###############################################################################

MAIN_EXIT_CODE=0

case $TEST_TYPE in
    unit)
        run_unit_tests
        MAIN_EXIT_CODE=$?
        ;;
    e2e)
        run_e2e_tests
        MAIN_EXIT_CODE=$?
        ;;
    all)
        run_unit_tests
        UNIT_EXIT_CODE=$?

        run_e2e_tests
        E2E_EXIT_CODE=$?

        if [ $UNIT_EXIT_CODE -ne 0 ] || [ $E2E_EXIT_CODE -ne 0 ]; then
            MAIN_EXIT_CODE=1
        fi
        ;;
esac

###############################################################################
# 完成
###############################################################################

echo ""
if [ $MAIN_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}======================================"
    echo "  测试完成!"
    echo "======================================${NC}"
else
    echo -e "${RED}======================================"
    echo "  测试失败"
    echo "======================================${NC}"
fi

if [ -n "$COVERAGE" ] && [ -f "htmlcov/index.html" ]; then
    echo ""
    echo -e "${CYAN}覆盖率报告: ${NC}file://$BACKEND_DIR/htmlcov/index.html"
fi

echo ""

exit $MAIN_EXIT_CODE
