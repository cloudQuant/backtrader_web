# Requirements Document

> 迭代 175「质量加固与可观测性纵深」

## Introduction

本文档定义了 Backtrader Web 量化交易平台**迭代 175**的需求。迭代 175 在迭代 174「结构精简与工程债接续」基础上推进，聚焦于把已经搭好的骨架进一步收紧到「可观测、可验证、可阻塞回归」的状态。

### 175 与 174 的边界

为避免重复劳动，175 严格遵守以下边界：

- **174 已承诺完成、175 不再做**：根目录 / scripts / docker / src 多包结构精简（174 主线 A）；后端 API/Service 子包化（174 主线 B）；后端 ≥800 行文件切片与前端 ≥1000 行 .vue 拆分（174 主线 C 主体）；docs/ Diátaxis 分层与设计系统 v0.2 落地（174 主线 D）；Prompt 治理后半段、前端覆盖率二级棘轮 45→60、Docker Hub 发版自动化（174 流程线 E）。
- **175 接续做**：把 174 §10 显式登记的「175 候选」逐项落地，并补齐 174 完成后暴露出来的新质量缺口。
- **175 不做**：任何新业务功能 PRD；不新增框架/语言/构建工具；不动数据库 schema（除迁移守护脚本本身）；不在 `backtrader_web` 内新增 broker 适配；不重做 UI 信息架构。

### 175 关注的质量改进域

按重要性排序：

1. 后端 mypy 严格模式扩盘到 `app/services/*`（174 仅锁 `app/api`、`app/utils`、`app/schemas`、`app/services/quote`）。
2. 前端覆盖率三级棘轮：lines/functions/branches 全部从 60 提升到 75，关键 store 与 composables 标记≥90% 高覆盖核心。
3. 整站无障碍（A11y）基线达成 WCAG 2.1 AA；7 个核心页面 axe-core 0 critical/serious；Lighthouse Accessibility 阈值由 80 提至 90 并阻塞构建。
4. 整站国际化覆盖率达到 100%（zh-CN / en-US）；新增 lint/CI 检查防止裸字符串回归。
5. 后端 OpenTelemetry 全链路追踪覆盖核心业务流程（创建回测 → 执行 → 收集结果、提交策略、AI 对话、实盘单流转），span 携带业务属性。
6. 端到端测试上 CI（PR 必跑 e2e smoke ≤5 分钟，nightly 跑完整 e2e 套件）。
7. 前端 bundle size 棘轮强制阻塞 + vendor 拆分；首屏 entry chunk gzip 体积有上限阈值。
8. 数据库迁移自动化与守护：ORM↔ schema diff 校验、迁移性能/锁表预警。
9. `bt_api_py` 与 `backend` 的 monorepo 工具化（uv workspace 一键检查全工作区）。
10. 173B（FinceptTerminal T2/T7/T10）归属确认与处置（接 174 §10 E4）。
11. （可选）前端 500-999 行 .vue 收尾（174 主要拆 ≥1000 行）。

---

## Glossary

- **A11y**: Accessibility 缩写，指无障碍可访问性，涵盖屏幕阅读器、键盘导航、ARIA 属性、对比度等可被辅助技术正确识别使用的能力。
- **WCAG_2.1_AA**: Web Content Accessibility Guidelines 2.1 Level AA，万维网联盟（W3C）发布的无障碍标准的 AA 合规级别，包含可感知、可操作、可理解、健壮性四大原则下的具体可量化条款。
- **Axe_Core**: Deque Systems 出品的开源 A11y 自动化检测引擎，能扫描 DOM 并按 WCAG 条款返回违规列表，违规分级为 minor / moderate / serious / critical。
- **Lighthouse_A11y_Score**: 由 Google Lighthouse 工具基于 axe-core 子集与启发式规则计算的 0-100 分整数，反映页面无障碍合规度。
- **Bundle_Size_Ratchet**: 一种 CI 守护机制，当生产构建产物体积超过既定阈值或相对基线增长超过既定百分比时阻塞合入，仅允许"减小"或"持平"，类似于覆盖率棘轮。
- **OTel_Span**: OpenTelemetry 语义中的"跨度"对象，表示一次有起止时间、可携带属性（attributes）和事件（events）的工作单元；多个 span 通过 trace_id 关联成 trace。
- **Trace**: 由共享 trace_id 的一组 span 组成的完整调用链，能跨进程、跨服务还原一次请求的完整生命周期。
- **OTLP**: OpenTelemetry Protocol，OTel 默认的 wire 格式与协议，支持 gRPC/HTTP 两种传输；本项目 OTel 采集器（Jaeger/Tempo）通过 OTLP gRPC 接收 span。
- **E2E_Smoke**: 端到端冒烟测试集合，覆盖少量但关键的用户旅程（如登录、创建回测、查看结果、AI 对话、KB 问答），目标是在 PR 阶段以 ≤5 分钟成本暴露最严重的端到端回归。
- **Property_Based_Testing**: 性质测试（PBT），通过随机生成大量输入用例验证函数性质（如不变量、往返、幂等等）的测试方法；本项目使用 Hypothesis（后端）与 fast-check（前端）。
- **Mypy_Strict_Scope**: mypy 中通过 `[[tool.mypy.overrides]]` 节为指定模块开启 `disallow_untyped_defs = true` 等严格规则的作用域；175 用此机制把严格作用域从 `app/api` / `app/utils` / `app/schemas` / `app/services/quote` 扩到 `app/services/*`。
- **Coverage_Ratchet**: 覆盖率棘轮，CI 上配置覆盖率门禁阈值，只允许向上调整；175 把 vitest lines/functions/branches 三项门槛从 60 推至 75。
- **High_Coverage_Core**: 175 显式登记的"高覆盖率核心"模块集合，要求 lines/functions/branches 三项均 ≥90%，包含关键 Pinia store 与关键 composables。
- **i18n_Coverage_Lint**: 国际化覆盖率 lint 检查，通过 AST/正则扫描 .vue / .ts 源码，识别用户可见位置（template 文本、label、placeholder、message 文案等）出现的中文/英文裸字符串，阻断未走 i18n key 的回归。
- **Locale_Key_Parity**: 不同 locale 文件之间键集合的对等性约束；要求 zh-CN 与 en-US 两个 locale 命名空间下的 key 完全一致，缺失值会被 CI 报错。
- **Alembic_Drift_Check**: 通过 `alembic check` 等价机制对比当前 ORM 元数据与最新 migration 的 schema 差异，发现"忘记生成 migration"的情况；175 在此基础上补充 ORM ↔ live schema 的 round-trip 校验脚本。
- **Migration_Lock_Warning**: 在 Alembic 迁移脚本静态分析中识别可能引发长时间表锁/全表扫描的危险操作（如对大表 ALTER TABLE … ADD COLUMN NOT NULL DEFAULT、DROP COLUMN 等）并在 CI 中输出警告。
- **uv_Workspace**: Astral 出品的 `uv` 工具的 workspace 特性，支持在同一仓库内声明多个 Python 包并由统一入口安装、解锁、运行；175 用其把 `src/backend` 与 `src/bt_api_py` 收敛到一个工作区。
- **Bandit_Gate**: 已存在的 bandit 安全扫描阻塞门（173 引入），175 在此基础上不动语义，仅复用。
- **Critical_Page_Set**: 175 锁定的 7 个核心页面集合：登录页、首页（Dashboard）、AI Chat 页、回测列表页、回测详情页、知识库页、策略管理页。
- **User_Journey_Set**: 175 锁定的 5 条 PR-blocking 用户旅程集合：登录、创建回测并查看结果、AI 对话、KB 问答、策略管理（创建/列表）。

---

## Requirements

### Requirement 1: 后端 mypy 严格模式扩盘到 services 子包

**User Story:** 作为后端开发者，我希望 `app/services/*` 也强制类型注解，以便在 CI 阶段尽早暴露隐式 Any 与缺失返回类型造成的潜在缺陷。

#### Acceptance Criteria

1. THE `src/backend/pyproject.toml` 的 `[[tool.mypy.overrides]]` SHALL 在保留现有 `app.api.*`、`app.schemas.*`、`app.services.quote.*`、`app.utils.*` 严格作用域的基础上，新增以下子包并启用 `disallow_untyped_defs = true`：`app.services.strategy.*`、`app.services.backtest.*`、`app.services.gateway.*`、`app.services.akshare.*`、`app.services.optimization.*`、`app.services.live_trading.*`、`app.services.workspace.*`、`app.services.log_parser.*`、`app.services.ai_trading.*`。
2. WHEN 在 `src/backend/` 目录执行 `mypy app` 时，THE mypy 命令 SHALL 以 exit code 0 通过，新增类型错误数为 0。
3. THE 新增的 `# type: ignore[<error-code>]` 行数 SHALL 在 `src/backend/` 内总计不超过 80 行；超出阈值的 PR 必须由项目所有者明确批准并在 PR 描述中列出每条 ignore 的理由。
4. WHERE 子包内存在尚不能完全消除 Any 的旧代码，THE 175 实施 SHALL 在该子包根 `__init__.py` 顶部以注释形式登记残留 Any 的来源（不超过 5 类，每类一行），并在 175 验收报告中列入"已知尾巴"。
5. THE `.github/workflows/ci.yml` SHALL 在现有 `backend-lint` / `backend-mypy-ratchet` / `backend-mypy-quote` / `backend-mypy-api-subset` job 之外新增独立的 `backend-mypy-services` job，job 内执行 `mypy app/services/strategy app/services/backtest app/services/gateway app/services/akshare app/services/optimization app/services/live_trading app/services/workspace app/services/log_parser app/services/ai_trading`，且失败时阻塞合入。
6. THE `backend-mypy-services` job SHALL 被加入 `ci-summary` job 的 `needs` 列表，且其 `result == 'failure'` 进入失败合并条件。
7. IF 175 实施期间发现某子包暂时无法在不引入大于 80 行 ignore 的前提下完成扩盘，THEN THE 实施团队 SHALL 在该子包对应的 PR 描述中提供降级说明，并把该子包从本需求接受范围中移到 176 候选；175 验收时已扩盘的子包数量 SHALL 不少于 7 个。

### Requirement 2: 前端覆盖率三级棘轮（60 → 75）与高覆盖率核心标记

**User Story:** 作为前端开发者，我希望 vitest 覆盖率门禁继续上行到 75%，并把关键 store 与 composables 锁定到 90%，以便核心状态/能力一旦回归就被测试网兜住。

#### Acceptance Criteria

1. THE `src/frontend/vitest.config.ts` 中 `test.coverage.thresholds` SHALL 从当前的 `lines: 45, functions: 50, branches: 55, statements: 45` 调整为 `lines: 75, functions: 75, branches: 75, statements: 75`。
2. THE 175 实施 SHALL 显式登记 High_Coverage_Core 模块集合，集合至少包含以下两类条目：（a）Pinia store：`auth`、`user_preferences`、`backtest`、`strategy`、`knowledge_base` 五个 store；（b）composables：`useAuth`、`useApiClient`、`useI18n` 等关键能力（实际清单以代码现状为准，不少于 8 个 store/composable 模块）。
3. THE `src/frontend/vitest.config.ts` SHALL 通过 `test.coverage.thresholds.perFile` 或等价 `<modulePath>` 阈值配置，为 High_Coverage_Core 中每个模块路径设置 `lines: 90, functions: 90, branches: 90, statements: 90` 的独立覆盖率门槛。
4. WHEN 在 `src/frontend/` 目录执行 `npm run test -- --run --coverage` 时，THE 命令 SHALL 以 exit code 0 完成，且 v8 reporter 输出全局阈值通过、High_Coverage_Core 阈值通过。
5. THE `.github/workflows/ci.yml` `frontend-test` job SHALL 在 `npm run test` 步骤后新增"覆盖率核心阈值汇总"步骤，把 v8 reporter 输出的 lines/functions/branches/statements 与 High_Coverage_Core 命中情况注入 GitHub Actions job summary（使用 `$GITHUB_STEP_SUMMARY` markdown 表格）。
6. IF 任一 High_Coverage_Core 模块未达到 90% 阈值，THEN THE `frontend-test` job SHALL 以非零 exit code 失败，并在日志中列出未达标模块的当前覆盖率与缺口百分比。
7. THE 175 实施 SHALL 在 `src/frontend/__tests__/coverage_core.md`（或同等可读位置）登记 High_Coverage_Core 清单与每个模块的"已豁免行号区间"（如有），并在 PR 描述中链接此文件。

### Requirement 3: 整站 A11y 基线达成 WCAG 2.1 AA

**User Story:** 作为依赖辅助技术（屏幕阅读器、仅键盘）的用户，我希望 7 个核心页面满足 WCAG 2.1 AA 基线，以便在不使用鼠标和不依赖颜色感知的前提下也能完成关键任务。

#### Acceptance Criteria

1. THE Critical_Page_Set SHALL 锁定为以下 7 个页面（路径以 `src/frontend/src/router/` 中已注册路由为准）：登录页 `/login`、首页 `/dashboard`、AI Chat 页 `/ai-chat`、回测列表页 `/backtests`、回测详情页 `/backtests/:id`、知识库页 `/knowledge-base`、策略管理页 `/strategies`。
2. THE 前端依赖 SHALL 新增 `@axe-core/playwright` 作为 `devDependencies`；THE 项目 SHALL 在 `src/frontend/e2e/a11y/` 目录下提供针对 Critical_Page_Set 中每个页面的 Playwright 测试用例，每个测试用例使用 `AxeBuilder` 扫描页面并断言 `violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0`。
3. WHEN Playwright a11y 测试在登录态依赖的页面（除登录页外的 6 个）上运行时，THE 测试 SHALL 复用 `src/frontend/e2e/fixtures/` 下的认证 fixture 完成预登录，避免每个用例重复登录。
4. THE Critical_Page_Set 中所有交互元素（按钮、链接、表单控件）SHALL 满足以下硬约束：（a）非装饰性 `<img>` 与 icon 必须有 `alt` 或 `aria-label`；（b）所有表单输入有显式关联的 `<label>` 或 `aria-labelledby`；（c）颜色对比度 ≥ 4.5:1（正常文本）/ 3:1（大文本与图形元素）；（d）所有可点击元素可通过 `Tab` / `Shift+Tab` 到达，焦点可见（焦点环不被 outline:none 抹除）；（e）模态框打开时焦点被 trap 在框内，关闭后焦点返回触发元素。
5. THE `config/lighthouserc.js` SHALL 把 `categories:accessibility` 阈值由 `['error', { minScore: 0.8 }]` 调整为 `['error', { minScore: 0.9 }]`，并把 `collect.url` 数组扩展为覆盖 Critical_Page_Set 全部 7 个页面（登录页之外的页面通过 LHCI 的 `puppeteerScript` 或预注入 token 完成认证）。
6. THE `.github/workflows/ci.yml` SHALL 新增 `frontend-a11y` job，job 内执行 `npx playwright test e2e/a11y/`；job 失败阻塞合入。`frontend-a11y` job SHALL 加入 `ci-summary` 的 `needs` 列表，且其 `result == 'failure'` 进入失败合并条件。
7. WHEN `frontend-a11y` job 中任一页面发现 `critical` 或 `serious` 级别违规时，THE job SHALL 以非零 exit code 失败，并把违规列表写入 GitHub Actions job summary（包含页面 URL、规则 ID、影响节点 selector、修复建议链接）。
8. THE 175 实施 SHALL 在 `docs/explanation/accessibility-baseline.md` 中登记本次基线达成的方法、Critical_Page_Set 的扫描结果、所有"必要豁免"（exemptions）及其理由（不超过 5 条，每条引用 WCAG 条款编号），并在 README 索引中加入入口。

### Requirement 4: 整站 i18n 覆盖率达 100%（zh-CN / en-US）

**User Story:** 作为多语言用户，我希望前端 UI 中所有可见文本都可被 zh-CN/en-US 切换，以便在英文界面下不再看到任何中文残留或缺失键的占位符。

#### Acceptance Criteria

1. THE 前端项目 SHALL 提供 `scripts/dev/check_i18n_coverage.py`（或 `src/frontend/scripts/check-i18n-coverage.mjs` 等价 Node 脚本），脚本扫描 `src/frontend/src/**/*.{vue,ts}` 文件，识别出现在 `<template>` 文本节点、`<el-...>` 组件 `label`/`placeholder` props、`ElMessage(...)` / `ElMessageBox(...)` / `ElNotification(...)` 调用首参数中的中文裸字符串与英文长度 ≥4 的英文裸字符串，并输出违规清单（含文件路径、行号、片段、建议 i18n key 命名）。
2. WHEN 在仓库根目录运行 `python scripts/dev/check_i18n_coverage.py --strict` 时，THE 脚本 SHALL 以 exit code 0 退出，前提是违规清单为空；任何违规项 SHALL 导致 exit code 1。
3. THE 脚本 SHALL 支持 `// i18n-ignore-next-line` 与 `<!-- i18n-ignore-next-line -->` 两种豁免注释，被豁免的相邻一行不计入违规；175 验收时，全仓库豁免行数 SHALL 不超过 30 行，且每条豁免必须邻接 `i18n-reason: <短描述>` 注释。
4. THE `src/frontend/src/i18n/locales/zh-CN/` 与 `src/frontend/src/i18n/locales/en-US/` 两个命名空间下的 key 集合 SHALL 完全相同（Locale_Key_Parity）；脚本 `scripts/dev/check_i18n_coverage.py --check-parity` SHALL 在 key 集合不一致时输出差异并退出码 1。
5. THE `.github/workflows/ci.yml` `frontend-lint` job SHALL 新增"i18n 覆盖率检查"步骤，依次执行 `--strict` 与 `--check-parity` 两次扫描；任一失败阻塞合入。
6. THE 175 实施 SHALL 把 zh-CN 与 en-US locale 的 key 数量、增量、删除量写入 PR 描述中的"i18n 变更清单"段落（提交 PR 时强制要求的 PR 模板字段之一）。
7. WHILE 用户在浏览器把语言切换到 en-US，THE Critical_Page_Set 中所有用户可见文案 SHALL 不出现中文字符（通过 Playwright 测试 `e2e/i18n/en-us-no-chinese.spec.ts` 在 7 个页面上断言 `expect(await page.locator('body').innerText()).not.toMatch(/[\u4e00-\u9fff]/)`）。
8. THE Playwright i18n 测试 SHALL 加入 `frontend-a11y` 同 job 或新建 `frontend-i18n` job，并在 `ci-summary` 的 `needs` 与失败合并条件中登记。

### Requirement 5: 后端 OpenTelemetry 全链路追踪覆盖核心业务流程

**User Story:** 作为运维工程师，我希望在 Jaeger/Tempo 中能看到一次"创建回测 → 执行 → 收集结果"完整调用链的 span 树，并能按 user_id / strategy_id / backtest_id 检索 trace，以便在故障时分钟级定位瓶颈。

#### Acceptance Criteria

1. THE `src/backend/app/services/backtest/` 子包下的核心入口（创建回测、提交执行、收集结果三个方法）SHALL 通过 OpenTelemetry `tracer.start_as_current_span(...)` 创建命名空间为 `backtrader.backtest.<phase>` 的 OTel_Span，其中 `<phase>` 取值集合为 `{create, submit, execute, collect, finalize}`。
2. THE `src/backend/app/services/strategy/` 子包下的策略提交、版本创建两个核心方法 SHALL 创建命名空间为 `backtrader.strategy.<phase>` 的 OTel_Span，其中 `<phase>` 取值集合至少为 `{submit, version_create}`。
3. THE `src/backend/app/services/ai_trading/` 与 `src/backend/app/services/kb_chat_service.py`（或其拆分后子包等价位置）下的 AI 对话/AI 交易决策两个核心方法 SHALL 创建命名空间为 `backtrader.ai.<phase>` 的 OTel_Span，其中 `<phase>` 取值集合至少为 `{intent_parse, llm_call, response_format}`。
4. THE `src/backend/app/services/live_trading/` 子包下的实盘下单、撤单、成交回报三条路径 SHALL 创建命名空间为 `backtrader.live.<phase>` 的 OTel_Span，其中 `<phase>` 取值集合至少为 `{place_order, cancel_order, on_fill}`。
5. THE 上述所有 OTel_Span SHALL 在创建时通过 `span.set_attribute(...)` 至少携带以下业务属性中适用的子集：`bt.user_id`（int 或 str）、`bt.strategy_id`（int 或 str）、`bt.backtest_id`（int 或 str）、`bt.symbol`（str）、`bt.order_id`（str）；不适用的属性允许缺省。
6. WHEN 在本地通过 `docker compose -f docker-compose.yml -f docker/compose/dev.yml --profile observability up -d` 启动 Jaeger 后并访问其 UI（`http://localhost:16686`），且环境变量 `OTEL_ENABLED=true` 与 `OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317` 已配置时，THE Jaeger SHALL 在 5 分钟内收到至少一条以 `backtrader.backtest.create` 为根 span 的完整 trace，且该 trace 的 span 数量 ≥ 5（覆盖 create→submit→execute→collect→finalize 五个 phase 中至少 5 个）。
7. THE 175 实施 SHALL 在 `docker-compose.dev.yml`（或 174 已建立的 `docker/compose/dev.yml`）中以 `profiles: [observability]` 形式新增 Jaeger all-in-one 服务（image `jaegertracing/all-in-one:1.55+`），暴露端口 4317（OTLP gRPC）、4318（OTLP HTTP）、16686（UI），且在主 service 列表之外不影响默认 `up` 行为。
8. THE 性能开销控制：WHEN 启用 OTel（`OTEL_ENABLED=true`）后，THE 后端在 `pytest -m benchmark`（或 `tests/perf/test_backtest_throughput.py` 等价基准）下相对禁用 OTel 的同套用例的 P95 延迟增长 SHALL 不超过 5%；如基准缺失，本验收子项可降级为"不做硬阈值检测，但 PR 描述附带本机一次手动对比的相对差异表"。
9. THE `src/backend/tests/test_telemetry_e2e.py`（新增文件）SHALL 包含至少 6 个测试用例：分别验证 backtest 5 phase 全部产生 span、strategy 2 phase 产生 span、ai 3 phase 产生 span、live 3 phase 产生 span、business attributes 注入正确（`bt.user_id` 与 `bt.backtest_id`）、collector unreachable 时不抛异常仅 WARNING。

### Requirement 6: 端到端测试上 CI（PR 必跑 E2E_Smoke + nightly 全量）

**User Story:** 作为发版负责人，我希望关键用户旅程在每个 PR 上自动验证，而不依赖人工触发 `npm run test:e2e`，以便端到端回归在合并前就被发现。

#### Acceptance Criteria

1. THE User_Journey_Set SHALL 锁定为以下 5 条用户旅程（每条对应 1-2 个 Playwright 测试用例）：（a）登录与登出；（b）创建回测、提交执行、查看结果详情；（c）AI 对话发起会话并收到非空回复；（d）知识库提问并收到引用 ≥1 条的回答；（e）策略管理新建策略并出现在策略列表中。
2. THE `src/frontend/e2e/smoke/` 目录 SHALL 提供针对 User_Journey_Set 全部 5 条旅程的 Playwright 测试，单条测试 P95 wall-clock ≤ 60 秒，整个 smoke 套件 wall-clock 总耗时 ≤ 5 分钟（含浏览器启动）。
3. THE `.github/workflows/e2e.yml`（已存在）SHALL 被改造或拆分为以下两份 workflow：（a）`pr-e2e-smoke.yml`（或在 `ci.yml` 内新增 `frontend-e2e-smoke` job），仅跑 `e2e/smoke/`，由 `pull_request` 触发，必须阻塞合入；（b）`nightly.yml`（已存在）扩展跑完整 `e2e/` 目录，由 cron 与 `workflow_dispatch` 触发，失败仅产生 issue，不阻塞合入。
4. THE PR-blocking 的 e2e smoke job SHALL 加入 `ci-summary` 的 `needs` 列表，且其 `result == 'failure'` 进入失败合并条件。
5. THE smoke job SHALL 在 GitHub Actions runner 上自启后端（uvicorn）+ 前端预览服务器（vite preview 或预构建 dist + 静态服务器）+ Postgres service container；SHALL 在测试运行前等待 `/api/v1/health` 返回 200，等待超时 ≤ 60 秒；SHALL 在测试结束后无论成败收集 Playwright trace、video 与 screenshot 作为 7 天 artifact。
6. WHEN smoke job 失败时，THE workflow SHALL 通过 `actions/upload-artifact@v4` 上传失败用例的 trace zip，且在 job summary 中链接 artifact，便于本地 `npx playwright show-trace`。
7. THE nightly 全量 e2e job 失败时 SHALL 通过 GitHub API 自动创建（或 reopen）一个标题为 `[nightly-e2e] failure on <date>` 的 issue，body 中粘贴失败测试名与 trace artifact 链接；同标题 issue 在 7 天内已存在则改为追加评论而非新建。

### Requirement 7: 前端 Bundle Size Ratchet 强制阻塞 + Vendor 拆分

**User Story:** 作为终端用户，我希望首屏不被巨大的 JS 阻塞，且公共依赖被合理切分以利浏览器缓存复用，以便在弱网环境下首屏依然可用。

#### Acceptance Criteria

1. THE `src/frontend/vite.config.ts` 中 `build.rollupOptions.output.manualChunks` SHALL 至少包含以下独立 vendor chunk 划分键名：`element-plus`、`vue-router`、`pinia`、`echarts`、`monaco-editor`；每个键名命中相应包路径前缀的依赖且彼此不重叠。
2. THE 175 实施 SHALL 在 `scripts/ci/check_bundle_size.sh` 中定义并落实以下硬阈值：entry chunk（`dist/assets/index-*.js`）gzip 体积 ≤ 300 KB；首屏关键路由（登录路由组件）的关联 JS 请求数（不含 vendor）≤ 4 个。
3. WHEN `npm run build` 后，THE `scripts/ci/check_bundle_size.sh` SHALL 在任一硬阈值越界时以非零 exit code 失败，并在标准输出打印越界项的目标值与实际值。
4. THE `.github/workflows/ci.yml` `frontend-build` job SHALL 把 `scripts/ci/check_bundle_size.sh dist` 步骤的 `continue-on-error` 移除（如有）或保持其默认阻塞语义，使该步骤失败必然导致 job 失败；`frontend-build` job 已在 `ci-summary` 的 `needs` 列表中，无需二次登记。
5. THE PR 体积对比逻辑（已存在的"Compare bundle size with target branch"步骤）SHALL 把"超过 10% 增长 → warning"升级为"超过 10% 增长 → 阻塞 PR"，但首次为某 entry chunk 建立基线时（base 缺失）允许跳过；阻塞实现允许通过 `BUNDLE_SIZE_GROWTH_OVERRIDE` 标签或 PR description 中的 `<!-- bundle-size-override: <reason> -->` 注释绕过，且使用绕过的 PR 必须由项目所有者批准。
6. THE 175 实施 SHALL 在 `docs/reference/frontend-bundle-budget.md`（或同等可读位置）登记当前各 vendor chunk 体积、entry chunk 体积、首屏请求数；本文件作为下一轮调整阈值的基线引用。

### Requirement 8: 数据库迁移自动化与守护

**User Story:** 作为后端开发者，我希望忘记生成 migration 时 CI 立刻失败，且危险迁移在合并前就被警告，以便不再因迁移问题导致部署事故。

#### Acceptance Criteria

1. THE 175 实施 SHALL 提供 `scripts/ci/check_orm_schema_drift.py` 脚本，脚本流程：（a）使用 `alembic upgrade head` 把当前 migration 链应用到一次性 SQLite 数据库；（b）从应用 ORM `Base.metadata` 读取期望 schema；（c）通过 `sqlalchemy.MetaData.reflect` 从迁移后 DB 读取真实 schema；（d）对比两者表名、列名、列类型（粗粒度，忽略 server_default 的字面差异）、索引、外键集合，输出差异列表。
2. WHEN 执行 `python scripts/ci/check_orm_schema_drift.py` 时，THE 脚本 SHALL 以 exit code 0 退出当且仅当 schema 完全对齐；任何差异项 SHALL 触发 exit code 1 并打印差异 markdown 表格到 stdout。
3. THE `.github/workflows/ci.yml` `check-migrations` job SHALL 在现有 `alembic upgrade head` + `alembic check` 步骤之后追加运行 `python scripts/ci/check_orm_schema_drift.py`，失败阻塞合入。
4. THE 175 实施 SHALL 提供 `scripts/ci/check_migration_safety.py` 脚本，扫描 `src/backend/alembic/versions/*.py` 中本 PR 新增的迁移文件，识别以下危险操作并输出警告：（a）对生产已有表的 `op.add_column` 且列定义为 `nullable=False, server_default=None`（即无默认值的非空列）；（b）`op.drop_column` / `op.drop_table`；（c）`op.alter_column` 改变列类型或长度；（d）`op.create_index` 未指定 `postgresql_concurrently=True`（仅在 PG 方言下警告）。
5. WHEN `scripts/ci/check_migration_safety.py` 检测到危险操作时，THE 脚本 SHALL 以 exit code 0 退出（不阻塞合入），但在 stdout 输出 `::warning::` 注解并在 PR 上生成一条评论或 job summary 段落。
6. THE 175 实施 SHALL 在每个本轮新增迁移文件顶部要求添加形如 `# alembic-meta: estimated_rows=<N>; lock_kind=<short|long>` 的注释；`scripts/ci/check_migration_safety.py` 在缺失该注释时输出警告（不阻塞）。
7. THE 175 实施 SHALL 在 `docs/how-to/database-migration-playbook.md`（或 174 已建立的 docs 分层下等价位置）增补 1 节"长锁/全表扫描风险与降级策略"，内容覆盖：危险操作的 PG 推荐写法（`SET lock_timeout`、`CONCURRENTLY`、分批回填）、`scripts/ci/check_migration_safety.py` 输出的解读、危险操作的 PR review 必看清单。

### Requirement 9: bt_api_py 与 backend 的 monorepo 工具化

**User Story:** 作为多包维护者，我希望一条命令就能跑遍 `src/backend` 与 `src/bt_api_py` 两个 Python 包的 lint/test/typecheck，以便不再因为漏跑一边导致集成失败。

#### Acceptance Criteria

1. THE 仓库根目录 SHALL 新增（或更新）`pyproject.toml` 顶层 workspace 声明（基于 uv_Workspace），将 `src/backend` 与 `src/bt_api_py` 注册为成员包；如选用其他等价工具（如 hatch / pdm workspace），需在 `docs/explanation/python-monorepo.md` 中记录选型理由。
2. THE 仓库根目录 SHALL 提供单一入口命令（建议 `make check-all` 或 `bash scripts/dev/check_all.sh`），运行后等价于按顺序在两个成员包内分别执行：`ruff check`、`ruff format --check`、`mypy <strict scopes>`、`pytest -m "not e2e"`，任一步失败立刻退出非 0。
3. WHEN 在仓库根目录执行 `uv sync --workspace`（或所选等价工具的同义命令）时，THE 命令 SHALL 同时安装两个成员包到一个共享 venv 并 resolve 出统一锁文件，且不引入与 `config/requirements-dev.lock`（174 已落地的 SSOT）冲突的版本。
4. THE 175 实施 SHALL 在 `CONTRIBUTING.md` "依赖管理"节末追加 1 段说明：（a）开发期间何时使用 workspace、何时使用单包；（b）如何新增第三个成员包；（c）锁文件如何与 workspace 协同生成。
5. THE `.github/workflows/ci.yml` SHALL 新增 `monorepo-check` job，在该 job 内调用 §9.2 的入口命令，作为 advisory（非阻塞）gate；待 175 验收稳定后再在 176 决定是否升级为 blocker。job 失败仅在 `ci-summary` 中显示 ⚠️ 警告。
6. THE 175 实施 SHALL 提供一份 `docs/explanation/python-monorepo.md`，内容覆盖：选型对比（uv workspace vs pdm vs hatch）、对 `src/clientportal.gw`（vendored）的处理方式、与 174 §A6 已澄清的 `src/` 多包边界一致性。

### Requirement 10: 173B（FinceptTerminal T2/T7/T10）归属确认与处置

**User Story:** 作为项目负责人，我希望 173B 三个未完成迁移点（T2/T7/T10）有明确的"做/不做"决议，以便此条工程债不再悬而未决。

#### Acceptance Criteria

1. THE 175 实施 SHALL 在 175 启动前 1 周内完成对 173B（T2/T7/T10）当前进度的核实，输出一份 `docs/iterations/迭代175-质量加固与可观测性纵深/173B_disposition.md`（路径以 174 的 `docs/iterations/` 命名约定为准）。
2. THE 173B_disposition.md SHALL 对 T2 / T7 / T10 三项分别给出且仅给出以下三种决议之一：（a）**纳入 175** - 在本文档 §10 之外另开一个对应的 175 子需求登记；（b）**顺延 176** - 写入 `docs/REFACTORING_BACKLOG.md`，并指向新行号；（c）**终止/归档** - 在 `CHANGELOG.md` 与 `docs/iterations/迭代173B-171残项独立收口摘要.md` 中标注 "abandoned in 175" 与原因。
3. WHERE T2 / T7 / T10 中任一项被决议为"纳入 175"，THE 该项 SHALL 在 175 进入实施阶段前转写为 EARS 格式的子需求并合并到本文档的 Requirements 列表中（编号 11.x、11.y、11.z）；本需求不预先占用编号。
4. WHILE 175 进入 design 与 tasks 阶段，THE 173B_disposition.md SHALL 始终保持与 `iterations/README.md` 的状态一致；不一致时 175 验收不通过。
5. WHEN 175 关闭时，THE 173B 中所有"顺延 176"或"终止"项 SHALL 从本仓库的活跃工程债视野中清除（即 `docs/REFACTORING_BACKLOG.md` 不再以"173B 残项"为活动条目，仅留可追溯链接）。

### Requirement 11: （可选）前端 500-999 行 .vue 收尾扫尾

**User Story:** 作为前端开发者，我希望 174 主线 C 拆完 ≥1000 行后剩余的 500-999 行 .vue 也按容量推进切片，以便文件平均长度持续下行，避免再次堆出 1000 行巨型组件。

#### Acceptance Criteria

1. THE 175 实施 SHALL 在 175 启动后第 2 周末扫描一次 `find src/frontend/src -type f -name '*.vue' | xargs wc -l | awk '$1>=500 && $1<1000'`，把命中文件按行数降序登记到 `docs/iterations/迭代175-质量加固与可观测性纵深/PROGRESS.md` 的 §11 列表中。
2. WHERE 175 在剩余容量允许的前提下选择实施本需求，THE 实施团队 SHALL 在 §11 列表中以 ID `C-501..C-5NN` 的形式列出每个待拆分文件、目标拆分子组件命名、估计工作量（S/M/L），并按从大到小顺序串行推进。
3. IF 175 容量不足以消化全部 ≥500 行尾巴，THEN THE 实施团队 SHALL 至少消化前 5 个最大文件，且把剩余项写入 `docs/REFACTORING_BACKLOG.md` 标注 "175 顺延"。
4. THE 175 验收时 §11 列表中的"已完成"项 SHALL 至少为 5 个，否则本需求标记为"未达成（容量不足）"，但不影响其他 10 项需求的整体验收结论。
5. THE 本需求标注为**可选**：在 175 启动评审会上若一致认为容量不足，可整体降级为"175 不做"，但需在评审纪要中显式记录决议。

---

## 验收门（全局）

> 175 全部验收门由本节列出；175 关闭前必须全部呈现绿色或被项目所有者明确批准的降级。

| 维度 | 量化指标 | 测量方法 |
| --- | --- | --- |
| Mypy services 扩盘 | `mypy app` exit 0；`backend-mypy-services` job 绿；新增 ignore ≤ 80 行 | `cd src/backend && mypy app` + CI 状态 |
| 前端覆盖率三级棘轮 | lines/functions/branches/statements 全部 ≥ 75% | `cd src/frontend && npm run test -- --run --coverage` |
| 前端高覆盖率核心 | High_Coverage_Core 内每个模块 ≥ 90% | vitest perFile thresholds 通过 |
| A11y 基线 | Critical_Page_Set 7 页 axe 0 critical/serious；Lighthouse a11y ≥ 90 | `frontend-a11y` job + Lighthouse CI |
| i18n 覆盖率 | 中文裸串 0；en-US locale 无中文残留；Locale_Key_Parity | `python scripts/dev/check_i18n_coverage.py --strict` + `--check-parity` |
| OTel 全链路 | backtest/strategy/ai/live 四类 phase 集合全部产生 span；business attributes 命中 | `pytest tests/test_telemetry_e2e.py` |
| E2E_Smoke 上 CI | PR-blocking smoke job 5 旅程全绿；nightly 失败自动建 issue | CI 状态 + nightly artifact |
| Bundle Size Ratchet | entry chunk gzip ≤ 300 KB；首屏 JS 请求 ≤ 4 | `scripts/ci/check_bundle_size.sh dist` |
| DB 迁移守护 | drift check 0 差异；safety check 输出警告齐全 | `python scripts/ci/check_orm_schema_drift.py` + `check_migration_safety.py` |
| Monorepo 工具化 | `make check-all` 或等价命令一键全绿；`monorepo-check` job 成功 | 入口命令 + CI 状态 |
| 173B 处置 | 173B_disposition.md 存在；T2/T7/T10 各有明确决议 | 文件存在性检查 |

---

## 175 与 176 的接续

175 完成后预期暴露的下一批工程债（**不在 175 内做**）：

- 后端 mypy 严格模式扩盘到 `app/services/` 剩余子包（如 ai_observability/data_connectors/factor_lib/market_regime/orchestration/perf_attribution/prompt_registry/risk_analytics/strategy_explainer/strategy_score 等）。
- 前端覆盖率四级棘轮（75 → 85）；High_Coverage_Core 集合扩展。
- A11y AAA 级别探索（不强求 AAA 全合规，但 Critical_Page_Set 选定条款达 AAA）。
- 后端 OTel metrics（不只是 traces）+ logs correlation。
- E2E 全套用例上 PR-blocking gate（175 仅 smoke 阻塞）。
- Bundle size 阈值再下探（300 KB → 250 KB）。
- DB 迁移在 staging 真实数据集 dry-run。
- Monorepo `monorepo-check` job 由 advisory 升级为 blocker。
- 国际化扩展第三语言（ja-JP / ko-KR / es-ES 任一）。

---

## 输入文档索引

阅读本计划时建议交叉参考：

- `docs/iterations/迭代174-结构精简与工程债接续/index.md` — 174 计划与 §10 175 候选清单
- `docs/iterations/迭代174-结构精简与工程债接续/PROGRESS.md` — 174 当前进度（用于核对哪些项已完成、不必重做）
- `docs/iterations/迭代173-工程债收口与设计系统统一/index.md` — 173 基线（mypy / 覆盖率 / 安全等已落地能力）
- `.kiro/specs/best-practices-iteration-2/requirements.md` — 第二轮最佳实践改进基线（本文档结构对齐）
- `docs/REFACTORING_BACKLOG.md` — 工程债总账（175 §10 会用到 / 更新）
- `docs/CODING_STANDARDS.md` — 编码规范基线
- `AGENTS.md` — AI 代理工作约束与命令清单
- `config/lighthouserc.js` — A11y 阈值现状（175 §3 升级目标）
- `src/frontend/vitest.config.ts` — 覆盖率阈值现状（175 §2 升级目标）
- `src/backend/pyproject.toml` — mypy 严格作用域现状（175 §1 扩盘目标）
- `src/backend/app/telemetry.py` — OTel 入口（175 §5 在此基础上扩 span 网络）
- `.github/workflows/ci.yml` / `e2e.yml` / `nightly.yml` — CI 工作流（175 多处扩展）
