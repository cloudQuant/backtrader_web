# Implementation Plan: Logging Enhancement & User Audit

## Overview

本计划将日志增强和用户操作审计功能拆分为 10 个任务，按依赖关系排序。日志基础设施增强（Task 1）最先执行，后端 Call Logger 和审计模型（Task 2-7）随后，前端集成（Task 8-9）紧跟，最后在现有服务上应用装饰器（Task 10）。

## Task Dependency Graph

```json
{
  "waves": [
    ["1"],
    ["2", "3"],
    ["4", "7"],
    ["5"],
    ["6", "8"],
    ["9"],
    ["10"]
  ]
}
```

**依赖说明：**
- Wave 1: Task 1 (日志分级与轮转增强) — 基础设施，其他任务依赖
- Wave 2: Task 2 (Call Logger) 和 Task 3 (Model) 依赖 Task 1，可并行
- Wave 3: Task 4 (Schemas) 依赖 Task 3；Task 7 (Config) 可提前准备
- Wave 4: Task 5 (Service) 依赖 Task 3 + Task 4
- Wave 5: Task 6 (API) 依赖 Task 5；Task 8 (Tracker) 可独立开发
- Wave 6: Task 9 (Frontend API) 依赖 Task 6 + Task 8
- Wave 7: Task 10 (Apply Decorator) 依赖 Task 2

## Tasks

- [x] 1. 增强日志分级输出与按日轮转
  增强 `src/backend/app/utils/logger.py` 中的 `setup_logger()` 函数：
  - 实现环境感知的日志级别策略：DEBUG=true 时控制台和文件均输出 DEBUG+；DEBUG=false 时控制台输出 WARNING+，文件输出 INFO+
  - 新增 LOG_LEVEL 环境变量支持，设置后覆盖 DEBUG flag 的默认行为
  - 在 `app/config.py` 中添加 `LOG_LEVEL` (str, default=""), `LOG_DIR` (str, default="./logs"), `LOG_RETENTION_APP_DAYS` (int, default=30), `LOG_RETENTION_ERROR_DAYS` (int, default=90), `LOG_RETENTION_AUDIT_DAYS` (int, default=365)
  - 确保所有 file handler 使用 `{time:YYYY-MM-DD}` 命名格式（已有，验证一致性）
  - 确保 rotation="00:00"（按日轮转）和 compression="zip"（压缩归档）对所有文件 handler 生效
  - 使用各分类的保留期配置替代硬编码值（app→LOG_RETENTION_APP_DAYS, errors→LOG_RETENTION_ERROR_DAYS, audit→LOG_RETENTION_AUDIT_DAYS）
  - 在 `.env.example` 中添加 LOG_LEVEL, LOG_DIR, LOG_RETENTION_*_DAYS 配置说明

- [x] 2. 实现 Call Logger 装饰器
  创建 `src/backend/app/utils/call_logger.py`，实现 `call_logger` 装饰器：
  - 接受 `log_level`, `log_result`, `log_args`, `slow_threshold` 参数
  - 同时支持同步和异步函数（`inspect.iscoroutinefunction` 检测）
  - 敏感参数过滤（password/token/secret/api_key 大小写不敏感，替换为 "***"）
  - 返回值截断到 200 字符
  - request_id 上下文传播（从 loguru contextvars 获取，不存在时不报错）
  - 慢调用检测（duration > slow_threshold 时额外 WARNING 日志）
  - log_level 参数验证（无效值在 decoration time 抛出 ValueError）
  - 异常处理：记录 exception type + message + traceback 到 ERROR 级别，re-raise 原始异常
  - 遵循全局日志级别策略：当全局最低级别为 WARNING 时，INFO 级别的调用日志被自动抑制，ERROR 级别的异常日志仍然输出

- [x] 3. 创建 AuditRecord 数据库模型
  创建 `src/backend/app/models/audit_record.py`：
  - 定义 `AuditRecord` 模型继承 `Base`，表名 `audit_records`
  - 字段：id (String(36) UUID PK), user_id (String(36) FK→users.id), session_id (String(64)), event_type (String(50)), event_target (String(200)), page_path (String(500)), event_data (Text), client_timestamp (DateTime), server_timestamp (DateTime), client_ip (String(45))
  - 索引：user_id, event_type, server_timestamp, 复合索引 (user_id, server_timestamp)
  - 在 `app/models/__init__.py` 中导出 AuditRecord

- [x] 4. 创建审计 Pydantic Schemas
  创建 `src/backend/app/schemas/audit.py`：
  - `OperationEvent`：event_type (max 50), event_target (max 200), page_path (max 500), event_data (dict, optional), client_timestamp (datetime), session_id (optional)
  - `AuditEventBatch`：events (list[OperationEvent], max_length=50)
  - `AuditRecordResponse`：所有 AuditRecord 字段的响应 DTO
  - `AuditQueryParams`：user_id, event_type, start_time, end_time, page (ge=1), page_size (1-100, default=20)
  - `AuditQueryResponse`：items, total_count, current_page, total_pages
  - 验证：event_data JSON 大小不超过 10KB

- [x] 5. 实现 Audit Service
  创建 `src/backend/app/services/audit_service.py`：
  - `AuditService` 类使用 `SQLRepository(AuditRecord)`
  - `create_events` 方法：验证每条事件（非空字段、时间范围 ±24h、event_data 大小），持久化有效事件，验证失败记录 WARNING 日志并跳过
  - 数据库写入重试：指数退避 100ms → 200ms → 400ms，最多 3 次
  - `query_records` 方法：支持 user_id/event_type/start_time/end_time 过滤（AND），分页，按 server_timestamp DESC 排序
  - `cleanup_expired_records` 方法：按批次 1000 条删除过期记录，记录删除数量和耗时

- [x] 6. 实现审计 API 路由
  创建 `src/backend/app/api/audit.py`：
  - `POST /audit/events`：需要用户认证，接收 AuditEventBatch，提取 client_ip，调用 AuditService.create_events
  - `GET /audit/records`：需要 admin 权限，接收查询参数，返回 AuditQueryResponse
  - admin 权限检查（非 admin 返回 403）
  - 无效参数处理（错误时间格式、page_size 超限返回 422）
  - 在 `app/api/router.py` 注册：`api_router.include_router(audit_router, prefix="/audit", tags=["Audit"])`

- [x] 7. 添加审计配置和清理调度
  - 在 `app/config.py` Settings 中添加：AUDIT_RETENTION_DAYS (default=90, 7-365), AUDIT_CLEANUP_HOUR (default=2, 0-23), AUDIT_EVENT_MAX_SIZE_KB (default=10, 1-100)
  - 在 `.env.example` 中添加审计配置项说明
  - 在 `app/main.py` lifespan 中注册清理定时任务（APScheduler，每天 AUDIT_CLEANUP_HOUR 执行）
  - 清理任务错误处理：捕获异常记录日志，不影响应用运行

- [x] 8. 实现前端 Audit Tracker 插件
  创建 `src/frontend/src/plugins/auditTracker.ts`：
  - `AuditTracker` 类：事件 buffer、flush 定时器（10s）、最大批次（50 条）
  - 全局 click 事件监听：过滤 button/a/input/select/[role] 元素
  - `data-no-audit` 属性排除逻辑（含后代元素）
  - 元素标识生成：优先 id，否则最近祖先 id + tagName + index
  - Vue Router `afterEach` 钩子捕获导航事件
  - localStorage 离线缓存（最多 500 条，FIFO 淘汰）
  - 连接恢复后自动发送积压事件
  - OperationEvent 中包含 user_id 和 session_id（从 auth store 获取）

- [x] 9. 前端审计 API 集成
  - 创建 `src/frontend/src/api/audit.ts`：定义 `postAuditEvents(events)` 和 `getAuditRecords(params)` 方法
  - 在 `src/frontend/src/main.ts` 中注册 auditTrackerPlugin
  - Tracker 仅在用户已认证时激活（监听 auth store 状态）
  - 用户登出时调用 tracker.flush() 发送剩余事件并停止追踪

- [x] 10. 在现有服务层应用 Call Logger 装饰器
  - 在 `app/services/auth_service.py` 关键方法上添加 `@call_logger()`
  - 在 `app/services/backtest_service.py` 关键方法上添加 `@call_logger(slow_threshold=5000)`
  - 在 `app/services/strategy_service.py` 关键方法上添加 `@call_logger()`
  - 确保含敏感参数的方法正确过滤 password 字段
  - 验证装饰器不影响现有功能（现有测试通过）
  - 验证生产模式下 INFO 级别的调用日志不输出到控制台（只输出到文件）

## Notes

- 每个 Task 完成后应运行 `pytest` 确保不破坏现有功能
- Task 8-9 完成后应运行 `npm run typecheck` 确保类型安全
- 数据库模型变更需要通过 `alembic` 生成迁移脚本
- 建议在开发环境先验证 Call Logger 的性能开销（< 1ms）
- Task 1 是基础设施增强，现有代码已有部分实现（rotation/compression），主要是补充级别策略和配置化
