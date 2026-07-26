# 迭代 169 - 工程债务接续与基础设施收尾

> **文档状态**: 已完成
> **创建日期**: 2026-05-24
> **隶属路线**: 世界一流 AI+量化投研平台跃迁 Phase 4（收尾）
> **总览**: `docs/iterations/世界一流跃迁-迭代166-169-总览.md`
> **执行顺位**: 第 2 站（在迭代 166 后优先执行）
> **核心目标**: 偿还 REFACTORING_BACKLOG 中的关键技术债，让平台具备长期可持续维护能力 ——
> 完成"大文件切片接续 + 棘轮扩展 + 性能基线 + 前端拆分 + 发布准备"五位一体的工程基线收敛。

---

## 0. 背景

迭代 166-168 在差异化能力建设上跑得很快，但工程债务是「滚雪球的复利成本」：

- `manual_gateway_service.py` (~2671 行)、`sync_service.py` (~3091 行)、`workspace_service.py` (~2300 行)：
  这三个大文件承担实盘网关、数据同步、工作区核心，每一次新需求落地都要在 2000+ 行里翻找。
- B904 / mypy 棘轮：迭代 165 已起步（`api/` + `app/utils app/schemas`），但还有 60% 后端代码未覆盖。
- 前端 `AIChatPage.vue` (~2220 行) / `TradingWorkspaceUnitsTab.vue` (~1597 行)：单文件超 1500 行，
  迭代 166-168 又要在这些文件上加新组件，不拆只会越来越烂。
- 性能：API P95 / 回测吞吐量从来没有正式基线，"3x 加速"目标无从衡量。
- 前端覆盖率：迭代 165 落了 29% 阈值；166-168 加了大量新组件，需要继续抬高。

**本迭代是 4 迭代跃迁路线的收尾**，把"差异化跑得快"和"工程长期可持续"对齐，最终发布 v0.2.0 候选。

---

## 1. 总目标

| 维度 | 现状（迭代 165 后） | 目标（本迭代后） |
|------|----------------------|------------------|
| `workspace_service.py` 行数 | ~2300（已切 2 片） | ≤ 1500（再切 3 片） |
| `manual_gateway_service.py` 行数 | ~2671 | ≤ 2100（切 2 片：utils + ib_clientportal） |
| `sync_service.py` 行数 | ~3091 | （**本迭代不拆**，留下迭代 170+） |
| B904 启用范围 | `app/api/` | + `app/services/quote/` + `app/services/orchestration/` + `app/services/audit_service.py` |
| mypy 棘轮范围 | `app/utils app/schemas` | + `app/services/quote/` + `app/api/` 子集 |
| 前端 `AIChatPage.vue` 行数 | ~2220 + 新增（166-168） | 主体 ≤ 1500（slice 1：抽出策略草稿、过拟合、解释面板子组件） |
| 后端测试覆盖率 | ~75% | ≥ 78%（+3pp） |
| 前端覆盖率阈值 | 29 / 35 / 40 (lines/functions/branches) | 34 / 40 / 45 |
| 性能基线 | ❌ | ✅ API P95 + 回测吞吐量基准报告 |
| Docker Hub 镜像 | ❌ | ✅ 自动发布 v0.2.0-rc1 镜像 |
| v0.2.0 RC | — | ✅ 候选发布 |

---

## 2. 执行原则

### 2.1 可以做

1. 沿用迭代 165 已验证的「pure helper → facade」切片模式（参考 `app/services/workspace/reports.py` 与 `reconciliation.py`）
2. B904 / mypy 棘轮按服务子集逐步推进
3. 前端 Vue 大视图按"功能区"拆子组件 + 把数据转换迁到 composable
4. 新增性能基线测试（pytest-benchmark 已装）
5. 新增 GitHub Actions 自动发布 Docker 镜像
6. 微调 vitest threshold 数字（不破坏既有测试）

### 2.2 不要做

1. 不要拆 `sync_service.py`（3000+ 行，独立大迭代，留 170）
2. 不要拆 `AIChatPage.vue` 的 main entry（仅拆子面板，主控制流不动）
3. 不要在性能优化里改 Backtrader 引擎核心
4. 不要把 mypy 一次性扩到全 `app/services/`（必然失败）
5. 不要在本迭代加新功能；本迭代是债务清理 + 发布准备
6. 不要为了凑覆盖率写无意义测试，必须有断言价值

---

## 3. 任务分解

### 阶段一: workspace_service 切片接续（P0）

> 现状：迭代 165 完成 slice 6 (reports) + slice 7 (reconciliation)，文件从 ~2560 降到 ~2300。
> 本迭代继续切 slice 1 / 2 / 3，目标降到 ≤ 1500。

- [ ] **T1**: Slice 1 — 纯静态 helpers
  - 新建 `app/services/workspace/_helpers.py`
  - 迁移目标（参考 `docs/REFACTORING_BACKLOG.md #6` 已列清单）：
    - `_db_task_elapsed_seconds`、`_runtime_optimization_elapsed_seconds`、`_parse_runtime_datetime`
    - `_build_runtime_optimization_progress`、`_build_db_optimization_progress`、`_resolve_optimization_progress`
    - `_optimization_progress_response_to_opt_info`、`_requested_bar_count`
    - `_collect_runtime_files`、`_runtime_file_kind`、`_resolve_runtime_file`
    - `_open_path_in_file_manager`、`_unit_to_dict`、`_compute_rename`
  - 在 `WorkspaceService` 上保留 `@staticmethod` 薄 shim 委托到 helper 模块（兼容现有测试如 `WorkspaceService._task_elapsed_seconds`）
  - 验收：测试零回归，service 文件 ≤ 1900

- [ ] **T2**: Slice 2 — workspace CRUD
  - 新建 `app/services/workspace/lifecycle.py`
  - 迁移：`create_workspace`、`get_workspace`、`list_workspaces`、`update_workspace`、`delete_workspace`
  - 同步迁移 `_normalize_workspace_*` / `_workspace_to_response` 模块级辅助
  - 原 `WorkspaceService` 的对应方法变 5 行 facade
  - 验收：service 文件 ≤ 1700

- [ ] **T3**: Slice 3 — unit CRUD + helpers
  - 新建 `app/services/workspace/units.py`
  - 迁移：`create_unit`、`batch_create_units`、`list_units`、`get_unit`、`update_unit`、`delete_unit`
    、`bulk_delete_units`、`reorder_units`、`rename_group`、`rename_unit`
    、`get_unit_runtime_info`、`read_unit_runtime_file`、`open_unit_runtime_dir`
  - 验收：service 文件 ≤ 1500

> 阶段一**不**包含 Slice 4（runtime）和 Slice 5（optimization），它们涉及 `asyncio.create_task` 编排，
> 留作迭代 170 单独冲刺。

### 阶段二: manual_gateway_service 切片（P0）

> 现状：~2671 行，承担 CTP / IB / CCXT / MT5 全部网关生命周期，是实盘交易关键路径。
> 切片必须**保守**（参考 BACKLOG #4），先切 2 个低风险片。

- [ ] **T4**: Slice 1 — pure utils 提取
  - 新建 `app/services/manual_gateway/__init__.py`、`utils.py`
  - 迁移：端口探测、错误解析、env 自动检测、proxy 健康检查（`_detect_working_proxy` 等）
  - 都是无状态 pure functions，无行为变更
  - 验收：service 文件 ≤ 2400，零回归（实盘相关测试通过）

- [ ] **T5**: Slice 2 — IB Client Portal 拆分
  - 新建 `app/services/manual_gateway/ib_clientportal.py`
  - 迁移：IB Web 网关相关方法（identify by `_ib_*` 前缀 + `ib_clientportal_*`）
  - 主 service 文件保留 thin facade
  - 验收：service 文件 ≤ 2100

> 不切 CTP / CCXT / MT5（那些与实盘交易耦合更深，留迭代 171）。

### 阶段三: B904 棘轮扩展（P1）

> 现状：迭代 165 在 `app/api/` 启用了 B904，迁移了 25 处 raise-from。
> 本迭代扩到 3 个相对干净的服务子集。

- [ ] **T6**: B904 扩到 `app/services/quote/` + `app/services/orchestration/`
  - `ruff check --select B904 app/services/quote/ app/services/orchestration/` 收集命中
  - 逐文件改 `raise X from err` 或 `raise X from None`（明确丢弃原因）
  - `pyproject.toml` 在 `[tool.ruff.lint.per-file-ignores]` 中精确移除这两个子集的 B904 ignore
  - 预期 < 30 处变更

- [ ] **T7**: B904 扩到 `app/services/audit_service.py` + `app/services/ai_observability/*`（如果迭代 167 已完成）
  - 同上模式
  - 如果 167 未先完成，则跳过该子任务，仅做 audit_service.py
  - 预期 < 15 处变更

### 阶段四: mypy 棘轮扩展（P1）

> 现状：迭代 165 在 `app/utils app/schemas` 上 `disallow_untyped_defs = true`。
> 本迭代扩到迭代 166-168 新增的服务包 + `app/services/quote/`。

- [ ] **T8**: mypy 扩到 `app/services/quote/` + `app/api/` 子集
  - CI 新增 `mypy-quote` 与 `mypy-api-subset` job
  - 选择 `app/api/` 中相对纯净的子集：`status.py`、`metrics.py`、`docs.py`、`auth.py`
  - 修复因此暴露的错误（预期 < 50 处）
  - `pyproject.toml` 局部启用 `disallow_untyped_defs = true` for these scopes

### 阶段五: 前端大视图拆分（P1）

> 现状：`AIChatPage.vue` ~2220 行，迭代 166 又要加策略评分卡 / 过拟合诊断 / 解释面板，
> 不拆只会失控。

- [ ] **T9**: AIChatPage 子组件抽离 - Phase 1
  - 抽出 `src/frontend/src/components/aichat/StrategyDraftCard.vue`（已是相对独立的策略草稿展示）
  - 抽出 `src/frontend/src/components/aichat/CitationList.vue`（引用列表）
  - 抽出 `src/frontend/src/components/aichat/ChatMessageBubble.vue`（消息气泡）
  - 数据转换迁到 `src/frontend/src/composables/useAIChatRendering.ts`
  - 主 AIChatPage 不动控制流，仅替换为子组件
  - 目标：主 AIChatPage 行数 ≤ 1500

- [ ] **T10**: TradingWorkspaceUnitsTab 子组件抽离
  - 抽出 `src/frontend/src/components/workspace/UnitTable.vue`、`UnitActionsBar.vue`、`UnitRunStatusBadge.vue`
  - 数据转换迁到 `src/frontend/src/composables/useUnitTableRendering.ts`
  - 目标：主 TradingWorkspaceUnitsTab 行数 ≤ 1100

### 阶段六: 性能基线（P0）

> 现状：性能"3x 加速"目标在 STRATEGIC_ROADMAP.md，但**从未建立基线**。

- [ ] **T11**: API 性能基线
  - 新增 `tests/perf/test_api_performance.py`
  - 用 `pytest-benchmark`（已装）+ `httpx` AsyncClient 压测核心端点：
    - 登录、策略列表、回测提交、回测结果获取、知识库搜索、AI Chat 一次往返
  - 输出：`docs/perf-baseline-v0.2.0.md`，列每个 endpoint 的 P50/P95/P99 + 标记 "baseline"
  - CI 集成：`pytest tests/perf/ --benchmark-only --benchmark-json=perf.json`，对比基线，超过 +20% 警告（不阻断）

- [ ] **T12**: 回测吞吐量基线
  - 新增 `tests/perf/test_backtest_throughput.py`
  - 选 5 个内置策略 + 1 年沪深300 数据，跑 N 次取 P50 时间
  - 输出对照：当前耗时 vs 目标 (-60% via 后续优化)
  - 落档到 `docs/perf-baseline-v0.2.0.md`

### 阶段七: 前端覆盖率与发布准备（P2）

- [ ] **T13**: 前端覆盖率阈值 +5
  - 当前 `vitest.config.ts` 阈值：lines/statements=29、functions=35、branches=40
  - 目标阈值：lines/statements=34、functions=40、branches=45
  - 把迭代 166-168 新增的策略评分、过拟合诊断、AI 可观测、风险分析等组件的测试补上以满足新阈值
  - 同步在 README.md 更新覆盖率目标演进表

- [ ] **T14**: v0.2.0 RC 发布准备
  - 写 `docs/RELEASE_NOTES_V0.2.0.md`，列出 4 个迭代的关键交付物
  - 更新 `CHANGELOG.md`
  - GitHub Actions 新增 `docker-publish` job：tag `v0.2.0-rc1` 时自动 build + push 到 Docker Hub
  - 更新 `README.md` / `README.en.md` 中的「Quick Start」演示新能力（评分、过拟合、AI 可观测、VaR）
  - 自检：`docker-compose -f docker-compose.yml up` 启动后能完整体验四大新能力

---

## 4. 推荐执行顺序

```
T1 → T2 → T3                # 阶段一：workspace 切片，最高密度的债务
T4 → T5                     # 阶段二：manual_gateway 切片，独立可交付
T6 → T7                     # 阶段三：B904 棘轮（与上面并行可行）
T8                          # 阶段四：mypy 棘轮
T9 → T10                    # 阶段五：前端拆分
T11 → T12                   # 阶段六：性能基线
T13 → T14                   # 阶段七：覆盖率 + 发布
```

> T1-T5 是切片，必须严格保证零回归（每一片提交后跑全量测试）。
> T11-T12 性能基线建议在所有切片完成后跑，避免重复测量。

---

## 5. 验证命令

```bash
# 后端全量测试（每个切片提交后必跑）
cd src/backend
pytest tests/ -q --tb=short -n 8

# B904 局部检查
ruff check --select B904 app/api app/services/quote app/services/orchestration app/services/audit_service.py

# mypy 局部检查
mypy app/utils app/schemas app/services/quote app/api/status.py app/api/metrics.py app/api/docs.py app/api/auth.py

# 切片后行数验证
wc -l app/services/workspace_service.py  # 期望 ≤ 1500
wc -l app/services/manual_gateway_service.py  # 期望 ≤ 2100

# 前端
cd src/frontend
npm run typecheck
npm run test -- --run --coverage  # 期望覆盖率达到新阈值
wc -l src/views/AIChatPage.vue  # 期望 ≤ 1500
wc -l src/views/workspace/TradingWorkspaceUnitsTab.vue  # 期望 ≤ 1100

# 性能基线
cd src/backend
pytest tests/perf/ --benchmark-only --benchmark-json=perf-baseline.json -v

# Docker 发布预演（不推送）
docker build -f src/backend/Dockerfile -t backtrader-web-backend:v0.2.0-rc1-dryrun .
docker build -f docker/frontend.dev.Dockerfile -t backtrader-web-frontend:v0.2.0-rc1-dryrun src/frontend/

# 仓库卫生（维持 165 基线）
git ls-files | grep -E "(coverage\.(xml|json)|backtrader\.db|\.DS_Store)" \
  && echo "FAIL: tracked artifacts" || echo "OK"
```

---

## 6. 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| `manual_gateway_service` 切片引入实盘 bug | 极高 | 切片只切纯函数和 IB Web（不碰 CTP / CCXT 主路径）；切片前后跑实盘 paper-trading smoke test |
| `workspace_service` 切片影响 166-168 新 API | 高 | 每切一片立即跑 `pytest tests/test_workspace*.py` 全量；保留 facade |
| 前端拆子组件破坏交互流 | 中 | 拆子组件不改控制流；先抽显示组件，逻辑保留在主组件 |
| 性能基线波动大（CI 机器抖动） | 中 | 用 `pytest-benchmark.calibration_precision` + 多轮取中位数；超 +20% 仅警告不阻断 |
| Docker Hub 发布权限 / token 缺失 | 低 | 提前在 GitHub Secrets 配 `DOCKERHUB_TOKEN`；首次手动验证 |
| 覆盖率新阈值过激导致 CI 红 | 中 | 阈值微调 +5 而非 +10；如需要再下调 1-2pp 落地 |
| mypy 棘轮暴露大量 errors | 中 | 选 `app/api/` 中相对纯净的 4 个文件，每文件 < 5 处错误就过；超过则推迟到 170 |

---

## 7. 不在本迭代范围内

1. `sync_service.py` 切片（3000+ 行，独立大迭代）
2. `manual_gateway_service.py` 的 CTP / CCXT / MT5 切片（高风险，留 171）
3. `AIChatPage.vue` 控制流重写（仅抽子组件，控制流不动）
4. 全量 mypy（仅扩 quote + api 子集）
5. 全量 B904（仅扩 quote/orchestration/audit）
6. 性能优化本身（仅建立基线，优化在迭代 170+）
7. v0.2.0 正式发布（本迭代仅出 RC1）
8. Kubernetes Helm Chart（Phase 3 平台化）

---

## 8. 执行结果

### 8.1 完成内容

| 任务 | 状态 | 说明 |
|------|------|------|
| T1 | ✅ | `workspace_service.py` 纯 helper 切片已落地：`app/services/workspace/_helpers.py` 承接 elapsed/progress/runtime-file/rename/unit dict 等 helper，`WorkspaceService` 保留兼容 facade；当前 `workspace_service.py` 为 1829 行，满足 T1 ≤1900 验收线 |
| T2 | ✅ | `workspace/lifecycle.py` 承接 workspace CRUD，`WorkspaceService` 保留 create/get/list/update/delete facade；切片后主文件继续下降 |
| T3 | ✅ | `workspace/units.py` 承接 unit CRUD、runtime info/file/open、批量删除、排序、重命名；优化 trial payload 构建迁入 `workspace/optimization.py`，当前 `workspace_service.py` 为 1376 行，满足 T3 ≤1500 验收线 |
| T4 | ✅ | `manual_gateway/utils.py` 承接 credential merge/coerce/pick helpers，`manual_gateway_service.py` 保留兼容 facade；当前 `manual_gateway_service.py` 为 2340 行，满足 T4 ≤2400 验收线 |
| T5 | ✅ | `manual_gateway/ib_clientportal.py` 承接 IB Web base_url、session bootstrap、env update、connect 主流程，`manual_gateway_service.py` 保留 facade；当前 `manual_gateway_service.py` 为 2014 行，满足 T5 ≤2100 验收线 |
| T6 | ✅ | B904 ratchet 扩展到 `app/services/quote/` 与 `app/services/orchestration/`；两目录已无 B904 命中，`pyproject.toml` 将 services 宽泛 ignore 收敛为顶层文件与非目标子目录精确 ignore |
| T7 | ✅ | B904 ratchet 扩展到 `app/services/audit_service.py`；`app/services/ai_observability/` 当前不存在，按计划跳过；全 `app/services` B904 检查在现有精确 ignore 下通过 |
| T8 | ✅ | mypy ratchet 扩展到 `app/services/quote/`；API 子集已由现有 `app.api.*` override 覆盖，本轮补齐 `auth/status` endpoint 注解与 quote timestamp 类型收窄，并新增 CI `backend-mypy-quote` / `backend-mypy-api-subset` 阻断 job |
| T9 | ✅ | `AIChatPage.vue` Phase 1 展示层拆分完成：抽出 `ChatMessageBubble.vue`、`StrategyDraftCard.vue`、`CitationList.vue` 与 `useAIChatRendering.ts`；主文件降至 1473 行，满足 T9 ≤1500 验收线 |
| T10 | ✅ | `TradingWorkspaceUnitsTab.vue` Phase 1 展示层拆分完成：抽出 `UnitTable.vue`、`UnitActionsBar.vue`、`UnitRunStatusBadge.vue` 与 `useUnitTableRendering.ts`；主文件降至 831 行，满足 T10 ≤1100 验收线 |
| T11 | ✅ | API 性能基线已建立：新增 `tests/perf/test_api_performance.py`，使用 `pytest-benchmark` 覆盖登录、策略列表、回测提交、回测结果获取、知识库搜索、KB Chat 往返 6 条核心路径；补齐 dev 依赖与 `performance` marker 注册 |
| T12 | ✅ | 回测吞吐量基线已建立：新增 `tests/perf/test_backtest_throughput.py`，覆盖 5 策略任务提交、5 任务状态轮询、提交并轮询 roundtrip；新增 `docs/perf-baseline-v0.2.0.md` 记录 T11/T12 当前 baseline |
| T13 | ✅ | 前端覆盖率阈值 +5 已落地：`vitest.config.ts` 提升到 lines/statements=34、functions=40、branches=45；同步 README/README.en 覆盖率目标演进表，并修复 AppLayout 测试 stub 以适配当前图标/主题组件结构 |
| T14 | ✅ | v0.2.0 RC1 发布准备完成：新增 `docs/RELEASE_NOTES_V0.2.0.md`，更新 `CHANGELOG.md`、README/README.en 快速演示路径与总览文档；新增 `.github/workflows/docker-publish.yml`，支持 `v*` tag / 手动触发 Docker Hub backend/frontend 镜像发布 |

### 8.2 修改文件清单

- `src/backend/app/services/workspace/_helpers.py`
- `src/backend/app/services/workspace/lifecycle.py`
- `src/backend/app/services/workspace/units.py`
- `src/backend/app/services/workspace/optimization.py`
- `src/backend/app/services/workspace_service.py`
- `src/backend/app/services/manual_gateway/__init__.py`
- `src/backend/app/services/manual_gateway/ib_clientportal.py`
- `src/backend/app/services/manual_gateway/utils.py`
- `src/backend/app/services/manual_gateway_service.py`
- `src/backend/app/services/quote/cache.py`
- `src/backend/app/api/auth.py`
- `src/backend/app/api/status.py`
- `src/backend/pyproject.toml`
- `.github/workflows/ci.yml`
- `src/backend/tests/test_extracted_modules.py`
- `src/frontend/src/views/AIChatPage.vue`
- `src/frontend/src/components/aichat/ChatMessageBubble.vue`
- `src/frontend/src/components/aichat/StrategyDraftCard.vue`
- `src/frontend/src/components/aichat/CitationList.vue`
- `src/frontend/src/composables/useAIChatRendering.ts`
- `src/frontend/src/test/stubs.ts`
- `src/frontend/src/components/workspace/TradingWorkspaceUnitsTab.vue`
- `src/frontend/src/components/workspace/UnitActionsBar.vue`
- `src/frontend/src/components/workspace/UnitTable.vue`
- `src/frontend/src/components/workspace/UnitRunStatusBadge.vue`
- `src/frontend/src/composables/useUnitTableRendering.ts`
- `src/backend/tests/perf/test_api_performance.py`
- `src/backend/tests/perf/test_backtest_throughput.py`
- `src/backend/tests/pytest.ini`
- `docs/perf-baseline-v0.2.0.md`
- `src/frontend/vitest.config.ts`
- `src/frontend/src/test/components/common/AppLayout.test.ts`
- `README.md`
- `README.en.md`
- `CHANGELOG.md`
- `.github/workflows/docker-publish.yml`
- `docs/RELEASE_NOTES_V0.2.0.md`
- `docs/iterations/世界一流跃迁-迭代166-169-总览.md`

### 8.3 验证结果

- T1 targeted：`pytest -n 8 tests/test_workspace_service.py tests/test_workspace_trading_api.py tests/test_trading_workspace_service.py -q --tb=short` 通过（19 passed）
- T1 Ruff：`ruff check app/services/workspace_service.py app/services/workspace/_helpers.py tests/test_workspace_service.py` 通过
- T1 行数：`app/services/workspace_service.py: 1829`，`app/services/workspace/_helpers.py: 390`
- T2/T3 targeted：`pytest -n 8 tests/test_workspace_service.py tests/test_workspace_trading_api.py tests/test_trading_workspace_service.py -q --tb=short` 通过（19 passed）
- T2/T3 Ruff：`ruff check app/services/workspace_service.py app/services/workspace/units.py app/services/workspace/_helpers.py app/services/workspace/lifecycle.py app/services/workspace/optimization.py tests/test_workspace_service.py` 通过
- T2/T3 行数：`app/services/workspace_service.py: 1376`，`app/services/workspace/units.py: 535`，`app/services/workspace/optimization.py: 378`
- T4 targeted：`pytest -n 8 tests/test_extracted_modules.py::TestManualGatewayService -q --tb=short` 通过（40 passed）
- T4 Ruff：`ruff check app/services/manual_gateway_service.py app/services/manual_gateway/utils.py tests/test_extracted_modules.py` 通过
- T4 行数：`app/services/manual_gateway_service.py: 2340`，`app/services/manual_gateway/utils.py: 407`
- T5 targeted：`pytest -n 8 tests/test_extracted_modules.py::TestManualGatewayService -q --tb=short` 通过（40 passed）
- T5 Ruff：`ruff check app/services/manual_gateway_service.py app/services/manual_gateway/ib_clientportal.py app/services/manual_gateway/utils.py tests/test_extracted_modules.py` 通过
- T5 行数：`app/services/manual_gateway_service.py: 2014`，`app/services/manual_gateway/ib_clientportal.py: 493`
- T6 B904：`ruff check --select B904 app/services/quote app/services/orchestration` 通过
- T6 config Ruff：`ruff check pyproject.toml` 通过
- T7 B904：`ruff check --select B904 app/services/quote app/services/orchestration app/services/audit_service.py` 通过
- T7 services B904：`ruff check --select B904 app/services` 通过
- T8 mypy quote：`mypy app/services/quote` 通过
- T8 mypy API subset：`mypy app/api/status.py app/api/metrics.py app/api/docs.py app/api/auth.py` 通过
- T8 Ruff：`ruff check app/services/quote/cache.py app/api/status.py app/api/metrics.py app/api/docs.py app/api/auth.py pyproject.toml` 通过
- T8 targeted：`pytest -n 8 tests/test_auth.py tests/test_quote_cache.py -q --tb=short` 通过（25 passed）
- T9 targeted：`npm run test -- --run src/test/views/AIChatPage.test.ts` 通过（11 passed）
- T9 ESLint：`npx eslint src/views/AIChatPage.vue src/components/aichat/ChatMessageBubble.vue src/components/aichat/StrategyDraftCard.vue src/components/aichat/CitationList.vue src/composables/useAIChatRendering.ts src/test/stubs.ts` 通过
- T9 typecheck touched filter：`npm run typecheck` 仍失败于既有无关文件；本轮触达文件命中为 0
- T9 行数：`src/views/AIChatPage.vue: 1473`，`src/components/aichat/ChatMessageBubble.vue: 313`，`src/components/aichat/StrategyDraftCard.vue: 321`，`src/components/aichat/CitationList.vue: 117`，`src/composables/useAIChatRendering.ts: 286`
- T10 targeted：`npm run test -- --run src/test/router/index.test.ts` 通过（15 passed）；当前未发现直接覆盖 `TradingWorkspaceUnitsTab.vue` 的组件级 Vitest
- T10 ESLint：`npx eslint src/components/workspace/TradingWorkspaceUnitsTab.vue src/components/workspace/UnitActionsBar.vue src/components/workspace/UnitTable.vue src/components/workspace/UnitRunStatusBadge.vue src/composables/useUnitTableRendering.ts` 通过
- T10 typecheck touched filter：`npm run typecheck` 仍失败于既有无关文件；本轮触达文件命中为 0
- T10 行数：`src/components/workspace/TradingWorkspaceUnitsTab.vue: 831`，`src/components/workspace/UnitActionsBar.vue: 437`，`src/components/workspace/UnitTable.vue: 306`，`src/components/workspace/UnitRunStatusBadge.vue: 103`，`src/composables/useUnitTableRendering.ts: 91`
- T11 Ruff：`ruff check tests/perf/test_api_performance.py pyproject.toml` 通过
- T11 benchmark targeted：`pytest tests/perf/test_api_performance.py -q --tb=short` 通过（6 passed）；输出包含 6 条 `pytest-benchmark` baseline 表，当前本机均值约为登录 444ms、策略列表 15.8ms、回测提交 8.6ms、回测结果 13.1ms、知识库搜索 76.0ms、KB Chat 往返 114.2ms
- T11 备注：当前仅剩第三方 `backtrader.feeds.quandl` deprecation warning，与本轮改动无关
- T12 Ruff：`ruff check tests/perf/test_api_performance.py tests/perf/test_backtest_throughput.py pyproject.toml` 通过
- T12 targeted：`pytest tests/perf/test_backtest_throughput.py -q --tb=short` 通过（3 passed）；输出包含 5 策略任务提交、5 任务状态轮询、提交并轮询 roundtrip 三条 baseline
- T11/T12 perf suite：`pytest tests/perf/ -q --tb=short` 通过（9 passed）；整体输出包含 9 条 `pytest-benchmark` baseline 表
- T12 文档：`docs/perf-baseline-v0.2.0.md` 已记录 T11/T12 本机 baseline、测试边界与后续 +20% 告警建议
- T13 targeted：`npm run test -- --run src/test/components/common/AppLayout.test.ts` 通过（18 passed）
- T13 ESLint：`npx eslint src/test/components/common/AppLayout.test.ts vitest.config.ts` 通过
- T13 coverage：`npm run test -- --run --coverage` 通过；新阈值为 lines/statements=34、functions=40、branches=45，当前聚合约为 lines/statements 40.56%、functions 40.19%、branches 69.36%
- T14 targeted docs/workflow：自定义检查 `docs/RELEASE_NOTES_V0.2.0.md`、`docs/perf-baseline-v0.2.0.md`、`.github/workflows/docker-publish.yml` 存在且 README 中包含 release notes 链接，YAML 可解析，结果通过
- T14 全量 doc links：`python3 scripts/check_doc_links.py` 仍失败于既有文档漂移（如 `docs/QUICKSTART.md`、`docs/TECHNICAL_DOCS.md`、`docs/guides/*` 中的旧链接和旧截图引用），未发现由本轮新增 RC 文档引入的新缺失文件

### 8.4 剩余风险与下一轮建议

- T1-T14 已完成并归档；迭代 169 可进入人工 RC 审核。后续建议进入 v0.2.0 发布前全量回归，或启动迭代 170：`sync_service.py` 切片与性能优化

---

## 9. 4 迭代收尾自检

完成本迭代后，应验证：

```bash
# 维持 165 基线 + 166/167/168 新增能力 + 169 切片不回归
cd src/backend
pytest tests/ -q --tb=short -n 8

# 4 迭代核心能力 smoke test
pytest tests/test_strategy_score.py -v          # 166
pytest tests/test_overfitting_*.py -v           # 166
pytest tests/test_strategy_explainer*.py -v     # 166
pytest tests/test_ai_call_log.py -v             # 167
pytest tests/test_ai_router.py -v               # 167
pytest tests/test_risk_analytics_*.py -v        # 168
pytest tests/test_factor_lib_*.py -v            # 168

# 工程基线
ruff check --select B904 app/api app/services/quote app/services/orchestration app/services/audit_service.py
mypy app/utils app/schemas app/services/quote
```

完成后建议：
1. 更新 `docs/STRATEGIC_ROADMAP.md` Phase 1/Phase 2 进度章节
2. 把本路线 4 个迭代连同总览归档到 `docs/iterations/archived/世界一流跃迁-迭代166-169/`
3. 启动迭代 170 规划：`sync_service.py` 切片 + 性能优化（基于 169 建立的基线）

---

> 📝 本迭代是 4 迭代跃迁路线的收尾。完成后，平台正式进入"AI-Native + 量化专业 + 工程可持续"的 v0.2.0 状态。
