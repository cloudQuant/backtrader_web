# 常用命令

以下命令从仓库根目录开始。请在项目约定的 Python 环境中执行后端命令。

## 后端

```bash
cd src/backend
pip install -e ".[dev,backtrader]"
pytest -m "not e2e" -q --tb=short
ruff check app tests
mypy app
uvicorn app.main:app --reload --port 8000
```

需要在线数据或语义检索时分别安装对应 extra：

```bash
pip install -e ".[data]"
pip install -e ".[rag]"
```

## 前端

```bash
cd src/frontend
npm install
npm run dev
npm run typecheck
npm run lint
npm run test -- --run
npm run build
```

## 文档

```bash
python -m pip install -r docs/requirements.txt
python -m mkdocs serve -f docs/mkdocs.yml
python -m mkdocs build -f docs/mkdocs.yml --strict
```

## Docker

```bash
# 开发 Compose
docker compose -f docker/docker-compose.yml -f docker/compose/dev.yml up

# 生产 Compose
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml up -d
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml ps
```

运行高影响命令前先查看环境、配置与备份状态；测试/开发命令不应使用生产数据库或真实网关凭据。
