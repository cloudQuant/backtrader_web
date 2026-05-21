# Implementation Plan: Best Practices Iteration 2

## Overview

第二轮最佳实践改进，分 4 个阶段实施。Phase 1（Quick Wins）为低风险的 CI 缓存和状态持久化；Phase 2（Frontend）为前端性能和韧性优化；Phase 3（Backend）为后端缓存、限流和文档增强；Phase 4（Infrastructure）为优雅停机。

## Tasks

- [x] 1. Phase 1: Quick Wins - CI 缓存与状态持久化
  - [x] 1.1 CI 流水线缓存优化
    - 为 `backend-lint` 和 `backend-test` job 添加 `actions/setup-python@v5` 的 `cache: 'pip'` 参数
    - 为所有前端 job 确认 `actions/setup-node@v4` 的 `cache: 'npm'` 和 `cache-dependency-path` 配置
    - 为 `check-openapi`、`check-migrations`、`check-deps-sync` 预检 job 添加 pip 缓存
    - 添加 `actions/cache@v4` 缓存 backend `.venv` 目录，key 基于 `pyproject.toml` + `requirements-dev.lock` 哈希
    - 在 `ci-summary` job 中添加缓存命中状态和各 job 执行时间输出
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 1.2 安装并配置 Pinia 持久化插件
    - 安装 `pinia-plugin-persistedstate` 依赖
    - 在 `main.ts` 中 Pinia 实例创建后注册持久化插件
    - 为认证 store 配置 `persist: { storage: sessionStorage, paths: ['token', 'refreshToken'] }`
    - 为用户偏好相关 store 配置 `persist: { storage: localStorage, paths: [...] }`
    - 确保 loading、error 等临时状态不被持久化
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 1.3 编写 Pinia 持久化单元测试
    - 创建 `src/frontend/src/stores/__tests__/persistence.spec.ts`
    - 测试状态写入 localStorage/sessionStorage
    - 测试页面刷新后状态恢复
    - 测试 `paths` 选择性持久化（临时状态不写入）
    - 测试存储不可用时的静默降级
    - _Requirements: 6.7_

- [x] 2. Checkpoint - Phase 1 验证
  - 确保所有测试通过，CI 缓存生效。

- [x] 3. Phase 2: Frontend - Element Plus 按需导入与错误韧性
  - [x] 3.1 配置 Element Plus 按需自动导入
    - 安装 `unplugin-vue-components` 和 `unplugin-auto-import` 为 devDependencies
    - 在 `vite.config.ts` plugins 中注册两个插件，使用 `ElementPlusResolver`
    - 配置生成 `auto-imports.d.ts` 和 `components.d.ts` 类型声明文件
    - 将生成的 `.d.ts` 文件加入 `tsconfig.json` 的 `include`
    - 将 `auto-imports.d.ts` 和 `components.d.ts` 加入 `.gitignore`（或提交到仓库，视团队偏好）
    - _Requirements: 1.1, 1.2, 1.3, 1.6_

  - [x] 3.2 移除 Element Plus 全量导入
    - 移除 `main.ts` 中 `import ElementPlus from 'element-plus'` 和 `app.use(ElementPlus)`
    - 移除 `import 'element-plus/dist/index.css'`
    - 评估 `@element-plus/icons-vue` 全局注册方案：保留显式注册或使用 `unplugin-icons`
    - 移除 `vite.config.ts` 中 `manualChunks` 的 `'element-plus'` 条目
    - 运行 `npm run build` 验证构建成功，对比体积变化
    - 运行 `npm run typecheck` 确认无类型错误
    - _Requirements: 1.4, 1.5, 1.7_

  - [x] 3.3 验证 Element Plus 按需导入无回归
    - 运行 `npm run test -- --run` 确认所有单元测试通过
    - 运行 `npm run build` 确认生产构建成功
    - 记录构建前后的 gzip 体积对比
    - _Requirements: 1.8_

  - [x] 3.4 创建 ErrorBoundary 组件
    - 创建 `src/frontend/src/components/ErrorBoundary.vue`
    - 实现 `onErrorCaptured` 钩子，返回 `false` 阻止错误传播
    - 实现错误状态切换：正常显示 slot 内容 / 错误时显示错误提示 UI
    - 实现"重试"按钮，通过 key 变化触发子组件重新创建
    - 在 `App.vue` 或路由布局中包裹 `<router-view>` 使用 ErrorBoundary
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 3.5 实现 Axios Retry Interceptor
    - 在 `src/frontend/src/api/index.ts` 中添加响应错误拦截器的重试逻辑
    - 实现可重试状态码判断（408/429/500/502/503/504/ERR_NETWORK）
    - 实现幂等方法判断（GET/HEAD/OPTIONS/PUT/DELETE 自动重试，POST 需 Idempotency-Key）
    - 实现指数退避延迟（1000ms/2000ms/4000ms，±10% 抖动）
    - 使用 `__isRetrying` 标志跳过重试期间的 ElMessage 提示
    - _Requirements: 3.5, 3.6, 3.7, 3.8, 3.9_

  - [x] 3.6 编写错误边界与重试机制单元测试
    - 创建 `src/frontend/src/components/__tests__/ErrorBoundary.spec.ts`
    - 创建 `src/frontend/src/api/__tests__/retry-interceptor.spec.ts`
    - 测试 ErrorBoundary 捕获错误后显示错误 UI
    - 测试 ErrorBoundary 点击重试后恢复子组件
    - 测试 Retry Interceptor GET 请求 503 时执行 3 次重试
    - 测试退避延迟序列（1s/2s/4s ±10%）
    - 测试 POST 无 Idempotency-Key 不重试
    - 测试 POST 有 Idempotency-Key 执行重试
    - _Requirements: 3.10_

- [x] 4. Checkpoint - Phase 2 验证
  - 确保所有前端测试通过，构建体积减少。

- [x] 5. Phase 3: Backend - 缓存、限流头与文档增强
  - [x] 5.1 实现 API 响应缓存装饰器
    - 创建/增强 `src/backend/app/utils/response_cache.py`，实现 `@cache_response(ttl, key_prefix)` 装饰器
    - 实现 `CacheBackend` 协议及 `RedisCacheBackend`、`MemoryCacheBackend` 两个实现
    - 缓存键格式：`{key_prefix}:{path}:{md5(sorted_query_params)}`
    - 仅对 GET 请求缓存，添加 `X-Cache: HIT/MISS` 响应头
    - Redis 异常时 fail-open，记录 WARNING 日志
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.9_

  - [x] 5.2 为目标端点启用缓存并实现失效
    - 为 `/api/v1/health` 启用缓存（TTL 10s）
    - 为 `/api/v1/strategies` 启用缓存（TTL 30s）
    - 为 `/api/v1/backtests/{id}/result` 启用缓存（TTL 60s）
    - 在策略服务的写操作中调用 `invalidate_cache("strategies", ...)`
    - 在回测服务的写操作中调用 `invalidate_cache("backtests", ...)`
    - _Requirements: 2.7, 2.8_

  - [x] 5.3 实现速率限制响应头中间件
    - 创建 `src/backend/app/middleware/rate_limit_headers.py`
    - 实现 `RateLimitHeadersMiddleware` ASGI 中间件
    - 从 slowapi limiter 状态提取窗口信息，注入 X-RateLimit-* 头部
    - 429 响应添加 `Retry-After` 头和标准化响应体
    - 异常时 fail-open，不添加头部，记录警告
    - 在 `main.py` 中注册中间件
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 5.4 为核心 Pydantic Schema 添加 OpenAPI 示例值
    - 为 `app/schemas/auth.py` 添加登录、注册请求/响应示例
    - 为 `app/schemas/strategy.py` 添加策略创建、列表响应示例
    - 为 `app/schemas/backtest.py` 添加回测创建、结果查询示例
    - 为 `app/schemas/knowledge_base.py` 添加知识库创建、文档上传示例
    - 使用中文业务语义示例值（如"双均线交叉策略"）
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 5.5 实现 Postman Collection 生成端点
    - 创建 `src/backend/app/api/docs.py`，实现 `/api/v1/docs/postman` GET 端点
    - 从 `app.openapi()` 读取 OpenAPI schema，转换为 Postman Collection v2.1 格式
    - 包含所有端点的 URL、方法、请求体示例和响应示例
    - _Requirements: 7.6_

  - [x] 5.6 增强 CI OpenAPI 验证（示例值检查）
    - 修改 `scripts/export_openapi.py` 或 CI 步骤，添加示例值完整性检查
    - 遍历所有 requestBody 和 responses schema，检查 example/examples 字段
    - 缺失时输出 warning 注解（不阻塞构建）
    - _Requirements: 7.5_

  - [x] 5.7 编写后端缓存和限流头测试
    - 创建 `src/backend/tests/test_cache_response.py`：测试缓存命中/未命中、TTL 过期、Redis 异常回退、写操作失效
    - 创建 `src/backend/tests/test_rate_limit_headers.py`：测试正常响应包含头部、429 响应格式、异常时 fail-open
    - _Requirements: 2.1-2.9, 4.1-4.5_

- [x] 6. Checkpoint - Phase 3 验证
  - 确保所有后端测试通过。

- [x] 7. Phase 4: Infrastructure - 优雅停机
  - [x] 7.1 实现优雅停机流程
    - 在 `src/backend/app/config.py` 添加 `SHUTDOWN_TIMEOUT` 配置（默认 30s，范围 1-300）
    - 创建 `src/backend/app/shutdown.py`，实现 `GracefulShutdownManager` 类
    - 在 lifespan 的 shutdown 阶段集成：设置 shutting_down 状态 → 发送 WebSocket 关闭帧 → 等待连接排空 → 超时强制关闭
    - 增强 `websocket_manager.py`：添加 `close_all(code=1001)` 方法
    - 修改 `/api/v1/health` 端点：检查 `app.state.shutting_down`，为 True 时返回 503
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 7.2 编写优雅停机测试
    - 创建 `src/backend/tests/test_graceful_shutdown.py`
    - 测试 SIGTERM 后停止接受新连接
    - 测试 WebSocket 连接收到 1001 关闭帧
    - 测试超时后强制关闭
    - 测试健康检查返回 503 "shutting_down"
    - _Requirements: 5.6_

- [x] 8. Final Checkpoint - 全部验证
  - 确保所有测试通过，CI 流水线正常运行。

## Notes

- Phase 1 和 Phase 2 可并行开发（前端/后端独立）
- Element Plus 按需导入可能需要逐步清理手动 import 语句
- 缓存装饰器需注意认证端点的用户隔离（缓存键包含 user_id）
- 优雅停机测试需要模拟 SIGTERM 信号，可能需要 subprocess 方式

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3"] },
    { "id": 2, "tasks": ["3.1", "3.4", "3.5"] },
    { "id": 3, "tasks": ["3.2", "3.6"] },
    { "id": 4, "tasks": ["3.3"] },
    { "id": 5, "tasks": ["5.1", "5.3", "5.4"] },
    { "id": 6, "tasks": ["5.2", "5.5", "5.6", "5.7"] },
    { "id": 7, "tasks": ["7.1"] },
    { "id": 8, "tasks": ["7.2"] }
  ]
}
```
