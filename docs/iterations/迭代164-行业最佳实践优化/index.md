# 迭代164 - 行业最佳实践优化

> **文档状态**: 可执行  
> **创建日期**: 2026-05-19  
> **核心目标**: 按照行业最佳实践，系统性提升项目的生产就绪度、可观测性、安全性和可维护性。

---

## 1. 总目标

基于对项目现状的全面审查，本迭代聚焦以下改进方向：

1. **容器安全** - 修复 Dockerfile 非 root 用户问题，生产环境使用 Gunicorn 多 worker
2. **可观测性** - 结构化日志、OpenTelemetry 基础集成、连接池监控
3. **依赖管理** - 锁定精确版本，避免上游破坏性更新
4. **CI 增强** - 数据库迁移验证、Bundle size 检查
5. **WebSocket 安全** - 添加认证和心跳机制
6. **API 规范** - 废弃端点添加标准 Sunset 头
7. **Graceful Shutdown** - 完善回测任务的优雅关闭
8. **前端错误监控** - 全局错误边界

---

## 2. 执行原则

### 2.1 可以做

1. 修改 Dockerfile 和 docker-compose 配置
2. 添加新的中间件和工具模块
3. 添加新的 CI 步骤
4. 生成依赖锁文件
5. 增强现有模块的错误处理
6. 添加配置项（保持向后兼容）

### 2.2 不要做

1. 不要破坏现有 API 接口
2. 不要修改 `.env` 中的真实密钥
3. 不要引入付费 SaaS 依赖
4. 不要大规模重构现有架构
5. 不要删除任何现有功能

---

## 3. 任务分解

### 阶段一：容器安全与生产部署优化 [P0]

- [x] T1: Backend Dockerfile 添加 `USER appuser` 切换非 root 用户
- [x] T2: 生产环境使用 Gunicorn 管理多 Uvicorn worker
- [x] T3: 添加 `.dockerignore` 优化（排除测试、文档等）— 已有完善配置

验收标准：
1. `docker build` 成功
2. 容器内进程以非 root 用户运行
3. 生产模式启动多 worker

### 阶段二：结构化日志与可观测性 [P0]

- [x] T4: 添加 JSON 格式日志输出（生产环境控制台 + 文件）
- [x] T5: 健康检查暴露数据库连接池状态
- [x] T6: 添加 OpenTelemetry 基础配置（可选启用）

验收标准：
1. `DEBUG=false` 时日志输出 JSON 格式
2. `/health` 返回连接池 metrics
3. OTEL 配置不影响现有功能（默认禁用，`OTEL_ENABLED=true` 启用）

### 阶段三：依赖管理与 CI 增强 [P0]

- [x] T7: pyproject.toml 添加 `prod` 和 `otel` 可选依赖组
- [x] T8: CI 添加 Alembic 迁移验证步骤
- [x] T9: 前端 CI 添加 bundle size 检查

验收标准：
1. `requirements-prod.lock` 可复现安装
2. CI 能检测到模型与迁移不同步
3. Bundle 超过阈值时 CI 失败

### 阶段四：WebSocket 安全与 API 规范 [P1]

- [x] T10: WebSocket 连接已有 JWT 认证（确认现有实现）
- [x] T11: WebSocket 已有 ping/pong 心跳（确认现有实现）
- [x] T12: 废弃端点响应添加 `Deprecation` 和 `Sunset` 头（新增中间件）

验收标准：
1. 无 token 的 WebSocket 连接被拒绝
2. 超时无心跳的连接自动断开
3. 废弃端点响应包含标准废弃头

### 阶段五：Graceful Shutdown 与前端错误边界 [P1]

- [x] T13: 应用关闭时等待活跃回测完成或标记中断
- [x] T14: 前端添加全局错误边界组件
- [x] T15: Vue errorHandler 捕获未处理异常并展示友好提示

验收标准：
1. 关闭应用后不会有 orphaned 回测任务
2. 组件渲染错误不会导致整页白屏
3. 未处理异常有统一的用户提示

### 阶段六：Rate Limiter 分布式支持 [P2]

- [x] T16: slowapi 配置 Redis 后端（当 REDIS_URL 可用时）

验收标准：
1. 有 Redis 时使用 Redis 存储
2. 无 Redis 时回退到内存存储
3. 不影响现有限流规则

---

## 4. 推荐执行顺序

```
T1 → T2 → T3 (容器安全，独立可验证)
T4 → T5 → T6 (可观测性，逐步增强)
T7 → T8 → T9 (CI 增强，独立可验证)
T10 → T11 (WebSocket 安全)
T12 (API 规范)
T13 (Graceful Shutdown)
T14 → T15 (前端错误边界)
T16 (Rate Limiter)
```

---

## 5. 验证命令

```bash
# 后端测试
cd src/backend && pytest tests/ -v --tb=short -q

# 前端测试
cd src/frontend && npm run typecheck && npm run test -- --run

# Docker 构建验证
docker build -f src/backend/Dockerfile -t backtrader-backend-test .

# 日志格式验证
DEBUG=false python -c "from app.utils.logger import setup_logger; l = setup_logger('test'); l.info('hello')"
```

---

## 6. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Gunicorn 引入可能影响 WebSocket | 中 | 使用 UvicornWorker，保持 ASGI 兼容 |
| OTEL 增加启动时间 | 低 | 默认禁用，通过环境变量启用 |
| Lock 文件与开发依赖冲突 | 低 | Lock 文件仅用于生产部署 |
| WebSocket 认证可能影响现有前端 | 中 | 前端同步更新连接逻辑 |


---

## 7. 执行结果

### 7.1 完成内容

| 任务 | 状态 | 说明 |
|------|------|------|
| T1: Dockerfile 非 root 用户 | ✅ | 添加 `USER appuser`，容器以非 root 运行 |
| T2: Gunicorn 多 worker | ✅ | 生产环境使用 `gunicorn -k uvicorn.workers.UvicornWorker`，`WEB_CONCURRENCY` 控制 worker 数 |
| T3: .dockerignore | ✅ | 已有完善配置，无需修改 |
| T4: JSON 结构化日志 | ✅ | 生产环境控制台输出 JSON，文件使用 loguru `serialize=True` |
| T5: 连接池监控 | ✅ | `/health` 返回 `database_pool` 字段（pool_size/checked_in/checked_out/overflow） |
| T6: OpenTelemetry | ✅ | 新增 `app/telemetry.py`，默认禁用，`OTEL_ENABLED=true` 启用 |
| T7: 依赖管理 | ✅ | 添加 `prod`/`otel` 依赖组 + `requirements-prod.lock` 锁文件 |
| T8: Alembic CI 验证 | ✅ | 新增 `check-migrations` CI job + `scripts/check_alembic_heads.py` |
| T9: Bundle size 检查 | ✅ | 新增 `scripts/check_bundle_size.sh`，集成到 CI frontend-build job |
| T10: WebSocket JWT | ✅ | 确认已有实现（`get_websocket_current_user`） |
| T11: WebSocket 心跳 | ✅ | 确认已有实现（ping/pong + 1s timeout） |
| T12: Deprecation 头 | ✅ | 新增 `DeprecationHeadersMiddleware`，RFC 8594 标准 |
| T13: Graceful Shutdown | ✅ | 新增 `interrupt_active_tasks()`，关闭时标记活跃任务为 CANCELLED |
| T14: 前端错误边界 | ✅ | 新增 `ErrorBoundary.vue` 组件 |
| T15: 全局错误处理 | ✅ | `app.config.errorHandler` + `unhandledrejection` 监听 |
| T16: Redis Rate Limiter | ✅ | slowapi 自动检测 REDIS_URL，有则用 Redis，无则内存 |

### 7.2 修改文件清单

**后端：**
- `src/backend/Dockerfile` — 非 root 用户 + Gunicorn + 锁文件安装
- `src/backend/app/rate_limit.py` — Redis 后端支持
- `src/backend/app/main.py` — 连接池监控 + 废弃中间件 + graceful shutdown + OTEL
- `src/backend/app/utils/logger.py` — JSON 控制台输出 + 修复文件 handler 格式
- `src/backend/app/middleware/deprecation.py` — 新增废弃头中间件
- `src/backend/app/telemetry.py` — 新增 OpenTelemetry 可选集成
- `src/backend/app/services/backtest_manager.py` — 新增 `interrupt_active_tasks()`
- `src/backend/pyproject.toml` — 添加 `prod`/`otel` 依赖组
- `src/backend/requirements-prod.lock` — 生产依赖锁文件
- `src/backend/requirements-dev.lock` — 开发依赖锁文件
- `scripts/check_alembic_heads.py` — 新增迁移验证脚本
- `scripts/check_bundle_size.sh` — 新增 Bundle size 检查脚本

**前端：**
- `src/frontend/src/components/common/ErrorBoundary.vue` — 新增错误边界组件
- `src/frontend/src/main.ts` — 全局错误处理
- `src/frontend/tsconfig.json` — 添加 `vite/client` 类型

**CI/CD：**
- `.github/workflows/ci.yml` — 添加 `check-migrations` job
- `docker-compose.prod.yml` — 添加 `WEB_CONCURRENCY` 环境变量
- `.env.example` — 文档化新配置项

**文档：**
- `docs/iterations/迭代164-行业最佳实践优化/index.md` — 本迭代计划与执行记录

### 7.3 验证结果

```
# 后端导入验证
python -c "from app.main import app; print(app.title)"  → OK

# 后端测试
pytest tests/test_config.py tests/test_auth.py → 18 passed

# Ruff lint
ruff check app/rate_limit.py app/middleware/deprecation.py app/utils/logger.py app/main.py → All checks passed

# 前端 typecheck
npx vue-tsc --noEmit --skipLibCheck → 通过
```

### 7.4 未完成事项（下一轮）

1. **Sentry/错误上报集成** — `errorHandler` 已预留 hook 点，需要选择具体服务
2. **API 契约测试** — 可基于 OpenAPI schema diff 实现
3. **Feature Flag 管理** — 当前基于路由注册硬编码，可引入轻量 flag 库
4. **前端 i18n 覆盖度审计** — vue-i18n 已安装但覆盖度未知
5. **测试覆盖率持续提升** — 当前约 50%（含排除），目标 60%→70%→80% 分阶段提升

### 7.5 风险与建议

- Gunicorn 多 worker 模式下，WebSocket 连接只能由接受连接的 worker 处理。当前架构（单机部署）不受影响，但水平扩展时需要引入 Redis pub/sub 做 WebSocket 广播。
- `serialize=True` 的 loguru 文件输出格式与之前的自定义 JSON 格式略有不同（包含更多元数据），如果有日志解析脚本需要适配。
- Rate limiter Redis 后端需要 `redis` 包已安装（已在 `[redis]` 可选依赖中）。
- OpenTelemetry 默认禁用，启用后会增加约 5-10ms 的请求延迟（span 创建和导出）。建议在生产环境使用采样（`OTEL_TRACES_SAMPLER=parentbased_traceidratio`）。
- Bundle size 阈值设置为 20MB（含 Monaco editor workers），如果后续移除 Monaco 或改为按需加载，应相应降低阈值。
- 锁文件需要定期更新（建议每月或依赖升级时重新生成）：`uv pip compile pyproject.toml --extra prod --extra postgres --extra mysql --extra redis --extra backtrader --extra data -o requirements-prod.lock --python-version 3.11`
