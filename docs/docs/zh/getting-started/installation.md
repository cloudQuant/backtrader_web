# 安装指南

## 环境要求

- Python 3.10+
- Node.js 20+
- Git
- Docker Compose v2（可选；用于容器化环境）

## 本地开发安装

```bash
git clone https://github.com/cloudQuant/backtrader_web.git
cd backtrader_web

./scripts/dev/verify-dev-env.sh --preinstall

# 后端
cd src/backend
python -m venv .venv
source .venv/bin/activate               # Windows: .venv\Scripts\activate
pip install -e ".[dev,backtrader]"
# 需要 AkShare 在线刷新时：pip install -e ".[dev,backtrader,data]"
# 需要语义检索时：pip install -e ".[dev,backtrader,rag]"
cp .env.example .env

# 前端
cd ../frontend
npm install

cd ../..
./scripts/dev/verify-dev-env.sh --postinstall
```

`.env` 只保存本机或部署环境的配置。请替换密钥占位值，且不要提交该文件。基础配置示例：

```bash
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite+aiosqlite:///../../data/dev/backtrader.db
SECRET_KEY=replace-with-a-random-secret
JWT_SECRET_KEY=replace-with-a-different-random-secret
```

若应用主数据库使用 MySQL，请配置 `DATABASE_TYPE=mysql` 与 `DATABASE_URL=mysql+aiomysql://...`；市场行情仓库则由独立的 `AKSHARE_DATA_DATABASE_URL` 配置，详见[市场数据](../features/market-data.md)。

## 启动服务

在两个终端分别运行：

```bash
# 后端
cd src/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

```bash
# 前端
cd src/frontend
npm run dev
```

开发前端默认地址为 `http://localhost:3000`，API 文档为 `http://localhost:8000/docs`。

## Docker

仓库的 Compose 基础文件位于 `docker/docker-compose.yml`。选择一个环境覆盖文件：

```bash
docker compose -f docker/docker-compose.yml -f docker/compose/dev.yml up
# 或生产覆盖
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml up -d
```

继续阅读 [Docker 部署](../deployment/docker.md)，并在启动生产环境前配置数据库、密钥、CORS 与备份策略。
