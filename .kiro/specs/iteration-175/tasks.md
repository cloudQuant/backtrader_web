# Implementation Plan: 迭代 175「质量加固与可观测性纵深」

## Overview

迭代 175 分 5 个阶段实施。Phase 0（前置决议）只做 173B 处置评审；Phase 1（独立基线）落地三条彼此无依赖的基线扩盘（mypy services / 覆盖率 / bundle size）；Phase 2（前端可达性矩阵）落地 a11y + i18n + e2e smoke 三套 Playwright；Phase 3（后端可观测性）做 OTel span 网络与 Jaeger profile；Phase 4（守护与工具化）做 DB drift/safety + uv workspace + 可选 .vue 收尾。

## Tasks

- [x] 1. Phase 0: 前置决议
  - [x] 1.1 173B disposition 文档落地与一致性校验
    - 在 `docs/iterations/迭代175-质量加固与可观测性纵深/173B_disposition.md` 中按 design §10 表头登记 T2/T7/T10 三项实现完成度、剩余工作、决议类型、判定依据、责任人、目标日期
    - 同步更新 `iterations/README.md` 中 173B 行的决议类型、责任人、目标日期三个字段
    - 创建 `scripts/ci/check_173b_disposition_consistency.py`：解析两个文件的同标识符列，不一致 exit 1
    - WHERE 任一项决议为「纳入 175」，把对应 EARS 子需求追加到 `requirements.md` 编号 11.1+
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 2. Checkpoint - Phase 0 验证
  - 确认 173B_disposition.md 存在，三项决议字段齐全；T2/T7/T10 任一被纳入 175 的子需求已并入 requirements.md。

- [x] 3. Phase 1: 独立基线扩盘
  - [x] 3.1 后端 mypy 严格模式扩盘到 9 个 services 子包
    - 在 `src/backend/pyproject.toml` `[[tool.mypy.overrides]]` 新增 9 个子包条目（design §1），保留现有 4 个 override 不动
    - 逐子包补齐函数返回类型、参数注解；必要时在子包根 `__init__.py` 顶部添加 `# any-source: <类别> - <简述>` 行注释（每子包 ≤ 5 类）
    - 控制 `src/backend/` 内新增 `# type: ignore[<error-code>]` 行数 ≤ 80 行（相对 175 起点 commit）
    - WHERE 某子包暂时无法在 80 行 ignore 内扩盘，把它从 override 列表移到 PROGRESS.md「176 候选」并保证扩盘子包数 ≥ 7
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.7, 1.8_

  - [x] 3.2 backend-mypy-services CI job 落地与 ci-summary 接线
    - 在 `.github/workflows/ci.yml` 新增 `backend-mypy-services` job，工作目录 `src/backend`，单条 mypy 命令覆盖 9 个子包（design §1）
    - 在 `ci-summary` job 的 `needs:` 列表中追加 `backend-mypy-services`
    - 把 `needs.backend-mypy-services.result == 'failure'` 加入 `ci-summary` 失败合并条件
    - 验证：本地基于 175 终点 commit 在 `src/backend/` 跑 `mypy app`，要求 600 秒内 exit 0 且末行匹配 `^Found 0 errors`
    - _Requirements: 1.2, 1.6, 1.7_

  - [x] 3.3 前端覆盖率三级棘轮（60 → 75）+ High_Coverage_Core ≥ 90%
    - 修改 `src/frontend/vitest.config.ts`：全局 `lines/functions/branches/statements` 改为 75；新增 design §2 列出的 8 个模块路径键，每个键设 90%
    - WHERE 当前 vitest 版本不支持 `<modulePath>` 键，改用自定义 reporter `scripts/dev/coverage_core_reporter.ts` 等价校验
    - 创建 `src/frontend/__tests__/coverage_core.md` 登记 High_Coverage_Core 8 个模块路径与各模块的「已豁免行号区间」（如有）
    - 给低于阈值的 store / composable 补单测直至各项 ≥ 90%
    - _Requirements: 2.1, 2.2, 2.3, 2.7_

  - [x] 3.4 frontend-test job 增强 + 覆盖率核心阈值汇总
    - 创建 `scripts/dev/coverage_core_summary.mjs`：读取 `coverage/coverage-summary.json`，输出两张 markdown 表（全局指标 + High_Coverage_Core 指标）到 `$GITHUB_STEP_SUMMARY`
    - 在 `.github/workflows/ci.yml` `frontend-test` job 的 `npm run test` 步骤后追加「覆盖率核心阈值汇总」步骤（`if: always()`）
    - 任一 High_Coverage_Core 模块未达 90% → frontend-test job 以非零 exit code 失败，日志输出未达标项的「模块路径 | 指标名 | 实际 | 阈值 | 缺口」5 列
    - _Requirements: 2.4, 2.5, 2.6_

  - [x] 3.5 vite manualChunks vendor 拆分
    - 修改 `src/frontend/vite.config.ts` 中 `build.rollupOptions.output.manualChunks`，至少包含 5 个键（design §7）：`element-plus` / `vue-router` / `pinia` / `echarts`(含 zrender) / `monaco-editor`
    - 验证 5 个 chunk 命中规则两两不重叠（`scripts/ci/list_route_assets.mjs` 输出对照）
    - _Requirements: 7.1_

  - [x] 3.6 bundle size 强制阻塞 + PR 体积对比升级
    - 增强 `scripts/ci/check_bundle_size.sh`：entry chunk gzip ≤ 307200 字节；登录路由 `/login` 关联非 vendor JS 请求数 ≤ 4 个；越界 exit 1，输出「目标值 / 实际值 / 通过状态」三列
    - 创建 `scripts/ci/list_route_assets.mjs`：基于 vite manifest 解析指定路由关联的 JS 文件列表
    - 修改/创建 `scripts/ci/compare_bundle_size.sh`：增长比例 > 0.10 → exit 1；base 缺失输出 `bundle-size base missing, ratchet skipped`
    - 增强阻塞绕过路径：检测 `BUNDLE_SIZE_GROWTH_OVERRIDE` label 或 PR description 中 `<!--\s*bundle-size-override:\s*([^>]+?)\s*-->` 注释，且 PR 必须由 CODEOWNERS 中标注为 owner 的账户 approve（通过 `gh api` 查询）
    - 修改 `.github/workflows/ci.yml` `frontend-build` job：移除 `continue-on-error: true`（如有）使 bundle 检查步骤失败必然 fail job
    - _Requirements: 7.2, 7.3, 7.4, 7.5_

  - [x] 3.7 frontend-bundle-budget 基线文档
    - 创建 `docs/reference/frontend-bundle-budget.md`：登记当前 5 个 vendor chunk 体积、entry chunk gzip 体积、登录路由非 vendor JS 请求数；标注采集 ISO 日期与 git commit SHA
    - _Requirements: 7.6_

- [x] 4. Checkpoint - Phase 1 验证
  - 在本地基于 175 终点 commit 跑 `cd src/backend && mypy app`、`cd src/frontend && npm run test -- --run --coverage`、`cd src/frontend && npm run build && bash ../../scripts/ci/check_bundle_size.sh dist`，三项均通过。

- [x] 5. Phase 2: 前端可达性矩阵（a11y + i18n + e2e smoke）
  - [x] 5.1 安装 @axe-core/playwright + 准备认证 fixture
    - 在 `src/frontend/package.json` `devDependencies` 新增 `@axe-core/playwright`
    - 在 `src/frontend/e2e/fixtures/auth.ts` 提供 storageState fixture（一次预登录后产生 storageState 文件供其他 spec `test.use({ storageState })`）
    - _Requirements: 3.2, 3.3_

  - [x] 5.2 编写 a11y 7 页 Playwright 套件
    - 在 `src/frontend/e2e/a11y/` 目录下新建 7 个 spec：login / dashboard / ai-chat / backtests-list / backtest-detail / knowledge-base / strategies
    - 每个 spec：`AxeBuilder.withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze()`；30 秒超时；断言 `violations.filter(v => ['critical','serious'].includes(v.impact)).length === 0`；失败时 ::group:: 输出违规列表
    - _Requirements: 3.1, 3.2, 3.4_

  - [ ] 5.3 修复 7 页面 axe critical/serious 违规
    - 跑 a11y 套件，逐一处理：（a）非装饰性 `<img>` 与 icon 的 `alt`/`aria-label`；（b）表单输入显式 `<label>` 或 `aria-labelledby`；（c）颜色对比度 ≥4.5:1（正常文本）/ 3:1（大文本与图形元素）；（d）键盘焦点可见，不被 `outline:none` 抹除；（e）模态框焦点 trap + 关闭后焦点返回触发元素
    - WHERE 存在「必要豁免」（exemptions），登记到 `docs/explanation/accessibility-baseline.md`，每条引用 WCAG 条款编号，不超过 5 条
    - _Requirements: 3.4, 3.8_

  - [x] 5.4 Lighthouse a11y 阈值升级 + 覆盖 7 页面
    - 修改 `config/lighthouserc.js`：`categories:accessibility` 改为 `['error', { minScore: 0.9 }]`；`collect.url` 扩为 7 个核心页面
    - 创建 `lhci/login.js` puppeteerScript：登录后注入 token，跳转到目标 url
    - _Requirements: 3.5_

  - [x] 5.5 frontend-a11y CI job
    - 在 `.github/workflows/ci.yml` 新增 `frontend-a11y` job：构建前端 dist + 启动 vite preview + 启动后端 + Postgres service container；等待 7 页面 HTTP 200（最长 120s）；执行 `npx playwright test e2e/a11y/`
    - 失败时把违规列表（页面 URL / 规则 ID / 节点 selector / 修复建议链接）写入 `$GITHUB_STEP_SUMMARY`
    - 加入 `ci-summary` 的 `needs:` 列表与失败合并条件
    - _Requirements: 3.6, 3.7_

  - [x] 5.6 accessibility-baseline 文档
    - 创建 `docs/explanation/accessibility-baseline.md`：登记基线达成方法、Critical_Page_Set 扫描结果、必要豁免列表与 WCAG 条款编号
    - 在 `README.md` 与 `README.en.md` 索引段落中加入指向该文档的链接
    - _Requirements: 3.8_

  - [x] 5.7 i18n 覆盖率检查脚本（strict + parity 双模式）
    - 创建 `scripts/dev/check_i18n_coverage.py`：扫描 `src/frontend/src/**/*.{vue,ts}`，识别 `<template>` 文本、`<el-...>` 的 `label`/`placeholder` props、`ElMessage`/`ElMessageBox`/`ElNotification` 首参数中的中文裸串和英文长度 ≥4 裸串
    - 输出违规清单：仓库相对路径 / 行号 / 片段（≤80 字符）/ 建议 i18n key 命名（`<模块>.<页面>.<元素>` snake_case，≤80 字符）；末行 `summary: <N> violations`
    - 支持 `// i18n-ignore-next-line` 与 `<!-- i18n-ignore-next-line -->` 豁免（行号 +1，邻接 `i18n-reason: <5-120 字符>`，不满足约束的豁免无效）
    - 支持 `--strict` 与 `--check-parity` 两种模式；`--check-parity` 从 `src/frontend/src/i18n/locales/{zh-CN,en-US}/*.json` 递归点路径展开后字典序比较，输出 `only-in-zh:` / `only-in-en:` 差异块
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ] 5.8 消除中文裸串 + 补齐 zh-CN/en-US Locale_Key_Parity
    - 跑 `python scripts/dev/check_i18n_coverage.py --strict` → 把违规项接入 i18n key（按建议命名）
    - 跑 `python scripts/dev/check_i18n_coverage.py --check-parity` → 把缺失键双侧补齐
    - 全仓库豁免行数 ≤ 30 行
    - _Requirements: 4.3, 4.4_

  - [x] 5.9 frontend-lint job 接入 i18n strict + parity 检查
    - 在 `.github/workflows/ci.yml` `frontend-lint` job 末尾追加两步：`python scripts/dev/check_i18n_coverage.py --strict`、`python scripts/dev/check_i18n_coverage.py --check-parity`
    - 任一失败阻塞合入
    - _Requirements: 4.6_

  - [x] 5.10 PR 模板增加 i18n 变更清单段 + 模板校验
    - 修改 `.github/PULL_REQUEST_TEMPLATE.md` 增加「i18n 变更清单」段落（zh-CN key 数量 / en-US key 数量 / 本 PR 新增 key / 本 PR 删除 key 共 4 个子字段）
    - 创建 `scripts/ci/check_pr_template.py`：从 PR description 提取并校验 4 个子字段非占位符；缺失则失败
    - 在 `frontend-lint` 或 `ci-summary` 中接线
    - _Requirements: 4.7_

  - [x] 5.11 frontend-i18n CI job + Playwright en-us-no-zh 测试
    - 创建 `src/frontend/e2e/i18n/en-us-no-chinese.spec.ts`：对 7 个核心页面在 en-US locale 下断言 `body.innerText()` 不匹配 `[\u4e00-\u9fff]`；单页超时 30 秒
    - 在 `.github/workflows/ci.yml` 新增独立 `frontend-i18n` job：构建前端 + 启动后端 + Postgres + 等 7 页面 200 + `npx playwright test e2e/i18n/`
    - 加入 `ci-summary` 的 `needs:` 列表与失败合并条件
    - _Requirements: 4.8, 4.9, 4.10_

  - [x] 5.12 e2e/smoke 5 旅程 Playwright 套件 + seed 脚本
    - 在 `src/frontend/e2e/smoke/` 下创建 5 个 spec：auth / backtest / ai-chat / knowledge-base / strategy（design §6 表）
    - 每条 spec 写明「可观察断言」：登录 navbar 含用户名 / 详情页 `[data-test=equity-curve]` 存在 + 状态文本 `completed` / 首条 assistant 消息长度 ≥1 / `[data-test=citation-chip]` ≥1 且 href 非空 / 列表存在 name 完全匹配的行
    - 修改 `playwright.config.ts`：smoke 项目设置 `retries: 1`、`timeout: 60000`、单 worker 串行
    - 创建 `scripts/dev/seed_e2e_smoke.py`：≤30 秒注入最小种子集（≥1 测试用户、1 策略草稿、1 空白知识库）
    - _Requirements: 6.1, 6.2_

  - [x] 5.13 frontend-e2e-smoke CI job + nightly 全量扩展
    - 在 `.github/workflows/ci.yml` 新增 `frontend-e2e-smoke` job 或独立 `pr-e2e-smoke.yml`：services 接 Postgres；启动后端 uvicorn + 前端 vite preview；跑 seed_e2e_smoke.py；wait-on `/api/v1/health`（超时 60s，失败时打印末 50 行后端 stderr）；`npx playwright test e2e/smoke/`；上传 trace + video + screenshot artifact（7 天）
    - 加入 `ci-summary` 的 `needs:` 与失败合并条件
    - 修改 `.github/workflows/nightly.yml`：扩展跑完整 `e2e/`；失败时调 `scripts/ci/report_nightly_failure.sh`（用 `gh api` 查找近 7 天同标题 issue，存在则 comment 否则新建；gh api 失败 set+e + summary 输出 skip）
    - _Requirements: 6.3, 6.4, 6.5, 6.6, 6.7_

- [x] 6. Checkpoint - Phase 2 验证
  - 本地或 PR 验证：a11y / i18n / e2e-smoke 三套 job 全绿；i18n 中文裸串 0；en-US locale 测试无中文残留。

- [x] 7. Phase 3: 后端可观测性
  - [x] 7.1 OTel 业务 span 装饰器辅助
    - 创建 `src/backend/app/utils/tracing.py`：实现 `business_span(name: str, **attrs)` 上下文管理器，自动注入 `bt.*` 属性，异常路径 `set_status(StatusCode.ERROR) + record_exception()`，异常向上抛
    - 实现 no-op 模式：`OTEL_ENABLED ∈ {true,1,yes,on}` 大小写不敏感才启用；其他值走 NoOpTracerProvider，零开销
    - _Requirements: 5.1, 5.10, 5.11_

  - [x] 7.2 给 backtest 子包注入 5 phase span + 业务属性
    - 在 `src/backend/app/services/backtest/` 子包核心方法上包装 `business_span("backtrader.backtest.<phase>", user_id=..., backtest_id=...)`，phase 取值 `{create, submit, execute, collect, finalize}`
    - 必备业务属性：`bt.user_id`、`bt.backtest_id`
    - _Requirements: 5.1, 5.5_

  - [x] 7.3 给 strategy 子包注入 2 phase span
    - 在 `src/backend/app/services/strategy/` 子包策略提交、版本创建方法上注入 `backtrader.strategy.{submit, version_create}` span
    - 必备业务属性：`bt.user_id`、`bt.strategy_id`
    - _Requirements: 5.2, 5.5_

  - [x] 7.4 给 ai_trading + kb_chat 注入 3 phase span
    - 在 AI 对话 / AI 交易决策方法上注入 `backtrader.ai.{intent_parse, llm_call, response_format}` span
    - 必备业务属性：`bt.user_id`
    - _Requirements: 5.3, 5.5_

  - [x] 7.5 给 live_trading 子包注入 3 phase span
    - 在实盘下单 / 撤单 / 成交回报路径上注入 `backtrader.live.{place_order, cancel_order, on_fill}` span
    - 必备业务属性：`bt.user_id`、`bt.symbol`、`bt.order_id`
    - _Requirements: 5.4, 5.5_

  - [x] 7.6 docker compose dev observability profile + Jaeger
    - 修改 `docker/compose/dev.yml`：以 `profiles: [observability]` 形式新增 Jaeger all-in-one（image `jaegertracing/all-in-one:1.55+`），暴露 4317 / 4318 / 16686，不影响默认 `up`
    - 默认 service 列表保持不变；用户通过 `--profile observability` 才启动 Jaeger
    - _Requirements: 5.7_

  - [x] 7.7 OTel e2e 测试 + 性能基准对比
    - 创建 `src/backend/tests/test_telemetry_e2e.py`：≥6 用例，分别覆盖 backtest 5 phase / strategy 2 phase / ai 3 phase / live 3 phase 全部产生 span、business attributes 注入正确（含 `bt.user_id` 与 `bt.backtest_id`）、collector unreachable 时不抛异常仅 WARNING；用 `InMemorySpanExporter` 替代 OTLP exporter，并断言 span `end_time is not None`
    - 性能基准：在同一机器、同一 commit 上 `OTEL_ENABLED=true/false` 各跑 ≥30 次 `pytest -m benchmark tests/perf/test_backtest_throughput.py`，验证 P95 增长比例 ≤ 5%；如基准缺失，降级为 PR description 附手动对比表
    - _Requirements: 5.6, 5.8, 5.9_

- [x] 8. Checkpoint - Phase 3 验证
  - `pytest tests/test_telemetry_e2e.py` 全绿；启动 docker compose `--profile observability` 后能在 Jaeger UI 看到 `backtrader.backtest.create` 为根的完整 trace（≥4 个非根 span）。

- [x] 9. Phase 4: 守护与工具化
  - [x] 9.1 ORM ↔ schema drift 检查脚本
    - 创建 `scripts/ci/check_orm_schema_drift.py`：流程见 design §8（一次性 SQLite + alembic upgrade head + Base.metadata vs reflect 对比）；对比维度：表 / 列 / 列类型类别（粗粒度）/ 索引（按 `name + sorted col tuple`）/ 外键（按 `源表.源列 → 目标表.目标列`）；忽略 `String/Text` 长度差异；忽略 `server_default` 字面差异
    - exit 0 + `OK: schema aligned`（对齐）/ exit 1 + markdown 表格（差异）/ exit 2 + stderr（脚本失败）
    - 整体执行 ≤ 120 秒
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 9.2 check-migrations job 接入 drift check
    - 修改 `.github/workflows/ci.yml` `check-migrations` job：在现有 `alembic upgrade head` + `alembic check` 之后追加 `python scripts/ci/check_orm_schema_drift.py`，失败阻塞合入
    - _Requirements: 8.5_

  - [x] 9.3 migration safety 静态扫描脚本
    - 创建 `scripts/ci/check_migration_safety.py`：通过 `git diff --name-only --diff-filter=AM origin/<base>...HEAD` 限定本 PR 变更的 `src/backend/alembic/versions/*.py` 文件
    - AST 静态识别：（a）`op.add_column` `nullable=False` 且无 `server_default`；（b）`op.drop_column` / `op.drop_table`；（c）`op.alter_column` 含 `type_=`；（d）`op.create_index` 未指定 `postgresql_concurrently=True`（PG 方言下）
    - 输出 `::warning file=<path>,line=<n>::<message>` + `$GITHUB_STEP_SUMMARY` markdown 段落（迁移文件 / 行号 / 危险操作 / 风险描述 / 推荐写法 5 列）；exit 0（不阻塞）
    - 同时检查文件前 20 行内是否有 `# alembic-meta: estimated_rows=<N>; lock_kind=<short|long>` 注释；缺失或格式不合法则同格式 warning
    - _Requirements: 8.6, 8.7, 8.8_

  - [x] 9.4 database-migration-playbook 文档
    - 增补 `docs/how-to/database-migration-playbook.md` 「长锁/全表扫描风险与降级策略」节，4 个子小节（design §8）：危险操作识别速查 / PG 推荐写法（含 `SET lock_timeout`、`CONCURRENTLY`、分批回填三种代码示例）/ safety check 输出解读 / PR review 必看清单（≥5 条）
    - _Requirements: 8.9_

  - [x] 9.5 uv workspace 顶层声明 + 入口命令
    - 在仓库根目录 `pyproject.toml` 中加入 `[tool.uv.workspace]` 节，`members = ["src/backend", "src/bt_api_py"]`
    - 创建 `scripts/dev/check_all.sh`：1800 秒 timeout 包装；按 fail-fast 在两个成员包内顺序执行 `ruff check` / `ruff format --check` / `mypy <严格作用域>` / `pytest -m "not e2e"`；任一步 fail 立即非 0 退出，stderr 含失败步骤名 + 成员包名
    - 创建 `scripts/dev/extract_mypy_scope.py`：从成员包 `pyproject.toml` 提取已声明的 mypy 严格作用域路径，未声明则覆盖该成员包的 `app/` 或顶层包目录
    - 创建 `Makefile` 或等价 wrapper：`check-all` 目标调用 `scripts/dev/check_all.sh`
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 9.6 workspace lock 冲突检测
    - 创建 `scripts/dev/check_workspace_lock_conflict.py`：解析根 `uv.lock`（`uv sync --workspace` 后产物）与 `config/requirements-dev.lock`，按包名匹配版本字符串；不一致 stderr 输出 `<package> workspace=<v1> lock=<v2>` 并 exit 1
    - _Requirements: 9.4, 9.5_

  - [x] 9.7 monorepo-check advisory CI job
    - 在 `.github/workflows/ci.yml` 新增 `monorepo-check` job：调用 `bash scripts/dev/check_all.sh`；步骤上 `continue-on-error: true`
    - 在 `ci-summary` 中追加：`if: needs.monorepo-check.result == 'failure'` → echo `⚠️ monorepo-check failed (advisory only)` >> `$GITHUB_STEP_SUMMARY`；不进入失败合并条件
    - _Requirements: 9.6_

  - [x] 9.8 CONTRIBUTING.md 依赖管理节扩展
    - 在 `CONTRIBUTING.md` 「依赖管理」节末追加 ≥3 个子条目：（a）开发期间何时使用 workspace、何时使用单包；（b）如何新增第三个成员包；（c）锁文件如何与 workspace 协同生成
    - _Requirements: 9.7_

  - [x] 9.9 python-monorepo 选型说明文档
    - 创建 `docs/explanation/python-monorepo.md`：3 个命名小节（design §9）——工具选型（uv vs hatch vs pdm 对比表）/ 对 vendored 包的处理（`src/clientportal.gw` 不进入 workspace 成员）/ 与 174 §A6 边界一致性
    - _Requirements: 9.1, 9.8_

  - [x] 9.10 （可选）前端 500-999 行 .vue 收尾（**整体降级 §11.5**：175 不做；候选清单与决议登记在 PROGRESS.md / REFACTORING_BACKLOG.md § G）
    - 在 175 启动后第 2 周末（`D175_start + 14`）执行 `find src/frontend/src -type f -name '*.vue' | xargs wc -l | awk '$1>=500 && $1<1000'`，把命中文件按行数降序登记到 `docs/iterations/迭代175-质量加固与可观测性纵深/PROGRESS.md` §11 表（「ID | 文件 | 当前行数 | 目标拆分子组件 | 工作量 (S/M/L) | 状态」6 列）
    - 按从大到小顺序串行拆分；至少消化前 5 个最大文件（原文件行数 < 500 且新建子组件已合入主分支）
    - 剩余项写入 `docs/REFACTORING_BACKLOG.md` 标注 「175 顺延」
    - WHERE 启动评审一致认为容量不足，本任务可整体降级为「175 不做」，评审纪要中显式记录决议
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [ ] 10. Final Checkpoint - 全部验证
  - 全部 11 项需求对应 SLO 全绿（mypy services / 覆盖率 / a11y / i18n / OTel / e2e smoke / bundle size / DB drift / monorepo / 173B 处置 / 可选 .vue 收尾）；所有新增 / 修改的 CI job 均已并入 `ci-summary`（advisory 项除外）；175 retrospective 文档准备就绪。

## Notes

- Phase 0（173B 处置）必须在所有其他 phase 之前完成；如有「纳入 175」项则需先把对应 EARS 子需求并入 `requirements.md`。
- Phase 1 三条任务链（mypy / 覆盖率 / bundle）相互独立，可并行。
- Phase 2 三套 Playwright（a11y / i18n / e2e smoke）共享 fixtures/auth.ts；建议先做 fixture（5.1）再并行三套。
- Phase 3 OTel 改动按服务子包并行（7.2 / 7.3 / 7.4 / 7.5），完成后再统一接 docker observability profile（7.6）与测试（7.7）。
- Phase 4 中 9.5 → 9.6 → 9.7 → 9.8 → 9.9 串行；9.1-9.4（DB 守护）独立；9.10 可选。
- 对外不破坏：API path、CI 已有 job 名、CODEOWNERS 路径继承 174 不动。
- 任何降级路径（如 mypy 子包不达标、覆盖率 perFile 键不支持、OTel 性能基准缺失）均需在 PR description 中显式登记并由项目所有者批准。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["3.1", "3.3", "3.5", "3.7"] },
    { "id": 2, "tasks": ["3.2", "3.4", "3.6"] },
    { "id": 3, "tasks": ["5.1", "5.7"] },
    { "id": 4, "tasks": ["5.2", "5.4", "5.6", "5.8", "5.10", "5.12"] },
    { "id": 5, "tasks": ["5.3", "5.5", "5.9", "5.11", "5.13"] },
    { "id": 6, "tasks": ["7.1"] },
    { "id": 7, "tasks": ["7.2", "7.3", "7.4", "7.5", "7.6"] },
    { "id": 8, "tasks": ["7.7"] },
    { "id": 9, "tasks": ["9.1", "9.3", "9.5", "9.10"] },
    { "id": 10, "tasks": ["9.2", "9.4", "9.6", "9.8", "9.9"] },
    { "id": 11, "tasks": ["9.7"] }
  ]
}
```
