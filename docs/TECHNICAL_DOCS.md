# Backtrader Web 量化交易管理平台 - 技术文档

## 目录

1. [系统功能概览](#1-系统功能概览)
2. [项目目录结构](#2-项目目录结构)
3. [技术栈](#3-技术栈)
4. [数据模型关系图](#4-数据模型关系图)
5. [API 模块详细文档](#5-api-模块详细文档)
6. [部署运维手册](#6-部署运维手册)

---

## 1. 系统功能概览

### 1.1 核心功能模块

| 模块 | 功能描述 | 状态 |
|------|---------|------|
| **策略管理** | 策略的增删改查、模板管理、分类管理 | 100% |
| **策略版本控制** | 版本创建、比较、回滚、分支管理 | 100% |
| **历史数据回测** | 基于 Backtrader 的回测引擎 | 100% |
| **参数优化** | 网格搜索优化策略参数 | 100% |
| **模拟交易** | 账户、订单、持仓、交易记录管理 | 100% |
| **实盘交易** | 实盘实例管理、启停控制 | 100% |
| **实时行情** | 实时行情订阅、WebSocket 推送 | 100% |
| **回测对比** | 多个回测结果对比分析 | 100% |
| **投资组合** | 多策略组合管理、汇总分析 | 100% |
| **监控告警** | 告警规则、告警通知、统计 | 100% |
| **用户认证** | JWT 认证、刷新令牌、密码管理 | 100% |
| **权限控制** | RBAC 角色权限管理 | 100% |

### 1.2 功能架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端 (Vue 3)                            │
│  策略管理 | 回测分析 | 模拟交易 | 实盘监控 | 投资组合 | 系统设置   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP/WebSocket
┌───────────────────────────┴─────────────────────────────────────┐
│                      API 网关层 (FastAPI)                        │
├─────────────────────────────────────────────────────────────────┤
│ 认证中间件 │ 权限中间件 │ 限流中间件 │ 日志中间件 │ 异常处理      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────────┐
│                         服务层 (Services)                        │
├──────────┬──────────┬──────────┬──────────┬──────────┬─────────┤
│Strategy  │Backtest  │Paper     │Live      │Monitor   │Data     │
│Service   │Service   │Trading   │Trading   │Service   │Service  │
└──────────┴──────────┴──────────┴──────────┴──────────┴─────────┘
                            │
┌───────────────────────────┴─────────────────────────────────────┐
│                         数据层 (Data)                            │
├────────────────────┬────────────────────┬───────────────────────┤
│   SQLite/PG/MySQL  │   Backtrader Engine │   策略模板目录        │
│   (用户/策略/回测)  │   (回测/实盘执行)   │   (100+ 策略)         │
└────────────────────┴────────────────────┴───────────────────────┘
```

---

## 2. 项目目录结构

### 2.1 后端目录结构

```
src/backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI 应用入口
│   ├── config.py                # 配置管理
│   │
│   ├── api/                     # API 路由层
│   │   ├── __init__.py
│   │   ├── router.py            # 路由注册
│   │   ├── deps.py              # 依赖注入
│   │   ├── deps_permissions.py  # 权限依赖
│   │   ├── auth.py              # 认证 API
│   │   ├── strategy.py          # 策略管理 API
│   │   ├── strategy_version.py  # 策略版本控制 API
│   │   ├── backtest.py          # 回测 API
│   │   ├── optimization_api.py  # 参数优化 API
│   │   ├── paper_trading.py     # 模拟交易 API
│   │   ├── live_trading_api.py  # 实盘交易 API
│   │   ├── realtime_data.py     # 实时行情 API
│   │   ├── data.py              # 市场数据 API
│   │   ├── comparison.py        # 回测对比 API
│   │   ├── analytics.py         # 分析 API
│   │   ├── portfolio_api.py     # 投资组合 API
│   │   └── monitoring.py        # 监控告警 API
│   │
│   ├── services/                # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── strategy_service.py
│   │   ├── strategy_version_service.py
│   │   ├── backtest_service.py
│   │   ├── optimization_service.py
│   │   ├── param_optimization_service.py
│   │   ├── paper_trading_service.py
│   │   ├── live_trading_service.py
│   │   ├── live_trading_manager.py
│   │   ├── realtime_data_service.py
│   │   ├── comparison_service.py
│   │   ├── analytics_service.py
│   │   ├── monitoring_service.py
│   │   ├── report_service.py
│   │   ├── log_parser_service.py
│   │   └── backtest_analyzers.py
│   │
│   ├── models/                  # ORM 数据模型
│   │   ├── __init__.py
│   │   ├── user.py              # 用户模型
│   │   ├── strategy.py          # 策略模型
│   │   ├── strategy_version.py  # 策略版本模型
│   │   ├── backtest.py          # 回测模型
│   │   ├── comparison.py        # 对比模型
│   │   ├── paper_trading.py     # 模拟交易模型
│   │   ├── alerts.py            # 告警模型
│   │   └── permission.py        # 权限模型
│   │
│   ├── schemas/                 # Pydantic 数据校验模式
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── strategy.py
│   │   ├── strategy_version.py
│   │   ├── backtest.py
│   │   ├── paper_trading.py
│   │   ├── live_trading.py
│   │   ├── live_trading_instance.py
│   │   ├── realtime_data.py
│   │   ├── comparison.py
│   │   ├── analytics.py
│   │   ├── monitoring.py
│   │   └── backtest_enhanced.py
│   │
│   ├── db/                      # 数据库层
│   │   ├── __init__.py
│   │   ├── database.py          # 数据库连接
│   │   ├── base.py              # 基类
│   │   ├── factory.py           # 工厂模式
│   │   ├── sql_repository.py    # SQL 仓储
│   │   └── cache.py             # 缓存
│   │
│   ├── utils/                   # 工具类
│   │   ├── __init__.py
│   │   ├── logger.py            # 日志工具
│   │   ├── security.py          # 安全工具
│   │   ├── sandbox.py           # 沙箱执行
│   │   ├── exceptions.py        # 异常定义
│   │   └── validation.py        # 验证工具
│   │
│   ├── middleware/              # 中间件
│   │   ├── __init__.py
│   │   ├── logging.py           # 日志中间件
│   │   ├── exception_handling.py # 异常处理
│   │   └── security_headers.py  # 安全头
│   │
│   └── websocket_manager.py     # WebSocket 管理
│
├── tests/                       # 测试目录
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_strategy.py
│   ├── test_backtest.py
│   └── ...
│
├── requirements.txt             # Python 依赖
└── pyproject.toml              # 项目配置
```

### 2.2 前端目录结构

```
src/frontend/
├── src/
│   ├── api/                     # API 客户端
│   ├── components/              # Vue 组件
│   ├── views/                   # 页面视图
│   ├── stores/                  # Pinia 状态管理
│   ├── router/                  # Vue Router
│   └── utils/                   # 工具函数
├── package.json
└── vite.config.ts
```

---

## 3. 技术栈

### 3.1 后端技术栈

| 类别 | 技术 | 版本 | 说明 |
|------|------|------|------|
| Web 框架 | FastAPI | 0.109+ | 高性能异步 Web 框架 |
| ASGI 服务器 | Uvicorn | 0.27+ | 异步服务器 |
| 数据验证 | Pydantic | 2.5+ | 数据验证和序列化 |
| 配置管理 | pydantic-settings | 2.1+ | 配置管理 |
| ORM | SQLAlchemy | 2.0+ | Python SQL 工具包 |
| 数据库驱动 | aiosqlite/asyncpg/aiomysql | - | 异步数据库驱动 |
| 认证 | python-jose | 3.3+ | JWT 处理 |
| 密码加密 | passlib | 1.7+ | 密码哈希 |
| 日志 | loguru | 0.7+ | 日志库 |
| 回测引擎 | backtrader | 1.9.78+ | 量化回测框架 |
| 数据处理 | pandas | 2.1+ | 数据分析 |
| 数据源 | akshare | 1.12+ | A股数据 |
| 测试 | pytest | 8.0+ | 测试框架 |
| 限流 | slowapi | - | API 限流 |

### 3.2 前端技术栈

| 类别 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 框架 | Vue | 3.4+ | 渐进式框架 |
| 语言 | TypeScript | 5+ | 类型安全 |
| 构建工具 | Vite | 5+ | 下一代前端构建工具 |
| UI 组件 | Element Plus | - | Vue 3 组件库 |
| 图表 | ECharts | - | 数据可视化 |
| 状态管理 | Pinia | - | Vue 状态管理 |
| 路由 | Vue Router | 4+ | 路由管理 |

---

## 4. 数据模型关系图

### 4.1 ER 图（Mermaid）

```mermaid
erDiagram
    User ||--o{ Strategy : owns
    User ||--o{ BacktestTask : creates
    User ||--o{ Comparison : creates
    User ||--o{ Account : owns
    User ||--o{ Alert : receives
    User ||--o{ AlertRule : creates
    User ||--o{ RefreshToken : has

    Strategy ||--o{ StrategyVersion : has
    Strategy ||--o{ BacktestTask : uses
    Strategy ||--o{ Alert : triggers

    StrategyVersion ||--o{ BacktestTask : uses
    StrategyVersion ||--o{ StrategyVersion : parent
    StrategyVersion ||--o{ VersionBranch : belongs_to

    BacktestTask ||--|| BacktestResultModel : has
    BacktestTask ||--o{ Alert : triggers
    BacktestTask }o--|| Comparison : compares

    Account ||--o{ Position : has
    Account ||--o{ Order : has
    Account ||--o{ PaperTrade : has

    AlertRule ||--o{ Alert : generates
    Alert ||--o{ AlertNotification : sends
```

### 4.2 核心数据表

#### 用户表 (users)

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| id | String(36) | 用户唯一标识 | PK |
| username | String(50) | 用户名 | UNIQUE, NOT NULL |
| email | String(100) | 邮箱 | UNIQUE, NOT NULL |
| hashed_password | String(128) | 哈希密码 | NOT NULL |
| is_active | Boolean | 是否激活 | DEFAULT TRUE |
| created_at | DateTime | 创建时间 | |
| updated_at | DateTime | 更新时间 | |

#### 策略表 (strategies)

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| id | String(36) | 策略唯一标识 | PK |
| user_id | String(36) | 所属用户 | FK, NOT NULL |
| name | String(100) | 策略名称 | NOT NULL |
| description | Text | 策略描述 | |
| code | Text | 策略代码 | NOT NULL |
| params | JSON | 参数定义 | |
| category | String(50) | 分类 | DEFAULT "custom" |
| created_at | DateTime | 创建时间 | |
| updated_at | DateTime | 更新时间 | |

#### 回测任务表 (backtest_tasks)

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| id | String(36) | 任务唯一标识 | PK |
| user_id | String(36) | 所属用户 | FK, NOT NULL |
| strategy_id | String(36) | 策略ID | |
| strategy_version_id | String(36) | 策略版本ID | FK |
| symbol | String(20) | 交易标的 | |
| status | String(20) | 任务状态 | pending/running/completed/failed/cancelled |
| request_data | JSON | 请求参数 | |
| error_message | Text | 错误信息 | |
| log_dir | Text | 日志目录 | |
| created_at | DateTime | 创建时间 | |
| updated_at | DateTime | 更新时间 | |

#### 回测结果表 (backtest_results)

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| id | String(36) | 结果唯一标识 | PK |
| task_id | String(36) | 关联任务 | FK, UNIQUE |
| total_return | Float | 总收益率 | |
| annual_return | Float | 年化收益率 | |
| sharpe_ratio | Float | 夏普比率 | |
| max_drawdown | Float | 最大回撤 | |
| win_rate | Float | 胜率 | |
| metrics_source | String(20) | 指标来源 | manual/fincore |
| total_trades | Integer | 总交易次数 | |
| profitable_trades | Integer | 盈利交易数 | |
| losing_trades | Integer | 亏损交易数 | |
| equity_curve | JSON | 权益曲线 | |
| equity_dates | JSON | 权益日期 | |
| drawdown_curve | JSON | 回撤曲线 | |
| trades | JSON | 交易记录 | |
| created_at | DateTime | 创建时间 | |

#### 模拟交易账户表 (paper_trading_accounts)

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| id | String(36) | 账户唯一标识 | PK |
| user_id | String(36) | 所属用户 | FK, NOT NULL |
| name | String(100) | 账户名称 | NOT NULL |
| initial_cash | Float | 初始资金 | DEFAULT 100000 |
| current_cash | Float | 当前资金 | |
| total_equity | Float | 总权益 | |
| profit_loss | Float | 盈亏金额 | |
| profit_loss_pct | Float | 盈亏比例 | |
| commission_rate | Float | 手续费率 | DEFAULT 0.001 |
| slippage_rate | Float | 滑点率 | DEFAULT 0.001 |
| is_active | Boolean | 是否激活 | DEFAULT TRUE |
| created_at | DateTime | 创建时间 | |
| updated_at | DateTime | 更新时间 | |

---

## 5. API 模块详细文档

### 5.1 认证模块 (`/api/v1/auth`)

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/register` | 用户注册 | UserCreate | UserResponse |
| POST | `/login` | 用户登录 | UserLogin | Token |
| POST | `/login/refresh` | 登录(含刷新令牌) | UserLogin | RefreshTokenResponse |
| POST | `/refresh` | 刷新访问令牌 | RefreshTokenRequest | RefreshTokenResponse |
| POST | `/logout` | 用户登出 | RefreshTokenRequest | Message |
| PUT | `/change-password` | 修改密码 | ChangePassword | Message |
| GET | `/me` | 获取当前用户信息 | - | UserResponse |

#### Token Response
```json
{
  "access_token": "string (JWT令牌)",
  "token_type": "bearer",
  "expires_in": "integer (秒)",
  "refresh_token": "string (刷新令牌)"
}
```

### 5.2 策略管理模块 (`/api/v1/strategy`)

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/` | 创建策略 | StrategyCreate | StrategyResponse |
| GET | `/` | 列出用户策略 | - | StrategyListResponse |
| GET | `/templates` | 获取策略模板列表 | - | TemplatesResponse |
| GET | `/templates/{id}` | 获取模板详情 | - | TemplateDetail |
| GET | `/{strategy_id}` | 获取策略详情 | - | StrategyResponse |
| PUT | `/{strategy_id}` | 更新策略 | StrategyUpdate | StrategyResponse |
| DELETE | `/{strategy_id}` | 删除策略 | - | Message |

### 5.3 策略版本控制模块 (`/api/v1/strategy-versions`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/versions` | 创建策略版本 |
| GET | `/strategies/{id}/versions` | 列出版本 |
| POST | `/versions/compare` | 比较两个版本 |
| POST | `/versions/rollback` | 回滚到指定版本 |
| POST | `/branches` | 创建分支 |

#### WebSocket
| 路径 | 说明 |
|------|------|
| `/ws/strategies/{strategy_id}` | 版本变更实时推送 |

### 5.4 回测模块 (`/api/v1/backtest`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/run` | 运行回测 |
| GET | `/{task_id}` | 获取回测结果 |
| GET | `/{task_id}/status` | 获取任务状态 |
| GET | `/` | 列出回测历史 |
| POST | `/{task_id}/cancel` | 取消回测 |

#### WebSocket
| 路径 | 说明 |
|------|------|
| `/ws/backtest/{task_id}` | 回测进度实时推送 |

### 5.5 参数优化模块 (`/api/v1/optimization`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/strategy-params/{id}` | 获取策略参数 |
| POST | `/submit` | 提交优化任务 |
| GET | `/progress/{task_id}` | 查询优化进度 |
| GET | `/results/{task_id}` | 获取优化结果 |
| POST | `/cancel/{task_id}` | 取消优化任务 |

### 5.6 模拟交易模块 (`/api/v1/paper-trading`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/accounts` | 创建模拟账户 |
| GET | `/accounts` | 列出账户 |
| POST | `/orders` | 提交订单 |
| GET | `/orders` | 列出订单 |
| GET | `/positions` | 列出持仓 |
| GET | `/trades` | 列出成交记录 |

#### WebSocket
| 路径 | 说明 |
|------|------|
| `/ws/account/{account_id}` | 账户实时数据推送 |

### 5.7 实盘交易模块 (`/api/v1/live-trading`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 列出实盘实例 |
| POST | `/` | 添加实盘实例 |
| POST | `/{instance_id}/start` | 启动实例 |
| POST | `/{instance_id}/stop` | 停止实例 |
| GET | `/{instance_id}/detail` | 获取分析详情 |

### 5.8 实时行情模块 (`/api/v1/realtime`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/ticks/subscribe` | 订阅实时行情 |
| POST | `/ticks/unsubscribe` | 取消订阅 |
| GET | `/ticks` | 获取实时行情 |
| GET | `/ticks/batch` | 批量获取行情 |

#### WebSocket
| 路径 | 说明 |
|------|------|
| `/ws/ticks/{broker_id}` | 实时行情推送 |

### 5.9 市场数据模块 (`/api/v1/data`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/kline` | 获取A股K线数据 |

### 5.10 回测对比模块 (`/api/v1/comparisons`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/` | 创建对比 |
| GET | `/{comparison_id}` | 获取对比详情 |
| POST | `/{comparison_id}/toggle-favorite` | 切换收藏状态 |
| GET | `/{comparison_id}/metrics` | 获取指标对比 |

### 5.11 分析模块 (`/api/v1/analytics`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/{task_id}/detail` | 获取回测详情 |
| GET | `/{task_id}/kline` | 获取K线与信号 |
| GET | `/{task_id}/monthly-returns` | 获取月度收益 |

### 5.12 投资组合模块 (`/api/v1/portfolio`)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/overview` | 投资组合概览 |
| GET | `/positions` | 汇总持仓 |
| GET | `/equity` | 投资组合权益曲线 |

### 5.13 监控告警模块 (`/api/v1/monitoring`)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/rules` | 创建告警规则 |
| GET | `/rules` | 列出告警规则 |
| GET | `/` | 列出告警 |
| PUT | `/{alert_id}/resolve` | 解决告警 |
| GET | `/statistics/summary` | 告警统计摘要 |

#### WebSocket
| 路径 | 说明 |
|------|------|
| `/ws/alerts` | 告警实时推送 |

---

## 6. 部署运维手册

### 6.1 环境要求

| 组件 | 要求 |
|------|------|
| Python | 3.10+ |
| Node.js | 18+ |
| 数据库 | SQLite (开发) / PostgreSQL/MySQL (生产) |
| 缓存 | Redis (可选) |

### 6.2 配置清单

创建 `.env` 文件：

```bash
# 应用配置
APP_NAME=backtrader_web
DEBUG=false
SECRET_KEY=your-secret-key-change-in-production
JWT_SECRET_KEY=your-jwt-secret-change-in-production
JWT_EXPIRE_MINUTES=1440

# 服务配置
HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# 数据库配置
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite+aiosqlite:///./backtrader.db

# PostgreSQL 示例
# DATABASE_TYPE=postgresql
# DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/backtrader

# MySQL 示例
# DATABASE_TYPE=mysql
# DATABASE_URL=mysql+aiomysql://user:password@localhost:3306/backtrader

# 缓存配置 (可选)
REDIS_URL=redis://localhost:6379/0

# 回测配置
BACKTEST_TIMEOUT=300

# 默认管理员
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_EMAIL=admin@example.com

# SQL 日志
SQL_ECHO=false
```

### 6.3 后端部署

```bash
# 进入后端目录
cd src/backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 初始化数据库
python -c "from app.db.database import init_db; import asyncio; asyncio.run(init_db())"

# 启动服务 (开发模式)
uvicorn app.main:app --reload --port 8000

# 启动服务 (生产模式)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 6.4 前端部署

```bash
# 进入前端目录
cd src/frontend

# 安装依赖
npm install

# 开发模式
npm run dev

# 生产构建
npm run build

# 使用 nginx 部署构建产物
# 将 dist 目录部署到 nginx
```

### 6.5 Nginx 配置示例

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 前端静态文件
    location / {
        root /path/to/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # 后端 API 代理
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket 代理
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### 6.6 健康检查

| 端点 | 说明 |
|------|------|
| `GET /` | 服务基本信息 |
| `GET /health` | 健康检查 |
| `GET /info` | 系统信息 |
| `GET /docs` | Swagger API 文档 |
| `GET /redoc` | ReDoc API 文档 |

### 6.7 监控指标

系统提供了以下监控指标：

- **请求响应时间**：通过 PerformanceLoggingMiddleware 记录
- **慢查询日志**：超过 5 秒的请求会被标记
- **审计日志**：登录、权限变更等操作记录
- **告警系统**：可配置阈值告警

### 6.8 日志说明

日志文件位置（默认）：

| 日志类型 | 位置 |
|----------|------|
| 应用日志 | `logs/app.log` |
| 审计日志 | `logs/audit.log` |
| 回测日志 | `strategies/{strategy_id}/logs/{timestamp}/` |

### 6.9 备份建议

1. **数据库备份**：
   - SQLite: 定期复制 `backtrader.db` 文件
   - PostgreSQL: 使用 `pg_dump`
   - MySQL: 使用 `mysqldump`

2. **策略文件备份**：
   - 备份 `strategies/` 目录下用户自定义策略

3. **日志归档**：
   - 定期清理和归档历史回测日志

---

## 附录

### A. 项目完成度

| 模块 | 完成度 | 测试覆盖率 |
|------|--------|------------|
| 后端架构 | 100% | 100% |
| API 路由 | 100% | 100% |
| 数据模型 | 100% | 100% |
| 服务层 | 100% | 100% |
| 前端 | 100% | - |

### B. 测试状态

```
1462+ 测试用例，100% 代码覆盖
```

### C. 许可证

MIT License

---

*文档生成日期: 2026-02-24*
*项目版本: v2.0.0*
