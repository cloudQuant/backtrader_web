# 代码规范

本文档定义 Backtrader Web 项目的代码风格和最佳实践。

## 1. 后端 (Python)

### 1.1 代码风格

- **Python 版本**: 3.10+
- **格式化/Lint**: Ruff (line-length=100, rules: E/F/I/W)
- **类型检查**: Mypy (建议)
- **导入排序**: Ruff (isort 规则已包含)

```bash
# Lint 检查
ruff check src/backend

# 自动修复
ruff check src/backend --fix

# 格式化
ruff format src/backend
```

### 1.2 命名约定

| 元素 | 风格 | 示例 |
|------|------|------|
| 模块/文件 | snake_case | `backtest_service.py` |
| 类 | PascalCase | `BacktestService` |
| 函数/方法 | snake_case | `run_backtest()` |
| 常量 | UPPER_SNAKE | `MAX_RETRIES` |
| 变量 | snake_case | `task_id` |
| API 路由 | kebab-case | `/api/v1/live-trading` |

### 1.3 项目结构约定

```
app/
├── api/          # 路由层 — 仅负责请求解析、参数验证、调用服务
├── services/     # 业务逻辑层 — 核心业务实现
├── schemas/      # Pydantic 模型 — 请求/响应数据结构
├── db/           # 数据库 — ORM 模型、仓库、迁移
├── middleware/    # 中间件 — 日志、安全、异常处理
├── utils/        # 工具 — 日志器、通用辅助函数
└── config.py     # 配置 — 环境变量管理
```

### 1.4 API 路由编写规范

```python
@router.post("/run", response_model=BacktestResponse, summary="Run backtest")
async def run_backtest(
    request: BacktestRequest,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Submit a backtest task.

    Args:
        request: Backtest request payload.
        current_user: Authenticated user.
        service: Backtest service dependency.

    Returns:
        A task response containing task_id and initial status.
    """
    result = await service.run_backtest(current_user.sub, request)
    return result
```

**要点**:
- 使用 `response_model` 定义返回类型
- 使用 `summary` 作为 API 文档标题
- 使用 Google 风格 docstring (Args/Returns/Raises)
- 通过 `Depends()` 注入服务，不直接实例化
- 路由层不包含业务逻辑

### 1.5 服务层规范

- 每个服务类一个文件
- 使用 `@lru_cache` 实现单例
- 异步方法优先 (`async def`)
- 错误处理在服务层完成，返回 None/False 表示失败
- API 层负责将 None 转为 HTTPException

### 1.6 Schema 规范

```python
class BacktestRequest(BaseModel):
    """Backtest request schema.

    Attributes:
        strategy_id: The strategy template ID.
        symbol: Trading symbol (e.g., 000001.SZ).
        start_date: Backtest start date.
        end_date: Backtest end date.
    """
    strategy_id: str
    symbol: str = "000001.SZ"
    start_date: str = "2020-01-01"
    end_date: str = "2023-12-31"
    initial_cash: float = Field(default=100000, ge=1000)
```

## 2. 前端 (TypeScript / Vue 3)

### 2.1 代码风格

- **框架**: Vue 3 + Composition API
- **语言**: TypeScript (严格模式)
- **UI 库**: Element Plus
- **状态管理**: Pinia
- **构建工具**: Vite

### 2.2 命名约定

| 元素 | 风格 | 示例 |
|------|------|------|
| 组件文件 | PascalCase | `BacktestPage.vue` |
| 组合式函数 | camelCase + use 前缀 | `useBacktest()` |
| Store | camelCase + use 前缀 | `useAuthStore()` |
| API 模块 | camelCase | `backtestApi` |
| 类型/接口 | PascalCase | `BacktestResult` |
| 常量 | UPPER_SNAKE | `API_BASE_URL` |

### 2.3 组件结构

```vue
<template>
  <!-- 模板：单根元素，简洁 -->
</template>

<script setup lang="ts">
// 1. 导入
import { ref, computed, onMounted } from 'vue'
import { useBacktestStore } from '@/stores/backtest'

// 2. Props 和 Emits
const props = defineProps<{ taskId: string }>()
const emit = defineEmits<{ (e: 'complete', result: BacktestResult): void }>()

// 3. Store 和响应式数据
const store = useBacktestStore()
const loading = ref(false)

// 4. 计算属性
const hasResult = computed(() => !!store.currentResult)

// 5. 方法
async function runBacktest() { /* ... */ }

// 6. 生命周期
onMounted(() => { /* ... */ })
</script>

<style scoped>
/* 使用 scoped 避免样式污染 */
</style>
```

### 2.4 目录结构

```
src/
├── api/          # API 调用封装
├── components/   # 可复用组件
│   └── common/   # 通用组件 (AppLayout, etc.)
├── views/        # 页面组件 (路由级)
├── stores/       # Pinia 状态管理
├── types/        # TypeScript 类型定义
├── router/       # 路由配置
├── utils/        # 工具函数
└── assets/       # 静态资源
```

## 3. Git 提交约定

### 提交消息格式

```
<type>(<scope>): <description>

[optional body]
```

### 类型

| Type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档更新 |
| `style` | 代码格式（不影响逻辑） |
| `refactor` | 重构 |
| `test` | 测试相关 |
| `chore` | 构建/工具/依赖 |

### 示例

```
feat(backtest): add backtest cancel endpoint
fix(auth): handle expired token refresh
docs(api): update strategy API documentation
test(e2e): add optimization page E2E tests
```

## 4. 安全规范

- **永远不要**硬编码密码、密钥、Token
- 使用环境变量管理敏感配置
- API 密钥通过 `.env` 文件管理（不提交到 Git）
- 用户输入必须通过 Pydantic schema 验证
- 动态执行策略代码使用沙箱环境 (`execute_strategy_safely`)
