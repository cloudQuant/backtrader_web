# Requirements Document

## Introduction

本文档定义了 Backtrader Web 量化交易平台按照行业最佳实践进行系统性改进优化的需求。改进范围涵盖测试质量、安全加固、代码质量、性能可观测性、DevOps 基础设施、前端工程化、文档体验和数据库管理八个维度。采用分阶段交付策略，优先处理高风险、高收益的改进项。

## Glossary

- **CI_Pipeline**: GitHub Actions 持续集成流水线，负责代码质量检查、测试执行和安全扫描
- **Coverage_Gate**: 测试覆盖率阈值门禁，CI 中强制要求的最低覆盖率百分比
- **SAST**: 静态应用安全测试工具，在不运行代码的情况下分析源代码中的安全漏洞
- **Structured_Logging**: 结构化日志，以 JSON 等机器可解析格式输出日志，便于日志聚合和检索
- **OpenTelemetry**: 开放遥测标准，提供分布式追踪、指标和日志的统一采集框架
- **Mypy**: Python 静态类型检查工具，用于在运行前发现类型错误
- **Ruff**: Python 代码检查和格式化工具，替代 flake8、isort 等传统工具
- **ESLint_Flat_Config**: ESLint v9 引入的新配置格式，使用 eslint.config.js 替代 .eslintrc
- **Alembic**: SQLAlchemy 的数据库迁移工具，管理数据库 schema 版本变更
- **Bundle_Analysis**: 前端构建产物体积分析，用于监控和优化打包大小
- **Lighthouse_CI**: Google 提供的自动化网页性能和可访问性审计工具
- **Pre_Commit**: Git 提交前自动执行代码检查的钩子框架
- **Dependency_Pinning**: 依赖版本锁定策略，确保构建可重现性
- **Health_Check_Endpoint**: 健康检查端点，用于监控服务运行状态

## Requirements

### Requirement 1: 提升后端测试覆盖率门禁

**User Story:** 作为开发团队，我希望将后端测试覆盖率门禁从 50% 提升到 70%，以便在 CI 中更早发现回归缺陷。

#### Acceptance Criteria

1. WHEN CI_Pipeline 执行后端测试时，THE Coverage_Gate SHALL 使用 `--cov-fail-under=70` 参数要求整体行覆盖率（line coverage）不低于 70%
2. IF 整体行覆盖率低于 70%，THEN THE CI_Pipeline SHALL 将 backend-test job 标记为失败，使其作为 required status check 阻止 PR 合并
3. THE Coverage_Gate SHALL 在 `.coveragerc` 的 `[run]` omit 和 `[report]` omit 中移除 `app/services/workspace_service.py` 和 `app/services/sync_service.py` 两个条目，将这两个文件纳入覆盖率统计范围，其余现有 omit 条目保持不变
4. WHEN PR 中新增或修改 Python 源文件时，THE CI_Pipeline SHALL 使用 diff-cover 工具检查本次变更行的覆盖率，要求变更行覆盖率不低于 60%
5. IF diff-cover 检测到变更行覆盖率低于 60%，THEN THE CI_Pipeline SHALL 将该检查步骤标记为失败并在日志中输出未覆盖的文件及行号列表

### Requirement 2: 启用严格 Mypy 类型检查

**User Story:** 作为开发者，我希望 Mypy 类型检查在 CI 中强制执行，以便在编码阶段发现类型错误。

#### Acceptance Criteria

1. THE CI_Pipeline SHALL 在 backend-lint job 中执行 `mypy app`（工作目录为 `src/backend`），且该步骤的退出码非零时阻塞流水线通过
2. THE Mypy 配置 SHALL 将 `check_untyped_defs` 设置为 `true`
3. IF Mypy 以非零退出码退出（即报告一个或多个类型错误），THEN THE CI_Pipeline SHALL 将 backend-lint job 标记为失败，阻止 PR 合并
4. THE Mypy 配置 SHALL 对 `app/api/` 和 `app/schemas/` 目录通过 `[[tool.mypy.overrides]]` 启用 `disallow_untyped_defs = true`
5. THE Mypy 配置 SHALL 保留 `ignore_missing_imports = true` 以及对缺少类型存根的第三方包（backtrader、akshare、fincore、loguru、slowapi、apscheduler、passlib、jose 等）的 `[[tool.mypy.overrides]]` 豁免配置
6. THE Mypy 配置 SHALL 保留对 `alembic/`、`migrations/`、`tests/`、`scripts/` 目录的排除规则，使这些目录不参与类型检查

### Requirement 3: 安全扫描升级为阻塞门禁

**User Story:** 作为安全负责人，我希望安全扫描结果能阻止存在高危漏洞的代码合并，以便降低生产环境安全风险。

#### Acceptance Criteria

1. THE CI_Pipeline SHALL 移除 backend-security job 的 job 级别 `continue-on-error: true` 配置，并移除其各 step 上的 `continue-on-error: true` 配置
2. WHEN Bandit 报告 HIGH 级别且 confidence 为 MEDIUM 或 HIGH 的问题时，THE CI_Pipeline SHALL 将安全扫描步骤标记为失败（exit code 非零）
3. WHEN Safety 检测到任意已知漏洞时，THE CI_Pipeline SHALL 将依赖检查步骤标记为失败（exit code 非零）
4. THE CI_Pipeline SHALL 在 ci-summary job 中将 backend-security 从 Advisory 区域移至 Blocker 区域，并将 `needs.backend-security.result == 'failure'` 加入工作流失败判定条件
5. IF Bandit 报告仅包含 LOW 或 MEDIUM 级别问题，THEN THE CI_Pipeline SHALL 在步骤输出中记录警告信息但以 exit code 0 结束（不阻塞合并）
6. IF Bandit 或 Safety 因工具自身错误（如网络超时、数据库不可用）导致无法完成扫描，THEN THE CI_Pipeline SHALL 将该步骤标记为失败并在步骤输出中注明扫描未完成

### Requirement 4: 迁移废弃的 python-jose 依赖

**User Story:** 作为开发者，我希望将 JWT 库从已废弃的 python-jose 迁移到活跃维护的 PyJWT，以便获得持续的安全更新。

#### Acceptance Criteria

1. THE 后端依赖 SHALL 将 `python-jose[cryptography]` 替换为 `PyJWT[crypto]>=2.8.0`，并将 `pyproject.toml` 中 mypy overrides 的 `jose.*` 模块引用更新为 `jwt.*`
2. WHEN JWT token 被签发时，THE 认证服务 SHALL 使用 PyJWT 的 `jwt.encode()` 接口，传入相同的 payload 字段（sub、exp、token_type、jti）、SECRET_KEY 和 HS256 算法
3. WHEN JWT token 被验证时，THE 认证服务 SHALL 使用 PyJWT 的 `jwt.decode()` 接口，并捕获 `jwt.exceptions.InvalidTokenError`（替代原 `jose.JWTError`），对于无效或过期 token 返回 None
4. THE 迁移 SHALL 保持现有 JWT token 格式的向后兼容性：使用相同的 HS256 算法和 SECRET_KEY 签发的 token，在迁移前后均可被正确解码并返回一致的 payload 内容
5. THE 所有认证相关测试（test_auth.py、test_auth_improved.py、test_refresh_token.py）SHALL 在迁移后全部通过，且 HTTP 状态码、响应体结构和 token 验证结果与迁移前一致

### Requirement 5: Pre-Commit 工具版本同步

**User Story:** 作为开发者，我希望 pre-commit 中的 Ruff 版本与项目实际使用的版本保持一致，以便本地检查结果与 CI 一致。

#### Acceptance Criteria

1. THE Pre_Commit 配置 SHALL 将 Ruff hook 的 `rev` 字段更新为与本地环境实际使用的 Ruff 版本（即 `.ruff_cache` 中最新缓存版本）对应的 Git tag（格式为 `v<major>.<minor>.<patch>`），且该版本不低于 `pyproject.toml` 中 `ruff>=0.1.0` 所声明的最低版本
2. WHEN 开发者执行 `pre-commit run --all-files` 时，THE Ruff hook SHALL 对 `^src/backend/` 路径下的文件执行 lint 检查和格式化检查，且使用的 Ruff 规则集（`select`、`ignore`、`line-length`）与 `pyproject.toml` 中 `[tool.ruff]` 配置段定义的规则集相同
3. WHEN 开发者执行 `pre-commit run --all-files` 时，THE Ruff hook SHALL 使用与 CI 工作流 `backend-lint` job 中 `ruff check` 和 `ruff format` 相同版本的 Ruff，使得对同一代码文件产生的 lint 告警和格式化差异结果完全一致（零差异）
4. THE Pre_Commit 配置 SHALL 在 Ruff hook 的 `repo` 条目上方包含注释，说明版本更新方式为执行 `pre-commit autoupdate --repo https://github.com/astral-sh/ruff-pre-commit` 命令，并提示更新后需同步验证 CI 中的 Ruff 版本一致性

### Requirement 6: 添加 Docker 本地开发环境

**User Story:** 作为新加入的开发者，我希望通过一条命令启动完整的本地开发环境，以便快速开始开发工作。

#### Acceptance Criteria

1. THE 项目根目录 SHALL 包含 `docker-compose.dev.yml` 文件，定义后端（FastAPI）、前端（Vite dev server）和 PostgreSQL 数据库三个服务
2. WHEN 开发者执行 `docker compose -f docker-compose.dev.yml up` 时，THE 开发环境 SHALL 在 60 秒内使所有服务的 healthcheck 达到 healthy 状态，且后端在端口 8000、前端在端口 3000 可响应 HTTP 请求
3. THE docker-compose.dev.yml SHALL 通过 volume mount 将 `src/backend/` 目录挂载到后端容器内，并使用 `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` 启动，使本地代码修改无需重建容器即可生效
4. THE docker-compose.dev.yml SHALL 通过 volume mount 将 `src/frontend/` 目录挂载到前端容器内，并使用 `npm run dev -- --host 0.0.0.0 --port 3000` 启动，使本地代码修改通过 Vite HMR 即时生效
5. THE docker-compose.dev.yml SHALL 包含 PostgreSQL 服务，并在首次启动时自动创建数据库 schema（通过设置环境变量 `DB_AUTO_CREATE_SCHEMA=true`）和默认管理员账户（通过设置 `DB_AUTO_CREATE_DEFAULT_ADMIN=true`）
6. IF 开发者本地已有端口占用，THEN THE docker-compose.dev.yml SHALL 支持通过环境变量 `LOCAL_BACKEND_PORT`（默认 8000）、`LOCAL_FRONTEND_PORT`（默认 3000）和 `LOCAL_DB_PORT`（默认 5432）自定义宿主机映射端口
7. IF docker-compose.dev.yml 中任一服务启动失败，THEN THE 失败服务 SHALL 输出包含错误原因的日志到 stdout，且其 healthcheck 状态保持为 unhealthy 以便开发者通过 `docker compose ps` 识别故障服务

### Requirement 7: 前端 ESLint 升级到 v9 Flat Config

**User Story:** 作为前端开发者，我希望将 ESLint 升级到 v9 并使用 flat config 格式，以便获得更好的性能和更清晰的配置结构。

#### Acceptance Criteria

1. THE 前端依赖 SHALL 将 `eslint` 从 `^8.56.0` 升级到 `^9.0.0`，并将 `eslint-plugin-vue`、`@typescript-eslint/eslint-plugin`、`@typescript-eslint/parser` 升级到与 ESLint v9 兼容的版本
2. THE 前端项目 SHALL 使用 `eslint.config.js`（flat config）替代旧版 `.eslintrc.cjs` 配置，新配置须包含等效的 Vue 3、TypeScript 及项目现有自定义规则，且旧版 `.eslintrc.cjs` 文件须删除
3. WHEN 执行 `npx eslint .` 对前端项目进行 lint 检查时，THE 现有代码 SHALL 通过检查且产生 0 个 error（warning 数量不超过升级前的数量）
4. THE CI_Pipeline 中 `frontend-lint` job 的 ESLint 命令 SHALL 移除已废弃的 `--ext` 参数，改为通过 `eslint.config.js` 中的 `files` 配置指定目标文件类型（`.vue`, `.js`, `.jsx`, `.cjs`, `.mjs`, `.ts`, `.tsx`, `.cts`, `.mts`）
5. THE Pre_Commit 中的 `frontend-eslint` hook SHALL 移除 `--ext` 参数，直接将文件路径传递给 `npx eslint`，并保留 `--no-error-on-unmatched-pattern` 和 `--max-warnings 0` 参数
6. THE `package.json` 中的 `lint` 和 `lint:fix` 脚本 SHALL 移除 `--ext` 参数，更新为与 ESLint v9 兼容的调用格式

### Requirement 8: 集成结构化日志标准

**User Story:** 作为运维人员，我希望后端日志以 JSON 格式输出，以便在日志聚合系统中高效检索和分析。

#### Acceptance Criteria

1. IF 环境变量 `LOG_FORMAT` 设置为 `json`，THEN THE 后端服务 SHALL 将控制台及文件 sink 的所有日志条目以单行 JSON 格式输出，每条日志为一个独立的 JSON 对象
2. THE Structured_Logging 的每条 JSON 日志 SHALL 包含以下字段：`timestamp`（ISO 8601 格式，精确到毫秒）、`level`（取值范围：DEBUG / INFO / WARNING / ERROR / CRITICAL）、`message`（字符串，最大长度 10000 字符）、`module`（产生日志的模块名称）、`request_id`（当前请求上下文的唯一标识，无请求上下文时值为 `"N/A"`）
3. WHILE 环境变量 `DEBUG` 为 `true` 且 `LOG_FORMAT` 未设置或不为 `json` 时，THE 后端服务 SHALL 默认使用带 ANSI 颜色码的人类可读日志格式输出到控制台
4. THE 日志配置 SHALL 通过 loguru 的 sink 机制实现，现有使用 `get_logger(__name__)` 和 `logger.info/error/warning` 的调用代码无需任何修改即可生效
5. WHEN HTTP 请求进入时，THE LoggingMiddleware SHALL 为每个请求生成一个 8 字符的 UUID v4 前缀作为 `request_id`，通过 loguru bind 注入日志上下文，并在响应头 `X-Request-ID` 中返回该值
6. IF 环境变量 `LOG_FORMAT` 的值既不是 `json` 也不是 `text`（或未设置），THEN THE 后端服务 SHALL 根据 `DEBUG` 环境变量的值回退到默认行为：`DEBUG=true` 使用彩色文本格式，`DEBUG=false` 使用 JSON 格式

### Requirement 9: 添加 OpenAPI Schema 验证到 CI

**User Story:** 作为 API 开发者，我希望 CI 自动验证 OpenAPI schema 的正确性和向后兼容性，以便防止意外的 API 破坏性变更。

#### Acceptance Criteria

1. THE CI_Pipeline SHALL 添加一个 pre-flight job，用于从 FastAPI 应用导出 OpenAPI schema 并对其进行 OpenAPI 3.1 规范验证，该 job 须在 60 秒内完成
2. WHEN 导出的 OpenAPI schema 包含结构性语法错误或不符合 OpenAPI 3.1 规范（如缺少必填字段、类型定义无效、引用路径不存在）时，THE CI_Pipeline SHALL 将该 job 标记为失败并在日志中输出具体的验证错误信息
3. THE CI_Pipeline SHALL 将生成的 `openapi.json` 作为构建产物存档，保留期为 7 天
4. WHEN PR 修改了 `app/api/` 目录下的任意 Python 文件时，THE CI_Pipeline SHALL 在 PR 评论中标注 API 变更摘要，包括：新增的端点列表、删除的端点列表、以及请求或响应 schema 发生变化的端点列表
5. WHEN PR 引入了向后不兼容的 API 变更（删除端点、删除必填响应字段、或修改现有端点的 URL 路径）时，THE CI_Pipeline SHALL 将该 job 标记为失败并在 PR 评论中明确标注破坏性变更内容

### Requirement 10: 建立数据库迁移规范

**User Story:** 作为开发者，我希望所有数据库 schema 变更都通过 Alembic 迁移管理，以便在多环境部署时保持数据库一致性。

#### Acceptance Criteria

1. THE 项目 SHALL 为现有数据库 schema 生成 Alembic baseline 迁移文件，覆盖 ORM Base.metadata 中定义的所有表和索引
2. WHEN 开发者修改 ORM 模型时，THE 开发流程 SHALL 要求在同一 Pull Request 中提交对应的 Alembic 迁移文件
3. THE CI_Pipeline SHALL 验证 Alembic 迁移链的完整性（无分叉、无缺失），通过执行 `alembic heads` 确认仅存在单一 head，并通过 `alembic history` 确认迁移链无断裂
4. THE CI_Pipeline SHALL 对空数据库执行 `alembic upgrade head`，并在命令以退出码 0 完成且数据库到达最新 revision 时判定为通过，超时限制为 120 秒
5. IF `alembic check` 检测到 ORM 模型存在未被现有迁移文件覆盖的变更，THEN THE CI_Pipeline SHALL 输出差异摘要并将该检查步骤标记为失败
6. THE 每个迁移文件 SHALL 同时包含 upgrade 和 downgrade 函数，且 downgrade 函数能将 schema 回退到前一 revision 的状态

### Requirement 11: 添加前端性能审计

**User Story:** 作为前端开发者，我希望 CI 自动执行 Lighthouse 性能审计，以便持续监控页面加载性能和可访问性。

#### Acceptance Criteria

1. THE CI_Pipeline SHALL 添加 Lighthouse CI job，对以下页面执行性能审计：至少包含登录页及一个需认证的代表性页面（如 dashboard），审计类别包含 Performance 和 Accessibility
2. WHEN 任一被审计页面的 Performance 分数低于 60 分时，THE CI_Pipeline SHALL 在 job 输出中产生 GitHub Actions warning 注解，但 job 状态保持为通过
3. WHEN 任一被审计页面的 Accessibility 分数低于 80 分时，THE CI_Pipeline SHALL 将该 job 标记为失败（非零退出码）
4. THE CI_Pipeline SHALL 将 Lighthouse HTML 报告作为构建产物存档，保留期限为 7 天
5. WHEN 前端构建完成后，THE 前端构建 job SHALL 将当前 entry chunk（index-*.js）体积与目标分支（master 或 develop）上最近一次成功构建的 entry chunk 体积进行比较
6. IF entry chunk 体积相对于目标分支基线增长超过 10%，THEN THE 前端构建 job SHALL 在 job 输出中产生 GitHub Actions warning 注解，但不阻断构建

### Requirement 12: 依赖版本锁定与漏洞扫描

**User Story:** 作为安全负责人，我希望所有依赖版本被严格锁定且自动扫描漏洞，以便防止供应链攻击和已知漏洞引入。

#### Acceptance Criteria

1. THE CI_Pipeline SHALL 在每次运行时使用 `npm ci` 安装前端依赖，并验证 `package-lock.json` 与 `package.json` 声明一致（即 `npm ci` 成功退出，退出码为 0）
2. WHEN 前端依赖存在 severity 为 high 或 critical 的已知漏洞时，THE CI_Pipeline SHALL 执行 `npm audit --audit-level=high` 并将该步骤标记为失败（退出码非 0）
3. THE nightly workflow SHALL 对前端执行 `npm audit` 全量扫描，并对后端执行 `pip-audit` 扫描，覆盖所有生产与开发依赖
4. WHEN nightly workflow 的漏洞扫描发现 severity 为 high 或 critical 的漏洞，且该漏洞在最近 7 天内未被已有 open 状态的 GitHub Issue 覆盖时，THE nightly workflow SHALL 创建一个 GitHub Issue，标题包含漏洞包名和严重级别，正文包含受影响的包名、当前版本、漏洞编号（CVE/GHSA）及建议修复版本
5. THE CI_Pipeline SHALL 在后端安装步骤中使用 `pip install -e ".[dev,backtrader]"` 后执行 `pip freeze`，并将输出与仓库中的 `requirements-dev.lock` 文件进行逐包版本比对，若存在版本不一致则将该步骤标记为失败
6. WHEN 后端依赖发生变更时，THE 开发者 SHALL 通过运行锁文件生成命令更新 `requirements-dev.lock` 和 `requirements-prod.lock` 文件，确保锁文件中记录所有传递依赖的精确版本号

### Requirement 13: 添加开发环境数据种子

**User Story:** 作为新加入的开发者，我希望本地开发环境能自动填充示例数据，以便快速体验和调试各功能模块。

#### Acceptance Criteria

1. THE 项目 SHALL 提供 `scripts/seed_dev_data.py` 脚本，生成开发用示例数据
2. WHEN 执行种子脚本时，THE 脚本 SHALL 创建至少 2 个示例用户、至少 3 条策略、至少 3 条回测记录和至少 2 个知识库（各含至少 1 篇文档）数据
3. THE 种子脚本 SHALL 支持 `--reset` 参数清除并重新生成所有示例数据
4. IF 数据库中已存在种子数据，THEN THE 脚本 SHALL 跳过已存在的记录并向标准输出打印每种实体类型的已跳过数量与新建数量
5. THE docker-compose.dev.yml SHALL 支持通过环境变量 `SEED_DATA=true` 在首次启动时自动执行种子脚本，首次启动通过检测数据库中是否已存在种子用户记录来判定
6. IF 种子脚本执行时数据库连接不可用，THEN THE 脚本 SHALL 在标准错误输出中打印包含失败原因的错误信息并以非零退出码退出
7. THE 种子脚本 SHALL 在 30 秒内完成全部示例数据的生成

### Requirement 14: OpenTelemetry 默认集成

**User Story:** 作为运维人员，我希望 OpenTelemetry 作为默认可观测性方案集成，以便在生产环境中获得分布式追踪和性能指标。

#### Acceptance Criteria

1. THE 后端依赖 SHALL 将 `opentelemetry-api`、`opentelemetry-sdk`、`opentelemetry-instrumentation-fastapi`、`opentelemetry-instrumentation-sqlalchemy`、`opentelemetry-instrumentation-httpx` 和 `opentelemetry-exporter-otlp-proto-grpc` 从 `[otel]` 可选依赖组移至核心 `dependencies` 列表
2. IF 环境变量 `OTEL_ENABLED` 设置为 `true`（不区分大小写，同时接受 `1` 和 `yes`），THEN THE 后端服务 SHALL 在应用启动阶段完成 OpenTelemetry SDK 初始化，并在日志中输出包含服务名称和 collector 地址的初始化成功信息
3. WHILE 环境变量 `OTEL_ENABLED` 设置为 `true`，THE OpenTelemetry 集成 SHALL 为每个 FastAPI 入站请求生成 trace span、为每个 SQLAlchemy 数据库查询生成 trace span、以及为每个 httpx 出站 HTTP 调用生成 trace span，并将 span 数据通过 OTLP gRPC 协议导出至配置的 collector
4. WHILE `OTEL_ENABLED` 未设置或值不为 `true`/`1`/`yes`，THE 后端服务 SHALL 正常运行，不加载 OpenTelemetry SDK 的 TracerProvider，且请求处理延迟增加不超过 1 毫秒
5. THE 配置 SHALL 支持通过环境变量 `OTEL_EXPORTER_OTLP_ENDPOINT` 指定 collector 地址，默认值为 `http://localhost:4317`，并支持通过 `OTEL_SERVICE_NAME` 指定服务名称，默认值为 `backtrader-web-api`
6. IF `OTEL_ENABLED` 为 `true` 且配置的 collector 地址不可达，THEN THE 后端服务 SHALL 继续正常处理请求而不阻塞或崩溃，并在日志中记录 collector 连接失败的警告信息

### Requirement 15: 健康检查端点 CI 验证

**User Story:** 作为 DevOps 工程师，我希望 CI 验证健康检查端点的可用性和响应格式，以便确保部署后监控系统能正常工作。

#### Acceptance Criteria

1. WHEN CI_Pipeline 集成测试阶段启动后端服务后，THE CI_Pipeline SHALL 向 `/api/v1/health` 端点发送 HTTP GET 请求，并验证响应状态码为 200 且响应体为合法 JSON 格式
2. WHEN `/api/v1/health` 端点返回 200 响应时，THE Health_Check_Endpoint 响应体 SHALL 包含以下字段：`status`（字符串，值为 "healthy"）、`version`（字符串，符合语义化版本格式）、`database`（字符串，值为 "healthy" 或 "unhealthy"）、`uptime`（数值，表示服务运行秒数，大于等于 0）
3. IF 数据库连接失败（连接超时超过 5 秒或连接被拒绝），THEN THE Health_Check_Endpoint SHALL 返回 HTTP 503 状态码，响应体中 `status` 字段值为 "unhealthy"，`database` 字段值为 "unhealthy"，且其余字段（`version`、`uptime`）仍正常返回
4. WHEN CI_Pipeline 验证健康检查响应时间时，THE CI_Pipeline SHALL 断言从发送请求到收到完整响应的耗时不超过 2000ms，若超时则标记该测试步骤为失败
5. IF `/api/v1/health` 端点返回非 200 且非 503 的状态码或响应体缺少必需字段，THEN THE CI_Pipeline SHALL 将集成测试标记为失败并输出包含实际状态码和响应体的错误信息

### Requirement 16: 前端 marked 库安全配置

**User Story:** 作为安全负责人，我希望前端 Markdown 渲染使用安全的 sanitization 配置，以便防止 XSS 攻击。

#### Acceptance Criteria

1. THE 前端 SHALL 对所有 Markdown 转 HTML 的输出在插入 DOM 之前通过 DOMPurify 进行净化，覆盖每一处使用 `v-html` 渲染 Markdown 内容的组件
2. WHEN Markdown 内容包含 `<script>`、`<iframe>`、`<object>`、`<embed>`、`<form>` 标签、`javascript:` 或 `data:` 协议 URI、或 HTML 事件处理属性（如 `onerror`、`onload`）时，THE 渲染器 SHALL 将这些危险元素及属性从输出中完全移除，保留其余合法内容不变
3. THE DOMPurify 配置 SHALL 通过 `ALLOWED_TAGS` 显式定义允许的 HTML 标签白名单（限定为 Markdown 渲染所需的标签，包括：段落、标题、列表、表格、代码块、行内格式化、链接、图片），并通过 `ALLOWED_ATTR` 限定允许的属性（如 `href`、`src`、`alt`、`class`），拒绝白名单之外的所有标签和属性
4. THE 前端 SHALL 包含不少于 8 个针对不同类别 XSS payload 的 Vitest 单元测试用例，覆盖以下攻击向量类别：脚本标签注入、事件处理器注入、协议型 XSS（javascript:/data:）、iframe 嵌入，每个类别至少 2 个测试用例，每个用例验证净化后的输出不包含可执行脚本内容
