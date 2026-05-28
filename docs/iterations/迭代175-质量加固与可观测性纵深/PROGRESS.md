# 迭代 175 · 进度跟踪

> 关联计划：`/.kiro/specs/iteration-175/`（requirements.md / design.md / tasks.md）
> 启动 commit：`51efc51e`
> 跟踪粒度：到任务卡 ID
> 更新约定：每次有任务卡状态变化时更新此文件

---

## 状态图例

- ✅ 已完成（CI/本地验证通过）
- 🟡 进行中（已开工，未合）
- ⚪ 未开始
- ⏭️ 本轮不做（降级或顺延）

---

## Phase 0 · 173B 处置

| ID | 任务 | 状态 | 备注 |
|---|---|---|---|
| 1.1 | 173B disposition.md + 一致性检查脚本 | ✅ | T2/T7/T10 全部决议为「顺延 176」；脚本 `scripts/ci/check_173b_disposition_consistency.py`；本地校验 OK |

---

## Phase 1 · 独立基线扩盘

### Task 3.1 · mypy services 扩盘

| 子包 | 175 起点错误数 | 175 实际状态 | 备注 |
|---|---:|---|---|
| `app.services.optimization` | 3 | ✅ 已扩盘（fix 1 处 narrowing） | `app/services/optimization/task_gateway.py` |
| `app.services.log_parser` | 0 | ✅ 已扩盘（zero-cost） | |
| `app.services.ai_trading` | 0 | ✅ 已扩盘（zero-cost） | |
| `app.services.gateway` | 29 | ⏭️ 顺延 176 | 需补类型注解；超 175 容量 |
| `app.services.akshare` | 49 | ⏭️ 顺延 176 | 同上 |
| `app.services.strategy` | 56 | ⏭️ 顺延 176 | SQLAlchemy `Column[T]` vs `T` 类型分歧大量出现 |
| `app.services.backtest` | 57 | ⏭️ 顺延 176 | 同上 |
| `app.services.live_trading` | 56 | ⏭️ 顺延 176 | 同上 |
| `app.services.workspace` | 88 | ⏭️ 顺延 176 | 错误数最多；最值得拿一个独立 sprint |

**已扩盘子包数：3** —— 不达 §1.7 的 ≥7 阈值；按 §1.7 降级路径，未扩盘的 6 个子包写入「176 候选」。175 验收报告需登记本节降级理由，并在 PR description 中显式列出。

#### 已知尾巴（Any 来源登记）

按 §1.5 限制 ≤5 类/子包：

```
app.services.optimization:
  - any-source: backtrader-runtime
  - any-source: dict-tasks
  - any-source: callback-injection

app.services.log_parser:
  - any-source: pandas-frames
  - any-source: heterogeneous-rows

app.services.ai_trading:
  - any-source: llm-payloads
  - any-source: order-context
```

### Task 3.2 · backend-mypy-services CI job

✅ 在 `.github/workflows/ci.yml` 新增独立 `backend-mypy-services` job；已加入 `backend-test` 的 needs 与 `ci-summary` 的 needs / 失败合并条件。

### Task 3.3-3.4 · 前端覆盖率三级棘轮 + High_Coverage_Core

| 项 | 状态 |
|---|---|
| `vitest.config.ts` 全局 lines/functions/branches/statements → 75 | ✅ |
| 8 个 High_Coverage_Core 模块阈值 → 90 | ✅ |
| `coverage_core.md` 登记清单 | ✅ |
| `coverage_core_summary.mjs` summary 脚本 | ✅ |
| `frontend-test` job 接入 summary 步骤 | ✅ |

> ⚠️ 当前前端总体覆盖率距离 75% 仍有差距。175 设置目标阈值后，CI 将开始报红，团队需在每个 PR 中逐步补齐单测直至全绿。这是 §2 「ratchet」语义的预期工作流——175 把门禁建好，内容由后续 PR 补齐。

### Task 3.5-3.7 · vendor split + bundle size + baseline

| 项 | 状态 |
|---|---|
| `vite.config.ts` manualChunks 5 vendor split | ✅ |
| `scripts/ci/check_bundle_size.sh` 升级到 175 §7 硬阈值 | ✅ |
| `scripts/ci/list_route_assets.mjs` 路由资产解析 | ✅ |
| `scripts/ci/compare_bundle_size.sh` PR 阻塞版本 | ✅ |
| `frontend-build` job 调用阻塞 compare | ✅ |
| `docs/reference/frontend-bundle-budget.md` 基线文档 | ✅ (体积数字待首次 CI 跑后回填) |

> 📌 「待回填」：基线文档中的体积表格条目当前是 `_tbd_`，需要 CI 上完成一次 `npm run build` 后用真实数值更新——见文档底部的「How to refresh the baseline」段。

---

## Phase 2 · A11y / i18n / E2E_Smoke

### Task 5.1-5.6 · A11y 套件

| 项 | 状态 |
|---|---|
| `@axe-core/playwright` 加入 devDependencies | ✅ |
| `e2e/a11y/` 目录与 7 个核心页面 spec | ✅ (login + critical_pages.spec 覆盖全部 7 页) |
| Lighthouse a11y 阈值 0.8 → 0.9 | ✅ |
| `config/lighthouserc.js` collect.url 扩展为 7 页 | ✅ |
| `lhci/login.js` puppeteerScript | ✅ |
| `frontend-a11y` CI job 落地 | ✅ |
| `accessibility-baseline.md` 文档 | ✅ |

> ⚠️ 本轮只搭建了 a11y CI 框架，**实际违规修复**会在 frontend-a11y job 首次跑红时由团队推进。175 验收要求是「7 页 0 critical/serious」；进度由后续 PR 单独跟踪。

### Task 5.7-5.11 · i18n

| 项 | 状态 |
|---|---|
| `scripts/dev/check_i18n_coverage.py` (strict + check-parity) | ✅ |
| 本地试跑 parity → 0 violations (zh-CN/en-US 各 181 keys) | ✅ |
| 本地试跑 strict → 15553 violations | 🟡 baseline 已记 |
| `frontend-i18n` CI job (parity 阻塞 / strict advisory) | ✅ |
| `e2e/i18n/en-us-no-chinese.spec.ts` Playwright 测试 | ✅ |
| 中文裸串清理 | ⏭️ **顺延** —— 15553 处违规超 175 容量；advisory 模式提示，团队按模块逐步消化 |

#### i18n 尾巴清单（顺延规模）

- 15553 中文裸字符串（advisory only），按目录优先级清理建议：
  - `views/` （高优先级，用户直接看到）
  - `components/` （次高）
  - `composables/` （低，多为日志/调试）
- 每完成一批清理，将 `scripts/dev/check_i18n_coverage_baseline.json` 中的 `baseline_violations` 字段更新为新数字
- 当 `baseline_violations = 0` 时，把 CI 中 strict 步骤的 `continue-on-error: true` 移除（即翻成阻塞门）

### Task 5.10 · PR 模板 + 模板检查

| 项 | 状态 |
|---|---|
| `.github/PULL_REQUEST_TEMPLATE.md` 含 i18n 变更清单段 | ✅ |
| `scripts/ci/check_pr_template.py` 校验 4 子字段 | ✅ |

> 📌 此脚本已就绪，但**尚未接入** `frontend-lint` 或 `ci-summary` job。建议在团队适应模板填写后再纳入阻塞门。

### Task 5.12-5.13 · E2E_Smoke

| 项 | 状态 |
|---|---|
| `e2e/smoke-175/journeys.spec.ts` 5 旅程 | ✅ |
| `scripts/dev/seed_e2e_smoke.py` 种子脚本 | ✅ |
| `frontend-e2e-smoke` CI job (含 Postgres service container) | ✅ |
| `nightly.yml` 扩展跑完整 e2e | ⏭️ 175 已建 `scripts/ci/report_nightly_failure.sh`；nightly.yml 内的实际接入留给团队 |
| `scripts/ci/report_nightly_failure.sh` 失败 issue 自动化 | ✅ |

---

## Phase 3 · 后端 OpenTelemetry 全链路

### Task 7.1 · `business_span` 装饰器

✅ `src/backend/app/utils/tracing.py`：
- 4 个命名空间矩阵（backtest / strategy / ai / live）
- 异常路径 ERROR + record_exception 后再抛
- `OTEL_ENABLED` 真值集合校验后才启用；no-op 模式真零开销

### Task 7.2-7.5 · 4 类业务流程 span 织入

| 命名空间 | phase 集合 | 织入状态 |
|---|---|---|
| `backtrader.backtest.*` | create / submit / execute / collect / finalize | ✅ 5 个 phase 全部织入（`backtest/manager.py` + `backtest/runner.py`） |
| `backtrader.strategy.*` | submit / version_create | ✅ 2 个 phase 织入（`strategy/core.create_strategy` + `strategy/version.create_version`） |
| `backtrader.ai.*` | intent_parse / llm_call / response_format | ✅ 3 个 phase 织入（`trading_intent_parser.parse_trading_intent` / `_call_llm` / `_extract_json` 包装） |
| `backtrader.live.*` | place_order / cancel_order / on_fill | ✅ 3 个 phase 织入（`paper_trading_service.submit_order` / `cancel_order` / `_fill_order`） |

> 📌 175 §5.6 验收要求：「在 5 分钟内收到 backtest 5 phase span tree」——所有 4 类命名空间的 phase span 已在服务子包中织入完毕，本地 `pytest tests/test_telemetry_e2e.py` 仍 8/8 通过。生产环境 trace 验证由首次部署后人工核查，写入 RETROSPECTIVE.md。

### Task 7.6 · docker compose observability profile

✅ `docker/compose/dev.yml` 已加入 Jaeger all-in-one (image 1.55)，`profiles: [observability]`；端口 4317/4318/16686。

### Task 7.7 · OTel e2e 测试 + 性能基准

| 项 | 状态 |
|---|---|
| `tests/test_telemetry_e2e.py` 8 用例 | ✅ 8/8 本地通过 |
| 性能基准 P95 ≤ 5% 增长 | ⏭️ 顺延（需 `tests/perf/test_backtest_throughput.py` 等同基准存在；175 不强制） |

---

## Phase 4 · 守护与工具化

### Task 9.1-9.4 · DB 迁移守护

| 项 | 状态 |
|---|---|
| `scripts/ci/check_orm_schema_drift.py` (硬阻塞) | ✅ |
| `scripts/ci/check_migration_safety.py` (advisory + warning) | ✅ |
| `check-migrations` job 接入两个脚本 | ✅ |
| `docs/how-to/database-migration-playbook.md` (4 子小节，PR review 清单 6 条) | ✅ |

### Task 9.5-9.9 · uv workspace 工具化

| 项 | 状态 |
|---|---|
| 根 `pyproject.toml` `[tool.uv.workspace]` 声明 | ✅ |
| `scripts/dev/check_all.sh` 单一入口（fail-fast + 1800s timeout） | ✅ |
| `scripts/dev/check_workspace_lock_conflict.py` | ✅ |
| `Makefile` 包装：`make check-all` / `make workspace-lock-check` 等 | ✅ |
| `monorepo-check` advisory CI job | ✅ |
| `CONTRIBUTING.md` 「Dependency Management」节扩展（含 3 子条目） | ✅ |
| `docs/explanation/python-monorepo.md` (3 命名小节) | ✅ |

### Task 9.10 · （可选）500-999 行 .vue 收尾

⏭️ **本轮不做**（§11.5 整体降级）。

#### 175-close 时的扫描结果（2026-05-28）

按 `find src/frontend/src -type f -name '*.vue' | xargs wc -l | awk '$1>=500 && $1<1000'` 得到的 10 个候选文件（行数降序）：

| 行数 | 文件 | 拟拆分子组件方向（建议） | 工作量 (S/M/L) |
|---:|---|---|:---:|
| 860 | `views/AITradingPage.vue` | confirm dialog / history table / context panel | M |
| 851 | `views/data/DataSyncPage.vue` | sync table / config panel / progress card | M |
| 831 | `components/workspace/TradingWorkspaceUnitsTab.vue` | unit row / param dialog / status bar | L |
| 715 | `views/KnowledgeBaseDocumentPage.vue` | citation panel / outline tree / chunk list | M |
| 680 | `views/StrategyPage.vue` | template gallery / form / ai draft section | M |
| 642 | `views/data/DataScriptsPage.vue` | script list / editor pane / upload dialog | M |
| 604 | `views/data/DataInterfacesPage.vue` | tree / form / preview pane | M |
| 599 | `views/PortfolioPage.vue` | summary card / position table / trade history | S |
| 564 | `components/workspace/CreateUnitDialog.vue` | params section / data source section | S |
| 541 | `views/data/DataTasksPage.vue` | task table / filter bar / detail drawer | S |

#### 决议

按 §11.5 的降级路径：

> WHERE 启动评审一致认为容量不足，本任务可整体降级为「175 不做」，评审纪要中显式记录决议。

**评审决议（@yunjinqi，2026-05-28）**：175 主线已饱和（mypy services / 覆盖率 60→75 / a11y / i18n / OTel 4 命名空间织入 / e2e smoke / bundle ratchet / DB 守护 / monorepo），无容量消化 ≥5 个 .vue 切片。本任务整体顺延 176，候选文件清单已写入 `docs/explanation/REFACTORING_BACKLOG.md` 「176 候选 § G」。

#### 顺延依据

1. 174 主线 C 把 ≥1000 行 .vue 全部清理后，500-999 区间是「第二批」工程债，与 175 的「质量加固」横切关注点正交。
2. 每个 .vue 拆分都要重新走完整测试矩阵（vitest unit + e2e smoke + 视觉回归），单 PR 容量消耗大。
3. 175 §11.5 显式标注本任务可整体降级为「175 不做」。

---

## SLO 当前数字

| 维度 | 175 目标 | 当前 | 差距 / 备注 |
|---|---|---|---|
| `backend-mypy-services` 通过子包数 | ≥7 | **3** (optimization / log_parser / ai_trading) | 175 §1.7 降级；6 个子包顺延 176 |
| `mypy app` 整体新增错误 | 0 | **−3** (净降低) | ✅ |
| 前端全局覆盖率 | ≥75% | 待首次 CI 跑出 | 阈值已设定，团队补单测 |
| 前端 High_Coverage_Core 8 模块 ≥90% | 是 | 待首次 CI 跑出 | 同上 |
| Critical_Page_Set 7 页 axe 0 critical/serious | 是 | 待首次 frontend-a11y 跑出 | CI 已建 |
| Lighthouse a11y | ≥0.9 | 阈值已升 | |
| zh-CN/en-US Locale_Key_Parity | 100% | **✅ 0 violations (181 keys 各)** | |
| 中文裸串数 | 0 (long-term) | **15553** (baseline) | 顺延 176+，advisory only |
| OTel 业务命名空间覆盖 | 4 类 × phase 集合全 | ✅ 4/4 命名空间均已织入：backtest 5/5；strategy 2/2；ai 3/3；live 3/3 | |
| `test_telemetry_e2e.py` 通过率 | 100% | **8/8 ✅** | |
| Bundle entry chunk gzip | ≤300KB | 待首次 CI 跑出 | vendor split 已建立 |
| `check_orm_schema_drift.py` 0 diff | 是 | 待 CI 跑出 | 脚本已落地 |
| 173B disposition consistency | OK | **✅** | |

---

## 175 关闭前剩余动作

1. CI 上跑通一次完整 pipeline，回填 `frontend-bundle-budget.md` 中的体积数字。
2. 为 `frontend-test` job 准备一个团队过渡窗口（覆盖率从 60 升到 75 的过程中预期会出现一段红线期）。
3. 当中文裸串清理至 0 时，把 `frontend-i18n` strict 步骤的 `continue-on-error` 移除。
4. ~~把 OTel span 织入推进到 strategy / ai / live 三个命名空间~~ ✅ 已完成（4/4 命名空间 + 13 个 phase span）
5. 175 retrospective 文档归档至 `docs/iterations/迭代175-质量加固与可观测性纵深/RETROSPECTIVE.md`，并把「176 候选」清单写入 `docs/REFACTORING_BACKLOG.md`。

---

## 时间线（实际）

- W1（启动）：Phase 0 + Phase 1 全部脚手架就绪（mypy/coverage/bundle/vendor split）
- W1：Phase 2 a11y/i18n/e2e-smoke 全部 CI job + 套件骨架就绪
- W1：Phase 3 OTel 装饰器 + backtest 5 phase 织入 + 8 测试 + Jaeger profile
- W1：Phase 4 DB 守护 + uv workspace 工具化 + 文档全部就绪
- 后续：a11y 修复 / 中文裸串清理 / mypy 6 子包扩盘 / 前端覆盖率补齐由团队按 PR 推进
