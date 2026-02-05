#!/bin/bash
"""
使用 pip 安装依赖（正确方式）

在虚拟环境中使用 pip，避免 externally-managed-environment 错误
"""

PROJECT_ROOT="/home/yun/Documents/backtrader_web"
BACKEND_DIR="$PROJECT_ROOT/backend"
VENV_DIR="$BACKEND_DIR/.venv"

echo "==================================="
echo "🚀 Using pip to Install Dependencies"
echo "==================================="
echo ""

# 1. 创建虚拟环境（如果不存在）
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "✅ Virtual environment created: $VENV_DIR"
else
    echo "✅ Virtual environment already exists: $VENV_DIR"
fi

echo ""
echo "==================================="
echo "📦 Activating Virtual Environment"
echo "==================================="
echo ""

# 2. 激活虚拟环境
source "$VENV_DIR/bin/activate"

echo "✅ Virtual environment activated"
echo "   Python: $(which python)"
echo "   Pip: $(which pip)"
echo ""

# 3. 升级 pip
echo "📦 Upgrading pip..."
pip install --upgrade pip --quiet
echo "✅ Pip upgraded: $(pip --version)"
echo ""

# 4. 安装核心依赖
echo "==================================="
echo "📦 Installing Core Dependencies"
echo "==================================="
echo ""

echo "Installing FastAPI..."
pip install fastapi==0.104.1 --quiet
echo "✅ FastAPI installed"

echo "Installing Uvicorn..."
pip install 'uvicorn[standard]'==0.27.0 --quiet
echo "✅ Uvicorn installed"

echo "Installing Pydantic..."
pip install 'pydantic==2.5.0' --quiet
echo "✅ Pydantic installed"

echo "Installing Pydantic-Settings..."
pip install 'pydantic-settings==2.1.0' --quiet
echo "✅ Pydantic-Settings installed"

echo "Installing SQLAlchemy..."
pip install 'sqlalchemy==2.0.23' --quiet
echo "✅ SQLAlchemy installed"

echo "Installing SQLAlchemy-Utils..."
pip install 'sqlalchemy-utils==0.41.1' --quiet
echo "✅ SQLAlchemy-Utils installed"

echo "Installing Passlib..."
pip install 'passlib[bcrypt]'==1.7.4 --quiet
echo "✅ Passlib installed"

echo "Installing python-jose..."
pip install 'python-jose[cryptography]'==3.3.0 --quiet
echo "✅ python-jose installed"

echo "Installing python-multipart..."
pip install 'python-multipart' --quiet
echo "✅ python-multipart installed"

echo ""
echo "==================================="
echo "📦 Installing Async Dependencies"
echo "==================================="
echo ""

echo "Installing httpx..."
pip install 'httpx==0.24.0' --quiet
echo "✅ httpx installed"

echo "Installing slowapi..."
pip install 'slowapi==0.1.9' --quiet
echo "✅ slowapi installed"

echo "Installing websockets..."
pip install 'websockets==12.0' --quiet
echo "✅ websockets installed"

echo "Installing redis..."
pip install 'redis==5.0.1' --quiet
echo "✅ redis installed"

echo "Installing celery..."
pip install 'celery==5.3.4' --quiet
echo "✅ celery installed"

echo "Installing alembic..."
pip install 'alembic==1.12.1' --quiet
echo "✅ alembic installed"

echo ""
echo "==================================="
echo "📦 Installing Report Dependencies"
echo "==================================="
echo ""

echo "Installing reportlab..."
pip install 'reportlab==4.0.7' --quiet
echo "✅ reportlab installed"

echo "Installing openpyxl..."
pip install 'openpyxl==3.1.2' --quiet
echo "✅ openpyxl installed"

echo "Installing jinja2..."
pip install 'jinja2==3.1.3' --quiet
echo "✅ jinja2 installed"

echo ""
echo "==================================="
echo "📦 Installing Test Dependencies"
echo "==================================="
echo ""

echo "Installing pytest..."
pip install 'pytest==7.4.3' --quiet
echo "✅ pytest installed"

echo "Installing pytest-asyncio..."
pip install 'pytest-asyncio==0.21.0' --quiet
echo "✅ pytest-asyncio installed"

echo "Installing pytest-cov..."
pip install 'pytest-cov==4.1.0' --quiet
echo "✅ pytest-cov installed"

echo "Installing pytest-mock..."
pip install 'pytest-mock==3.11.1' --quiet
echo "✅ pytest-mock installed"

echo "Installing coverage..."
pip install 'coverage==7.3.2' --quiet
echo "✅ coverage installed"

echo ""
echo "==================================="
echo "📦 Installing Trading Dependencies"
echo "==================================="
echo ""

echo "Installing pandas..."
pip install 'pandas==2.1.4' --quiet
echo "✅ pandas installed"

echo "Installing numpy..."
pip install 'numpy==1.26.4' --quiet
echo "✅ numpy installed"

echo "Installing backtrader..."
pip install 'backtrader==1.9.78' --quiet
echo "✅ backtrader installed"

echo "Installing ccxt..."
pip install 'ccxt==4.2.25' --quiet
echo "✅ ccxt installed"

echo ""
echo "==================================="
echo "✅ All Dependencies Installed Successfully!"
echo "==================================="
echo ""

# 5. 验证安装
echo "==================================="
echo "🔍 Verifying Installation"
echo "==================================="
echo ""

echo "Python: $(python --version)"
echo "Pip: $(pip --version)"
echo ""

echo "FastAPI: $(python -c 'import fastapi; print(fastapi.__version__)')"
echo "Uvicorn: $(python -c 'import uvicorn; print(uvicorn.__version__)')"
echo "Pydantic: $(python -c 'import pydantic; print(pydantic.__version__)')"
echo "SQLAlchemy: $(python -c 'import sqlalchemy; print(sqlalchemy.__version__)')"
echo "pytest: $(python -c 'import pytest; print(pytest.__version__)')"
echo "Backtrader: $(python -c 'import backtrader; print(backtrader.__version__)')"
echo "CCXT: $(python -c 'import ccxt; print(ccxt.__version__)')"
echo ""

echo "==================================="
echo "📋 Next Steps"
echo "==================================="
echo ""
echo "1. Verify installation:"
echo "   cd $BACKEND_DIR"
echo "   source .venv/bin/activate"
echo "   python -c 'import fastapi; print(\"FastAPI:\", fastapi.__version__)'"
echo ""
echo "2. Run tests:"
echo "   cd $BACKEND_DIR"
echo "   source .venv/bin/activate"
echo "   pytest tests/ -v"
echo ""
echo "3. Start server:"
echo "   cd $BACKEND_DIR"
echo "   source .venv/bin/activate"
echo "   python -m fastapi dev --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "4. Access API docs:"
echo "   http://0.0.0.0:8000/docs"
echo ""
echo "==================================="
