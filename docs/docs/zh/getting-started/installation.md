# 安装指南

## 环境要求

- **Python**: 3.10+
- **Node.js**: 20+
- **Docker**: 24+ (可选，用于容器化部署)
- **Git**

## 后端安装

### 1. 创建虚拟环境

```bash
cd src/backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 2. 安装依赖

```bash
pip install -e ".[dev,backtrader]"
```

这将安装：
- 核心依赖 (FastAPI, SQLAlchemy 等)
- 开发依赖 (pytest, ruff)
- Backtrader 及相关包

### 3. 配置环境

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```bash
# 数据库 (默认 SQLite)
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite:///./backtrader.db

# 可选: PostgreSQL
# DATABASE_TYPE=postgresql
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/backtrader

# 可选: MySQL
# DATABASE_TYPE=mysql
# DATABASE_URL=mysql+aiomysql://user:pass@localhost:3306/backtrader

# JWT 配置
SECRET_KEY=your-secret-key-here
JWT_EXPIRE_MINUTES=1440
```

### 4. 验证安装

```bash
# 检查环境
cd ../..
./scripts/verify-dev-env.sh --postinstall
```

## 前端安装

### 1. 安装 Node 依赖

```bash
cd src/frontend
npm install
```

### 2. 配置

如需要，在 `src/frontend/` 创建 `.env` 文件：

```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

## 启动服务

### 开发模式

**终端 1 - 后端：**
```bash
cd src/backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**终端 2 - 前端：**
```bash
cd src/frontend
npm run dev
```

### Docker 部署

```bash
# 生产环境
docker compose -f docker-compose.prod.yml up -d
```

## 访问地址

| 服务 | 地址 |
|------|------|
| 前端 (开发) | http://localhost:8080 |
| 前端 (Docker) | http://localhost |
| 后端 API 文档 | http://localhost:8000/docs |
| WebSocket | ws://localhost:8000/ws |

## 故障排查

### Backtrader 导入问题

如果遇到 backtrader 导入错误，请查看 [Backtrader 导入问题排查](../../BACKTRADER_IMPORT_TROUBLESHOOTING.md)。

### 数据库连接问题

确保数据库服务正在运行，且 `.env` 中的凭据正确。

### 端口冲突

如果 8000 或 8080 端口被占用，可修改启动命令中的端口：

```bash
uvicorn app.main:app --reload --port 8001
```
