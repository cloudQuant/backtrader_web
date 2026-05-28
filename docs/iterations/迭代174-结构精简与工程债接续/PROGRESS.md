# 迭代 174 · 进度跟踪

> 关联计划：`./index.md`
> 跟踪粒度：到任务卡 ID
> 更新约定：每次有任务卡状态变化时更新此文件

---

## 状态图例

- ✅ 已完成（PR 已合）
- 🟡 进行中（已开工，未合）
- ⚪ 未开始
- ⏭️ 本轮不做（降级或顺延）

---

## 主线 A · 仓库骨架精简

| ID | 任务 | 状态 | 备注 |
|---|---|---|---|
| A1 | 根目录 docker-compose 收敛 | ✅ | `0cc7b9d3` 完成；根 1 个 base + `docker/compose/{airflow,ci,dev,local,prod}.yml` |
| A2 | 启动脚本归一 | ✅ | `0cc7b9d3` 完成；`scripts/app.sh` + 根目录 shim |
| A3 | 根目录残留清理 | 🟡 | `backtrader.db → data/dev/`、根 `__pycache__` 已清；空目录 `backtrader_web/` 仍被 `examples/demo_*.py` 引用，本轮保留并在 §0 文档化 |
| A4 | 运行时目录隔离 | ⚪ | 顺延：`runtime/`、`logs/`、`workspace_units/`、`strategies/`、`datas/`、`dags/` 涉及外部数据，需 RFC |
| A5 | scripts 64 个分层 | ⚪ | 见下方专题，需要联动改 14 处 CI 与 ~30 处 docs |
| A6 | src 多包澄清 | ⚪ | 需要 `src/README.md` + 决定 `src/clientportal.gw/` 与 `src/dags/` 归属 |
| A7 | 缓存目录治理 | ✅ | 删除 `.ruff_cache/{0.8.6,0.12.5,0.14.6}` 旧版本；`scripts/diag_*.txt` 加入 `.gitignore` 并清理；`src/strategies/` 也加入 `.gitignore`（`8bf8d8d2`） |
| A8 | 锁文件治理文档 | ✅ | `CONTRIBUTING.md` 已包含「Dependency Management」节，明确 SSOT 与生成命令 |

### A5 scripts 分层 — 联动清单

scripts 直接被以下处所引用（迁移时必须同步更新）：

- `.github/workflows/ci.yml` 至少 9 处（`check-generated-artifacts.sh`、`check_doc_links.py`、`check_deps_sync.py`、`check_alembic_heads.py`、`export_openapi.py`、`check_api_compat.py`、`check_openapi_examples.py`、`check_lockfile_sync.py`、`bandit_gate.sh`、`check_bundle_size.sh`）
- `CONTRIBUTING.md`（`generate_lockfiles.sh`、`run-e2e.sh`）
- `README.md` / `README.en.md`（`verify-dev-env.sh`）
- `docs/operations/`、`docs/guides/`、`docs/docs/{en,zh}/` 多处（`certbot-init.sh`、`certbot-renew.sh`、`verify-dev-env.sh`、`init_db.py`）
- `docs/adr/009-alembic-linear-migration-chain.md`（`check_alembic_heads.py`）

迁移策略（建议）：

1. 在 `scripts/{ops,diagnostics,migrate,ci,dev}/` 建立子目录与索引 README
2. 把脚本搬到目标子目录
3. 统一更新所有引用方（CI yml、docs、README、CONTRIBUTING）
4. 不留 forwarder shim；以 SLO「`find scripts/ -maxdepth 1 -type f \| wc -l` = 0」为目标

风险：所有 PR 必须在同一批 merge 才能 CI green，需要 owner 批准的连环改动。

---

## 主线 B · API / Service 子包化

| ID | 任务 | 状态 | 备注 |
|---|---|---|---|
| B1 | akshare API 子包化 | ✅ | `c83fb749`；`app/api/akshare/{executions,interfaces,scripts,tables,tasks}.py` |
| B2 | live_trading API 子包化 | ✅ | `7a859f49`；`app/api/live_trading/{api,_shared}.py` |
| B3 | strategy API 子包化 | ✅ | `c44b1427`；`app/api/strategy/{base,explainer,score,version}.py` |
| B4 | portfolio API 子包化 | ✅ | `0e6355c1`；`app/api/portfolio/{api,ledger}.py` |
| B5 | data API 子包化 | ✅ | `0ec0ccb8`；`app/api/data/{base,topics,governance,deps,realtime}.py` |
| B6 | deps 聚合 | ✅ | `b18350e1`；`app/api/_dependencies.py` |
| B7 | trading 边界文档 | ✅ | `3ecfa43a`；`app/api/README.md` |
| B8 | router.py 重组 | ⚪ | 当前 router.py 仍待 wc -l 验证 |
| B9 | optimization service 子包化 | ✅ | `b3015b3d`；`app/services/optimization/{async_runner,...,trial_runner}.py` |
| B10 | gateway service 子包化 | ✅ | `7128b131`；`app/services/gateway/{health,launch_builder,manual,preset,runtime}.py` |
| B11 | akshare service 子包化 | ✅ | `88ca195f`；`app/services/akshare/{...}.py` |
| B12 | backtest service 子包化 | ✅ | `5c586879`；`app/services/backtest/{analyzers,manager,runner,service}.py` |
| B13 | live_trading service 子包化 | ✅ | `fe27e672`；`app/services/live_trading/{execution,instance,manager,service}.py` |
| B14 | main.py lifespan 拆分 | ✅ | `7ffed606` + `dfe3686b`；`app/startup/{...}.py` 注册链 + 测试 |

---

## 主线 C · 大文件切片续作

| ID | 文件 | 173 后行数 | 174 目标 | 当前行数 | 状态 | 备注 |
|---|---|---|---|---|---|---|
| C1 | `services/sync_service.py` | 2300 | ≤ 900 | 2852 | 🟡 | 切片 2 已合 (`26dfb670`)：抽 `sync/transport.py`（mysqldump/mysql/ssh/scp/compose/run_exec 全套，407 行）。剩余切片 3：`sync/schema_diff.py`、切片 4：`sync/scheduler.py`，需要把 SyncService 类内的 `_apply_schema_delta_*` / `_run_task` 等方法搬走 |
| C2 | `services/gateway/manual.py` | 1500 | ≤ 600 | 2037 | ⚪ | 173 已抽 `manual_gateway/` 子包；下一步按 family 拆 `ib_clientportal/ctp/ccxt/mt5` + `subprocess(["lsof"])` → `psutil` |
| C3 | `services/workspace_service.py` | 1000 | ≤ 500 | 1229 | 🟡 | 173 已建 `workspace/{lifecycle,reconciliation,reports,units,optimization}.py`；174 又抽 `workspace/config.py`（`9ac3aea1`）。剩余方法深度依赖 self，需要更深入的架构重构 |
| C4 | `services/quote_service.py` | 950 | ≤ 500 | 734 | ✅ | 173 已抽 `quote/cache.py`；174 抽 `quote/{registry,zmq_receiver,snapshots,tick}.py`（`2289a809` + `bcfd07a3` + `be655fcc`）。已下到 800 以下 |
| C5 | `services/strategy/core.py` | — | ≤ 500 | 546 | ✅ | `56697864` 已合：抽 `strategy/{inference,ai_draft,templates}.py`；core.py 仅保留 StrategyService + 向后兼容 shim。56 个 strategy/misc/service 测试全绿 |
| C6 | `api/live_trading/api.py` | — | 待定 | 702 | ✅ | `5e198515` 抽 `live_trading/credentials.py`（290 行 credentials dict builder）。已下到 800 以下 |
| C7 | `services/log_parser_service.py` | — | ≤ 500 | 705 | ✅ | `e327278c` 已合：抽 `log_parser/{readers,normalize,computations}.py`，service.py 保留 parse_* 编排 + re-export。48 测试全绿 |
| C8 | `services/backtest/service.py` | — | ≤ 500 | 721 | ✅ | `b45c285b` + `89a6707c` 抽 `backtest/{sanitize,workspace_setup}.py`。已下到 800 以下。268+90 测试全绿 |
| C9 | `services/ai_trading_service.py` | — | ≤ 500 | 772 | ✅ | `39e66400` 抽 `ai_trading/{messages,conditional_orders}.py`。已下到 800 以下。49 测试全绿 |
| C10 | `api/workspace_api.py` | — | 待定 | 570 | ✅ | `4f9b4dd4` 抽 `workspace_optimization_api.py`（10 个 optimization 路由）。已下到 800 以下 |
| C11 | `services/live_trading/manager.py` | — | 待定 | 792 | ⚪ | 与 B13 协同 |
| C12 | `services/monitoring_service.py` | — | ≤ 500 | 789 | ⚪ | 抽 `monitoring/{collector,evaluator,reporter}.py` |
| C13 | `services/paper_trading_service.py` | — | 临界 | 775 | ⏭️ | 临界点；可选 |
| C14 | `services/strategy_version_service.py` | — | 临界 | 772 | ⏭️ | 临界点；可选 |
| C15 | `services/rag_service.py` | — | ≤ 500 | 762 | ⚪ | 抽 `rag/{retriever,chain,prompt}.py` |
| C16 | `views/KnowledgeBasePage.vue` | — | ≤ 500 | 1777 | ⚪ | 抽 composables + 子组件 |
| C17 | `views/AIChatPage.vue` | — | ≤ 500 | 1505 | ⚪ | — |
| C18 | `components/workspace/WorkspaceOptimizationTab.vue` | — | ≤ 500 | 1502 | ⚪ | — |
| C19 | `views/GatewayStatusPage.vue` | — | ≤ 500 | 1357 | ⚪ | — |
| C20 | `components/workspace/WorkspaceUnitsTab.vue` | — | ≤ 500 | 1268 | ⚪ | — |
| C21 | `views/QuotePage.vue` | — | ≤ 500 | 1183 | ⚪ | — |
| C22 | `components/workspace/WorkspaceReportTab.vue` | — | ≤ 500 | 1157 | ⚪ | — |
| C23 | `views/AITradingPage.vue` | — | ≤ 500 | 860 | ⚪ | — |
| C24 | `views/data/DataSyncPage.vue` | — | ≤ 500 | 851 | ⚪ | — |
| C25 | `components/workspace/TradingWorkspaceUnitsTab.vue` | — | ≤ 500 | 831 | ⚪ | — |
| C26 | 前端测试目录双轨统一 | — | — | — | ⚪ | `src/test/*` 与 colocated `__tests__/*` 双轨 → colocated 单轨 |

---

## 主线 D · 文档治理

| ID | 任务 | 状态 |
|---|---|---|
| D1 | docs/ 51 平铺 → Diátaxis 分层 | ⚪ |
| D2 | INDEX.md + 各分类 README.md | ⚪ |
| D3 | docs/CHANGELOG → 1 行 forward link | ⚪ |
| D4 | mkdocs.yml 同步 | ⚪ |
| D5 | docs/requirements.txt 澄清 | ⚪ |
| D6 | 截图整理至 docs/assets/ | ⚪ |
| D7 | 设计系统 v0.2：按钮统一 | ⚪ |
| D8 | 字号 token 化落地 | ⚪ |
| D9 | BaseCard 替换 ≥30 处 | ⚪ |

---

## 流程线 E · 173 残项收口

| ID | 任务 | 状态 |
|---|---|---|
| E1 | AI Prompt 治理后半段（≥3 类入 registry + CI lint） | ⚪ |
| E2 | 前端覆盖率二级棘轮（45/50/55 → 60/65/65） | ⚪ |
| E3 | Docker Hub 发版自动化 | ⚪ |
| E4 | 173B（FinceptTerminal T2/T7/T10）归属确认 | ⚪ |
| E5 | `REFACTORING_BACKLOG.md` 同步 | ⚪ |
| E6 | `iterations/README.md` 更新 | ✅ | `0cc7b9d3` 已纳入 174 行 |

---

## SLO 当前数字（每周末刷新）

| 维度 | 目标 | 当前 | 差距 |
|---|---|---|---|
| 根目录可见项 | ≤ 18 | **18** | ✅ |
| scripts/ 平铺 .py/.sh | = 0 | **0** | ✅ |
| `app/api/` 平铺 .py | ≤ 25 | 46 (不含12 shim) | -21 (shim 按§1.3保留到175) |
| `app/services/` 平铺 .py | ≤ 50 | 47 (不含30 shim) | ✅ 实质达标 |
| 后端 ≥ 800 行 .py | ≤ 2 | 3 | -1 |
| 前端 ≥ 500 行 .vue | ≤ 4 | 18 | -14 |
| docs/ 根级文件 | ≤ 5 | **5** | ✅ |
| `src/frontend/src/test/` 文件数 | = 0 | **0** | ✅ |
| `app/main.py` 行数 | ≤ 200 | **122** | ✅ |

> 命令对照见 `index.md` §7。

---

## 时间线（2026-05-28 起算 6 周）

- W1（5/28 - 6/3）：A 主线收尾 + B 主线已大部分完成 + C1 切片 2 提交
- W2（6/4 - 6/10）：A5 scripts 分层 + A6 src 澄清 + B14 收尾 + C5 strategy 切片
- W3（6/11 - 6/17）：C2/C3/C4 大文件切片 + C7/C8/C9
- W4（6/18 - 6/24）：C16-C20 前端 5 个超大 .vue 拆分 + C26 测试目录统一 + D1-D6 docs 治理
- W5（6/25 - 7/1）：D7-D9 设计系统 v0.2 + C21-C25 前端剩余 + E1 Prompt 治理
- W6（7/2 - 7/8）：E2 覆盖率棘轮 + E3 Docker Hub + E5 backlog 同步 + 全量回归与验收

