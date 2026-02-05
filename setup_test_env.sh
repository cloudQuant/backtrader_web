#!/bin/bash
"""
安装测试依赖脚本

为 backtrader_web 项目创建虚拟环境并安装所有依赖
"""

run_command() {
    "$@"
}

main() {
    PROJECT_ROOT=$(dirname "$0")
    BACKEND_DIR="$PROJECT_ROOT/backtrader_web/backend"

    echo "================================"
    echo "📦 Setting up Backtrader Web Test Environment"
    echo "================================"
    echo ""

    # 1. 创建虚拟环境
    echo "📦 Creating virtual environment..."
    python3 -m venv "$BACKEND_DIR/.venv"
    echo "✓ Virtual environment created"
    echo ""

    # 2. 升级 pip
    echo "📦 Upgrading pip..."
    "$BACKEND_DIR/.venv/bin/python" -m pip install --upgrade pip
    echo ""

    # 3. 安装测试依赖
    echo "📦 Installing test dependencies..."
    "$BACKEND_DIR/.venv/bin/pip" install \
        pytest \
        pytest-asyncio \
        pytest-cov \
        pytest-mock \
        httpx \
        coverage
    echo "✓ Test dependencies installed"
    echo ""

    # 4. 安装后端依赖
    echo "📦 Installing backend dependencies..."
    "$BACKEND_DIR/.venv/bin/pip" install \
        fastapi \
        uvicorn[standard] \
        sqlalchemy \
        sqlalchemy-utils \
        pydantic \
        python-jose \
        passlib[bcrypt] \
        python-multipart \
        alem \
        redis \
        slowapi \
        websockets
    echo "✓ Backend dependencies installed"
    echo ""

    # 5. 安装 backtrader
    echo "📦 Installing backtrader..."
    "$BACKEND_DIR/.venv/bin/pip" install \
        -e ../backtrader \
        pandas \
        numpy \
        ccxt
    echo "✓ Backtrader installed"
    echo ""

    echo "================================"
    echo "✅ Setup complete!"
    echo "================================"
    echo ""
    echo "To activate the virtual environment:"
    echo "  source $BACKEND_DIR/.venv/bin/activate"
    echo ""
    echo "To run the application:"
    echo "  cd $BACKEND_DIR"
    echo "  $BACKEND_DIR/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
    echo ""
    echo "To run tests:"
    echo "  cd $BACKEND_DIR"
    echo "  $BACKEND_DIR/.venv/bin/python -m pytest tests/ -v"
    echo ""
    echo "================================"
}

main
