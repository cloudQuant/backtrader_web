# Technical Design Document

## Overview

本设计文档描述 Backtrader Web 第二轮最佳实践改进的技术方案。涵盖前端 Element Plus 按需导入、后端 API 响应缓存、前端错误边界与重试、速率限制响应头、优雅停机、Pinia 状态持久化、OpenAPI 文档增强和 CI 缓存优化八个模块的架构设计。

## Architecture

### 系统架构变更概览

本轮改进不改变系统整体架构（FastAPI 后端 + Vue 3 前端 + SQLite/PostgreSQL），而是在现有架构上增加横切关注点（缓存层、韧性层、可观测性增强）。

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (Vue 3)                       │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ErrorBound│  │Retry Intercep│  │Pinia Persistence Plugin│ │
│  │  ary     │  │    tor       │  │  (localStorage/session)│ │
│  └──────────┘  └──────────────┘  └────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐│
│  │ Element Plus Auto-Import (unplugin-vue-components)        ││
│  └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Backend (FastAPI)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │RateLimit Hdrs│  │@cache_response│  │GracefulShutdown  │  │
│  │  Middleware  │  │  Decorator    │  │   Manager        │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐│
│  │ OpenAPI Examples (Pydantic json_schema_extra)             ││
│  └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Cache Layer (Redis / In-Memory)                  │
└─────────────────────────────────────────────────────────────┘
```

### CI 流水线缓存架构

```
GitHub Actions Runner
  ├─ actions/cache@v4 (.venv directory)
  │   └─ Key: venv-${{ hashFiles('pyproject.toml', 'requirements-dev.lock') }}
  ├─ actions/setup-python cache: pip
  │   └─ Key: pip-${{ hashFiles('pyproject.toml') }}
  └─ actions/setup-node cache: npm
      └─ Key: npm-${{ hashFiles('package-lock.json') }}
```

## Components and Interfaces

### 1. CacheBackend Protocol (后端缓存抽象)

```python
from typing import Protocol

class CacheBackend(Protocol):
    """缓存后端协议，支持 Redis 和内存两种实现。"""

    async def get(self, key: str) -> bytes | None:
        """获取缓存值，不存在返回 None。"""
        ...

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        """设置缓存值，ttl 为过期秒数。"""
        ...

    async def delete_pattern(self, pattern: str) -> int:
        """删除匹配模式的所有键，返回删除数量。"""
        ...

    async def exists(self, key: str) -> bool:
        """检查键是否存在。"""
        ...
```

**实现类**:
- `RedisCacheBackend`: 使用 `redis.asyncio` 客户端，`delete_pattern` 通过 `SCAN` + `DEL` 实现
- `MemoryCacheBackend`: 使用 `dict` + `asyncio.Lock`，TTL 通过 `time.monotonic()` 检查

### 2. cache_response 装饰器

```python
def cache_response(ttl: int = 60, key_prefix: str = "api") -> Callable:
    """API 响应缓存装饰器。

    Args:
        ttl: 缓存过期时间（秒），范围 1-86400
        key_prefix: 缓存键前缀，最大 64 字符
    """
```

### 3. RateLimitHeadersMiddleware

```python
class RateLimitHeadersMiddleware:
    """ASGI 中间件，注入速率限制响应头。

    Headers:
        X-RateLimit-Limit: 窗口最大请求数
        X-RateLimit-Remaining: 剩余可用请求数
        X-RateLimit-Reset: 窗口重置 Unix 时间戳
        Retry-After: (仅 429) 建议等待秒数
    """
```

### 4. GracefulShutdownManager

```python
class GracefulShutdownManager:
    """优雅停机管理器。

    Attributes:
        timeout: 最大等待时间（秒）
        is_shutting_down: 停机状态标志

    Methods:
        initiate(): 启动停机流程
        close_websockets(): 向所有 WS 客户端发送关闭帧
        wait_for_drain(): 等待连接排空或超时
    """
```

### 5. ErrorBoundary.vue 组件接口

```typescript
// Props
interface ErrorBoundaryProps {
  fallbackTitle?: string  // 错误标题，默认 "页面出错了"
}

// Emits
interface ErrorBoundaryEmits {
  (e: 'error', error: Error, info: string): void
  (e: 'retry'): void
}

// Slots
// default: 正常内容
// error: 自定义错误 UI（可选）
```

### 6. Retry Interceptor 配置接口

```typescript
interface RetryConfig {
  maxRetries: number       // 默认 3
  initialDelay: number     // 默认 1000ms
  backoffFactor: number    // 默认 2
  jitterRange: number      // 默认 0.1 (±10%)
  retryableStatuses: number[]  // [408, 429, 500, 502, 503, 504]
  idempotentMethods: string[]  // ['GET', 'HEAD', 'OPTIONS', 'PUT', 'DELETE']
}
```

## Data Models

### 缓存数据结构（Redis）

```
Key:    "api:strategies:/api/v1/strategies:a1b2c3d4"
Value:  {"status_code": 200, "body": {...}, "cached_at": "2025-01-01T00:00:00Z"}
TTL:    30 seconds
```

### Pinia 持久化数据结构（Browser Storage）

```
// sessionStorage
Key:    "auth"
Value:  {"token": "eyJ...", "refreshToken": "eyJ..."}

// localStorage
Key:    "preferences"
Value:  {"theme": "dark", "locale": "zh-CN", "sidebarCollapsed": false}
```

### 无数据库 Schema 变更

本轮改进不涉及 SQLAlchemy ORM 模型或 Alembic 迁移变更。所有新增数据存储在 Redis（临时缓存）或浏览器 Storage（客户端状态）中。

## Error Handling

### 缓存层错误处理

| 场景 | 处理策略 |
|------|---------|
| Redis 连接超时 | fail-open，直接执行路由处理函数，记录 WARNING |
| Redis 序列化失败 | 跳过缓存，返回原始响应，记录 ERROR |
| 缓存键过长 | 截断或哈希处理，记录 WARNING |
| 内存缓存 OOM | 使用 LRU 淘汰策略，限制最大条目数 |

### 速率限制头错误处理

| 场景 | 处理策略 |
|------|---------|
| slowapi 状态不可读 | fail-open，不添加头部，记录 WARNING |
| Redis 限流后端异常 | 允许请求通过，不限流，记录 WARNING |

### 优雅停机错误处理

| 场景 | 处理策略 |
|------|---------|
| WebSocket 关闭帧发送失败 | 记录 WARNING，继续处理其他连接 |
| 超时后仍有连接 | 强制关闭，记录连接数和等待时间 |
| SHUTDOWN_TIMEOUT 配置无效 | 使用默认值 30s，记录 WARNING |

### 前端错误处理

| 场景 | 处理策略 |
|------|---------|
| ErrorBoundary 捕获错误 | 显示错误 UI，记录到 console.error |
| Retry 达到最大次数 | 抛出最后一次错误，触发一次 ElMessage |
| Storage 不可用 | 静默降级，不持久化，不抛异常 |

## Correctness Properties

### Property 1: 缓存写后读一致性

写操作后立即读取同一资源，必须返回最新数据（缓存已失效）。验证方式：写操作后调用 `invalidate_cache`，随后的 GET 请求返回 `X-Cache: MISS` 且数据为最新值。

**Validates: Requirements 2.8**

### Property 2: 缓存 TTL 过期正确性

缓存 TTL 过期后，下一次读取必须执行路由处理函数获取最新数据。验证方式：设置 TTL=1s 的缓存，等待 2s 后请求返回 `X-Cache: MISS`。

**Validates: Requirements 2.1, 2.3, 2.4**

### Property 3: 缓存故障透明性

Redis 不可用时，系统行为与无缓存时完全一致（功能正确性不依赖缓存）。验证方式：断开 Redis 连接后所有 API 端点正常返回正确数据。

**Validates: Requirements 2.5**

### Property 4: 重试幂等安全性

Retry Interceptor 仅对幂等方法自动重试，POST 请求不会被意外重复执行。验证方式：模拟 POST 请求 503 响应，确认不触发重试。

**Validates: Requirements 3.7**

### Property 5: 停机请求完整性

停机期间已接受的请求必须被完整处理或在超时后明确中断。验证方式：发起长请求后触发 SIGTERM，请求在 SHUTDOWN_TIMEOUT 内正常完成或收到明确错误。

**Validates: Requirements 5.2, 5.4**

### Property 6: 状态持久化隔离性

持久化的 token 仅存在于 sessionStorage，浏览器关闭后自动清除；localStorage 中不包含认证凭据。验证方式：检查 localStorage 中无 token 相关键。

**Validates: Requirements 6.3**

## Security Considerations

- **缓存隔离**: 需要认证的端点（如策略列表）缓存键必须包含 `user_id`，防止用户间数据泄露
- **Token 存储**: access token 使用 sessionStorage 而非 localStorage，降低 XSS 持久化风险
- **停机安全**: 停机期间健康检查返回 503，确保负载均衡器及时摘除节点
- **Rate Limit 信息**: 仅暴露标准化配额信息，不泄露内部限流实现细节
- **缓存投毒防护**: 缓存键基于请求路径和参数哈希，不包含用户可控的任意内容

## Testing Strategy

### 后端测试矩阵

| 模块 | 测试类型 | 文件 | 用例数 |
|------|---------|------|--------|
| 缓存装饰器 | 单元测试 | `tests/test_cache_response.py` | ≥8 |
| 速率限制头 | 集成测试 | `tests/test_rate_limit_headers.py` | ≥5 |
| 优雅停机 | 集成测试 | `tests/test_graceful_shutdown.py` | ≥4 |
| OpenAPI 示例 | 验证测试 | `tests/test_openapi_examples.py` | ≥4 |

### 前端测试矩阵

| 模块 | 测试类型 | 文件 | 用例数 |
|------|---------|------|--------|
| ErrorBoundary | 单元测试 | `src/components/__tests__/ErrorBoundary.spec.ts` | ≥3 |
| Retry Interceptor | 单元测试 | `src/api/__tests__/retry-interceptor.spec.ts` | ≥4 |
| Pinia 持久化 | 单元测试 | `src/stores/__tests__/persistence.spec.ts` | ≥4 |

## Dependencies

### 新增前端依赖

| 包名 | 类型 | 版本 | 用途 |
|------|------|------|------|
| `unplugin-vue-components` | devDependency | `^28.0.0` | Element Plus 组件按需导入 |
| `unplugin-auto-import` | devDependency | `^19.0.0` | Element Plus API 按需导入 |
| `pinia-plugin-persistedstate` | dependency | `^4.0.0` | Pinia 状态持久化 |

### 新增后端依赖

无新增。Redis 客户端已在 `[redis]` 可选依赖中。

## Migration Plan

1. **Phase 1 (Quick Wins)**: CI 缓存优化 + Pinia 持久化 — 低风险，立即见效
2. **Phase 2 (Frontend)**: Element Plus 按需导入 + 错误边界与重试 — 前端独立变更
3. **Phase 3 (Backend)**: API 缓存 + 速率限制头 + OpenAPI 示例 — 后端增强
4. **Phase 4 (Infrastructure)**: 优雅停机 — 需要集成测试验证
