# 迭代 174 - 结构精简与工程债接续

> **文档状态**: 计划（草案 v1，可直接对外交付执行）
> **创建日期**: 2026-05-27
> **前置基线**:
> - 迭代 173 已发起「安全配置 + 大文件切片 + 设计系统 + 性能与 AI 可观测性 + 流程清场」五维收口；其「后续接续（174 候选）」已显式列出本轮承接对象（见 173 §9）
> - 迭代 172 已完成首批 14 个 `bt_api_xx` 券商扩展包独立落地，`backtrader_web` 保持 consumer-only 边界，broker 相关重构不进本轮
> - v0.2.0-rc1 已发版（2026-05-24），距 GA 仍需把"Known Boundaries 与工程残债"收到尾
> - 本轮基于 2026-05-27 项目骨架审计，识别出 173 未覆盖的 4 类结构性债（根目录散乱、API/Service 平铺过密、文档无分类、scripts 64 个无层级）
> **核心目标**:
> 在不删减任何功能的前提下，把项目从"内部逻辑已经成熟、但外部骨架仍像草稿"的状态，收敛到"行业最佳实践骨架 + 173 大文件切片续作完成"的状态，让任何新加入的工程师在第一天就能凭目录结构定位 80% 的代码与文档。
> **执行假设**:
> - 本计划默认由**外部团队**接手执行（创建者不在场），因此每一项都给出文件路径、行数现状、验证命令、依赖顺序，避免任何"靠对话上下文才能补全"的歧义
> - 默认遵循 `AGENTS.md` 与 `docs/CODING_STANDARDS.md`；所有重组以**保留功能、保留 API 兼容、保留测试可绿**为最高约束

---

## 0. 立项背景

### 0.1 174 必须做的 4 件事是什么样子

本轮立项不基于主观感受，而是基于以下可验证的事实：

| 维度 | 证据（命令） | 当前数字 |
|---|---|---|
| 根目录视觉噪音 | `ls /Users/yunjinqi/Documents/new_projects/backtrader_web \| wc -l` | 30+ 项；6 个 `docker-compose.*.yml`、6 个 `start/stop/restart_app.{sh,bat}`、空目录 `backtrader_web/`、根目录 `backtrader.db`、`__pycache__/` |
| API 平铺 | `ls src/backend/app/api \| grep -v __pycache__ \| wc -l` | 58 个 `.py` 平铺；5 个 `akshare_*`、4 个 `strategy*`、5 个 `data*`、2 个 `live_trading*`、2 个 `portfolio*`、3 个 `deps*` 全平铺 |
| Service 平铺 | `ls src/backend/app/services \| grep -v __pycache__ \| wc -l` | 92 个；其中 7 个 `optimization_*`、5 个 `gateway_*`、4 个 `akshare_*`、3 个 `backtest_*` 平铺 |
| 后端 800 行硬线超标 | `find src/backend/app -name '*.py' \| xargs wc -l \| awk '$1>800'` | 173 收口后仍剩 ≥10 个文件 ≥800 行（见 §3.1） |
| 前端 500 行典型线超标 | `find src/frontend/src -type f \( -name '*.ts' -o -name '*.vue' \) \| xargs wc -l \| awk '$1>500'` | ≥18 个文件；其中 7 个 ≥1000 行（见 §4.1） |
| scripts 平铺 | `ls scripts/ \| wc -l` | 64 个 `.py/.sh` 平铺，混合 ops/diagnostics/migrate/ci/dev 五类 |
| docs 平铺 | `ls docs/ \| wc -l` | 51 项；CHANGELOG 与根目录重复；含 4 张 `.png` 截图、3 份战略路线图、API 参考、ADR 全平铺 |
| 双轨测试目录 | `ls src/frontend/src/test src/frontend/src/stores/__tests__` | `src/test/*` 与 `__tests__/*` 双轨共存 |
| 锁文件分裂 | `ls requirements-*.lock src/backend/pyproject.toml` | 根目录 `requirements-{dev,prod}.lock` 与后端 `pyproject.toml` 共存，未注明分工 |
| main.py 启动膨胀 | `wc -l src/backend/app/main.py` | 431 行；`lifespan()` 已混合 DB / reconcile / audit sink / AI log sink / orchestration / 安全告警 6 个子系统 |
| src 多包混杂 | `ls src/` | `backend/`、`frontend/`、`bt_api_py/`、`clientportal.gw/`（第三方 vendored）、`dags/`（疑似与根 `dags/` 重复）并存 |

### 0.2 为什么是"结构精简"

- 173 主线聚焦在「文件内部切片」「设计系统颜色 token」「安全默认值」「AI 可观测性补完」——属于**逻辑内**的债。
- 174 的目标是**结构外**的债：项目从仓库视角看像不像一个能直接交付的开源/商业代码库。
- 这类债不修，每加一轮迭代就会再增加一类入口（脚本、compose、API、view），到 v1.0 之前压不下去。
- 同时，173 在 §9 列出的延期切片（manual_gateway 3/4、sync 2/3/4、workspace 3/4/5、quote 3/4）需要一个明确的"载体迭代"承接，否则会沉到 backlog 底部。

### 0.3 与 173 的边界

- 173 = 内部逻辑收口 + 设计系统颜色 token 单一来源 + 安全默认值翻转 + 性能与 AI 观测补完。
- 174 = 仓库骨架收敛 + 173 大文件切片续作 + 文档治理 + 173 残项（Prompt 治理后半段、覆盖率二级棘轮、Docker Hub 发版自动化）。
- **174 不重做 173 已完成的颜色 token、安全默认值、AI 观测 sink**。

---

## 1. 范围定义

### 1.1 范围结构

本迭代采用「四主线 + 一流程线」结构：

```
迭代 174
├── 主线 A · 仓库骨架精简（根目录 / scripts / docker / src 多包）
├── 主线 B · API / Service 子包化（58 → ~25 / 92 → ~60 个入口）
├── 主线 C · 大文件切片续作（接 173 残项 + 后端 800 行 / 前端 500 行硬线扫尾）
├── 主线 D · 文档治理（51 平铺 → Diátaxis 分层）
└── 流程线 E · 173 残项收口（Prompt 治理 / 覆盖率棘轮 / Docker Hub / backlog 同步）
```

主线 A / B / D 相互独立，可并行；主线 C 与 B 在同一文件家族内时需要 serialize（避免冲突）。

### 1.2 明确不在本迭代范围

为防止范围漂移，以下事项**明确排除**：

- ❌ 不接受任何新功能 PRD；任何新需求一律记到 175+
- ❌ 不重做 173 已完成的颜色 token、安全默认值翻转、AI sink；仅在 174 收尾时确认 173 验收门已绿
- ❌ 不引入新语言、新框架、新构建工具（仍是 Python 3.10+ / FastAPI / SQLAlchemy 2.x / Vue 3 / Vite）
- ❌ 不动数据库 schema；如必须改，单独 RFC，不挂 174
- ❌ 不在 `backtrader_web` 内新增 broker 适配（172 已固化边界）
- ❌ 不做 FinceptTerminal 新批迁移；173B 残项独立线程不并入
- ❌ 不重做 UI 信息架构；本轮 D 主线只动文档目录与设计系统 v0.2（按钮/字号/卡片落地），不动顶层路由
- ❌ 不做整站性能二轮优化；173 已达成 60% 降耗目标后保持
- ❌ 不做大规模目录改名（除 §2、§5 明确列出的项），避免 git history 难追

### 1.3 兼容性约束

所有重组必须满足：

1. **API 路径零破坏**：FastAPI 路由 URL 在 §3 / §4 之外保持稳定；子包化只动 import 树，不动 `@router.get/post` 的 path
2. **CLI 命令保持可用**：根目录 `start_app.sh` / `stop_app.sh` / `restart_app.sh` 在归并到 `scripts/app.sh` 后必须保留**根目录薄入口**（一行调用 + deprecation 注释），避免文档/CI/外部脚本依赖断裂
3. **测试套件全程绿**：任何切片提交必须先确保 `pytest -m "not e2e"` 与 `npm run test -- --run` 通过，再合并
4. **导入兼容**：服务层子包化必须在原模块保留**门面 re-export**（如 `from app.services.optimization import *`）至少 1 个迭代周期，给下游消费者迁移窗口

---

## 2. 主线 A · 仓库骨架精简

### 2.1 任务卡

| ID | 任务 | 当前 → 目标 | 验证 | 工作量 |
|---|---|---|---|---|
| A1 | 根目录 docker-compose 收敛 | 根目录 6 个 `docker-compose.*.yml` → 根 1 个 `docker-compose.yml` + `docker/compose/{dev,prod,ci,airflow,local}.yml` 各为 override；或用 `profiles:` 收到单文件 | `docker compose -f docker-compose.yml -f docker/compose/dev.yml config` 全部 5 套环境 schema 合法 | M |
| A2 | 启动脚本归一 | 根目录 6 个 `{start,stop,restart}_app.{sh,bat}` → `scripts/app.sh` + `scripts/app.bat` 单入口（参数 `start\|stop\|restart\|status`）；根目录 6 个文件保留为 1 行 forward 兼容 shim（含 deprecation 注释） | `./start_app.sh` 行为不变；`./scripts/app.sh start` 与原行为对等 | S |
| A3 | 根目录残留清理 | 删除空目录 `backtrader_web/`（仅有 `__pycache__`）；`backtrader.db` 移到 `data/dev/backtrader.db` + 更新默认 SQLite 路径；根 `__pycache__` 加入 `.gitignore` 并 `git rm -rf --cached` | `ls /` 无以上 4 项；新克隆 + `make dev` 仍能跑通 | S |
| A4 | 运行时目录隔离 | `runtime/`、`logs/`、`workspace_units/`、`strategies/`、`datas/`、`dags/`（如是运行时产出） → 统一到 `var/` 根；通过 env var `APP_RUNTIME_DIR` 切换；保留旧路径符号链接 1 个迭代周期 | 默认配置下应用启动后产出物落到 `var/`；`tests/` 不动 | M |
| A5 | scripts 64 个分层 | `scripts/` 平铺 64 项 → `scripts/{ops,diagnostics,migrate,ci,dev}/` 五个子目录；`scripts/README.md` 索引；`diag_err.txt / diag_out.txt` 加入 `.gitignore` 并清理；同名文件以脚本调用方为准（如 CI yaml） | `ls scripts/ -d */` 输出 5 项；CI green | M |
| A6 | src 多包澄清 | `src/clientportal.gw/` → `vendor/clientportal.gw/`（明确 vendored）；`src/dags/` vs 根 `dags/` 二选一并删另一份；`src/bt_api_py/` 与 `src/backend/` 关系在 `src/README.md` 中显式说明（package / sub-package / vendored 哪种） | `src/README.md` 存在；CI 与文档 build 不破 | M |
| A7 | 缓存目录治理 | 删除 `.ruff_cache/{0.8.6,0.12.5,0.14.6,0.15.11}` 旧版本目录；`.gitignore` 补齐 `.ruff_cache`、`.mypy_cache`、`.pytest_cache`、`.benchmarks`、`htmlcov`、`coverage`、`.hypothesis` | `git ls-files \| grep -E '(ruff_cache\|mypy_cache\|pytest_cache)/' \| wc -l` = 0 | S |
| A8 | 锁文件治理 | 根目录 `requirements-{dev,prod}.lock` 角色与 `src/backend/pyproject.toml` 关系在 `CONTRIBUTING.md` "依赖管理" 节中明确：哪个是 SSOT、何时生成、谁可改 | `CONTRIBUTING.md` 含 1 节 "依赖管理"；`scripts/generate_lockfiles.sh` 文档化 | S |

### 2.2 验收 DoD

- 根目录可见项 ≤ 18 个（当前 30+）
- `ls scripts/` 显示 5 个分类目录 + 1 个 README.md，平铺脚本数 = 0（全归入子目录）
- `docker compose config` 在 5 套环境下均合法
- `git ls-files \| grep cache \| wc -l` 为 0
- 新克隆后跑 `./start_app.sh` 或 `./scripts/app.sh start` 行为完全等价

---

## 3. 主线 B · API / Service 子包化

### 3.1 后端 API 子包化（58 → ~25 入口）

| ID | 当前平铺文件 | 目标子包 | 验证 |
|---|---|---|---|
| B1 | `akshare_executions.py` + `akshare_interfaces.py` + `akshare_scripts.py` + `akshare_tables.py` + `akshare_tasks.py` | `app/api/akshare/{executions,interfaces,scripts,tables,tasks}.py` + `app/api/akshare/__init__.py` 聚合 router | API path 不变；`pytest tests/api/akshare/` 全绿 |
| B2 | `live_trading_api.py` + `live_trading_common.py` | `app/api/live_trading/{__init__.py,api.py,_shared.py}` | path 不变；shared 模块名以 `_` 开头表内部 |
| B3 | `strategy.py` + `strategy_explainer.py` + `strategy_score.py` + `strategy_version.py` | `app/api/strategy/{__init__.py,base.py,explainer.py,score.py,version.py}` | path 不变 |
| B4 | `portfolio_api.py` + `portfolio_ledger.py` | `app/api/portfolio/{api.py,ledger.py,__init__.py}` | path 不变 |
| B5 | `data.py` + `data_topics.py` + `data_governance.py` + `data_management_deps.py` + `realtime_data.py` | `app/api/data/{base.py,topics.py,governance.py,deps.py,realtime.py,__init__.py}` | path 不变；data_topics WebSocket 端点继续可达 |
| B6 | `deps.py` + `deps_permissions.py` | `app/api/_dependencies.py`（单文件聚合，permissions 作为子节）；`data_management_deps.py` 在 B5 中已归位 | 所有 `Depends(...)` 来源不变 |
| B7 | `auto_trading.py` + `ai_trading.py` + `live_trading_*` 关系梳理 | 在 `app/api/README.md` 中画 1 张领域图，标注 4 类 trading 入口的边界（paper / auto / ai / live） | README 与 routes 对照通过 review |
| B8 | router.py 重组 | `app/api/router.py` 中 import 由 58 行 → 按子包 import + 在子包 `__init__.py` 暴露 router；router.py 行数 ≤200 | `wc -l app/api/router.py` ≤ 200 |

### 3.2 后端 Service 子包化（92 → ~60 入口）

| ID | 当前平铺文件 | 目标子包 |
|---|---|---|
| B9 | `optimization_async_runner.py` + `optimization_execution_manager.py` + `optimization_submission.py` + `optimization_task_gateway.py` + `optimization_task_state.py` + `optimization_thread_runner.py` + `optimization_trial_runner.py`（共 7） | `app/services/optimization/{async_runner,execution_manager,submission,task_gateway,task_state,thread_runner,trial_runner}.py`；额外保留 `app/services/optimization/__init__.py` 暴露常用入口 |
| B10 | `gateway_health_service.py` + `gateway_launch_builder.py` + `gateway_preset_service.py` + `gateway_runtime_service.py` + `manual_gateway_service.py`（共 5） | `app/services/gateway/{health,launch_builder,preset,runtime,manual}.py`；注意 `manual_gateway/` 已被 173 A3 抽 utils，本轮把整族纳进同一根 |
| B11 | `akshare_data_service.py` + `akshare_execution_service.py` + `akshare_interface_loader.py` + `akshare_interface_service.py` + `akshare_scheduler_service.py` + `akshare_scheduler.py` + `akshare_script_service.py`（共 7） | `app/services/akshare/{data,execution,interface_loader,interface,scheduler_service,scheduler,script}.py` |
| B12 | `backtest_analyzers.py` + `backtest_manager.py` + `backtest_runner.py` + `backtest_service.py`（共 4） | `app/services/backtest/{analyzers,manager,runner,service}.py` |
| B13 | `live_execution_service.py` + `live_instance_service.py` + `live_trading_manager.py` + `live_trading_service.py`（共 4） | `app/services/live_trading/{execution,instance,manager,service}.py` |

### 3.3 main.py lifespan 拆分

| ID | 任务 | 目标 | 验证 |
|---|---|---|---|
| B14 | `app/main.py` 431 行 → 拆分 lifespan | 新建 `app/startup/` 子包：`{database,reconcile,audit_sink,ai_log_sink,orchestration,security_check}.py`；每个文件暴露 `async def register(app, settings) -> None`；`main.py` 仅遍历 register 链 | `main.py` ≤ 200 行；启动日志输出与 173 之前一致；`pytest tests/test_main_startup.py` 增加 6 个 sub-system 注册顺序断言 |

### 3.4 验收 DoD

- `ls app/api/ -d */` 输出至少 5 个子包目录（akshare/strategy/data/portfolio/live_trading）
- `ls app/services/ -d */` 输出至少 9 个子包目录（含 173 已有的 ai_observability/ai_router/data_connectors/factor_lib/market_regime/orchestration/overfitting/perf_attribution/prompt_registry/quote/risk_analytics/strategy_explainer/strategy_score/workspace/manual_gateway + 174 新加的 optimization/gateway/akshare/backtest/live_trading）
- 所有 FastAPI URL path 通过 `tests/test_openapi_path_stability.py` 对照 v0.2.0-rc1 baseline，0 破坏
- `wc -l app/api/router.py` ≤ 200；`wc -l app/main.py` ≤ 200
- `pytest` 全套测试与重组前对比 0 净下降

---

## 4. 主线 C · 大文件切片续作 & 前端拆分

### 4.1 后端 800 行硬线扫尾

> 173 已对 sync / manual_gateway / workspace / quote 切了首 1-2 刀；174 继续推到 800 行硬线以下，并把 173 范围外的其他 ≥800 行文件纳入。

**接续 173 的切片**

| ID | 文件 | 173 后预估行数 | 174 目标 | 切片建议 |
|---|---|---|---|---|
| C1 | `services/sync_service.py` | 2300 | ≤ 900 | 切片 2：抽 `sync/transport.py`（direct_mysql / ssh_docker 双适配器，统一 `SyncTransport` 协议）；切片 3：`sync/schema_diff.py`；切片 4：`sync/scheduler.py` |
| C2 | `services/manual_gateway_service.py`（或 173 后已落入 `services/manual_gateway/` 包） | 1500 | ≤ 600（拆为子包 4 个文件） | 切片 3：按 gateway family 分文件 `manual_gateway/{ib_clientportal,ctp,ccxt,mt5}.py` + façade；切片 4：`subprocess(["lsof"])` → `psutil` fallback |
| C3 | `services/workspace_service.py`（或 173 后已落入 `services/workspace/` 包） | 1000 | ≤ 500 | 切片 3：`workspace/units.py`；切片 4：`workspace/runtime.py`；切片 5：`workspace/optimization.py` |
| C4 | `services/quote_service.py`（或 173 后已落入 `services/quote/` 包） | 950 | ≤ 500 | 切片 3：façade 收薄到 ≤200 行；切片 4：补单测覆盖到 60%（173 已抽 runtime / symbols） |

**173 未覆盖的 ≥800 行文件**

| ID | 文件 | 当前行数 | 切片建议 | 工作量 |
|---|---|---|---|---|
| C5 | `services/strategy_service.py` | 1012 | 抽 `strategy/{crud,query,validation}.py` | M |
| C6 | `api/live_trading_api.py` | 998 | B2 已规划子包化；在子包内继续按 endpoint 类别拆分 | M |
| C7 | `services/log_parser_service.py` | 956 | 抽 `log_parser/{patterns,extractors,formatter}.py` | M |
| C8 | `services/backtest_service.py` | 926 | 抽 `backtest/{validate,prepare,run,collect}.py`；与 B12 协同 | M |
| C9 | `services/ai_trading_service.py` | 881 | 抽 `ai_trading/{intent,planner,executor}.py` | M |
| C10 | `api/workspace_api.py` | 862 | 拆为 `app/api/workspace/{crud,units,reports}.py` | M |
| C11 | `services/live_trading_manager.py` | 792 | 与 B13 协同，在子包内进一步分层 | S |
| C12 | `services/monitoring_service.py` | 789 | 抽 `monitoring/{collector,evaluator,reporter}.py` | M |
| C13 | `services/paper_trading_service.py` | 775 | 临界点，留作可选；如已被 173 拉到 770 以下不强制 | S |
| C14 | `services/strategy_version_service.py` | 772 | 临界点，可选 | S |
| C15 | `services/rag_service.py` | 762 | 抽 `rag/{retriever,chain,prompt}.py` | M |

### 4.2 前端超大 .vue 拆分

> 单文件 ≥1000 行硬性拆分；500-1000 行拆分为 "强烈建议"。AGENTS.md / 173 已确立单文件 ≤500 行目标。

| ID | 文件 | 当前行数 | 拆分建议 |
|---|---|---|---|
| C16 | `views/KnowledgeBasePage.vue` | 1777 | 173 B3 已规划；174 收尾：抽 `composables/useKnowledgeBaseList.ts` / `useKnowledgeBaseSearch.ts`；子组件 `components/kb/{Sidebar,Editor,DocumentList,RetrievalConfig,ChatPanel}.vue` |
| C17 | `views/AIChatPage.vue` | 1505 | 173 B2 已规划；174 收尾 |
| C18 | `components/workspace/WorkspaceOptimizationTab.vue` | 1502 | 拆 `OptimizationConfigForm.vue` / `OptimizationResultsGrid.vue` / `OptimizationProgress.vue` + `useOptimizationRunner.ts` |
| C19 | `views/GatewayStatusPage.vue` | 1357 | 拆 `GatewayList.vue` / `GatewayDetail.vue` / `GatewayLogPanel.vue` + `useGatewayStatus.ts` |
| C20 | `components/workspace/WorkspaceUnitsTab.vue` | 1268 | 拆 `UnitTable.vue` / `UnitDetailDrawer.vue` / `UnitActionsBar.vue` + `useUnitsList.ts` |
| C21 | `views/QuotePage.vue` | 1183 | 拆 `QuoteSearchBar.vue` / `QuoteMatrix.vue` / `QuoteDetailPanel.vue` + `useQuoteSubscription.ts` |
| C22 | `components/workspace/WorkspaceReportTab.vue` | 1157 | 拆 `ReportSummary.vue` / `ReportCharts.vue` / `ReportExport.vue` + `useReportData.ts` |
| C23 | `views/AITradingPage.vue` | 860 | 拆 `AITradingControlPanel.vue` / `AITradingLog.vue` / `AITradingDiagnostics.vue` |
| C24 | `views/data/DataSyncPage.vue` | 851 | 拆 `SyncTaskList.vue` / `SyncDetailPanel.vue` |
| C25 | `components/workspace/TradingWorkspaceUnitsTab.vue` | 831 | 与 C20 共享 `UnitTable.vue` 抽出后受益 |

### 4.3 前端测试目录双轨统一

| ID | 任务 | 验证 |
|---|---|---|
| C26 | `src/frontend/src/test/{components,views,stores,utils,api,i18n,router,composables,styles}/` 与 colocated `__tests__/` 双轨 → 统一到 colocated `__tests__/` | 移完后 `find src/frontend/src/test -type f \| wc -l` = 0；`npm run test -- --run` 全绿 |

### 4.4 验收 DoD

- 后端 `find src/backend/app -name '*.py' \| xargs wc -l \| awk '$1>800 {print}'` 输出文件数 ≤ 2（仅允许 `__init__.py` 或 generated 文件超线）
- 前端 `find src/frontend/src -type f -name '*.vue' \| xargs wc -l \| awk '$1>500 {print}'` 输出文件数 ≤ 4
- 单文件最大行数：后端 ≤ 900，前端 ≤ 600
- `src/test/` 全空或已删除

---

## 5. 主线 D · 文档治理

### 5.1 docs/ 51 平铺 → Diátaxis 分层

**目标结构**（参考 https://diataxis.fr/）：

```
docs/
├── tutorials/       # 新手入门：QUICKSTART.md / QUICKSTART_EN.md
├── how-to/          # 解决具体任务：AIRFLOW_SETUP.md / deployment guides / certbot setup
├── reference/       # 查阅式：API_REFERENCE_EN.md / DATABASE.md / CODING_STANDARDS.md / DESIGN_SYSTEM.md / REQUEST_SCOPED_SESSION.md / SECURITY.md
├── explanation/     # 为什么：ARCHITECTURE.md / MARKET_RESEARCH.md / INNOVATION_STRATEGY.md / CENTENNIAL_VISION.md / STRATEGIC_ROADMAP.md / TECHNICAL_RESEARCH.md / IMPROVEMENT_ROADMAP.md / REFACTORING_BACKLOG.md / PRODUCT_BRIEF.md
├── adr/             # 已存在
├── iterations/      # 已存在
├── operations/      # 已存在
├── guides/          # 已存在 → 内容并入 how-to/ 或 reference/
├── plans/           # 已存在 → 评估归并到 iterations/ 或 explanation/
├── reports/         # 已存在
├── strategies/      # 已存在
├── contracts/       # 已存在
└── assets/          # 新增：4 张 tbquant_screen_*.png + tbquant_screenshots/ 整体迁入
```

| ID | 任务 | 验证 |
|---|---|---|
| D1 | 按上表迁移 51 个平铺文件到 5 个分类目录 + assets/ | `ls docs/ \| grep -v / \| wc -l` ≤ 5（仅 README/INDEX/CHANGELOG/mkdocs.yml/CNAME） |
| D2 | 更新 `docs/INDEX.md` 反映新结构 + 每个分类目录加 README.md | 每个子目录 README.md 至少 1 页 |
| D3 | `docs/CHANGELOG.md` vs 根 `CHANGELOG.md` 二选一 | 保留根目录，docs/ 内改为 1 行 forward 链接 |
| D4 | `mkdocs.yml` 同步新目录结构 | `mkdocs build` 0 warning |
| D5 | `docs/requirements.txt`（文档自身依赖）澄清是否还在用，否则归并到 docs/how-to/ 内或删除 | mkdocs 构建仍通过 |
| D6 | 截图整理：4 张 `tbquant_screen_*.png` + `tbquant_screenshots/` 迁入 `docs/assets/` | 所有引用路径同步更新 |

### 5.2 设计系统 v0.2（173 输出规范，174 落地）

| ID | 任务 | 验证 |
|---|---|---|
| D7 | 按 173 B5 输出的 `DESIGN_SYSTEM.md` v0.1 规范，落地全站按钮（primary/secondary/danger/ghost）统一 | grep `<el-button` 使用 props 而非自定义 class；视觉回归 4 个基线页面 0 diff |
| D8 | 字号 token 化 + 落地（h1/h2/h3/body/caption 五级） | tailwind config 中定义 `text-display / text-headline / text-body / text-caption`；硬编码 `font-size` 出现次数 ≤ 5 |
| D9 | 卡片组件统一 | 抽 `components/common/BaseCard.vue`；全站 `<div class="card">` 改为 `<BaseCard>`；至少替换 30 处 |

### 5.3 验收 DoD

- `docs/` 根级文件 ≤ 5
- `mkdocs build` 0 warning
- `grep -RE 'font-size: ' src/frontend/src \| wc -l` ≤ 5
- 全站 BaseCard 替换 ≥ 30 处

---

## 6. 流程线 E · 173 残项收口

### 6.1 任务卡

| ID | 任务 | 来源 | 验证 |
|---|---|---|---|
| E1 | AI Prompt 治理后半段 | 167 残项；173 §4.2 明确推到 174 | 至少 3 类 Prompt 走 registry（KB Chat、Strategy Copilot、Risk Advisor）；CI lint 强制 prompt 注册 |
| E2 | 前端覆盖率二级棘轮 | 173 C5 已 45/50/55，174 → 60/65/65 | `vitest.config.ts` 阈值更新；CI 红线 |
| E3 | Docker Hub 发版自动化 | 173 §1.2 明确不做，留 174 | GitHub Actions release workflow 推 `cloudquant/backtrader-web:v0.2.x` tag |
| E4 | 173B（FinceptTerminal T2/T7/T10）收口对齐 | 见 `迭代173B-171残项独立收口摘要.md` | 174 不直接做 T2/T7/T10，但需在 §10 给出明确的下批承接（175 或 173B 独立线） |
| E5 | `REFACTORING_BACKLOG.md` 同步 | backlog 中本轮承诺消化的条目直接删除（173 D4 已建立此规范） | 删除 §3.1 全部 C1-C15 对应 backlog 条目 + §3 / §4 子包化对应条目 |
| E6 | `iterations/README.md` 更新 | 173 收口、174 在列、175 候选预告 | README 表格中 174 行存在；173 标记 "已完成"（前置） |

### 6.2 验收 DoD

- Prompt registry 覆盖 ≥3 类对话路径
- 前端覆盖率 lines/functions/branches 均 ≥60
- Docker Hub `latest` 与 `v0.2.x` tag 在 release 发布后 ≤10 分钟可拉到
- backlog 中本轮承诺条目已删除
- iterations README 状态准确

---

## 7. 全局验收门 / SLO

| 维度 | 量化指标 | 测量方法 |
|---|---|---|
| 仓库骨架 | 根目录可见项 ≤ 18 | `ls /Users/yunjinqi/Documents/new_projects/backtrader_web \| wc -l` |
| scripts 分层 | scripts/ 子目录 = 5，平铺 .py/.sh = 0 | `find scripts/ -maxdepth 1 -type f \| wc -l` |
| API 子包化 | `app/api/` 平铺文件数 ≤ 25 | `ls app/api/*.py \| wc -l`（不含子包内文件） |
| Service 子包化 | `app/services/` 平铺文件数 ≤ 50 | `ls app/services/*.py \| wc -l` |
| 后端 800 行硬线 | ≥ 800 行 .py 文件数 ≤ 2 | `find app -name '*.py' \| xargs wc -l \| awk '$1>800' \| wc -l` |
| 前端 500 行典型线 | ≥ 500 行 .vue 文件数 ≤ 4 | `find src/frontend/src -name '*.vue' \| xargs wc -l \| awk '$1>500' \| wc -l` |
| 文档分层 | docs/ 根级文件 ≤ 5 | `ls docs/ -p \| grep -v / \| wc -l` |
| 双轨测试 | `src/frontend/src/test/` 文件数 = 0 | `find src/frontend/src/test -type f \| wc -l` |
| 覆盖率 | 前端 lines/functions/branches 均 ≥ 60% | `npm run test -- --run --coverage` |
| 启动膨胀 | `app/main.py` ≤ 200 行 | `wc -l src/backend/app/main.py` |
| 兼容性 | OpenAPI path 0 破坏 | `pytest tests/test_openapi_path_stability.py` |
| CI 绿 | 全套测试通过 | `pytest && npm run test -- --run && npm run typecheck && ruff check && mypy app/api app/utils app/schemas` |

---

## 8. 推荐切片顺序（6 周）

> 切片原则：**先骨架（A）→ 再子包（B）→ 同步切大文件（C）→ 文档（D）→ 残项（E）**。
> 每两周做一次 mid-iteration retro，按风险调整顺序。

### 第 1 周 · 仓库骨架精简（A 主线）
- A1（compose 收敛）
- A2（启动脚本归一）
- A3（根目录残留清理）
- A7（缓存目录治理）
- A8（锁文件治理文档）
- E6（iterations README 更新）

### 第 2 周 · 骨架收尾 + B 启动
- A4（运行时目录隔离）
- A5（scripts 64 个分层）
- A6（src 多包澄清）
- B1（akshare API 子包化）
- B2（live_trading API 子包化）
- B14（main.py lifespan 拆分） ← 早做，给后续 startup 子系统统一入口

### 第 3 周 · API/Service 子包化主体
- B3 / B4 / B5 / B6（strategy / portfolio / data / deps API 子包化）
- B7 / B8（trading 边界文档 + router 重组）
- B9 / B10（optimization / gateway service 子包化）
- C1（sync_service 切片 2/3/4）
- C5（strategy_service 切片）

### 第 4 周 · Service 子包化收尾 + 大文件切片
- B11 / B12 / B13（akshare / backtest / live_trading service 子包化）
- C2（manual_gateway 切片 3/4）
- C3（workspace 切片 3/4/5）
- C7 / C8 / C9（log_parser / backtest / ai_trading 切片）
- C26（前端测试双轨统一）

### 第 5 周 · 前端拆分 + 文档治理
- C16 / C17 / C18 / C19 / C20（前端 5 个 ≥1000 行 .vue 拆分）
- D1 / D2 / D3 / D4 / D5 / D6（docs Diátaxis 重组）
- E1（Prompt 治理）

### 第 6 周 · 收尾 + 残项 + 验收
- C21 / C22 / C23 / C24 / C25（前端剩余拆分）
- C4 / C6 / C10 / C11 / C12 / C14 / C15（后端剩余切片）
- D7 / D8 / D9（设计系统 v0.2 落地）
- E2 / E3 / E4 / E5（覆盖率 / Docker Hub / 173B 对齐 / backlog 同步）
- 全量回归 + 验收门检查

---

## 9. 风险与降级路径

| 风险 | 概率 | 影响 | 降级路径 |
|---|---|---|---|
| 子包化破坏第三方 import（如 `from app.services.optimization_async_runner import ...`） | 高 | 中 | 所有原模块保留 1 个迭代周期的 re-export shim（如 `from app.services.optimization.async_runner import *`），并在 CHANGELOG 标记 Deprecation；175 收尾再删 |
| `src/clientportal.gw/` 移到 `vendor/` 时漏改 docker-compose / Dockerfile 中的 COPY 路径 | 中 | 高 | A6 PR 必须同时改 compose / Dockerfile，并跑 `docker compose build` 验证；rollback：保留 `src/clientportal.gw/` 符号链接 1 个迭代 |
| 运行时目录迁移到 `var/` 破坏既有数据库/策略文件路径 | 中 | 高 | A4 PR 含 1 个 migration 脚本，从旧路径软链或迁移到新路径；env var `APP_RUNTIME_DIR` 优先读取，向后兼容旧默认值 |
| docs 大规模迁移破坏外部链接（GitHub Pages / 第三方文章引用） | 中 | 中 | D1 在 `mkdocs.yml` 配置 redirect 插件；保留 `docs/_redirects` 表 |
| 前端 .vue 拆分破坏组件 prop 协议 | 中 | 高 | 每个 C16-C25 任务先补 e2e smoke（核心交互流），再拆分；commit-by-commit 等量替换 |
| 工作量估算偏乐观，6 周做不完 | 中 | 中 | 第 4 周末做 mid-iteration checkpoint；优先牺牲顺序：C13/C14（临界点）→ D8/D9（设计系统 v0.2 细化）→ C21-C25 部分 → E3（Docker Hub）。E2 / E5 / D1 不可降级 |
| 多人同时改大文件冲突 | 高 | 中 | 按 A→B→C→D→E 主线串行 + 同主线内按 ID 顺序 serialize；同一文件同一天最多 1 个开发者，PR 不超过 24h merge 窗 |
| 锁文件治理改动 CI 依赖 | 低 | 高 | A8 仅做文档化，不动 `generate_lockfiles.sh` 行为；如需改 lock，单独 RFC |
| 173 主线未完全收口就开始 174 | 高 | 高 | 174 第 0 周（启动前）由 PM 检查 173 §6 全局验收门是否全绿；任何一项不绿则 174 启动延后或抽出冲突项 |

---

## 10. 后续接续（175 候选）

本迭代收口后会留下的下一批债，明确登记为 175 候选，**不在 174 内做**：

- 173B（FinceptTerminal T2 / T7 / T10）独立线收口（如未在 174 期间独立完成）
- 前端覆盖率三级棘轮（60 → 75）
- 后端 mypy 扩盘到 `app/services`（173 已扩到 `app/api + app/utils + app/schemas`）
- `bt_api_py` 与 `backend` 的 monorepo 工具化（uv workspace 或 pnpm workspace 等价）
- 全站 A11y 审计（WCAG 2.1 AA 基线）
- 全站国际化（i18n）覆盖率达 100%，目前 zh-CN/en-US 双语 ≥80%
- 后端 OpenTelemetry 全链路追踪（173 仅做 AI sink，未覆盖 backtest / live_trading）
- 数据库 schema migration 自动化（alembic 多分支合并工具）
- 前端 vendor split + bundle size 棘轮（lighthouserc.js 已存在但未启用 CI gate）
- 整站 e2e smoke 上 CI（目前 `npm run test:e2e` 仍为人工触发）

---

## 11. 输入文档索引

阅读本计划时建议交叉参考：

- `docs/iterations/迭代173-工程债收口与设计系统统一/index.md` — 上一轮工程债收口基线（**必读**）
- `docs/iterations/迭代173B-171残项独立收口摘要.md` — 173B 独立线（与 174 E4 协同）
- `docs/REFACTORING_BACKLOG.md` — 工程债总账（174 E5 会清理本轮承诺条目）
- `docs/iterations/README.md` — 迭代历史索引
- `docs/CODING_STANDARDS.md` — 编码规范基线
- `AGENTS.md` — AI 代理工作约束（含命令重试规则、风格规则）
- `CONTRIBUTING.md` — 贡献规范（A8 会补依赖管理节）
- `docs/ARCHITECTURE.md` — 架构现状
- `docs/perf-baseline-v0.2.0.md` — 性能基线（174 不改基线，作为对照参考）
- `CHANGELOG.md` — v0.2.0-rc1 Known Boundaries

---

## 12. 交接清单（移交执行团队前）

> 本计划由原项目所有者起草，准备移交给外部团队执行。以下清单是移交前必须确认的项：

- [ ] 173 §6 全局验收门是否已全绿？任何一项未绿都需要先标记为 174 启动前置条件
- [ ] 174 §6 中 E4（173B 对齐）的归属是否清晰：是 174 内做、175 内做、还是独立 173B 线做？
- [ ] §1.2 "不做" 列表是否已对齐项目所有者预期？特别是 broker 适配、新功能、数据库 schema 三项
- [ ] §7 全局 SLO 中所有"测量方法"命令是否在本机可执行通过？
- [ ] §8 推荐切片顺序与执行团队的 sprint 节奏是否匹配（2 周 sprint × 3 期 = 6 周）
- [ ] §9 风险表中"7 多人冲突"是否已经与执行团队 agreed 串行约定
- [ ] 执行团队是否有权限：① 改 `pyproject.toml` ② 改 `mkdocs.yml` ③ 改 GitHub Actions ④ 改 docker-compose ⑤ 改 `.gitignore`？任何一项受限都需提前协商
- [ ] 执行期间的 PR review 路径是否明确：是项目所有者 review、还是执行团队内部互 review？
- [ ] 174 的 mid-iteration retro 时点（推荐第 2、4 周末）是否纳入双方日历

---

## 13. 评审清单（提交合并前）

- [ ] §0.1 证据表中所有命令是否仍能复现（项目状态在 174 启动时可能已变）？
- [ ] §1.2 "不做" 项是否仍然成立，未被悄悄越界？
- [ ] §7 SLO 每一行是否都有可执行的测量命令？
- [ ] §9 风险表是否覆盖了每一条主线的最大风险？
- [ ] §8 切片顺序是否与 git log 实际开发节奏匹配？
- [ ] backlog 中本轮承诺消化的条目，是否已在 §6 E5 中映射到 C/B 系列任务卡？
- [ ] 175 候选清单（§10）是否清晰，避免下轮再次返工讨论"到底该不该做"？
- [ ] 与 173 是否存在重复工作？特别是 manual_gateway / sync / workspace / quote 切片的 173 收口范围是否已确认
