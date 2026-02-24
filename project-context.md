# Backtrader Web - 项目上下文文档

> 本文档为 AI 代理优化的项目上下文参考，包含关键实现规则、模式和约定。

## 1. 项目概览

### 核心定位
基于 Backtrader 的**全栈量化交易管理平台**，提供策略回测、模拟交易、实盘交易、参数优化等完整功能。

### 技术栈
| 层级 | 技术 | 版本 |
|------|------|------|
| 前端 | Vue 3 + TypeScript + Vite | 3.4+, 5.0+ |
| 前端UI | Element Plus + Echarts | 2.5+, 5.4+ |
| 前端状态 | Pinia | 2.1+ |
| 后端 | FastAPI + Uvicorn | 0.109+, 0.27+ |
| 后端ORM | SQLAlchemy 2.0 (async) | 2.0+ |
| 数据库 | SQLite (默认) / PostgreSQL / MySQL | - |
| 认证 | JWT (python-jose) | - |
| 回测引擎 | Backtrader | 1.9.78+ |
| E2E测试 | Playwright + pytest | - |

## 2. 目录结构

```
backtrader_web/
├── src/
│   ├── backend/                    # FastAPI 后端
│   │   ├── app/
│   │   │   ├── api/                # API 路由 (模块化)
│   │   │   │   ├── router.py       # 统一路由注册
│   │   │   │   ├── auth.py         # 认证路由
│   │   │   │   ├── backtest.py     # 回测路由
│   │   │   │   ├── deps.py         # 依赖注入 (get_current_user)
│   │   │   │   └── deps_permissions.py  # 权限依赖
│   │   │   ├── services/           # 业务逻辑层
│   │   │   │   ├── backtest_service.py      # 回测服务
│   │   │   │   ├── auth_service.py          # 认证服务
│   │   │   │   ├── strategy_service.py      # 策略服务
│   │   │   │   ├── optimization_service.py  # 参数优化
│   │   │   │   ├── paper_trading_service.py # 模拟交易
│   │   │   │   └── live_trading_service.py  # 实盘交易
│   │   │   ├── models/             # SQLAlchemy ORM 模型
│   │   │   │   ├── user.py         # User 模型
│   │   │   │   ├── backtest.py     # BacktestTask, BacktestResultModel
│   │   │   │   ├── strategy.py     # Strategy 模型
│   │   │   │   └── permission.py   # Permission, Role 模型
│   │   │   ├── schemas/            # Pydantic 请求/响应模型
│   │   │   │   ├── auth.py         # Token, UserCreate, UserLogin
│   │   │   │   ├── backtest.py     # BacktestRequest, BacktestResponse
│   │   │   │   └── strategy.py     # Strategy, StrategyCreate
│   │   │   ├── db/                 # 数据库层
│   │   │   │   ├── database.py     # async_session_maker, init_db()
│   │   │   │   ├── sql_repository.py  # 通用 CRUD 仓储
│   │   │   │   └── cache.py        # 缓存抽象
│   │   │   ├── middleware/         # 中间件
│   │   │   │   ├── logging.py      # LoggingMiddleware, AuditLoggingMiddleware
│   │   │   │   ├── exception_handling.py  # 全局异常处理
│   │   │   │   └── security_headers.py    # 安全头
│   │   │   ├── utils/              # 工具函数
│   │   │   │   ├── security.py     # 密码哈希, JWT 编解码
│   │   │   │   ├── sandbox.py      # 策略安全执行沙箱
│   │   │   │   └── logger.py       # 日志配置
│   │   │   ├── config.py           # Pydantic Settings 配置
│   │   │   ├── main.py             # FastAPI 应用入口
│   │   │   └── websocket_manager.py  # WebSocket 连接管理
│   │   └── pyproject.toml          # Python 项目配置
│   └── frontend/                   # Vue 3 前端
│       ├── src/
│       │   ├── api/                # API 调用模块
│       │   │   ├── index.ts        # axios 实例 + 拦截器
│       │   │   ├── auth.ts         # 认证 API
│       │   │   ├── backtest.ts     # 回测 API
│       │   │   ├── strategy.ts     # 策略 API
│       │   │   └── optimization.ts # 优化 API
│       │   ├── stores/             # Pinia 状态管理
│       │   │   └── auth.ts         # useAuthStore
│       │   ├── views/              # 页面组件
│       │   │   ├── LoginPage.vue
│       │   │   ├── Dashboard.vue
│       │   │   ├── BacktestPage.vue
│       │   │   ├── StrategyPage.vue
│       │   │   └── LiveTradingPage.vue
│       │   ├── components/         # 可复用组件
│       │   │   ├── charts/         # 图表组件 (Echarts)
│       │   │   │   ├── KlineChart.vue
│       │   │   │   ├── EquityCurve.vue
│       │   │   │   └── PerformancePanel.vue
│       │   │   └── common/         # 通用组件
│       │   │       ├── AppLayout.vue
│       │   │       └── MonacoEditor.vue
│       │   ├── router/             # Vue Router 配置
│       │   ├── types/              # TypeScript 类型定义
│       │   │   └── index.d.ts      # 核心类型 (UserInfo, BacktestRequest, etc.)
│       │   └── main.ts             # 应用入口
│       ├── vite.config.ts          # Vite 配置 (代理 /api -> 8000)
│       └── package.json
├── tests/
│   ├── e2e/                        # Playwright E2E 测试
│   │   ├── conftest.py             # pytest fixtures (browser, page, authenticated_page)
│   │   ├── test_auth.py
│   │   ├── test_backtest.py
│   │   └── run_tests.py            # E2E 测试运行脚本
│   └── test_backtest_e2e.py        # 项目级 E2E
├── strategies/                     # 策略示例 (120+ 策略)
│   └── XXX_strategy_name/
│       └── strategy_xxx.py
└── docs/                           # 文档
```

## 3. 核心实现模式

### 3.1 后端架构模式

#### 分层架构
```
API 路由层 (api/) -> 服务层 (services/) -> 数据层 (db/)
                  -> 仓储模式 (SQLRepository)
```

#### 路由注册规范
所有路由在 `api/router.py` 统一注册，使用 `try/except ImportError` 处理可选路由：

```python
api_router = APIRouter()

# 核心路由
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(backtest_router, prefix="/backtest", tags=["Backtest"])

# 可选路由 (插件化)
try:
    from app.api.paper_trading import router as paper_trading_router
    api_router.include_router(paper_trading_router, prefix="/paper-trading", tags=["Paper Trading"])
except ImportError:
    pass
```

#### 依赖注入模式
```python
# 服务依赖 (单例)
@lru_cache
def get_backtest_service():
    return BacktestService()

# 用户认证依赖
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenPayload:
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenPayload(**payload)

# 路由使用
@router.post("/run")
async def run_backtest(
    request: BacktestRequest,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    return await service.run_backtest(current_user.sub, request)
```

#### 异步数据库模式
```python
# database.py - 使用 SQLAlchemy 2.0 async
engine = create_async_engine(settings.DATABASE_URL, echo=settings.SQL_ECHO)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()

# 仓储模式
class SQLRepository(Generic[T]):
    async def create(self, obj: T, session: AsyncSession) -> T:
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        return obj
```

### 3.2 前端架构模式

#### API 调用模式
```typescript
// api/index.ts - axios 实例配置
const api: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

// 请求拦截器 - 添加 JWT
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器 - 统一错误处理
api.interceptors.response.use(
  (response) => response.data,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// 模块化 API
export const backtestApi = {
  async run(data: BacktestRequest): Promise<BacktestResponse> {
    return api.post('/backtest/run', data)
  }
}
```

#### Pinia 状态管理
```typescript
// stores/auth.ts
export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const isAuthenticated = computed(() => !!token.value)

  async function login(data: LoginRequest) {
    const response = await authApi.login(data)
    token.value = response.access_token
    localStorage.setItem('token', response.access_token)
  }

  function logout() {
    token.value = null
    localStorage.removeItem('token')
  }

  return { token, isAuthenticated, login, logout }
})
```

#### 路由守卫
```typescript
// router/index.ts
router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
  } else {
    next()
  }
})
```

### 3.3 认证与授权

#### JWT 认证流程
1. 用户登录 -> `auth_service.login()` -> 生成 JWT token
2. 前端存储 token 到 localStorage
3. 每次请求在 header 添加 `Authorization: Bearer <token>`
4. 后端 `get_current_user` 依赖验证并解析 token

#### RBAC 权限模型
```python
# models/permission.py
class Permission(str, enum.Enum):
    CREATE_STRATEGY = "create_strategy"
    UPDATE_STRATEGY = "update_strategy"
    DELETE_STRATEGY = "delete_strategy"
    RUN_BACKTEST = "run_backtest"
    MANAGE_USERS = "manage_users"

ROLE_PERMISSIONS = {
    "admin": [Permission.*],  # 管理员全部权限
    "user": [Permission.CREATE_STRATEGY, Permission.RUN_BACKTEST]
}

# 使用
@router.delete("/strategies/{id}", dependencies=[RequireDeleteStrategy])
async def delete_strategy(strategy_id: str):
    ...
```

### 3.4 回测执行流程

```mermaid
sequenceDiagram
    participant Frontend
    participant API
    participant Service
    participant Subprocess
    participant WebSocket

    Frontend->>API: POST /backtest/run
    API->>Service: run_backtest(user_id, request)
    Service->>Service: 创建 BacktestTask
    Service->>Service: 启动异步任务
    Service-->>Frontend: 返回 task_id
    Service->>Subprocess: 运行 backtrader 子进程
    Subprocess->>WebSocket: 推送进度更新
    Subprocess->>Service: 返回结果
    Service->>Service: 保存 BacktestResultModel
    WebSocket->>Frontend: 推送完成通知
    Frontend->>API: GET /backtest/{task_id}
    API->>Frontend: 返回完整结果
```

### 3.5 策略沙箱执行

用户策略代码在受限环境中执行：

```python
# utils/sandbox.py
class StrategySandbox:
    _ALLOWED_BUILTINS = {
        'abs', 'all', 'any', 'bool', 'dict', 'float', 'int', 'len',
        'list', 'max', 'min', 'range', 'sorted', 'str', 'sum'
    }
    _ALLOWED_MODULES = {'bt', 'datetime', 'math'}

    @classmethod
    def execute_strategy(cls, code: str, **kwargs):
        safe_globals = cls._create_safe_globals()
        safe_locals = kwargs
        exec(code, safe_globals, safe_locals)
        return safe_locals
```

## 4. 关键文件说明

### 后端关键文件
| 文件 | 作用 |
|------|------|
| `main.py` | FastAPI 应用入口，CORS、中间件、路由注册 |
| `config.py` | 环境变量配置 (Settings, get_settings) |
| `api/deps.py` | get_current_user 认证依赖 |
| `api/deps_permissions.py` | RBAC 权限依赖 |
| `services/backtest_service.py` | 回测核心逻辑 (子进程执行) |
| `utils/sandbox.py` | 策略安全执行 |
| `websocket_manager.py` | WebSocket 连接管理 |

### 前端关键文件
| 文件 | 作用 |
|------|------|
| `main.ts` | Vue 应用入口 |
| `router/index.ts` | 路由配置 + 守卫 |
| `api/index.ts` | axios 实例 + 拦截器 |
| `stores/auth.ts` | 认证状态管理 |
| `types/index.d.ts` | TypeScript 类型定义 |

### 配置文件
| 文件 | 作用 |
|------|------|
| `.env` | 环境变量 (DATABASE_URL, SECRET_KEY, etc.) |
| `src/backend/pyproject.toml` | Python 依赖和项目配置 |
| `src/frontend/package.json` | Node.js 依赖 |
| `src/frontend/vite.config.ts` | Vite 配置 (代理 /api 到 :8000) |

## 5. 开发规范

### 后端规范
1. **异步优先**: 所有数据库操作使用 `async/await`
2. **类型注解**: 函数必须包含类型提示
3. **错误处理**: 使用 HTTPException 返回错误
4. **日志**: 使用 `loguru` 记录关键操作
5. **依赖注入**: 服务通过 `Depends` 注入，使用 `@lru_cache` 单例化

### 前端规范
1. **TypeScript 严格模式**: 所有变量需要类型注解
2. **组件式开发**: 优先使用 Composition API (`<script setup>`)
3. **API 模块化**: 按功能拆分 API 模块
4. **状态管理**: 全局状态使用 Pinia，局部状态使用 `ref/reactive`
5. **样式**: Element Plus + Tailwind CSS

### 测试规范
```python
# E2E 测试模式 (Playwright)
@pytest.fixture(scope="function")
def authenticated_page(context, test_user):
    """已登录的页面 fixture"""
    page = context.new_page()
    # 登录逻辑...
    yield page
    page.close()

# 使用
def test_backtest_flow(authenticated_page):
    authenticated_page.goto("/backtest")
    authenticated_page.click("button:has-text('运行')")
    authenticated_page.wait_for_selector(".backtest-result")
```

## 6. 策略开发模式

策略文件位置: `strategies/XXX_strategy_name/strategy_xxx.py`

标准策略结构:
```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""策略描述."""

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class MyStrategy(bt.Strategy):
    """策略类."""

    params = (
        ("param1", 10),
        ("param2", 20),
    )

    def __init__(self):
        """初始化指标."""
        self.indicator = bt.indicators.SMA(self.data.close, period=self.p.param1)

    def next(self):
        """每根 K 线调用."""
        if self.indicator[0] > self.data.close[0]:
            self.buy()
```

## 7. 环境变量

```bash
# 必需配置
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite+aiosqlite:///./backtrader.db
SECRET_KEY=<32+ 字符随机字符串>
JWT_SECRET_KEY=<32+ 字符随机字符串>

# 可选配置
DEBUG=true
HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<安全密码>

# 使用 PostgreSQL
# DATABASE_TYPE=postgresql
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/backtrader
```

## 8. 常用命令

```bash
# 后端开发
cd src/backend
uvicorn app.main:app --reload --port 8000

# 前端开发
cd src/frontend
npm run dev        # http://localhost:3000

# 测试
pytest tests/e2e/ -v --headed  # E2E 测试
npm run test:e2e               # 前端 E2E

# 构建
cd src/frontend && npm run build
```

## 9. API 端点速查

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/auth/register` | POST | 用户注册 |
| `/api/v1/auth/login` | POST | 用户登录 |
| `/api/v1/backtest/run` | POST | 提交回测 |
| `/api/v1/backtest/{task_id}` | GET | 获取结果 |
| `/api/v1/backtest/` | GET | 回测列表 |
| `/api/v1/strategy/` | GET/POST | 策略 CRUD |
| `/api/v1/optimization/run` | POST | 参数优化 |
| `/ws/backtest/{task_id}` | WebSocket | 回测进度 |

## 10. 注意事项

1. **安全**: 生产环境必须更改 `SECRET_KEY` 和 `ADMIN_PASSWORD`
2. **并发**: 回测有全局并发限制 (MAX_GLOBAL_TASKS=10)
3. **数据库**: 默认 SQLite，生产环境推荐 PostgreSQL
4. **WebSocket**: 用于回测进度实时推送，连接路径 `/ws/backtest/{task_id}`
5. **权限**: 使用 RBAC，管理员拥有所有权限
6. **代码风格**: Python 遵循 ruff (line-length=100), TypeScript 遵循 ESLint
