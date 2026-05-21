# Requirements Document

## Introduction

本文档定义了 Backtrader Web 量化交易平台第二轮最佳实践改进的需求。在第一轮改进（覆盖率门禁、Mypy 严格检查、ESLint v9、安全扫描阻塞、JWT 迁移、Docker 开发环境、结构化日志、OpenTelemetry 等）的基础上，本轮聚焦于前端性能优化、API 响应缓存、错误恢复韧性、速率限制增强、优雅停机、状态持久化、API 文档增强和 CI 流水线缓存优化八个维度，进一步提升平台的生产就绪度和开发体验。

## Glossary

- **Element_Plus_Auto_Import**: 通过 unplugin-vue-components 和 unplugin-auto-import 插件实现 Element Plus 组件和 API 的按需自动导入，消除全量引入带来的包体积浪费
- **Redis_Cache**: 基于 Redis 的服务端响应缓存层，用于缓存计算密集型 API 端点的响应结果
- **Error_Boundary**: Vue 3 组件级错误边界，通过 `onErrorCaptured` 生命周期钩子捕获子组件树中的未处理异常，防止错误传播导致整个应用崩溃
- **Retry_Interceptor**: Axios 请求拦截器中的自动重试机制，针对网络瞬时故障和服务端临时错误进行指数退避重试
- **Rate_Limit_Headers**: HTTP 响应头中携带的速率限制元数据（X-RateLimit-Limit、X-RateLimit-Remaining、X-RateLimit-Reset），帮助客户端感知并适配限流策略
- **Graceful_Shutdown**: 应用收到终止信号后的优雅停机流程，包括停止接受新连接、等待进行中请求完成、关闭 WebSocket 连接和释放资源
- **Connection_Draining**: 在停机过程中允许已建立的连接完成当前操作后再关闭，避免请求中断
- **Pinia_Persistence**: 通过 pinia-plugin-persistedstate 插件将关键 Pinia store 状态持久化到 localStorage/sessionStorage，实现页面刷新后状态恢复
- **OpenAPI_Examples**: OpenAPI schema 中为请求体和响应体提供的示例值（example/examples 字段），提升 API 文档的可读性和可测试性
- **CI_Cache**: GitHub Actions 中通过 actions/cache 或内置缓存机制缓存依赖安装产物，减少重复下载和安装时间
- **Stale_While_Revalidate**: 数据获取策略，先返回缓存中的陈旧数据以快速渲染 UI，同时在后台发起请求获取最新数据并更新缓存

## Requirements

### Requirement 1: Element Plus 按需自动导入

**User Story:** 作为前端开发者，我希望 Element Plus 组件和 API 通过按需自动导入加载，以便显著减小生产构建包体积并提升首屏加载速度。

#### Acceptance Criteria

1. THE 前端构建配置 SHALL 安装 `unplugin-vue-components` 和 `unplugin-auto-import` 为 devDependencies，并在 `vite.config.ts` 的 plugins 数组中注册 `ElementPlusResolver`，使其同时作为 `unplugin-vue-components` 的组件解析器和 `unplugin-auto-import` 的 API 解析器
2. WHEN 组件模板中使用任意 Element Plus 组件（如 `<el-button>`、`<el-table>`）时，THE 构建系统 SHALL 自动按需导入对应组件代码和样式，无需在源码中手动编写 `import` 语句
3. WHEN 组件脚本中使用 Element Plus API（如 `ElMessage`、`ElMessageBox`、`ElNotification`）时，THE 构建系统 SHALL 自动按需导入对应 API，无需手动 `import`
4. THE 前端项目 SHALL 移除 `main.ts` 中 Element Plus 的全量注册代码（`app.use(ElementPlus)` 及对应的全量样式导入 `import 'element-plus/dist/index.css'`），并将 `@element-plus/icons-vue` 的全局注册改为按需导入或保留显式注册，确保所有使用图标的组件仍正常渲染
5. THE `vite.config.ts` 中 `rollupOptions.output.manualChunks` 的 `'element-plus'` 条目 SHALL 被移除，因为按需导入后 Element Plus 代码将分散到使用它的各个 chunk 中
6. THE 自动导入插件 SHALL 生成类型声明文件（`auto-imports.d.ts` 和 `components.d.ts`），且这些文件 SHALL 被包含在 `tsconfig.json` 的 `include` 中，使 `npm run typecheck`（vue-tsc）通过且无 Element Plus 相关类型错误
7. WHEN 执行 `npm run build` 后，THE 生产构建的总 JavaScript 体积（以 `vite build` 输出的 gzip 体积汇总计算）SHALL 相比按需导入前的同一代码库全量导入构建减少至少 15%
8. THE 所有现有 Vitest 单元测试和 Playwright E2E 测试 SHALL 在按需导入配置后全部通过，功能行为无回归

### Requirement 2: API 响应缓存（Redis）

**User Story:** 作为平台用户，我希望读取密集型 API 端点的响应被缓存，以便获得更快的响应速度并降低数据库负载。

#### Acceptance Criteria

1. THE 后端 SHALL 提供一个 `@cache_response(ttl=<seconds>, key_prefix=<string>)` 装饰器，用于标记需要缓存响应的 API 端点，其中 `ttl` 参数接受 1 至 86400 之间的整数（秒），`key_prefix` 为非空字符串且最大长度 64 字符
2. WHILE Redis 连接可用（`REDIS_URL` 环境变量已配置且连接正常），THE 缓存装饰器 SHALL 将 API 响应体序列化为 JSON 并连同 HTTP 状态码一起存储到 Redis，使用 `{key_prefix}:{request_path}:{query_params_hash}` 作为缓存键，其中 `query_params_hash` 为查询参数按键名排序后计算的 MD5 摘要
3. WHEN 缓存命中时，THE 缓存装饰器 SHALL 直接返回缓存的响应数据（保留原始 HTTP 状态码和 `Content-Type: application/json`），跳过路由处理函数的执行，并在响应头中添加 `X-Cache: HIT`
4. WHEN 缓存未命中时，THE 缓存装饰器 SHALL 执行路由处理函数，将响应缓存后返回，并在响应头中添加 `X-Cache: MISS`
5. IF Redis 连接不可用或操作发生异常，THEN THE 缓存装饰器 SHALL 回退到直接执行路由处理函数（不缓存），使用 WARNING 级别在日志中记录异常类型和缓存键信息，且不影响正常请求处理（不抛出异常、不改变响应状态码）
6. THE 缓存装饰器 SHALL 仅对 HTTP GET 请求生效，对 POST/PUT/DELETE 等写操作请求直接透传不缓存，且不添加 `X-Cache` 响应头
7. THE 后端 SHALL 对以下端点启用响应缓存：`/api/v1/health`（TTL 10 秒）、策略列表 `/api/v1/strategies`（TTL 30 秒）、回测结果详情 `/api/v1/backtests/{id}/result`（TTL 60 秒）
8. WHEN 策略或回测数据发生写操作（创建、更新、删除）时，THE 对应服务 SHALL 删除与该资源关联的所有缓存键（通过匹配 `key_prefix:{resource_path}:*` 前缀模式），确保后续读取获得最新数据，删除操作在 2 秒内完成
9. IF REDIS_URL 未配置或为空，THEN THE 缓存装饰器 SHALL 使用内存缓存（MemoryCache）作为存储后端，行为与 Redis 缓存一致（相同的键格式、TTL 语义和响应头），但缓存数据不跨进程共享

### Requirement 3: 前端错误边界与重试机制

**User Story:** 作为平台用户，我希望单个组件的错误不会导致整个页面崩溃，且网络瞬时故障能自动恢复，以便获得更稳定的使用体验。

#### Acceptance Criteria

1. THE 前端 SHALL 提供一个 `ErrorBoundary.vue` 组件，通过 Vue 3 的 `onErrorCaptured` 钩子捕获子组件树中的运行时错误，并通过返回 `false` 阻止错误向上传播
2. WHEN ErrorBoundary 捕获到错误时，THE 组件 SHALL 隐藏崩溃的子组件树，渲染一个包含错误标题、错误摘要文本（不超过 200 个字符）和一个"重试"按钮的错误提示界面
3. WHEN 用户点击错误提示中的"重试"按钮时，THE ErrorBoundary SHALL 将错误状态重置为无错误，并重新渲染原始子组件树（即恢复到 slot 默认内容的展示）
4. THE 前端 SHALL 在所有路由级页面组件（即 `<router-view>` 渲染的顶层组件）外层包裹 `ErrorBoundary`，确保任何单个页面级组件的崩溃仅影响该页面区域，应用的导航栏和布局框架保持可用
5. THE Axios 请求实例 SHALL 配置 Retry Interceptor，对满足以下条件的失败请求自动重试：HTTP 状态码为 408、429、500、502、503、504，或请求错误码为 `ERR_NETWORK`
6. THE Retry Interceptor SHALL 使用指数退避策略，最大重试次数为 3 次，初始延迟 1000ms，退避因子 2（即延迟序列为 1000ms、2000ms、4000ms），每次延迟的抖动范围为 ±10%
7. THE Retry Interceptor SHALL 仅对幂等请求方法（GET、HEAD、OPTIONS、PUT、DELETE）自动重试；IF 请求方法为 POST 且响应头不包含 `Idempotency-Key`，THEN THE Retry Interceptor SHALL 不执行自动重试，直接将错误返回给调用方
8. IF Retry Interceptor 达到最大重试次数（3 次）后请求仍然失败，THEN THE Retry Interceptor SHALL 将最后一次失败的错误对象原样抛出给调用方，不做额外包装
9. WHILE Retry Interceptor 正在执行重试等待期间，THE Axios 实例 SHALL 不对同一请求重复触发响应拦截器中的用户提示（如 ElMessage），仅在最终失败后触发一次错误提示
10. THE 前端 SHALL 包含不少于 6 个 Vitest 单元测试，覆盖以下场景：ErrorBoundary 捕获子组件抛出的错误后显示错误提示界面、ErrorBoundary 点击重试后恢复子组件渲染、Retry Interceptor 对 GET 请求在 503 响应时执行 3 次重试、Retry Interceptor 的退避延迟符合 1000ms/2000ms/4000ms 序列（允许 ±10% 抖动误差）、Retry Interceptor 对无 `Idempotency-Key` 的 POST 请求不执行重试、Retry Interceptor 对包含 `Idempotency-Key` 响应头的 POST 请求执行重试

### Requirement 4: 速率限制响应头增强

**User Story:** 作为 API 消费者，我希望响应头中包含速率限制状态信息，以便客户端能感知剩余配额并合理调度请求。

#### Acceptance Criteria

1. THE 后端 SHALL 在所有经过速率限制检查的 API 响应中添加以下 Rate_Limit_Headers：`X-RateLimit-Limit`（当前窗口允许的最大请求数）、`X-RateLimit-Remaining`（当前窗口剩余可用请求数）、`X-RateLimit-Reset`（当前窗口重置的 Unix 时间戳，精确到秒）
2. WHEN 请求未触发速率限制时，THE 响应 SHALL 包含上述三个头部，且 HTTP 状态码为正常业务响应码（如 200、201 等）
3. WHEN 请求触发速率限制时，THE 响应 SHALL 返回 HTTP 429 状态码，响应体包含 `{"detail": "Rate limit exceeded", "retry_after": <seconds>}` 格式的 JSON，且响应头包含 `Retry-After`（秒数）和上述三个 Rate_Limit_Headers（其中 `X-RateLimit-Remaining` 值为 0）
4. THE Rate_Limit_Headers SHALL 通过 FastAPI 中间件统一注入，无需在每个路由处理函数中手动添加
5. IF 速率限制后端（Redis 或内存）发生异常无法获取限流状态，THEN THE 中间件 SHALL 允许请求通过（fail-open），不添加 Rate_Limit_Headers，并在日志中记录警告

### Requirement 5: 优雅停机与连接排空

**User Story:** 作为运维人员，我希望应用在部署更新时能优雅停机，以便进行中的请求和 WebSocket 连接不会被突然中断。

#### Acceptance Criteria

1. WHEN 应用收到 SIGTERM 信号时，THE Graceful_Shutdown 流程 SHALL 按以下顺序执行：首先将 `/api/v1/health` 端点响应状态改为 `"shutting_down"`（HTTP 503），然后停止接受新的 HTTP 连接和 WebSocket 连接，最后进入连接排空阶段
2. WHILE 存在进行中的 HTTP 请求，THE Graceful_Shutdown 流程 SHALL 等待这些请求完成，最长等待时间由环境变量 `SHUTDOWN_TIMEOUT` 控制（默认 30 秒，有效范围 1–300 秒整数；若环境变量值无法解析为该范围内的整数，则使用默认值 30 秒并记录警告日志）
3. WHILE 存在活跃的 WebSocket 连接，THE Graceful_Shutdown 流程 SHALL 向所有连接的客户端发送关闭帧（close frame，状态码 1001 Going Away），然后等待客户端确认关闭，单个连接的关闭确认等待时间不超过 5 秒
4. IF 从停机开始计算的总等待时间超过 `SHUTDOWN_TIMEOUT` 秒，THEN THE 后端服务 SHALL 强制关闭所有剩余的 HTTP 连接和 WebSocket 连接，并以退出码 0 退出进程
5. WHEN Graceful_Shutdown 流程启动时，THE Graceful_Shutdown 流程 SHALL 在日志中记录停机开始的 ISO 8601 时间戳和当前活跃的 HTTP 请求数量及 WebSocket 连接数量；WHEN Graceful_Shutdown 流程完成时，THE Graceful_Shutdown 流程 SHALL 在日志中记录停机完成的 ISO 8601 时间戳和是否触发了强制关闭
6. THE 后端 SHALL 包含不少于 4 个 pytest 测试用例，分别验证：（a）收到 SIGTERM 后停止接受新连接、（b）向活跃 WebSocket 连接发送 1001 关闭帧、（c）超时后强制关闭剩余连接、（d）健康检查端点在停机期间返回 HTTP 503 且响应体包含 `"shutting_down"` 状态

### Requirement 6: 前端状态持久化（Pinia）

**User Story:** 作为平台用户，我希望页面刷新后关键状态（如用户偏好、筛选条件）能自动恢复，以便不必重复设置。

#### Acceptance Criteria

1. THE 前端依赖 SHALL 安装 `pinia-plugin-persistedstate` 包，并在 Pinia 实例创建时注册该插件
2. THE 用户偏好 store（如主题、语言、侧边栏折叠状态）SHALL 配置 `persist: true`，将状态持久化到 `localStorage`
3. THE 认证 store 中的 access token SHALL 配置持久化到 `sessionStorage`（而非 localStorage），确保浏览器关闭后 token 自动清除
4. WHEN 页面刷新或重新打开时，THE Pinia_Persistence 插件 SHALL 自动从存储中恢复已持久化的 store 状态，无需手动调用恢复逻辑
5. THE 持久化配置 SHALL 支持通过 `paths` 选项选择性持久化 store 中的部分字段，避免将临时状态（如 loading 标志、错误信息）写入存储
6. IF localStorage/sessionStorage 不可用（如隐私模式下存储已满），THEN THE 插件 SHALL 静默降级，应用正常运行但不持久化状态，不抛出异常
7. THE 前端 SHALL 包含不少于 4 个 Vitest 单元测试，验证状态持久化写入、页面刷新后恢复、选择性字段持久化和存储不可用时的降级行为

### Requirement 7: API 文档增强（OpenAPI 示例值）

**User Story:** 作为 API 消费者，我希望 Swagger UI 中的 API 文档包含请求和响应示例，以便快速理解接口用法并直接测试。

#### Acceptance Criteria

1. THE 后端 Pydantic schema SHALL 为所有公开 API 端点的请求体和响应体模型配置 `model_config` 中的 `json_schema_extra`（或字段级 `examples`），提供至少一个完整的示例值
2. WHEN 访问 `/docs`（Swagger UI）时，THE 文档页面 SHALL 在每个端点的请求体和响应体区域显示预填充的示例值，用户可直接点击"Try it out"使用示例值发起请求
3. THE 示例值 SHALL 覆盖以下核心 API 模块：认证（登录、注册）、策略管理（创建、列表）、回测（创建、结果查询）、知识库（创建、文档上传）
4. THE 每个示例值 SHALL 使用符合业务语义的真实数据格式（如策略名称使用中文示例"双均线交叉策略"，日期使用 ISO 8601 格式），而非占位符或随机字符串
5. WHEN CI_Pipeline 执行 OpenAPI schema 验证时，THE 验证步骤 SHALL 额外检查导出的 schema 中所有 `requestBody` 和 `responses` 的 schema 是否包含 `example` 或 `examples` 字段，缺失时输出警告（不阻塞构建）
6. THE 后端 SHALL 提供 `/api/v1/docs/postman` 端点，返回从当前 OpenAPI schema 自动生成的 Postman Collection v2.1 格式 JSON，包含所有端点及其示例值

### Requirement 8: CI 流水线缓存优化

**User Story:** 作为开发团队，我希望 CI 流水线通过依赖缓存减少重复安装时间，以便加快反馈循环并降低 CI 资源消耗。

#### Acceptance Criteria

1. THE CI_Pipeline 中所有使用 `pip install` 的 job SHALL 配置 Python pip 缓存，通过 `actions/setup-python@v5` 的 `cache: 'pip'` 参数启用，缓存键基于 `pyproject.toml` 和 `requirements-dev.lock` 文件的哈希值
2. THE CI_Pipeline 中所有使用 `npm ci` 的 job SHALL 通过 `actions/setup-node@v4` 的 `cache: 'npm'` 参数启用 npm 缓存，缓存键基于 `package-lock.json` 文件的哈希值
3. WHEN 缓存命中时，THE CI_Pipeline 的依赖安装步骤 SHALL 跳过网络下载，直接从缓存恢复依赖包，使安装时间相比无缓存时减少至少 50%
4. THE CI_Pipeline SHALL 为 `backend-lint` 和 `backend-test` job 共享同一个 Python 虚拟环境缓存，避免重复安装相同依赖
5. THE CI_Pipeline 中 `check-openapi`、`check-migrations` 等预检 job SHALL 配置独立的轻量级缓存（仅缓存核心依赖），避免安装不必要的可选依赖
6. WHEN `pyproject.toml` 或 `package-lock.json` 文件内容发生变更时，THE 缓存 SHALL 自动失效并重新构建，确保依赖版本始终与声明一致
7. THE CI_Pipeline SHALL 在 ci-summary job 中输出各 job 的缓存命中状态（HIT/MISS）和总执行时间，便于监控缓存效果
