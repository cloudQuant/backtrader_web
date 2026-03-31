# 系统架构

本文档描述 Backtrader Web 的整体架构设计。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端 (Vue 3)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  策略管理    │  │  回测分析    │  │  实时监控    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────┬───────────────────────────────────┘
                              │ HTTP/WebSocket
┌─────────────────────────────▼───────────────────────────────────┐
│                      FastAPI 后端                               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                      中间件层                             │    │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │    │
│  │  │  异常处理   │ │  安全头     │ │  日志记录   │       │    │
│  │  └─────────────┘ └─────────────┘ └─────────────┘       │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                      路由层 (API)                         │    │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐         │    │
│  │  │ Auth │ │Strategy│ │Backtest│ │ Data │ │Trading│      │    │
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘         │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                      服务层 (Services)                   │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐               │    │
│  │  │ AuthService│ │BacktestService│ │StrategyService│        │    │
│  │  └──────────┘ └──────────┘ └──────────┘               │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                      数据层                              │    │
│  │  ┌─────────────┐         ┌─────────────┐               │    │
│  │  │SQL Repository│         │    Cache    │               │    │
│  │  └─────────────┘         └─────────────┘               │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                       数据存储                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ PostgreSQL/  │  │    Redis     │  │   文件存储   │          │
│  │  MySQL/SQLite│  │    (缓存)    │  │  (策略/报告)  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                      外部服务                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  数据服务商  │  │   券商API    │  │  消息队列    │          │
│  │  (AkShare)   │  │  (CCXT/CTP)  │  │  (Celery)    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## 分层架构

### 1. 路由层 (API Layer)

**位置**: `app/api/`

**职责**:
- 接收 HTTP 请求
- 参数验证
- 调用服务层
- 返回响应

**示例**:
```python
@router.post("/backtest/run")
async def run_backtest(
    request: BacktestRequest,
    current_user: User = Depends(get_current_user)
):
    return await backtest_service.run_backtest(current_user.id, request)
```

### 2. 服务层 (Service Layer)

**位置**: `app/services/`

**职责**:
- 实现业务逻辑
- 协调多个数据源
- 事务管理

**示例**:
```python
class BacktestService:
    async def run_backtest(self, user_id: str, request: BacktestRequest):
        # 创建任务
        # 执行回测
        # 保存结果
        return result
```

## 数据存储

### 支持的数据库

| 数据库类型 | 状态 | 说明 |
|------------|------|------|
| SQLite | ✅ 支持 | 默认选项，适合开发和小型部署 |
| PostgreSQL | ✅ 支持 | 生产环境推荐，需要 `asyncpg` 驱动 |
| MySQL | ✅ 支持 | 需要 `aiomysql` 驱动 |
| MongoDB | ❌ 不支持 | 规划中，当前版本不可用 |

### 数据层组件

- `database.py`: 数据库连接
- `sql_repository.py`: 通用仓储
- `cache.py`: 缓存封装
- `factory.py`: 仓储工厂（自动选择实现）

### 配置方式

```bash
# SQLite (默认)
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite+aiosqlite:///./backtrader.db

# PostgreSQL
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/backtrader

# MySQL
DATABASE_TYPE=mysql
DATABASE_URL=mysql+aiomysql://user:pass@localhost:3306/backtrader
```

> **注意**: MongoDB 支持计划在未来版本中实现，当前请求 MongoDB 会抛出 `NotImplementedError`。

### 4. 中间件层 (Middleware Layer)

**位置**: `app/middleware/`

**职责**:
- 异常处理
- 安全头
- 日志记录
- 速率限制

## 核心模块

### 1. 认证授权

```
┌─────────────────────────────────────────┐
│           认证流程                        │
├─────────────────────────────────────────┤
│  1. 用户登录 (username + password)      │
│  2. 验证凭证                             │
│  3. 生成 JWT Token                       │
│  4. 返回 Token (access + refresh)        │
│  5. 后续请求携带 Token                   │
└─────────────────────────────────────────┘
```

### 2. 回测引擎

```
┌─────────────────────────────────────────┐
│           回测流程                        │
├─────────────────────────────────────────┤
│  1. 接收回测请求                         │
│  2. 加载策略代码                         │
│  3. 加载历史数据                         │
│  4. 初始化 Backtrader Cerebro            │
│  5. 执行回测                             │
│  6. 收集结果                             │
│  7. 计算指标                             │
│  8. 保存结果                             │
└─────────────────────────────────────────┘
```

### 3. 实时数据

```
┌─────────────────────────────────────────┐
│         WebSocket 推送                    │
├─────────────────────────────────────────┤
│  1. 客户端连接                           │
│  2. 订阅数据流                           │
│  3. 服务端推送更新                       │
│  4. 客户端处理更新                       │
└─────────────────────────────────────────┘
```

## 数据流

### 回测数据流（Mermaid）

```mermaid
sequenceDiagram
    participant U as 用户/前端
    participant API as FastAPI
    participant BS as BacktestService
    participant BT as Backtrader Engine
    participant DB as 数据库
    participant WS as WebSocket

    U->>API: POST /backtest/run
    API->>API: JWT 验证 + 参数校验
    API->>BS: run_backtest(user_id, request)
    BS->>DB: 创建 BacktestTask (status=pending)
    BS->>BS: 加载策略代码 (模板/用户)
    BS->>BT: 初始化 Cerebro + 添加策略
    BT->>BT: 加载历史数据 (AkShare)
    BT->>BT: 执行回测
    BT-->>WS: 推送进度 (10%...90%)
    BT->>BS: 返回回测结果
    BS->>BS: 计算指标 (fincore)
    BS->>DB: 保存 BacktestResult
    BS->>DB: 更新 Task (status=completed)
    BS-->>WS: 推送完成通知
    API-->>U: 返回 task_id
    U->>API: GET /analytics/{task_id}/detail
    API-->>U: 返回分析数据
```

### 实盘交易数据流（Mermaid）

```mermaid
sequenceDiagram
    participant U as 用户/前端
    participant API as FastAPI
    participant LTM as LiveTradingManager
    participant BT as Backtrader Engine
    participant Broker as 券商 (CCXT/CTP)
    participant WS as WebSocket

    U->>API: POST /live-trading/ (添加实例)
    API->>LTM: create_instance(config)
    U->>API: POST /live-trading/{id}/start
    API->>LTM: start_instance(id)
    LTM->>BT: 初始化 Cerebro (live mode)
    BT->>Broker: 连接券商 API
    loop 交易循环
        Broker-->>BT: 实时行情推送
        BT->>BT: 策略计算信号
        BT->>Broker: 下单/撤单
        Broker-->>BT: 订单状态更新
        BT-->>WS: 推送持仓/盈亏
    end
    U->>API: POST /live-trading/{id}/stop
    API->>LTM: stop_instance(id)
    LTM->>BT: 停止引擎
```

### 部署架构（Mermaid）

```mermaid
graph TB
    subgraph 客户端
        Browser[浏览器 Vue 3 SPA]
    end

    subgraph 反向代理
        Nginx[Nginx / Vite Dev Server]
    end

    subgraph 应用层
        FastAPI[FastAPI + Uvicorn]
        WSM[WebSocket Manager]
    end

    subgraph 服务层
        AuthSvc[Auth Service]
        BtSvc[Backtest Service]
        LiveSvc[Live Trading Manager]
        OptSvc[Optimization Service]
        MonSvc[Monitoring Service]
    end

    subgraph 数据层
        DB[(SQLite / PostgreSQL / MySQL)]
        Cache[(Redis 缓存)]
        Files[策略文件 118+]
    end

    subgraph 外部服务
        AkShare[AkShare 数据源]
        CCXT[CCXT 交易所]
        CTP[CTP 券商]
    end

    Browser -->|HTTP/WS| Nginx
    Nginx -->|proxy /api| FastAPI
    Nginx -->|proxy /ws| WSM
    FastAPI --> AuthSvc
    FastAPI --> BtSvc
    FastAPI --> LiveSvc
    FastAPI --> OptSvc
    FastAPI --> MonSvc
    BtSvc --> DB
    BtSvc --> Files
    BtSvc --> AkShare
    LiveSvc --> CCXT
    LiveSvc --> CTP
    AuthSvc --> DB
    MonSvc --> DB
    OptSvc --> DB
```

## 安全架构

### 1. 认证机制

- JWT Token 认证
- Refresh Token 轮换
- 密码 bcrypt 加密

### 2. 授权机制

- 基于角色的访问控制 (RBAC)
- 用户资源隔离
- API 权限检查

### 3. 安全防护

- SQL 注入防护
- XSS 防护
- CSRF 防护
- 速率限制

## 部署架构

### 单机部署

```
┌─────────────────────────────────────┐
│           单服务器                    │
│  ┌─────────────────────────────┐   │
│  │  Nginx                       │   │
│  │  (静态文件 + 反向代理)      │   │
│  └──────────────┬──────────────┘   │
│                 │                   │
│  ┌──────────────▼──────────────┐   │
│  │  Gunicorn + Uvicorn Workers │   │
│  └──────────────┬──────────────┘   │
│                 │                   │
│  ┌──────────────▼──────────────┐   │
│  │  PostgreSQL/SQLite          │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

### 分布式部署

```
┌─────────────────────────────────────────────────────────────┐
│                        负载均衡器                            │
└────────────────────┬────────────────────────────────────────┘
                     │
    ┌────────────────┼────────────────┐
    │                │                │
┌───▼───┐     ┌────▼────┐     ┌────▼────┐
│ Web 1 │     │  Web 2  │     │  Web 3  │
└───┬───┘     └────┬────┘     └────┬────┘
    │              │                │
    └──────────────┼────────────────┘
                   │
    ┌──────────────▼──────────────┐
    │      PostgreSQL (主从)       │
    └─────────────────────────────┘
```
