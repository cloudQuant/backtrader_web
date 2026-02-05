#!/bin/bash
"""
快速安装后端依赖

安装所有需要的包，确保项目可以运行
"""

PROJECT_ROOT="/home/yun/Documents/backtrader_web"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo "==================================="
echo "🚀 Installing Dependencies"
echo "==================================="
echo ""

# 1. 升级 pip
echo "1. Upgrading pip..."
python3 -m pip install --upgrade pip --quiet

# 2. 安装后端核心依赖
echo ""
echo "2. Installing backend dependencies..."
cd "$BACKEND_DIR"

# 核心 Web 框架
echo "   - FastAPI & Uvicorn..."
python3 -m pip install --quiet \
    fastapi==0.104.1 \
    uvicorn[standard]==0.27.0 \
    python-multipart

# 数据验证
echo "   - Pydantic..."
python3 -m pip install --quiet \
    pydantic==2.5.0 \
    pydantic-settings==2.1.0 \
    email-validator

# 数据库
echo "   - SQLAlchemy..."
python3 -m pip install --quiet \
    sqlalchemy==2.0.23 \
    sqlalchemy-utils==0.41.1 \
    psycopg2-binary==2.9.9

# 认证和安全
echo "   - Auth & Security..."
python3 -m pip install --quiet \
    passlib[bcrypt]==1.7.4 \
    python-jose[cryptography]==3.3.0 \
    python-multipart

# API 和工具
echo "   - API Tools..."
python3 -m pip install --quiet \
    httpx==0.24.0 \
    slowapi==0.1.9

# 任务队列
echo "   - Task Queue..."
python3 -m pip install --quiet \
    redis==5.0.1 \
    celery==5.3.4

# WebSocket
echo "   - WebSocket..."
python3 -m pip install --quiet \
    websockets==12.0

# 文档生成
echo "   - Documentation..."
python3 -m pip install --quiet \
    alembic==1.12.1

# 实时数据处理
echo "   - Realtime Data..."
python3 -m pip install --quiet \
    pandas==2.1.4 \
    numpy==1.26.4

# 回测和策略
echo "   - Backtrader Tools..."
python3 -m pip install --quiet \
    backtrader==1.9.78 \
    ccxt==4.2.25

# 文件生成
echo "   - Report Generation..."
python3 -m pip install --quiet \
    reportlab==4.0.7 \
    openpyxl==3.1.2 \
    jinja2==3.1.3

echo "   ✅ Backend dependencies installed"

# 3. 安装测试依赖
echo ""
echo "3. Installing test dependencies..."
python3 -m pip install --quiet \
    pytest==7.4.3 \
    pytest-asyncio==0.21.0 \
    pytest-cov==4.1.0 \
    pytest-mock==3.11.1 \
    httpx==0.24.0

echo "   ✅ Test dependencies installed"

# 4. 验证安装
echo ""
echo "4. Verifying installation..."
echo ""
echo "   Checking FastAPI..."
python3 -c "import fastapi; print('✓ FastAPI:', fastapi.__version__)" 2>&1 || echo "   ✗ FastAPI: Failed"
echo ""
echo "   Checking Pydantic..."
python3 -c "import pydantic; print('✓ Pydantic:', pydantic.__version__)" 2>&1 || echo "   ✗ Pydantic: Failed"
echo ""
echo "   Checking SQLAlchemy..."
python3 -c "import sqlalchemy; print('✓ SQLAlchemy:', sqlalchemy.__version__)" 2>&1 || echo "   ✗ SQLAlchemy: Failed"
echo ""
echo "   Checking Backtrader..."
python3 -c "import backtrader; print('✓ Backtrader: Available')" 2>&1 || echo "   ✗ Backtrader: Not Available"

echo ""
echo "==================================="
echo "✅ Dependencies Installation Complete!"
echo "==================================="
echo ""
echo "Next Steps:"
echo "1. Check that all modules import correctly"
echo "2. Run: cd $BACKEND_DIR && python3 quick_test.py"
echo "3. Run: cd $BACKEND_DIR && python3 -m pytest tests/test_websocket_manager.py -v"
echo ""
