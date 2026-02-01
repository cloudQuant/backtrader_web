# Backtrader Web Backend

基于 FastAPI 的 Backtrader 量化交易回测 Web 服务后端。

## 功能特性

- **用户认证**: JWT 认证 + bcrypt 密码加密
- **回测服务**: 异步回测任务执行、结果存储
- **策略管理**: 策略 CRUD、模板库、YAML 配置
- **数据库抽象**: 支持 SQLite/PostgreSQL/MySQL，通过环境变量切换
- **缓存层**: 可选 Redis 缓存

## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件配置数据库等参数
```

### 3. 启动服务

```bash
# 开发模式
uvicorn app.main:app --reload --port 8000

# 或直接运行
python -m app.main
```

### 4. 访问 API 文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 项目结构

```
backend/
├── app/
│   ├── api/              # API 路由
│   │   ├── auth.py       # 认证接口
│   │   ├── backtest.py   # 回测接口
│   │   └── strategy.py   # 策略接口
│   ├── db/               # 数据库层
│   │   ├── base.py       # Repository 基类
│   │   ├── database.py   # 数据库连接
│   │   └── sql_repository.py
│   ├── models/           # ORM 模型
│   ├── schemas/          # Pydantic 模型
│   ├── services/         # 业务服务
│   │   ├── auth_service.py
│   │   ├── backtest_service.py
│   │   └── strategy_service.py
│   ├── utils/            # 工具函数
│   ├── config.py         # 配置管理
│   └── main.py           # 应用入口
├── tests/                # 测试
├── requirements.txt
├── pyproject.toml
└── .env.example
```

## API 接口

### 认证

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/v1/auth/register | 用户注册 |
| POST | /api/v1/auth/login | 用户登录 |
| GET | /api/v1/auth/me | 获取当前用户 |

### 回测

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/v1/backtest/run | 运行回测 |
| GET | /api/v1/backtest/{id} | 获取回测结果 |
| GET | /api/v1/backtest/ | 列出回测历史 |
| DELETE | /api/v1/backtest/{id} | 删除回测 |

### 策略

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/v1/strategy/ | 创建策略 |
| GET | /api/v1/strategy/ | 列出策略 |
| GET | /api/v1/strategy/{id} | 获取策略详情 |
| PUT | /api/v1/strategy/{id} | 更新策略 |
| DELETE | /api/v1/strategy/{id} | 删除策略 |
| GET | /api/v1/strategy/templates | 获取策略模板 |

## 测试

```bash
# 运行测试
pytest

# 带覆盖率
pytest --cov=app
```

## 环境变量

| 变量 | 默认值 | 描述 |
|------|--------|------|
| DATABASE_TYPE | sqlite | 数据库类型 |
| DATABASE_URL | sqlite+aiosqlite:///./backtrader.db | 数据库连接 |
| JWT_SECRET_KEY | - | JWT 密钥 |
| JWT_EXPIRE_MINUTES | 1440 | Token 过期时间 |
| DEBUG | true | 调试模式 |

## License

MIT
