# 迭代 175 - 质量加固与可观测性纵深

> **文档状态**：实施中（脚手架已就绪，内容补齐由团队按 PR 推进）
> **创建日期**：2026-05-28
> **前置基线**：迭代 174「结构精简与工程债接续」承诺范围内不重做
> **核心目标**：在不引入新功能的前提下，把 11 个独立的"质量门"建成 CI 上可阻塞回归的基础设施
> **执行节奏**：脚手架（CI job、脚本、配置）一次会话内完成；内容补齐（修 a11y、补单测、消灭裸字符串、织入 OTel span）由团队后续 PR 逐个收口

---

## 关联文档

- **Spec**：`/.kiro/specs/iteration-175/`（requirements.md / design.md / tasks.md）
- **进度**：`./PROGRESS.md`
- **173B 处置**：`./173B_disposition.md`
- **A11y 基线**：`/docs/explanation/accessibility-baseline.md`
- **Bundle budget**：`/docs/reference/frontend-bundle-budget.md`
- **DB migration playbook**：`/docs/how-to/database-migration-playbook.md`
- **Python monorepo**：`/docs/explanation/python-monorepo.md`

---

## 175 实际交付总览

### 11 条质量门，全部建立 CI 入口

| # | 质量门 | CI Job | 类型 | 实际状态 |
|---|---|---|---|---|
| 1 | mypy services 严格扩盘 | `backend-mypy-services` | 阻塞 | ✅ 3 子包扩盘（optimization / log_parser / ai_trading） |
| 2 | 前端覆盖率三级棘轮 60→75 | `frontend-test` (强化) | 阻塞 | ✅ 阈值已升 + High_Coverage_Core 8 模块阈值 90 |
| 3 | A11y 基线 WCAG 2.1 AA | `frontend-a11y` (新) | 阻塞 | ✅ 框架就绪 + 7 页 spec |
| 4 | i18n 100%（zh-CN/en-US） | `frontend-i18n` (新) | parity 阻塞 / strict advisory | ✅ parity 已 100%；strict baseline 15553 顺延 |
| 5 | OTel 全链路追踪 | `pytest test_telemetry_e2e` | 阻塞 | ✅ 装饰器 + backtest 5 phase + 8 测试 |
| 6 | E2E_Smoke 上 CI | `frontend-e2e-smoke` (新) | 阻塞 | ✅ 5 旅程 + Postgres service container |
| 7 | Bundle Size Ratchet | `frontend-build` (强化) | 阻塞 | ✅ entry≤300KB + vendor 5 chunk + 10% 阻塞 |
| 8 | DB drift + safety | `check-migrations` (强化) | drift 阻塞 / safety advisory | ✅ 两脚本 + playbook |
| 9 | uv workspace 工具化 | `monorepo-check` (新) | advisory | ✅ check_all.sh + workspace lock conflict |
| 10 | 173B 处置 | 文件存在性检查 | 必备 | ✅ T2/T7/T10 全顺延 176 |
| 11 | （可选）.vue 收尾 | n/a | 可选 | ⏭️ 175 不做 |

### 为什么有些项是「⏭️ 顺延」而不是「✅ 完成」？

175 真实包含两类工作：

1. **基础设施类**（CI job、脚本、配置、文档）—— 一次会话内可全部建立。这部分 175 全部完成 ✅。
2. **内容补齐类**（修 a11y 违规、消灭 15553 处中文裸字符串、给 6 个 services 子包补类型注解、给 strategy/ai/live 织入 OTel span）—— 这是工程团队按 PR 持续推进的工作量级（多周乃至数月）。

175 的**正确成功标准**是：**所有 11 个质量门都建立了 CI 上可见、可阻塞回归的入口**，让"内容补齐"工作进入"被持续度量"的状态——而不是把所有质量缺口在一次迭代内修光。这与 §1.7 「降级路径 + 顺延 176」、§4 「i18n 长尾顺延」、§5 「业务方法侧 span 织入按子包推进」三处的设计意图一致。

详细的 SLO 当前数字、已知尾巴、剩余动作清单见 `./PROGRESS.md`。

---

## 关键产物索引

### 新增/修改的 CI workflow

- `.github/workflows/ci.yml`：新增 `backend-mypy-services` / `frontend-a11y` / `frontend-i18n` / `frontend-e2e-smoke` / `monorepo-check`；强化 `frontend-test` / `frontend-build` / `check-migrations`；扩展 `lighthouse-ci` 阈值至 0.9；ci-summary 接入全部新 jobs
- `.github/PULL_REQUEST_TEMPLATE.md`：i18n 变更清单段落

### 新增脚本

- `scripts/ci/check_173b_disposition_consistency.py`
- `scripts/ci/check_orm_schema_drift.py`
- `scripts/ci/check_migration_safety.py`
- `scripts/ci/check_pr_template.py`
- `scripts/ci/list_route_assets.mjs`
- `scripts/ci/compare_bundle_size.sh`
- `scripts/ci/report_nightly_failure.sh`
- `scripts/ci/check_bundle_size.sh`（升级到 175 §7 硬阈值版本）
- `scripts/dev/check_all.sh`（uv workspace 单一入口）
- `scripts/dev/check_i18n_coverage.py`
- `scripts/dev/check_workspace_lock_conflict.py`
- `scripts/dev/coverage_core_summary.mjs`
- `scripts/dev/seed_e2e_smoke.py`
- `lhci/login.js`（Lighthouse puppeteerScript）

### 新增/修改配置

- 根 `pyproject.toml`（uv workspace 声明）
- 根 `Makefile`（check-all / workspace-lock-check / i18n-check 等便捷目标）
- `src/backend/pyproject.toml`：mypy 严格作用域扩 3 子包
- `src/frontend/vitest.config.ts`：覆盖率阈值 60→75 + 8 模块阈值 90
- `src/frontend/vite.config.ts`：5-vendor manualChunks
- `src/frontend/package.json`：`@axe-core/playwright` devDep
- `config/lighthouserc.js`：a11y 阈值 0.8→0.9 + 7 个核心页面
- `docker/compose/dev.yml`：Jaeger observability profile

### 新增源代码

- `src/backend/app/utils/tracing.py`（business_span 装饰器，no-op 模式）
- `src/backend/tests/test_telemetry_e2e.py`（8 用例，全绿）
- `src/backend/app/services/optimization/__init__.py` / `log_parser/__init__.py` / `ai_trading/__init__.py`：any-source 登记
- `src/backend/app/services/backtest/manager.py` / `runner.py`：backtest 5 phase span 织入
- `src/frontend/e2e/a11y/_template.spec.ts` / `login.spec.ts` / `critical_pages.spec.ts`
- `src/frontend/e2e/i18n/en-us-no-chinese.spec.ts`
- `src/frontend/e2e/smoke-175/journeys.spec.ts`
- `src/frontend/src/__tests__/coverage_core.md`

### 新增文档

- `docs/iterations/迭代175-质量加固与可观测性纵深/index.md`（本文）
- `docs/iterations/迭代175-质量加固与可观测性纵深/PROGRESS.md`
- `docs/iterations/迭代175-质量加固与可观测性纵深/173B_disposition.md`
- `docs/explanation/accessibility-baseline.md`
- `docs/explanation/python-monorepo.md`
- `docs/reference/frontend-bundle-budget.md`
- `docs/how-to/database-migration-playbook.md`

---

## 175 启动后第一条建议路径（团队侧）

按风险与影响优先级，建议团队接续推进的顺序：

1. **W1**：让 CI 跑一次 PR 检查 175 的所有新 job 是否真的能起来；逐一修复任何配置问题（环境变量、依赖缺失、permission）
2. **W2-W4**：补充前端单测把覆盖率从当前推到 75 / 90；同步在每个 PR 中修 a11y 违规（按 7 页轮转）
3. **W3-W6**：消灭中文裸字符串（按 views/ → components/ → composables/ 顺序，每周降低 baseline）
4. **W4-W6**：给 strategy / ai / live 三个命名空间织入 OTel span（按子包独立 PR）
5. **持续**：mypy 扩盘到剩余 6 个 services 子包（每周一个 PR）

---

## 与 174 / 176 的边界

- **不重做 174**：根目录精简、API/Service 子包化、前端 ≥1000 行 .vue 拆分、docs/ Diátaxis、设计系统 v0.2、Prompt 治理、覆盖率二级棘轮 45→60、Docker Hub 自动化 —— 全部由 174 承接，175 不动。
- **顺延到 176**：mypy 6 子包扩盘 / 173B T2/T7/T10 / 中文裸串清理 / strategy+ai+live OTel 织入 / OTel 性能基准 / .vue 500-999 收尾 / OTel metrics+logs / e2e 全套 PR-blocking / bundle ratchet 250KB / 国际化第三语言。
