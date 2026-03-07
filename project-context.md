---
project_name: backtrader_web
user_name: cloud
date: 2026-03-07
sections_completed:
  - technology_stack
  - directory_structure
  - implementation_patterns
  - key_files
  - development_standards
  - strategy_development
  - environment_variables
  - common_commands
  - api_endpoints
  - cicd_pipeline
  - fincore_integration
  - testing_framework
  - error_handling
  - performance_optimization
  - monitoring
  - usage_guidelines
status: complete
rule_count: 150+
optimized_for_llm: true
last_updated: 2026-03-07
---

# Backtrader Web - 项目上下文文档

> 本文档为 AI 代理优化的项目上下文参考，包含关键实现规则、模式和约定。
>
> **最后更新**: 2026-03-07 | **新增章节**: 14. 错误处理规范 | 15. 性能优化指南 | 16. 监控方案

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

## 11. CI/CD 质量管道

### GitHub Actions 工作流

项目使用 5 个生产级 GitHub Actions 工作流实现自动化质量保证：

| 工作流文件 | 触发条件 | 功能 |
|-----------|---------|------|
| `ci.yml` | push/PR to master/develop | 主 CI：lint、测试、安全扫描、覆盖率 |
| `e2e.yml` | push/PR + 手动 | E2E 多浏览器测试（Chromium/Firefox/WebKit/Mobile） |
| `pr-check.yml` | PR 事件 | PR 验证、大小检查、自动审查清单 |
| `nightly.yml` | 每日 2:00 UTC | 夜间全面测试、覆盖率徽章生成 |
| `deploy-preview.yml` | PR 事件 | 预览环境部署 |

### 质量门控标准

**后端质量门：**
- ✅ Ruff lint 通过 (E, F, I, W 规则)
- ✅ 导入排序检查
- ✅ 单元测试通过 + 100% 覆盖率
- ✅ 安全扫描 (Bandit, Safety)
- ✅ 集成测试通过 (PostgreSQL)

**前端质量门：**
- ✅ ESLint 检查通过
- ✅ TypeScript 类型检查
- ✅ 单元测试通过 + 覆盖率
- ✅ 生产构建成功

**E2E 质量门：**
- ✅ Chromium 浏览器测试通过
- ✅ Firefox 浏览器测试通过
- ✅ WebKit (Safari) 测试通过
- ✅ Mobile Chrome 测试通过
- ✅ Mobile Safari 测试通过

### E2E 测试配置

**Playwright 配置要点：**
```typescript
// playwright.config.ts
- 浏览器矩阵：5 个浏览器（Desktop 3 + Mobile 2）
- 失败处理：自动截图、视频、追踪
- 报告格式：HTML/JSON/JUnit
- 重试策略：CI 环境 2 次重试
- storageState：避免重复登录
```

**E2E 测试最佳实践：**
- 使用 `storageState` 消除重复登录
- 只在失败时截图和录制视频
- 并行执行独立测试
- 智能等待替代硬编码延迟

### 覆盖率集成

- **Codecov**: 自动上传覆盖率报告
- **Badge**: 覆盖率徽章自动生成
- **报告**: HTML/XML/Term 多格式输出
- **保留**: 覆盖率报告保留 7-30 天

### PR 审查自动化

**PR 检查清单（自动生成）：**
```markdown
## Review Checklist

### Code Quality
- [ ] Code follows project style guidelines
- [ ] No console.log or debug statements
- [ ] Proper error handling implemented
- [ ] Tests added/updated for new features

### Testing
- [ ] All tests pass locally
- [ ] Unit tests cover new code
- [ ] E2E tests pass for affected areas
- [ ] Manual testing completed

### Documentation
- [ ] API documentation updated (if needed)
- [ ] README updated (if needed)
- [ ] Comments explain complex logic

### Security
- [ ] No hardcoded credentials
- [ ] Input validation implemented
- [ ] Proper authentication/authorization checks
```

**PR 大小警告：**
- > 2000 行变更：警告
- > 50 个文件：警告

## 12. 金融指标标准化 (fincore)

### fincore 库集成

项目使用 `fincore>=1.0.0` 库提供标准化的金融性能指标计算。

**核心适配器：**
```python
# app/services/backtest_analyzers.py
class FincoreAdapter:
    """fincore 库适配器，提供标准化金融指标计算"""
    
    def calculate_basic_metrics(self, returns: List[float]) -> Dict:
        """计算基础性能指标"""
        return {
            "sharpe_ratio": self._calculate_sharpe(returns),
            "max_drawdown": self._calculate_max_drawdown(returns),
            "total_returns": self._calculate_total_returns(returns),
            "annual_returns": self._calculate_annual_returns(returns),
        }
    
    def calculate_advanced_metrics(self, trades: List[Trade]) -> Dict:
        """计算高级分析指标"""
        return {
            "win_rate": self._calculate_win_rate(trades),
            "profit_factor": self._calculate_profit_factor(trades),
            "avg_holding_period": self._calculate_avg_holding(trades),
            "max_consecutive_wins": self._calculate_max_consecutive(trades, win=True),
        }
```

### 可用指标

| 指标 | 描述 | 来源 |
|------|------|------|
| Sharpe Ratio | 风险调整收益 | FincoreAdapter |
| Max Drawdown | 最大回撤 | FincoreAdapter |
| Total Returns | 总收益率 | FincoreAdapter |
| Annual Returns | 年化收益 | FincoreAdapter |
| Win Rate | 胜率 | FincoreAdapter |
| Profit Factor | 盈亏比 | FincoreAdapter |
| Avg Holding Period | 平均持仓时间 | FincoreAdapter |
| Max Consecutive | 最大连续赢/亏 | FincoreAdapter |

### 使用规范

**在回测服务中使用：**
```python
# app/services/backtest_service.py
from app.services.backtest_analyzers import FincoreAdapter

class BacktestService:
    def __init__(self):
        self.fincore_adapter = FincoreAdapter()
    
    async def run_backtest(self, user_id: str, request: BacktestRequest):
        # ... 执行回测 ...
        
        # 使用 fincore 计算指标
        metrics = self.fincore_adapter.calculate_basic_metrics(returns)
        advanced_metrics = self.fincore_adapter.calculate_advanced_metrics(trades)
        
        # 保存结果时标记指标来源
        result.metrics_source = "fincore"
        result.metrics = {**metrics, **advanced_metrics}
```

### 指标来源追踪

数据库模型包含 `metrics_source` 字段用于追踪指标计算来源：

```python
# app/models/backtest.py
class BacktestResultModel(Base):
    __tablename__ = "backtest_results"
    
    id = Column(Integer, primary_key=True)
    task_id = Column(String, unique=True)
    metrics_source = Column(String, default="fincore")  # fincore | manual
    metrics = Column(JSON)
```

### 回退机制

如果 fincore 不可用，系统自动回退到手动计算：

```python
class FincoreAdapter:
    def calculate_basic_metrics(self, returns: List[float]) -> Dict:
        try:
            # 优先使用 fincore
            return self._fincore_metrics(returns)
        except ImportError:
            # 回退到手动计算
            return self._manual_metrics(returns)
```

### 测试覆盖

fincore 集成包含完整测试套件：
- 88 个 fincore 相关测试
- 导入验证测试
- 适配器单元测试
- 集成测试
- 高级指标测试

## 13. 测试框架详解

### 后端测试框架

**pytest 配置：**
```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "W"]
ignore = ["E501"]
```

**测试文件组织：**
```
src/backend/tests/
├── conftest.py              # pytest fixtures
├── factories.py             # 测试数据工厂
├── test_*.py                # 73 个测试文件
├── pytest.ini               # pytest 配置
└── IMPROVEMENTS.md          # 测试改进记录
```

**测试命名规范：**
- 文件：`test_*.py`
- 类：`TestFeatureName`
- 方法：`test_specific_scenario`

### 前端测试框架

**Vitest 配置：**
```typescript
// vite.config.ts
test: {
  globals: true,
  environment: 'jsdom',
  include: ['src/**/*.{test,spec}.{ts,tsx}'],
  setupFiles: ['./src/test/setup.ts'],
  coverage: {
    provider: 'v8',
    include: ['src/**/*.{ts,vue}'],
    exclude: ['src/main.ts', 'src/**/*.d.ts', 'src/test/**'],
  },
}
```

**测试命令：**
```bash
npm run test              # 单元测试
npm run test -- --coverage # 覆盖率报告
npm run test:e2e          # E2E 测试
npm run test:e2e:headed   # E2E 可视化
npm run test:e2e:ui       # E2E UI 模式
```

### 测试覆盖率要求

- **后端：** 100% 覆盖率（1218 个测试通过）
- **前端：** 100% 覆盖率
- **E2E：** 覆盖关键用户流程

### Mock 使用规范

**后端 Mock：**
```python
from unittest.mock import Mock, patch

@patch('app.services.backtest_service.BacktestService')
def test_backtest_mock(mock_service):
    mock_service.return_value.run_backtest.return_value = {"task_id": "123"}
    # 测试逻辑
```

**前端 Mock：**
```typescript
import { vi } from 'vitest'

vi.mock('@/api/backtest', () => ({
  backtestApi: {
    run: vi.fn().mockResolvedValue({ task_id: '123' })
  }
}))
```

### CI/CD 测试集成

**测试自动运行：**
- 每次 push/PR 自动运行所有测试
- 测试失败阻止合并
- 覆盖率报告自动上传 Codecov
- E2E 失败自动保存截图/视频/追踪

**质量门控：**
- 所有测试必须通过
- 覆盖率不能下降
- 新代码必须有测试覆盖
- E2E 测试在 5 个浏览器上通过

## 14. 错误处理规范

### API 错误响应格式

**统一错误结构:**
```json
{
  "detail": "错误描述信息",
  "error_code": "OPTIONAL_ERROR_CODE",
  "timestamp": "2026-03-07T10:30:00Z",
  "error_id": "uuid-for-tracking"
}
```

**HTTP 状态码使用规范:**
| 状态码 | 使用场景 | 示例 |
|--------|---------|------|
| 200 | 成功响应 | GET/POST 成功 |
| 201 | 资源创建成功 | POST 创建策略 |
| 400 | 请求参数错误 | 缺少必需字段 |
| 401 | 未认证 | Token 无效/过期 |
| 403 | 无权限 | RBAC 权限不足 |
| 404 | 资源不存在 | 策略 ID 不存在 |
| 409 | 资源冲突 | 重复创建 |
| 422 | 验证失败 | Pydantic 验证错误 |
| 429 | 速率限制 | 过于频繁请求 |
| 500 | 服务器内部错误 | 未预期的异常 |
| 502 | 第三方服务错误 | 交易所 API 故障 |
| 503 | 服务不可用 | 数据库连接断开 |
| 507 | 资源不足 | 内存溢出 |

### 后端错误处理模式

**Service 层错误处理:**
```python
# ✅ 正确: Service 层返回 None/False 表示预期失败
async def get_strategy(strategy_id: int, db: AsyncSession) -> Optional[Strategy]:
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    return result.scalar_one_or_none()  # 不存在时返回 None

# ✅ 正确: 在 API 层转换为 HTTPException
@router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db)
):
    strategy = await strategy_service.get_strategy(strategy_id, db)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy
```

**数据库事务错误处理:**
```python
async def create_strategy(data: StrategyCreate, db: AsyncSession):
    try:
        strategy = Strategy(**data.dict())
        db.add(strategy)
        await db.commit()
        await db.refresh(strategy)
        return strategy
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"Duplicate entry: {e}")
        raise ValueError("Strategy name already exists")
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create strategy: {e}")
        raise
```

**并发竞态条件处理:**
```python
from contextlib import asynccontextmanager
import asyncio

class BacktestTaskLock:
    """回测任务锁，防止并发冲突"""
    def __init__(self):
        self._locks = {}
    
    @asynccontextmanager
    async def acquire(self, task_id: str):
        while task_id in self._locks:
            await asyncio.sleep(0.1)
        self._locks[task_id] = True
        try:
            yield
        finally:
            del self._locks[task_id]

# 使用示例
async def cancel_backtest(task_id: str, db: AsyncSession):
    async with task_lock.acquire(task_id):
        task = await db.get(BacktestTask, task_id)
        if task.status == "completed":
            raise ValueError("Cannot cancel completed task")
        task.status = "cancelled"
        await db.commit()
```

**策略沙箱执行超时:**
```python
import signal
from contextlib import contextmanager

class TimeoutException(Exception):
    pass

@contextmanager
def timeout_handler(seconds: int):
    """策略执行超时处理器"""
    def timeout_func(signum, frame):
        raise TimeoutException(f"Strategy execution timed out after {seconds} seconds")
    
    signal.signal(signal.SIGALRM, timeout_func)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)

async def execute_strategy_safely(code: str, timeout: int = 30):
    """安全执行策略代码"""
    try:
        with timeout_handler(timeout):
            result = StrategySandbox.execute_strategy(code)
            return {"success": True, "result": result}
    except TimeoutException:
        logger.error(f"Strategy execution timeout")
        return {"success": False, "error": "Execution timeout"}
    except Exception as e:
        logger.error(f"Strategy execution error: {e}")
        return {"success": False, "error": str(e)}
```

**第三方 API 错误处理:**
```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

class ExchangeAPIError(Exception):
    """交易所 API 错误"""
    pass

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry_error_exceptions=(httpx.TimeoutException, httpx.NetworkError)
)
async def fetch_market_data(symbol: str):
    """获取市场数据（带重试）"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"https://api.exchange.com/market/{symbol}",
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            logger.error(f"Exchange API timeout for {symbol}")
            raise ExchangeAPIError("Market data request timed out")
        except httpx.HTTPStatusError as e:
            logger.error(f"Exchange API error: {e.response.status_code}")
            raise ExchangeAPIError(f"API returned {e.response.status_code}")
        except httpx.NetworkError as e:
            logger.error(f"Network error: {e}")
            raise ExchangeAPIError("Network connection failed")
```

### 前端错误处理模式

**axios 拦截器统一处理:**
```typescript
// api/index.ts
api.interceptors.response.use(
  (response) => response.data,
  (error: AxiosError) => {
    // 401: Token 过期
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
      return Promise.reject(error)
    }
    
    // 422: 验证错误
    if (error.response?.status === 422) {
      const detail = error.response.data?.detail
      const message = Array.isArray(detail) 
        ? detail[0]?.msg 
        : detail
      ElMessage.error(message || 'Validation failed')
      return Promise.reject(error)
    }
    
    // 429: 速率限制
    if (error.response?.status === 429) {
      ElMessage.warning('请求过于频繁，请稍后重试')
      return Promise.reject(error)
    }
    
    // 500: 服务器错误
    if (error.response?.status === 500) {
      const errorId = error.response.data?.error_id
      ElMessage.error(`服务器错误 ${errorId ? `(错误ID: ${errorId})` : ''}`)
      return Promise.reject(error)
    }
    
    // 其他错误
    const message = error.response?.data?.detail || error.message || '请求失败'
    ElMessage.error(message)
    return Promise.reject(error)
  }
)
```

**Vue 错误边界:**
```typescript
// App.vue
<script setup lang="ts">
import { onErrorCaptured } from 'vue'

onErrorCaptured((error, instance, info) => {
  logger.error('Vue error:', { 
    error, 
    component: instance?.$options?.name, 
    info 
  })
  ElMessage.error('应用发生错误，请刷新页面')
  return false // 阻止错误继续传播
})
</script>
```

### 全局异常处理

**后端全局异常处理器:**
```python
# app/middleware/exception_handling.py
import uuid
from datetime import datetime

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_id = str(uuid.uuid4())
    
    # 结构化日志
    logger.error(
        f"Unhandled exception {error_id}",
        extra={
            "error_id": error_id,
            "path": request.url.path,
            "method": request.method,
            "error_type": type(exc).__name__,
            "stack_trace": traceback.format_exc(),
        }
    )
    
    # 敏感信息过滤
    error_message = sanitize_error_message(exc)
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_id": error_id,
            "timestamp": datetime.utcnow().isoformat()
        }
    )

def sanitize_error_message(error: Exception) -> str:
    """过滤错误消息中的敏感信息"""
    message = str(error)
    # 过滤数据库连接字符串
    message = re.sub(
        r'postgresql://[^@]+@[^/]+', 
        'postgresql://***:***@***', 
        message
    )
    # 过滤 API 密钥
    message = re.sub(r'api_key=[^&\s]+', 'api_key=***', message)
    return message
```

### 关键错误处理规则

**必须遵循:**
- ✅ Service 层返回 `None`/`False` 表示预期失败，不抛出异常
- ✅ API 层将 Service 层失败转换为 `HTTPException`
- ✅ 数据库操作必须有 try/except 和 rollback
- ✅ 并发操作必须使用锁机制
- ✅ 策略执行必须有超时保护
- ✅ 第三方 API 调用必须有重试机制
- ✅ 前端统一通过 axios 拦截器处理错误
- ✅ 使用 `loguru` 记录所有错误（`logger.error()`）
- ✅ 所有用户操作失败记录到审计日志
- ✅ 错误消息必须过滤敏感信息

**禁止:**
- ❌ Service 层直接抛出 `HTTPException`（违反分层原则）
- ❌ 前端直接 `console.log` 错误（使用 ElMessage）
- ❌ 捕获异常后不记录日志
- ❌ 返回不明确的错误消息（如 "Error occurred"）
- ❌ 在错误消息中暴露敏感信息（密码、API 密钥、路径）

### 测试错误场景

**错误处理测试覆盖:**
```python
class TestErrorHandling:
    """测试错误处理边界情况"""
    
    @pytest.mark.asyncio
    async def test_database_connection_timeout(self, client):
        """测试数据库连接超时"""
        with patch('app.db.database.async_session_maker') as mock_session:
            mock_session.side_effect = asyncio.TimeoutError()
            
            response = await client.get("/api/v1/strategies")
            assert response.status_code == 503
    
    @pytest.mark.asyncio
    async def test_strategy_not_found(self, client):
        """测试策略不存在"""
        response = await client.get("/api/v1/strategies/99999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Strategy not found"
    
    @pytest.mark.asyncio
    async def test_validation_error(self, client):
        """测试验证错误"""
        response = await client.post("/api/v1/strategies", json={
            "name": "",  # 空名称
        })
        assert response.status_code == 422
```

## 15. 性能优化指南

### 数据库查询优化

**索引策略:**
```python
# ✅ 为常用查询添加索引
class BacktestTask(Base):
    __tablename__ = "backtest_tasks"
    
    # 复合索引
    __table_args__ = (
        Index('idx_user_status', 'user_id', 'status'),
    )
    
    # 单列索引
    user_id = Column(Integer, index=True)
    status = Column(String, index=True)
    created_at = Column(DateTime, index=True)
```

**查询优化规则:**
```python
# ✅ 使用 JOIN 而不是 N+1 查询
async def get_backtest_with_results(task_id: str, db: AsyncSession):
    result = await db.execute(
        select(BacktestTask, BacktestResult)
        .where(BacktestTask.id == task_id)
        .options(joinedload(BacktestResult))
    )
    return result.scalar_one_or_none()

# ✅ 使用分页避免全表扫描
async def get_strategies_paginated(
    user_id: int, 
    skip: int = 0, 
    limit: int = 20,
    db: AsyncSession
):
    query = select(Strategy).where(Strategy.user_id == user_id)
    
    # 总数查询
    count_query = select(func(count(Strategy.id)).label('total')).where(Strategy.user_id == user_id)
    total = await db.scalar(count_query)
    
    # 分页查询
    query = query.offset(skip).limit(limit).order_by(Strategy.created_at.desc())
    strategies = await db.execute(query)
    
    return {
        "total": total,
        "items": strategies.scalars().all(),
        "skip": skip,
        "limit": limit
    }

# ✅ 使用 exists 而不是 count > 0
async def strategy_exists(strategy_id: int, db: AsyncSession) -> bool:
    result = await db.execute(
        select(Strategy.id).where(Strategy.id == strategy_id).exists()
    )
    return result.scalar()
```

**N+1 查询反模式:**
```python
# ❌ 避免: N+1 查询问题
async def get_strategies_bad(user_id: int, db: AsyncSession):
    strategies = await db.execute(select(Strategy).where(Strategy.user_id == user_id))
    strategies = strategies.scalars().all()
    
    # 这会导致 N+1 查询问题
    for strategy in strategies:
        versions = await db.execute(
            select(StrategyVersion).where(StrategyVersion.strategy_id == strategy.id)
        )
        strategy.versions = versions.scalars().all()
    
    return strategies

# ✅ 正确: 使用 joinedload 或显式 JOIN
async def get_strategies_good(user_id: int, db: AsyncSession):
    strategies = await db.execute(
        select(Strategy)
        .options(joinedload(Strategy.versions))
        .where(Strategy.user_id == user_id)
    )
    return strategies.scalars().all()
```

### API 响应优化

**响应序列化优化:**
```python
# ✅ 使用 Pydantic 的 exclude 排除敏感字段
class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    # 排除密码等敏感字段
    
    class Config:
        from_attributes = True

# ❌ 避免: 返回完整的 ORM 对象
@router.get("/users/{user_id}")
async def get_user_bad(user_id: int, db: AsyncSession):
    user = await db.get(User, user_id)
    return user  # 会暴露所有字段

# ✅ 正确: 使用 Pydantic schema 过滤
@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user_good(user_id: int, db: AsyncSession):
    user = await db.get(User, user_id)
    return UserResponse.model_validate(user)
```

**大数据集响应:**
```python
# ✅ 使用流式响应处理大数据集
from fastapi.responses import StreamingResponse

@router.get("/backtest/{task_id}/trades")
async def get_trades_stream(task_id: str, db: AsyncSession):
    """流式返回交易记录"""
    async def generate():
        offset = 0
        batch_size = 1000
        
        while True:
            trades = await db.execute(
                select(Trade)
                .where(Trade.backtest_id == task_id)
                .offset(offset)
                .limit(batch_size)
            )
            
            batch = trades.scalars().all()
            if not batch:
                break
            
            for trade in batch:
                yield f"data: {trade.json()}\n\n"
            
            offset += batch_size
    
    return StreamingResponse(
        content=generate(),
        media_type="application/x-ndjson"
    )
```

### 异步任务优化

**回测任务并发控制:**
```python
import asyncio
from contextlib import asynccontextmanager

class BacktestConcurrencyManager:
    """回测任务并发控制"""
    
    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_tasks = {}
    
    @asynccontextmanager
    async def acquire_slot(self, task_id: str):
        """获取执行槽位"""
        async with self._semaphore:
            self._active_tasks[task_id] = {
                "start_time": datetime.utcnow(),
                "status": "running"
            }
            try:
                yield
            finally:
                del self._active_tasks[task_id]
    
    async def get_active_count(self) -> int:
        """获取活跃任务数"""
        return len(self._active_tasks)
    
    async def get_queue_length(self) -> int:
        """获取等待队列长度"""
        return self._semaphore._value

# 使用示例
concurrency_manager = BacktestConcurrencyManager(max_concurrent=10)

async def run_backtest_with_limit(task_id: str):
    """带并发限制的回测执行"""
    async with concurrency_manager.acquire_slot(task_id):
        # 执行回测逻辑
        result = await execute_backtest(task_id)
        return result
```

**任务优先级队列:**
```python
import asyncio
from enum import IntEnum
from dataclasses import dataclass

class TaskPriority(IntEnum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

@dataclass
class PrioritizedTask:
    """优先级任务"""
    task_id: str
    priority: TaskPriority
    created_at: datetime = field(default_factory=datetime.utcnow)

class PriorityTaskQueue:
    """优先级任务队列"""
    
    def __init__(self):
        self._queue = []
        self._lock = asyncio.Lock()
    
    async def put(self, task: PrioritizedTask):
        """添加任务"""
        async with self._lock:
            heapq.heappush(self._queue, (-task.priority.value, task.created_at, task))
    
    async def get(self) -> Optional[PrioritizedTask]:
        """获取最高优先级任务"""
        async with self._lock:
            if self._queue:
                _, _, task = heapq.heappop(self._queue)
                return task
            return None
    
    async def size(self) -> int:
        """队列大小"""
        async with self._lock:
            return len(self._queue)
```

### 内存优化

**大数据集内存优化:**
```python
# ✅ 使用生成器处理大数据集
async def process_large_dataset(file_path: str):
    """使用生成器逐行处理大数据集"""
    with open(file_path, 'r') as f:
        for line in f:
            data = json.loads(line)
            # 处理每一行
            yield process_data(data)

# ❌ 避免: 一次性加载所有数据到内存
async def process_large_dataset_bad(file_path: str):
    """一次性加载所有数据（内存溢出风险）"""
    with open(file_path, 'r') as f:
        all_data = [json.loads(line) for line in f]  # 可能导致内存溢出
    for data in all_data:
        process_data(data)

# ✅ 使用流式处理
async def stream_process_backtest_results(task_id: str):
    """流式处理回测结果"""
    async for trade in get_trades_stream(task_id):
        # 逐条处理交易记录
        await process_trade(trade)
```

**对象池优化:**
```python
from queue import Queue

class PyObjectPool:
    """Python 对象池"""
    
    def __init__(self, factory_func, max_size: int = 100):
        self.factory_func = factory_func
        self.max_size = max_size
        self._pool = Queue(maxsize=max_size)
    
    def get(self):
        """从池中获取对象"""
        if not self._pool.empty():
            return self._pool.get()
        return self.factory_func()
    
    def put(self, obj):
        """归还对象到池中"""
        if not self._pool.full():
            self._pool.put(obj)
    
    def clear(self):
        """清空对象池"""
        while not self._pool.empty():
            self._pool.get()

# 使用示例
strategy_pool = PyObjectPool(lambda: Strategy())

def get_strategy():
    strategy = strategy_pool.get()
    # 使用 strategy...
    return strategy

def release_strategy(strategy):
    # 重置 strategy 状态
    strategy_pool.put(strategy)
```

### 缓存策略

**虽然架构决策是"无缓存 - 始终重新计算",但以下场景可考虑缓存:**

**计算密集型指标缓存:**
```python
from functools import lru_cache

# ✅ 对纯函数计算结果缓存
@lru_cache(maxsize=128)
def calculate_sharpe_ratio_cached(returns_tuple: tuple) -> float:
    """缓存夏普比率计算结果"""
    returns = list(returns_tuple)
    return calculate_sharpe_ratio(returns)

# 使用示例
async def get_backtest_metrics(task_id: str):
    trades = await get_trades(task_id)
    returns = tuple([t.return_pct for t in trades])  # 转为元组以便缓存
    sharpe = calculate_sharpe_ratio_cached(returns)
    return {"sharpe_ratio": sharpe}
```

**配置数据缓存:**
```python
from datetime import timedelta
import redis.asyncio as redis

class ConfigCache:
    """配置数据缓存（允许短暂缓存）"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.ttl = timedelta(minutes=5)
    
    async def get_strategy_config(self, strategy_id: int) -> dict:
        """获取策略配置（缓存 5 分钟）"""
        cache_key = f"config:strategy:{strategy_id}"
        
        # 尝试从缓存获取
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)
        
        # 从数据库获取
        config = await self._load_config_from_db(strategy_id)
        
        # 缓存
        await self.redis.setex(
            cache_key,
            self.ttl,
            json.dumps(config)
        )
        
        return config
    
    async def invalidate(self, strategy_id: int):
        """使缓存失效"""
        await self.redis.delete(f"config:strategy:{strategy_id}")
```

### 前端性能优化

**组件懒加载:**
```typescript
// router/index.ts
import { defineAsyncComponent } from 'vue'

const routes = [
  {
    path: '/backtest',
    name: 'Backtest',
    component: defineAsyncComponent(() => import('@/views/BacktestPage.vue')),
  },
  {
    path: '/live-trading',
    name: 'LiveTrading',
    component: defineAsyncComponent(() => import('@/views/LiveTradingPage.vue')),
  },
]
```

**虚拟滚动优化:**
```vue
<template>
  <el-table-v2
    :columns="columns"
    :data="data"
    :width="800"
    :height="600"
    :row-height="50"
    :item-size="50"
  />
</template>

<script setup lang="ts">
import { ElTableV2 } from 'element-plus'

// 虚拟滚动适用于大数据集（>1000 行）
const data = ref([]) // 大数据集
</script>
```

**防抖和节流:**
```typescript
import { debounce, throttle } from 'lodash-es'

// 搜索输入防抖
const handleSearch = debounce((query: string) => {
  fetchStrategies(query)
}, 300)

// 滚动事件节流
const handleScroll = throttle(() => {
  loadMoreData()
}, 200)
```

### 性能监控

**慢查询监控:**
```python
import time
from contextlib import contextmanager

@contextmanager
def query_performance_monitor(query_name: str, threshold_ms: int = 100):
    """查询性能监控"""
    start_time = time.time()
    try:
        yield
    finally:
        duration_ms = (time.time() - start_time) * 1000
        if duration_ms > threshold_ms:
            logger.warning(
                f"Slow query detected",
                extra={
                    "query_name": query_name,
                    "duration_ms": duration_ms,
                    "threshold_ms": threshold_ms
                }
            )

# 使用示例
async def get_strategies(user_id: int, db: AsyncSession):
    with query_performance_monitor("get_strategies", threshold_ms=100):
        result = await db.execute(select(Strategy).where(Strategy.user_id == user_id))
        return result.scalars().all()
```

**API 响应时间监控:**
```python
from fastapi import Request
import time

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """添加处理时间响应头"""
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
    
    # 记录慢请求
    if process_time > 500:
        logger.warning(
            f"Slow request: {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "process_time_ms": process_time
            }
        )
    
    return response
```

### 性能优化清单

**数据库优化:**
- ✅ 为常用查询字段添加索引
- ✅ 使用 JOIN 而不是 N+1 查询
- ✅ 使用分页避免全表扫描
- ✅ 使用 `exists()` 而不是 `count() > 0`
- ✅ 大数据集使用流式响应
- ✅ 监控慢查询（>100ms）

**API 优化:**
- ✅ 使用 Pydantic schema 过滤敏感字段
- ✅ 大数据集使用流式响应（NDJSON）
- ✅ 添加响应时间监控
- ✅ 实现请求速率限制

**异步任务优化:**
- ✅ 使用信号量控制并发
- ✅ 实现优先级队列
- ✅ 任务超时保护
- ✅ 任务取消机制

**内存优化:**
- ✅ 使用生成器处理大数据集
- ✅ 对象池复用
- ✅ 避免一次性加载大量数据

**前端优化:**
- ✅ 组件懒加载
- ✅ 虚拟滚动（大数据集）
- ✅ 防抖和节流
- ✅ 图片懒加载

**缓存策略:**
- ⚠️ 默认无缓存（架构决策）
- ✅ 纯函数计算结果可缓存（lru_cache）
- ✅ 配置数据可短暂缓存（5 分钟 TTL）

## 16. 监控方案

### 应用健康监控

**健康检查端点:**
```python
from fastapi import APIRouter
from datetime import datetime
import asyncio

router = APIRouter()

@router.get("/health")
async def health_check():
    """应用健康检查"""
    checks = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "checks": {
            "database": await check_database_health(),
            "redis": await check_redis_health(),
            "memory": check_memory_usage(),
            "disk": check_disk_usage(),
        }
    }
    
    # 任何检查失败则返回 503
    if not all(checks["checks"].values()):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "checks": checks["checks"]
            }
        )
    
    return checks

async def check_database_health() -> bool:
    """检查数据库连接"""
    try:
        from app.db.database import async_session_maker
        async with async_session_maker() as session:
            await session.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False

async def check_redis_health() -> bool:
    """检查 Redis 连接"""
    try:
        import redis.asyncio as redis
        from app.config import settings
        
        client = redis.from_url(settings.REDIS_URL)
        await client.ping()
        await client.close()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False

def check_memory_usage() -> bool:
    """检查内存使用"""
    import psutil
    memory_percent = psutil.virtual_memory().percent
    return memory_percent < 90  # 内存使用率 < 90%

def check_disk_usage() -> bool:
    """检查磁盘使用"""
    import psutil
    disk_percent = psutil.disk_usage('/').percent
    return disk_percent < 90  # 磁盘使用率 < 90%
```

**Kubernetes 探针配置:**
```yaml
# deployment.yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 3

startupProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 30
```

### 日志聚合

**结构化日志配置:**
```python
# utils/logger.py
from loguru import logger
import sys
import json

def setup_logging():
    """配置结构化日志"""
    
    # 移除默认处理器
    logger.remove()
    
    # JSON 格式日志（生产环境）
    def json_sink(message):
        """JSON 格式日志输出"""
        record = message.record
        log_entry = {
            "timestamp": record["time"].isoformat(),
            "level": record["level"].name,
            "message": record["message"],
            "module": record["module"],
            "function": record["function"],
            "line": record["line"],
            "extra": record.get("extra", {}),
        }
        
        # 添加错误信息
        if record["exception"]:
            log_entry["exception"] = {
                "type": record["exception"].type.__name__,
                "value": str(record["exception"].value),
                "traceback": record["exception"].traceback,
            }
        
        print(json.dumps(log_entry), file=sys.stderr)
    
    # 配置日志级别
    import os
    log_level = os.getenv("LOG_LEVEL", "INFO")
    
    # 添加 JSON sink（生产环境）
    if os.getenv("ENVIRONMENT") == "production":
        logger.add(
            json_sink,
            level=log_level,
            format="{message}",
        )
    else:
        # 开发环境使用彩色输出
        logger.add(
            sys.stderr,
            level=log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            colorize=True,
        )
    
    # 文件日志（审计）
    logger.add(
        "logs/audit.log",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        rotation="100 MB",
        retention="30 days",
        filter=lambda record: record["extra"].get("audit"),
    )
    
    # 性能日志
    logger.add(
        "logs/performance.log",
        level="WARNING",
        format="{time} | {message}",
        rotation="50 MB",
        retention="7 days",
        filter=lambda record: record["extra"].get("performance"),
    )
```

**日志使用规范:**
```python
# ✅ 正确: 使用结构化日志
logger.info(
    "User logged in",
    extra={
        "user_id": user.id,
        "username": user.username,
        "ip_address": request.client.host,
        "user_agent": request.headers.get("user-agent"),
        "audit": True,  # 标记为审计日志
    }
)

# ✅ 正确: 记录性能问题
logger.warning(
    "Slow database query",
    extra={
        "query": str(query),
        "duration_ms": duration_ms,
        "threshold_ms": 100,
        "performance": True,  # 标记为性能日志
    }
)

# ✅ 正确: 记录错误上下文
logger.error(
    "Backtest execution failed",
    extra={
        "task_id": task_id,
        "strategy_id": strategy_id,
        "error_type": type(e).__name__,
        "stack_trace": traceback.format_exc(),
    }
)
```

**ELK Stack 集成:**
```yaml
# filebeat.yml
filebeat.inputs:
- type: log
  enabled: true
  paths:
    - /app/logs/*.log
  json.keys_under_root: true
  json.add_error_key: true

output.elasticsearch:
  hosts: ["http://elasticsearch:9200"]
  index: "backtrader-web-%{[agent.version]}-%{+yyyy.MM.dd}"

setup.kibana:
  host: "http://kibana:5601"
```

### 性能监控

**Prometheus 指标收集:**
```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# 定义指标
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint']
)

ACTIVE_REQUESTS = Gauge(
    'http_requests_active',
    'Active HTTP requests'
)

BACKTEST_TASKS_RUNNING = Gauge(
    'backtest_tasks_running',
    'Running backtest tasks'
)

BACKTEST_TASKS_QUEUED = Gauge(
    'backtest_tasks_queued',
    'Queued backtest tasks'
)

BACKTEST_DURATION = Histogram(
    'backtest_duration_seconds',
    'Backtest execution duration',
    ['strategy_type']
)

DATABASE_QUERY_DURATION = Histogram(
    'database_query_duration_seconds',
    'Database query duration',
    ['query_type']
)

# FastAPI 中间件
@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    """Prometheus 监控中间件"""
    ACTIVE_REQUESTS.inc()
    
    with REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path
    ).time():
        response = await call_next(request)
    
    ACTIVE_REQUESTS.dec()
    
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    return response

# 指标端点
@app.get("/metrics")
async def metrics():
    """Prometheus 指标端点"""
    return Response(
        content=generate_latest(),
        media_type="text/plain"
    )
```

**Grafana Dashboard 配置:**
```json
{
  "dashboard": {
    "title": "Backtrader Web Monitoring",
    "panels": [
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(http_requests_total[5m])",
            "legendFormat": "{{method}} {{endpoint}}"
          }
        ]
      },
      {
        "title": "Request Latency (P95)",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))",
            "legendFormat": "P95 Latency"
          }
        ]
      },
      {
        "title": "Active Backtest Tasks",
        "type": "gauge",
        "targets": [
          {
            "expr": "backtest_tasks_running",
            "legendFormat": "Running"
          },
          {
            "expr": "backtest_tasks_queued",
            "legendFormat": "Queued"
          }
        ]
      },
      {
        "title": "Database Query Performance",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(database_query_duration_seconds_bucket[5m]))",
            "legendFormat": "{{query_type}}"
          }
        ]
      }
    ]
  }
}
```

### 错误追踪

**Sentry 集成:**
```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

def init_sentry():
    """初始化 Sentry 错误追踪"""
    import os
    
    sentry_dsn = os.getenv("SENTRY_DSN")
    if not sentry_dsn:
        return
    
    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.getenv("ENVIRONMENT", "development"),
        release=os.getenv("RELEASE_VERSION", "1.0.0"),
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.1,  # 10% 请求追踪
        before_send=before_send_sentry,
    )

def before_send_sentry(event, hint):
    """发送前过滤敏感信息"""
    # 过滤请求头中的敏感信息
    if "request" in event and "headers" in event["request"]:
        headers = event["request"]["headers"]
        # 移除敏感头
        headers.pop("Authorization", None)
        headers.pop("Cookie", None)
    
    # 过滤请求体中的敏感信息
    if "request" in event and "data" in event["request"]:
        data = event["request"]["data"]
        if isinstance(data, dict):
            data.pop("password", None)
            data.pop("api_key", None)
    
    return event

# 添加用户上下文
@app.middleware("http")
async def sentry_user_context(request: Request, call_next):
    """添加 Sentry 用户上下文"""
    from app.api.deps import get_current_user_optional
    
    user = await get_current_user_optional(request)
    if user:
        sentry_sdk.set_user({
            "id": user.id,
            "username": user.username,
            "email": user.email,
        })
    
    return await call_next(request)
```

### 告警配置

**告警规则定义:**
```yaml
# alerting_rules.yml
groups:
  - name: backtrader_web_alerts
    rules:
      # 高错误率告警
      - alert: HighErrorRate
        expr: |
          rate(http_requests_total{status=~"5.."}[5m]) 
          / 
          rate(http_requests_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }}"
      
      # 高延迟告警
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95, 
            rate(http_request_duration_seconds_bucket[5m])
          ) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High API latency detected"
          description: "P95 latency is {{ $value | humanizeDuration }}"
      
      # 数据库连接池耗尽告警
      - alert: DatabasePoolExhausted
        expr: |
          db_connection_pool_available == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Database connection pool exhausted"
          description: "No available database connections"
      
      # 回测任务堆积告警
      - alert: BacktestTaskQueueBacklog
        expr: |
          backtest_tasks_queued > 50
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Backtest task queue backlog"
          description: "{{ $value }} tasks queued"
      
      # 内存使用率过高告警
      - alert: HighMemoryUsage
        expr: |
          (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) 
          / node_memory_MemTotal_bytes > 0.9
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High memory usage"
          description: "Memory usage is {{ $value | humanizePercentage }}"
```

**AlertManager 配置:**
```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m
  smtp_smarthost: 'smtp.example.com:587'
  smtp_from: 'alerts@backtrader-web.com'
  smtp_require_tls: true

route:
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'team-email'

receivers:
  - name: 'team-email'
    email_configs:
      - to: 'team@backtrader-web.com'
        send_resolved: true
        headers:
          Subject: '[{{ .Status | toUpper }}] {{ .GroupLabels.alertname }}'
```

### 实时监控仪表板

**监控指标看板:**
```python
@router.get("/admin/dashboard/metrics")
async def get_system_metrics():
    """系统监控指标"""
    import psutil
    from app.services.backtest_service import backtest_service
    
    return {
        "system": {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory": {
                "total_gb": psutil.virtual_memory().total / (1024**3),
                "available_gb": psutil.virtual_memory().available / (1024**3),
                "percent": psutil.virtual_memory().percent,
            },
            "disk": {
                "total_gb": psutil.disk_usage('/').total / (1024**3),
                "used_gb": psutil.disk_usage('/').used / (1024**3),
                "percent": psutil.disk_usage('/').percent,
            },
        },
        "application": {
            "active_requests": ACTIVE_REQUESTS._value.get(),
            "backtest": {
                "running": await backtest_service.get_running_count(),
                "queued": await backtest_service.get_queued_count(),
                "completed_today": await backtest_service.get_completed_count_today(),
            },
            "database": {
                "pool_size": await get_db_pool_size(),
                "active_connections": await get_db_active_connections(),
            },
        },
        "timestamp": datetime.utcnow().isoformat(),
    }
```

### 监控清单

**必须监控的指标:**
- ✅ HTTP 请求速率和延迟（P95/P99）
- ✅ 错误率（4xx/5xx）
- ✅ 活跃请求数
- ✅ 数据库连接池状态
- ✅ 回测任务队列长度
- ✅ 系统资源（CPU/内存/磁盘）
- ✅ 应用健康状态

**必须配置的告警:**
- ✅ 高错误率（>5%）
- ✅ 高延迟（P95 > 1s）
- ✅ 数据库连接池耗尽
- ✅ 任务队列堆积（>50）
- ✅ 内存使用率过高（>90%）

**日志要求:**
- ✅ 结构化 JSON 日志
- ✅ 审计日志（用户操作）
- ✅ 性能日志（慢查询/慢请求）
- ✅ 错误日志（包含堆栈跟踪）
- ✅ 敏感信息过滤

**错误追踪要求:**
- ✅ Sentry 集成
- ✅ 用户上下文
- ✅ 请求上下文
- ✅ 敏感信息过滤
- ✅ 错误分组和去重

---

## 使用指南

### 给 AI 代理的指南

**实现前必读:**
1. **完整阅读本文档** - 在开始任何实现之前,完整阅读相关章节
2. **遵循所有规则** - 严格按照文档中的规则和模式实现
3. **优先级原则** - 当有冲突时,选择更严格/保守的选项
4. **参考现有代码** - 查看现有代码库中的实现示例
5. **保持一致性** - 硵保新代码与现有代码风格一致

**关键提醒:**
- ⚠️ **不要假设** - 如果不确定,先搜索代码库或询问用户
- ⚠️ **不要跳过测试** - 所有新功能必须有测试覆盖
- ⚠️ **不要忽略错误处理** - 参考"错误处理规范"章节
- ⚠️ **不要硬编码** - 使用配置文件和环境变量
- ⚠️ **不要绕过沙箱** - 策略代码必须在沙箱中执行

**实现新功能清单:**
```
□ 1. 阅读 project-context.md 相关章节
□ 2. 搜索现有代码库中的类似实现
□ 3. 设计 API Schema (Pydantic)
□ 4. 实现 Service 层逻辑
□ 5. 实现 API 路由
□ 6. 编写单元测试
□ 7. 编写集成测试
□ 8. 更新 API 文档
□ 9. 运行所有测试确保通过
□ 10. 提交前进行代码审查
```

### 给开发人员的指南

**日常使用:**
- 📖 **开始工作前** - 快速浏览相关章节,特别是"开发规范"
- 🔍 **实现时参考** - 遇到不确定的规则时查阅对应章节
- ✅ **代码审查** - 使用本文档作为审查标准
- 🔄 **持续更新** - 发现新模式时更新文档

**维护建议:**
- 🗓️ **季度审查** - 每 3 个月审查一次,移除过时规则
- ➕ **添加新规则** - 发现新的关键模式时及时添加
- ➖ **精简冗余** - 发现规则变得明显时移除
- 📊 **版本更新** - 技术栈升级时更新对应章节

**团队协作:**
- 👥 **新成员入职** - 必读文档,快速了解项目规范
- 💬 **代码审查** - 使用文档作为统一标准
- 🎓 **知识共享** - 团队成员共同维护和更新
- 🔄 **持续改进** - 收集团队反馈优化规则

### 快速参考表

**关键技术栈:**
| 类别 | 技术 | 版本 |
|------|------|------|
| 后端 | FastAPI + SQLAlchemy 2.0 | 0.109+ / 2.0+ |
| 前端 | Vue 3 + TypeScript | 3.4+ / 5.3+ |
| 数据库 | SQLite / PostgreSQL / MySQL | - |
| 认证 | JWT + bcrypt | - |
| 回测 | Backtrader + fincore | 1.9.78+ / 1.0+ |
| 测试 | pytest + Playwright | - |

**关键文件位置:**
```
src/backend/app/
├── api/           # API 路由
├── services/      # 业务逻辑
├── models/        # 数据库模型
├── schemas/       # Pydantic 模型
└── db/            # 数据库层

src/frontend/src/
├── api/           # API 调用
├── stores/        # 状态管理
├── views/         # 页面组件
└── components/    # 可复用组件
```

**关键命令:**
```bash
# 后端
pytest                                    # 运行测试
pytest tests/test_auth.py                # 运行单个测试
ruff check src/backend                    # Lint
ruff format src/backend                   # 格式化

# 前端
npm run dev                               # 开发服务器
npm run test                              # 运行测试
npm run lint                              # Lint
npm run build                             # 构建
```

**关键章节快速导航:**
- 🏗️ 新功能实现 → 第 3 章"核心实现模式"
- 🐛 错误处理 → 第 14 章"错误处理规范"
- ⚡ 性能优化 → 第 15 章"性能优化指南"
- 📊 监控告警 → 第 16 章"监控方案"
- 🧪 测试规范 → 第 5.3 节"测试规范"
- 🚀 CI/CD → 第 11 章"CI/CD 质量管道"

---

**最后更新**: 2026-03-07 | **版本**: 2.0 | **维护者**: cloud
