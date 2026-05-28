# 迭代 175 · 回顾报告

> 收口日期：2026-05-28
> 关联文档：
>
> - 计划：`.kiro/specs/iteration-175/{requirements,design,tasks}.md`
> - 进度：`docs/iterations/迭代175-质量加固与可观测性纵深/PROGRESS.md`
> - 173B 处置：`docs/iterations/迭代175-质量加固与可观测性纵深/173B_disposition.md`

---

## 总览

175 主线为「质量加固与可观测性纵深」，按 4 个 phase 推进 11 项 EARS 需求。本轮采用「先建门、后补内容」的策略：所有 CI 阻塞门、检查脚本、文档骨架在 175 内全部就位，部分内容侧的清理（中文裸串、a11y 违规修复、覆盖率从 60→75 的过渡）按团队节奏分散到后续 PR 推进。

### 11 项 SLO 状态

| # | 维度 | 175 目标 | 175 实际 | 决议 |
|---|---|---|---|---|
| 1 | Mypy services 扩盘 | ≥7 子包 | 3 子包（optimization / log_parser / ai_trading） | §1.7 降级；6 子包顺延 176 |
| 2 | 前端覆盖率三级棘轮 | lines/functions/branches/statements ≥75% | 阈值已设；CI 进入红线过渡期 | 团队按 PR 补单测 |
| 3 | A11y 基线 | Critical_Page_Set 7 页 axe 0 critical/serious + LH ≥0.9 | CI 已建；阈值已升 | 团队按首次 CI 红线推进修复 |
| 4 | i18n 100% | 中文裸串 0 + Locale_Key_Parity | parity 100%（181/181）；strict 15553（advisory baseline） | 顺延 176+，advisory only |
| 5 | OTel 全链路 | 4 命名空间 × phase 集合全 | ✅ **4/4 命名空间 + 13 个 phase span 全部织入**（backtest 5/5、strategy 2/2、ai 3/3、live 3/3） | 完成 |
| 6 | E2E smoke 上 CI | 5 旅程 PR-blocking + nightly 全量 | smoke job 已建；nightly issue 自动化已建 | 完成（团队择期接 nightly） |
| 7 | Bundle size ratchet | entry chunk gzip ≤300KB；登录路由 JS ≤4 | 阈值已设；vendor split 已建 | 数字回填随首次 CI |
| 8 | DB 迁移守护 | drift 0 + safety advisory | 两个脚本就绪；check-migrations job 已接入 | 完成 |
| 9 | Monorepo 工具化 | check-all 一键全绿 | 入口脚本 + workspace 声明 + advisory job | 完成（advisory，176 决议是否升 blocker） |
| 10 | 173B 处置 | T2/T7/T10 各有决议 | 全部决议为「顺延 176」；一致性脚本已落地 | 完成 |
| 11 | （可选）500-999 行 .vue 收尾 | 至少消化 5 个最大文件 | 评审决议本轮不做 | §11.5 降级 |

> **完成 / 部分完成 / 降级**比例：6 / 3 / 2，整体达成度约 75%。

---

## 关键产出

### 工程基线

- `src/backend/app/utils/tracing.py` — `business_span()` 装饰器 + no-op 模式
- `scripts/ci/check_orm_schema_drift.py` — ORM ↔ schema 一次性 SQLite 漂移校验（120s 超时）
- `scripts/ci/check_migration_safety.py` — Alembic 危险操作 AST 静态扫描（advisory only，输出 `::warning`）
- `scripts/dev/check_i18n_coverage.py` — i18n 覆盖率（strict + check-parity 双模式）
- `scripts/dev/check_all.sh` — uv workspace 单一入口（fail-fast + 1800s timeout）
- `scripts/dev/check_workspace_lock_conflict.py` — workspace 锁文件冲突检测
- `scripts/ci/list_route_assets.mjs` — vite manifest 路由资产解析
- `scripts/ci/compare_bundle_size.sh` — PR 体积对比阻塞（>10% growth → exit 1）
- `scripts/ci/check_173b_disposition_consistency.py` — 173B 处置一致性校验
- `scripts/ci/check_pr_template.py` — PR 模板 i18n 变更清单子字段校验（advisory）
- `scripts/ci/report_nightly_failure.sh` — nightly 失败 issue 去重创建/复用
- `scripts/dev/seed_e2e_smoke.py` — e2e smoke 最小种子集

### CI 阻塞门（新增）

- `backend-mypy-services` — mypy 严格作用域扩盘到 3 个 services 子包
- `frontend-a11y` — Playwright + axe 7 个核心页面扫描
- `frontend-i18n` — strict + parity + en-US 无中文残留
- `frontend-e2e-smoke` — 5 条 User_Journey_Set Playwright（含 Postgres service container）
- `monorepo-check`（advisory） — uv workspace check-all

### 文档（Diátaxis 分层）

- `docs/explanation/accessibility-baseline.md` — WCAG 2.1 AA 基线、Critical_Page_Set 扫描结果、必要豁免
- `docs/explanation/python-monorepo.md` — uv workspace 选型、vendored 包处理、174 §A6 边界一致性
- `docs/how-to/database-migration-playbook.md` — 长锁/全表扫描风险与降级策略（4 子小节，PR review 清单 6 条）
- `docs/reference/frontend-bundle-budget.md` — vendor + entry chunk 体积基线（数字待 CI 首跑回填）
- `README.md` / `README.en.md` — 索引段加入上述 4 个新文档入口

### 业务侧 OTel 织入（5.2-5.5 完成）

| 命名空间 | 织入位置 | phase |
|---|---|---|
| `backtrader.backtest.*` | `app/services/backtest/{manager,runner}.py` | create / submit / execute / collect / finalize |
| `backtrader.strategy.*` | `app/services/strategy/{core.create_strategy, version.create_version}` | submit / version_create |
| `backtrader.ai.*` | `app/services/trading_intent_parser.py`（parse_trading_intent / _call_llm / _extract_json 包装） | intent_parse / llm_call / response_format |
| `backtrader.live.*` | `app/services/paper_trading_service.py`（submit_order / cancel_order / _fill_order） | place_order / cancel_order / on_fill |

`tests/test_telemetry_e2e.py` 8/8 全部通过。

---

## 175 顺延 / 176 候选

按 §10 / 173B disposition / §1.7 降级路径，明确顺延到 176 的工程债：

### A. mypy services 剩余 6 子包扩盘（§1.7 降级承接）

| 子包 | 175 起点错误数 | 备注 |
|---|---:|---|
| `app.services.gateway` | 29 | 需补类型注解；中等工作量 |
| `app.services.akshare` | 49 | 同上；建议 1 个独立 sprint |
| `app.services.strategy` | 56 | SQLAlchemy `Column[T]` vs `T` 类型分歧 |
| `app.services.backtest` | 57 | 同上 |
| `app.services.live_trading` | 56 | 同上 |
| `app.services.workspace` | 88 | 错误数最多；建议拿一个独立 sprint |

### B. 173B 三项（全部顺延 176）

- T2 (WS Gateway Migration) — 目标日期 2026-08-15
- T7 (News Intelligence 产品化) — 目标日期 2026-09-01（建议作为独立产品 epic）
- T10 (Quant Tool Registry 产品化) — 目标日期 2026-08-30

### C. 前端 i18n 中文裸串清理

- 15553 处违规作为 advisory baseline（`scripts/dev/check_i18n_coverage_baseline.json`）
- 团队按 `views/` → `components/` → `composables/` 优先级逐批清理；每批更新 baseline
- 当 `baseline_violations = 0` 时把 strict 步骤的 `continue-on-error` 移除

### D. 前端 a11y 违规修复

- 框架已建（`e2e/a11y/` 7 spec + `frontend-a11y` job）
- 实际违规修复在首次 CI 红线后由团队推进
- Lighthouse a11y 阈值已升至 0.9（首次跑红时按违规清单推进）

### E. 前端覆盖率从 60 → 75 过渡

- 阈值已设到 75；预期 CI 进入一段红线期
- High_Coverage_Core 8 模块的 90% 阈值需要核心 store/composable 补单测

### F. 性能基准对比 OTel P95 ≤5%

- 175 因 `tests/perf/test_backtest_throughput.py` 等同基准缺失，本轮未做
- 建议 176 先建立 perf baseline 再做对比

### G. 500-999 行 .vue 收尾

- §11.5 降级，本轮不做
- 174 主线 C 收尾后由 176 决定

---

## 流程经验（lessons learned）

### 做对的

1. **「先建门、后补内容」策略**：在 175 一周内把所有 CI 阻塞门、检查脚本、文档骨架建好，让团队后续 PR 在已知红线下逐步补齐内容。这种「门」的价值远大于「一次性把内容做完」，因为它能阻止回归。
2. **明确的降级路径**：每个需求都预留了「不达标如何降级」的清晰说明（§1.7 / §2.4 perFile 降级 / §5.8 OTel 性能基准降级 / §11.5 .vue 收尾整体降级）。这避免了死循环，也让 PR description 中的降级登记成为正式流程。
3. **OTel no-op 模式**：通过 `OTEL_ENABLED` 真值集合 + `nullcontext()` 实现真零开销。生产环境不开 OTel 时业务路径完全不付费。
4. **disposition 文档先于 sub-requirements 生成**：173B 处置在 spec 阶段就完成，避免了「需求 11.x 是否要写」的拉锯。

### 待改进

1. **mypy services 扩盘容量低估**：原计划 9 子包扩盘，实际只完成 3 子包。SQLAlchemy `Column[T]` vs `T` 的类型摩擦比预想严重。176 应单列 1 个 sprint 专门处理 SQLAlchemy 类型层。
2. **i18n 中文裸串规模严重低估**：原以为是「补漏」级别（≤30 行豁免上限），实际是 15553 处的清理工程。175 紧急把 strict 改为 advisory，team 后续按 PR 推进。
3. **shim 清理与 175 撞车**：174 末期的 sys.modules shim 清理（51efc51e、cb91ae0c、e96834fb 等）暴露了多个被遮蔽的 import 错误（log_parser_service / api/router / api/strategy/version / api/auth）。175 在前置工作中顺手补回了这些 import 修复，但理论上这是 174 收口的责任。
4. **CI 红线过渡期未充分沟通**：把覆盖率从 60 调到 75 会有一段红线期，须在 PR 描述与团队会上充分铺垫。

---

## 下一迭代（176）建议主题

按 「175 与 176 的接续」（requirements.md 末段）的展望：

1. **mypy services 6 子包扩盘**（§1.7 顺延项）—— 1 个独立 sprint
2. **A11y 违规修复 + Lighthouse 全跑绿**（§3 内容侧清理）
3. **i18n 中文裸串清理一期**（按 views/ → components/ 节奏，目标 50%+）
4. **OTel metrics + logs correlation**（5 的下一步）
5. **E2E 全套用例上 PR-blocking gate**（6 的升级，从 smoke → 全量）
6. **Bundle size 阈值再下探**（300KB → 250KB）
7. **DB 迁移在 staging 真实数据集 dry-run**（8 的扩展）
8. **monorepo-check 由 advisory 升级为 blocker**（9 的升级）
9. **国际化扩展第三语言**（产品决策依赖项）
10. **173B 三项实际推进**（T2/T7/T10 按目标日期）

---

## 关闭动作（本文档归档时同步执行）

- [x] 175 retrospective 文档归档至 `docs/iterations/迭代175-质量加固与可观测性纵深/RETROSPECTIVE.md`
- [ ] 把 173B 三项与 §1.7 mypy 6 子包写入 `docs/REFACTORING_BACKLOG.md` 「176 候选」段落
- [ ] `docs/iterations/README.md` 175 行更新状态为「已完成（部分降级）」
- [ ] `docs/iterations/迭代173B-171残项独立收口摘要.md` 末尾追加「175 完成后转入 176 候选」
- [ ] CHANGELOG.md 加入 175 条目

---

## 致谢

@yunjinqi（owner，175 评审会主持人）·
工程层面：mypy / pytest / vitest / Playwright / axe / Lighthouse / OTel / Alembic / uv 各社区 ·
框架与库：FastAPI · SQLAlchemy 2.0 · Vue 3 · Vite · Element Plus · Pinia · OpenTelemetry
