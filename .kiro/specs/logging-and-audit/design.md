# Technical Design: Logging Enhancement & User Audit

## Overview

本设计文档描述 backtrader_web 平台日志增强和用户操作审计功能的技术实现方案。基于现有的 loguru 日志框架和 SQLAlchemy 2.0 异步 ORM 架构，增强日志分级控制和按日轮转机制，新增函数调用日志装饰器和前端用户操作审计系统。

**核心目标：**
- 日志分级：测试环境输出 DEBUG 及以上所有日志，生产环境控制台仅输出 WARNING+，文件输出 INFO+
- 按日轮转：日志文件按日期自动分割，旧文件压缩归档，超期自动清理
- 后端装饰器：通过 `@call_logger` 自动记录函数调用时间、耗时、返回值和异常
- 前端审计：捕获用户交互行为并持久化到数据库，支持审计查询

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Vue 3)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │ AuditTracker │──│ EventBuffer  │──│ AuditAPI Client       │ │
│  │  (Plugin)    │  │ (localStorage│  │ (POST /audit/events)  │ │
│  └──────────────┘  │  fallback)   │  └───────────────────────┘ │
│                     └──────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Backend (FastAPI)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │ @call_logger │  │ Audit API    │  │ Audit Service         │ │
│  │  Decorator   │  │ /audit/*     │  │ (validate + persist)  │ │
│  └──────────────┘  └──────────────┘  └───────────────────────┘ │
│         │                                        │               │
│         ▼                                        ▼               │
│  ┌──────────────┐                    ┌───────────────────────┐  │
│  │ loguru       │                    │ AuditRecord Model     │  │
│  │ (file/JSON)  │                    │ (SQLAlchemy)          │  │
│  └──────────────┘                    └───────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**数据流：**
- 函数调用日志：`@call_logger` → loguru → 文件/控制台（JSON/text）
- 用户操作审计：AuditTracker → buffer/localStorage → POST API → AuditService → audit_records 表

## Components and Interfaces

### Component 1: Log Level Policy Enhancement (`app/utils/logger.py` 增强)

**Purpose:** 增强现有 `setup_logger()` 函数，实现基于环境的日志级别自动适配和显式 LOG_LEVEL 覆盖。

**Design:**
```python
# 级别决策逻辑（在现有 setup_logger 中增强）
def _resolve_log_level(settings) -> tuple[str, str]:
    """Resolve console and file log levels based on environment.

    Returns:
        Tuple of (console_level, file_level).

    Priority: LOG_LEVEL env var > DEBUG-based default
    - LOG_LEVEL set: both console and file use LOG_LEVEL
    - DEBUG=true (dev/test): console=DEBUG, file=DEBUG
    - DEBUG=false (production): console=WARNING, file=INFO
    """
```

**Key Decisions:**
- 复用现有 loguru 的 `level` 参数控制每个 sink 的最低输出级别
- 新增 `LOG_LEVEL` 环境变量作为显式覆盖（优先级最高）
- 生产环境控制台只输出 WARNING+（减少噪音），文件仍记录 INFO+（保留审计线索）
- Call Logger 装饰器的日志通过 loguru 统一过滤，无需额外逻辑

### Component 2: Daily Log Rotation Enhancement (`app/utils/logger.py` 增强)

**Purpose:** 确保日志文件按日期分割，旧文件压缩归档，超期自动清理。

**Design:**
```python
# 现有 _add_file_handler 已支持 rotation="00:00" 和 compression="zip"
# 增强点：
# 1. 确保所有 file handler 使用 {time:YYYY-MM-DD} 命名
# 2. 分类保留期：app=30d, errors=90d, audit=365d
# 3. 新增 LOG_DIR 配置项
# 4. 新增 LOG_RETENTION_APP_DAYS, LOG_RETENTION_ERROR_DAYS 配置项
```

**文件命名规范：**
- `{LOG_DIR}/app_YYYY-MM-DD.log` — 应用日志
- `{LOG_DIR}/errors_YYYY-MM-DD.log` — 错误日志
- `{LOG_DIR}/audit_YYYY-MM-DD.log` — 审计日志
- `{LOG_DIR}/backtest_YYYY-MM-DD.log` — 回测日志

**注意：** 项目现有的 `_add_file_handler` 已经实现了 `rotation="00:00"` 和 `compression="zip"`。本次增强主要是：添加 LOG_LEVEL 配置、区分控制台/文件级别、确保配置项可通过环境变量调整。

### Component 3: Call Logger Decorator (`app/utils/call_logger.py`)

**Purpose:** 提供通用的函数调用日志装饰器，自动记录调用时间、耗时、返回值和异常信息。遵循全局日志级别策略。

**Interface:**
```python
def call_logger(
    *,
    log_level: str = "INFO",       # DEBUG/INFO/WARNING/ERROR/CRITICAL
    log_result: bool = True,        # 是否记录返回值
    log_args: bool = True,          # 是否记录入参
    slow_threshold: int = 1000,     # 慢调用阈值(ms)
) -> Callable:
    """Decorator that logs function calls with timing, args, result, and exceptions.

    Raises ValueError at decoration time if log_level is invalid.
    """
```

**Key Decisions:**
- 使用单一装饰器同时支持同步和异步函数（通过 `inspect.iscoroutinefunction` 检测）
- 利用现有的 loguru contextvars 获取 request_id（不存在时不报错）
- 敏感参数过滤：参数名包含 password/token/secret/api_key（大小写不敏感）时替换为 "***"
- 返回值截断到 200 字符，避免大对象污染日志
- 异常处理：记录完整 traceback 后 re-raise 原始异常

### Component 4: Audit API Routes (`app/api/audit.py`)

**Endpoints:**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/audit/events` | User (Bearer) | 批量上报用户操作事件 |
| GET | `/api/v1/audit/records` | Admin only | 查询审计记录（过滤+分页） |

**Dependencies:** `get_current_user` for POST, admin check for GET

### Component 5: Audit Service (`app/services/audit_service.py`)

**Interface:**
```python
class AuditService:
    async def create_events(
        self, events: list[OperationEvent], user_id: str, client_ip: str
    ) -> int:
        """Validate and persist events. Returns count of persisted events."""

    async def query_records(self, params: AuditQueryParams) -> AuditQueryResponse:
        """Query audit records with filters and pagination."""

    async def cleanup_expired_records(self, retention_days: int = 90) -> int:
        """Delete expired records in batches. Returns deleted count."""
```

**Retry Logic:** 数据库写入失败时指数退避重试（100ms → 200ms → 400ms），最多 3 次。

### Component 6: Frontend Audit Tracker (`src/frontend/src/plugins/auditTracker.ts`)

**Interface:**
```typescript
class AuditTracker {
  start(): void       // 注册 click listener + router afterEach
  stop(): void        // 清理 listener 和 timer
  flush(): Promise<void>  // 立即发送 buffer
}

export const auditTrackerPlugin: Plugin  // Vue 3 plugin
```

**Behavior:**
- 全局 click 监听：捕获 button/a/input/select/[role] 元素的点击
- 排除 `data-no-audit` 属性元素及其后代
- Buffer flush：每 10s 或满 50 条时发送
- 离线支持：API 不可达时存入 localStorage（最多 500 条，FIFO）

## Data Models

### AuditRecord (SQLAlchemy Model)

```python
class AuditRecord(Base):
    __tablename__ = "audit_records"

    id: str              # UUID PK
    user_id: str         # FK → users.id, indexed
    session_id: str      # nullable, indexed
    event_type: str      # max 50, indexed
    event_target: str    # max 200, nullable
    page_path: str       # max 500
    event_data: str      # Text (JSON), max 10KB
    client_timestamp: datetime
    server_timestamp: datetime  # indexed
    client_ip: str       # max 45 (IPv6)
```

**Indexes:**
- `ix_audit_user_id` on `user_id`
- `ix_audit_event_type` on `event_type`
- `ix_audit_server_timestamp` on `server_timestamp`
- `ix_audit_user_timestamp` composite on `(user_id, server_timestamp)`

### Pydantic Schemas (`app/schemas/audit.py`)

- `OperationEvent` — 单条事件上报结构
- `AuditEventBatch` — 批量事件请求体（max 50 events）
- `AuditRecordResponse` — 单条记录响应
- `AuditQueryParams` — 查询参数（filters + pagination）
- `AuditQueryResponse` — 分页查询响应（items + metadata）

### Configuration (新增 Settings 字段)

```python
# Log level and rotation settings
LOG_LEVEL: str = ""               # 显式覆盖日志级别，空则按 DEBUG flag 自动决定
LOG_DIR: str = "./logs"           # 日志输出目录
LOG_RETENTION_APP_DAYS: int = 30  # 应用日志保留天数
LOG_RETENTION_ERROR_DAYS: int = 90  # 错误日志保留天数
LOG_RETENTION_AUDIT_DAYS: int = 365 # 审计日志保留天数

# Audit settings
AUDIT_RETENTION_DAYS: int = 90    # 数据库审计记录保留天数 (7-365)
AUDIT_CLEANUP_HOUR: int = 2      # 清理任务执行时间 (0-23)
AUDIT_EVENT_MAX_SIZE_KB: int = 10 # 单条事件最大大小 (1-100)
```

**环境级别策略总结：**

| 环境 | 控制台级别 | 文件级别 | 说明 |
|------|-----------|---------|------|
| 开发/测试 (DEBUG=true) | DEBUG | DEBUG | 输出所有日志 |
| 生产 (DEBUG=false) | WARNING | INFO | 控制台精简，文件保留详情 |
| 显式覆盖 (LOG_LEVEL=X) | X | X | 手动指定，优先级最高 |

## Error Handling

| 场景 | 处理方式 |
|------|----------|
| 装饰器 log_level 无效 | decoration time 抛出 ValueError |
| 被装饰函数异常 | 记录异常日志后 re-raise 原始异常 |
| 审计事件验证失败 | 跳过无效事件，记录 WARNING 日志 |
| 数据库写入失败 | 指数退避重试 3 次，全部失败返回 500 |
| 前端 API 不可达 | 存入 localStorage，下次 flush 时重试 |
| 清理任务数据库错误 | 记录错误，下次调度周期重试 |

## Testing Strategy

- **Log Level Policy:** 单元测试验证 DEBUG=true/false 时的级别输出、LOG_LEVEL 覆盖行为、各 sink 级别一致性
- **Daily Rotation:** 集成测试验证文件命名格式、压缩归档、过期清理（可用 mock 时间加速）
- **Call Logger:** 单元测试验证同步/异步函数、敏感参数过滤、慢调用告警、异常记录、级别策略遵循
- **Audit Service:** 集成测试验证批量写入、验证逻辑、重试机制、清理任务
- **Audit API:** API 测试验证权限控制、分页、过滤条件
- **Frontend Tracker:** Vitest 单元测试验证事件捕获、buffer 管理、localStorage 回退

## Correctness Properties

### Property 1: 环境级别一致性
日志级别策略在所有输出 sink（控制台、应用日志文件、错误日志文件）中一致应用。LOG_LEVEL 显式设置时覆盖 DEBUG flag 的默认行为。
**Validates: Requirements 1.4, 1.6**

### Property 2: 轮转无丢失
日志文件在午夜轮转时，不会丢失任何正在写入的日志条目。loguru 的 `enqueue=True` 确保异步写入的原子性。
**Validates: Requirements 2.6**

### Property 3: 装饰器透明性
`@call_logger` 不改变被装饰函数的返回值和异常行为。函数成功时返回原始值，异常时 re-raise 原始异常。
**Validates: Requirements 3.3, 3.4**

### Property 4: 事件原子性
单条事件验证失败不影响同批次其他有效事件的持久化。每条事件独立验证，有效事件正常写入。
**Validates: Requirements 6.1, 6.3**

### Property 5: 时间一致性
`server_timestamp` 使用 UTC 时区。`client_timestamp` 验证范围为服务器时间 ±24 小时。
**Validates: Requirements 6.1, 6.2**

### Property 6: 权限隔离
普通用户只能上报事件（POST /audit/events），不能查询审计记录。Admin 角色可查询所有用户的记录。
**Validates: Requirements 7.6, 7.7**

### Property 7: 数据完整性
清理任务按批次（1000 条）删除，避免长事务锁表。清理失败不影响应用正常运行。
**Validates: Requirements 8.3, 8.5**

### Property 8: 离线可靠性
前端 localStorage 缓存确保网络中断时事件不丢失（上限 500 条，超出时 FIFO 淘汰最旧事件）。
**Validates: Requirements 5.4**
