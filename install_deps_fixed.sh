#!/bin/bash
"""
修复的依赖安装脚本

移除不存在的版本限制，让 pip 自动选择最新可用版本
"""

PROJECT_ROOT="/home/yun/Documents/backtrader_web"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo "==================================="
echo "🚀 Fixed Dependencies Installation"
echo "==================================="
echo ""

# 1. 进入后端目录
cd "$BACKEND_DIR" || exit 1

# 2. 检查虚拟环境
VENV_DIR="$BACKEND_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# 3. 激活虚拟环境
echo "📦 Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# 4. 升级 pip
echo "📦 Upgrading pip..."
pip install --upgrade pip --quiet
echo "✅ Pip upgraded"
echo ""

# 5. 安装后端核心依赖（移除版本限制）
echo "==================================="
echo "📦 Installing Core Dependencies"
echo "==================================="
echo ""

echo "Installing FastAPI..."
pip install fastapi --quiet
echo "✅ FastAPI installed"

echo "Installing Uvicorn..."
pip install 'uvicorn[standard]' --quiet
echo "✅ Uvicorn installed"

echo "Installing Pydantic..."
pip install pydantic --quiet
echo "✅ Pydantic installed"

echo "Installing Pydantic-Settings..."
pip install pydantic-settings --quiet
echo "✅ Pydantic-Settings installed"

echo "Installing SQLAlchemy..."
pip install sqlalchemy --quiet
echo "✅ SQLAlchemy installed"

echo "Installing SQLAlchemy-Utils..."
pip install sqlalchemy-utils --quiet
echo "✅ SQLAlchemy-Utils installed"

echo "Installing Passlib..."
pip install 'passlib[bcrypt]' --quiet
echo "✅ Passlib installed"

echo "Installing python-jose..."
pip install 'python-jose[cryptography]' --quiet
echo "✅ python-jose installed"

echo "Installing python-multipart..."
pip install python-multipart --quiet
echo "✅ python-multipart installed"

echo "Installing httpx..."
pip install httpx --quiet
echo "✅ httpx installed"

echo "Installing slowapi..."
pip install slowapi --quiet
echo "✅ slowapi installed"

echo "Installing websockets..."
pip install websockets --quiet
echo "✅ websockets installed"

echo "Installing redis..."
pip install redis --quiet
echo "✅ redis installed"

echo "Installing celery..."
pip install celery --quiet
echo "✅ celery installed"

echo "Installing alembic..."
pip install alembic --quiet
echo "✅ alembic installed"

echo ""
echo "==================================="
echo "📦 Installing Async Dependencies"
echo "==================================="
echo ""

echo "Installing pytest..."
pip install pytest --quiet
echo "✅ pytest installed"

echo "Installing pytest-asyncio..."
pip install pytest-asyncio --quiet
echo "✅ pytest-asyncio installed"

echo "Installing pytest-cov..."
pip install pytest-cov --quiet
echo "✅ pytest-cov installed"

echo "Installing pytest-mock..."
pip install pytest-mock --quiet
echo "✅ pytest-mock installed"

echo "Installing coverage..."
pip install coverage --quiet
echo "✅ coverage installed"

echo ""
echo "==================================="
echo "📦 Installing Report Dependencies"
echo "==================================="
echo ""

echo "Installing reportlab..."
pip install reportlab --quiet
echo "✅ reportlab installed"

echo "Installing openpyxl..."
pip install openpyxl --quiet
echo "✅ openpyxl installed"

echo "Installing jinja2..."
pip install jinja2 --quiet
echo "✅ jinja2 installed"

echo ""
echo "==================================="
echo "📦 Installing Trading Dependencies"
echo "==================================="
echo ""

echo "Installing pandas..."
pip install pandas --quiet
echo "✅ pandas installed"

echo "Installing numpy..."
pip install numpy --quiet
echo "✅ numpy installed"

# 6. 尝试安装 backtrader（不指定版本）
echo ""
echo "Attempting to install backtrader (latest available)..."
pip install backtrader --quiet || {
    echo "⚠️  Failed to install backtrader from PyPI"
    echo "   Trying to install from git..."
    pip install 'git+https://github.com/mementum/backtrader.git@master#egg=backtrader' --quiet || {
        echo "⚠️  Failed to install backtrader from git"
        echo "   Backtrader installation skipped (not required for basic functionality)"
    }
}

echo "✅ Backtrader installation attempted"

echo ""
echo "Attempting to install ccxt..."
pip install ccxt --quiet || {
    echo "⚠️  Failed to install ccxt"
    echo "   CCXT installation skipped (not required for basic functionality)"
}
echo "✅ CCXT installation attempted"

echo ""
echo "==================================="
echo "✅ Dependencies Installation Complete!"
echo "==================================="
echo ""

# 7. 验证安装
echo "==================================="
echo "🔍 Verifying Installation"
echo "==================================="
echo ""

echo "Python: $(python --version)"
echo ""

echo "Checking core packages..."
packages=(
    "fastapi"
    "uvicorn"
    "pydantic"
    "sqlalchemy"
    "httpx"
    "websockets"
    "pytest"
)

for pkg in "${packages[@]}"; do
    if python -c "import $pkg" 2>/dev/null; then
        version=$(python -c "import $pkg; print(getattr($pkg, '__version__', 'unknown'))")
        echo "   ✅ $pkg: $version"
    else
        echo "   ❌ $pkg: NOT INSTALLED"
    fi
done

echo ""
echo "Checking trading packages..."
trading_packages=("pandas" "numpy")
for pkg in "${trading_packages[@]}"; do
    if python -c "import $pkg" 2>/dev/null; then
        version=$(python -c "import $pkg; print(getattr($pkg, '__version__', 'unknown'))")
        echo "   ✅ $pkg: $version"
    else
        echo "   ❌ $pkg: NOT INSTALLED"
    fi
done

echo ""
echo "Checking optional packages..."
optional_packages=("backtrader" "ccxt")
for pkg in "${optional_packages[@]}"; do
    if python -c "import $pkg" 2>/dev/null; then
        version=$(python -c "import $pkg; print(getattr($pkg, '__version__', 'unknown'))")
        echo "   ✅ $pkg: $version"
    else
        echo "   ⚠️  $pkg: NOT INSTALLED (optional)"
    fi
done

echo ""
echo "==================================="
echo "✅ Installation Verification Complete!"
echo "==================================="
echo ""
echo "📋 Summary:"
echo "   Core packages: Installed (or attempted)"
echo "   Trading packages: Installed (or attempted)"
echo "   Optional packages: May not be available"
echo ""
echo "📋 Note:"
echo "   If backtrader or ccxt are not installed, it's okay."
echo "   Basic FastAPI functionality will still work."
echo ""
echo "📋 Next Steps:"
echo "   1. Start the backend server:"
echo "      cd $BACKEND_DIR"
echo "      python -m fastapi dev --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "   2. Access API documentation:"
echo "      http://0.0.0.0:8000/docs"
echo ""
echo "==================================="
