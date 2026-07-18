# 迭代 183 - 安全授权收口与巨型文件分解及质量债续拧

> **创建日期**: 2026-07-17
> **来源方法**: `bmad-help` 定位 + 5 路并行静态扫描（后端质量 / 后端安全 / 前端质量 / 测试与 CI / 可观测性与仓库卫生）+ 既有迭代 175-182 基线复核
> **性质**: 安全授权 P0 收口 / god 文件分解 / 棘轮续拧与版本对齐 / 仓库卫生治理 / 非产品新功能
> **沟通语言**: 中文；代码、命令和配置名保留英文
> **上一轮**: 迭代 181（BMAD 代码质量与安全优化，2026-06-16）；其间一个月新增研究工作流、IB 网关双交易所压测、e2e 套件、AI trust/live gate

---

## 0. 一句话目标

在 181 已收口 sync 密码、v-html sanitizer、生产 `as any`、i18n baseline-gated 的基础上，优先堵住本轮新发现的**实盘越权与凭据外泄安全洞**，把**两个灾难级 god 文件**（`ai_strategy_research_service.py` 12206 行 / `StrategyPage.vue` 10471 行）开出可回归测试的切片，修复**失效的棘轮**（mypy 版本三向错配、npm audit 不阻断、181-G 文件不降反升），并清理**仓库卫生**与 **181 残项**。

---

## 1. BMAD Help 定位

本次按 `.kiro/skills/bmad-help/SKILL.md` 的数据源规则读取了：

- `.kiro/bmad/_config/bmad-help.csv`（技能清单与阶段）
- `.kiro/bmad/config.toml` / `.kiro/bmad/_config/config.yaml`（模块配置）
- `.kiro/bmad/output/code-review-adversarial-findings.md`（2025-03-10，已过时）
- `.kiro/bmad/output/test-artifacts/test-review.md`（2026-02-24，已过时）
- `.kiro/bmad/output/test-artifacts/ci-pipeline-progress.md`（2026-03-07，已过时）
- `.kiro/bmad/output/implementation-artifacts/sprint-status.yaml`（epic-1/2 done）

结论：

| 项 | 当前状态 |
| --- | --- |
| BMAD 模块 | `BMad Method` + `Test Architecture Enterprise` + `Core` 均已安装 |
| 当前阶段 | implementation / quality assurance 后段；既有 epic 已 done，适合做代码审查、NFR 安全评估、测试审查和下一轮 sprint planning |
| 已有产物 | PRD、Architecture、Epics、Readiness、Adversarial Code Review、Test Review、CI Progress、Sprint Status（均 2-5 个月前，需刷新） |
| 输出语言 | `communication_language = Chinese` |
| 下一步建议 | 本计划作为新迭代；实施前建议在新上下文运行 `[CR] bmad-code-review` 聚焦 183-A 安全改动与 183-B/C 切片；安全验收前运行 `bmad-testarch-nfr`；切片后运行 `[ECH] bmad-review-edge-case-hunter` 聚焦 IDOR 与异常吞没边界 |

> 注意：BMAD `config.toml` 的 `output_folder` 仍指向不存在的 `{project-root}/_bmad-output`，实际产物在 `.kiro/bmad/output/`。这是 181-H 残项，在 183-I 收口。

---

## 2. 本轮扫描摘要

5 路并行扫描覆盖 `src/backend/app/`、`src/backend/scripts/`、`src/backend/tests/`、`src/frontend/src/`、`tests/e2e/`、`src/frontend/e2e/`、`.github/workflows/`、`scripts/`、根目录与 `.gitignore`。排除 `node_modules`、`.venv*`、`workspace_units/`、vendored 数据抓取脚本噪音。

### 2.1 关键证据

| 类别 | 实测证据 | 判断 |
| --- | --- | --- |
| 实盘越权 | `api/live_trading/api.py:340` `start_instance`、`:367` `stop_instance` 不传 `user_id`；`manager.py:925,944` 签名无 user_id；同文件 `get_instance`/`remove_instance` 都传了 user_id | 🔴 任意认证用户可启停他人实盘实例 |
| 凭据外泄 | `api/live_trading/api.py:101` `get_gateway_credentials` 仅 `get_current_user`（非 admin）；`credentials.py:43-321` 明文返回 CTP/MT5/IB/Binance/OKX 全部密码与 API Key | 🔴 多用户下任意用户可一次性窃取全部券商凭据 |
| 无认证 WS | `api/data/realtime.py:224` `/ws/ticks/{broker_id}`、`api/monitoring.py:423` `/ws/alerts`、`api/strategy/version.py:508` `/ws/strategies/{strategy_id}` 均无 token 校验 | 🟠 未认证可窃听行情/告警/任意策略版本 |
| SSRF | `monitoring_service.py:535,569` 告警 webhook URL 来自用户配置，`urlopen` 前无内网/元数据地址过滤 | 🟠 可打 `169.254.169.254` 或内网 |
| 孤儿实例 IDOR | `live_trading/instance.py:136,251,279` `if user_id and inst.get("user_id") and ...` —— 实例 user_id 为空时过滤短路 | 🟠 无主实例对所有用户可见可操作 |
| AI 代码执行 | `ai_strategy_research_service.py:5711` `StrategySandbox.execute_strategy_code`；`utils/sandbox.py:253,263` 主进程 `exec`，沙箱靠 AST 黑名单 + `__base__` 未列入 `_DANGEROUS_ATTRS` | 🟠 prompt injection → 主进程 RCE 风险 |
| IB SSL | `config.py:342,357,373,382` `IB_*_VERIFY_SSL` 默认 `False`；`validate_runtime_security_guards` 未守此项 | 🟠 IB Web 连接可被 MITM |
| god 文件（后端） | `ai_strategy_research_service.py` **12206 行**、`run()` 1354 行（L526-1879）、类 3671 行 51 方法；`trading_asset_info_service.py` 4071 行 103 个模块级函数；`akshare/script.py` `_apply_safe_default_parameters()` 1152 行 | 🔴 最大技术债，几乎不可测不可维护 |
| god 组件（前端） | `views/StrategyPage.vue` **10471 行**（template 2747 + script 7723，295 函数）；`DataPage.vue` 3445 行；`ScannerPage.vue` 2292 行；`QuotePage.vue` 2032 行 | 🔴 前端最大技术债 |
| 棘轮回退 | `sync_service.py` 181 时 ~2100 → 当前 **2525**；`gateway/manual.py` ~1700 → **2711**；前端 `KnowledgeBasePage.vue` 1282→**1796**、`GatewayStatusPage.vue` 1256→**1730**、`WorkspaceUnitsTab.vue` 1271→**1498** | 🔴 181-G 目标全部反向恶化 |
| mypy 棘轮失效 | `mypy_app_baseline.json` baseline 958（1.20.2）；`requirements-dev.lock` pin `mypy==2.1.0`；`ci.yml:219` pin `1.20.2`；本地 `1.14.1` 跑出 1374；`mypy_ratchet.py:103-108` 版本错配仅 `::warning::` 不 fail | 🔴 三向错配，ratchet 形同虚设 |
| npm audit 失效 | `ci.yml:645` `npm audit --audit-level=high` 看似 blocking；npm 11 下即便 11 high+2 critical 也 exit 0 | 🔴 依赖漏洞门禁实际不阻断 |
| 静默吞异常 | `ai_strategy_research_service.py:2489,4401,10761,4984,3239,3267,4553,5394` + `task_manager.py:73,106,113,161` + `trading_workspace_service.py:1244` 等；`:4401`/`:10761` 脱敏失败返回**未脱敏** record | 🔴 AI 研究链路错误不可观测，部分泄露敏感字段 |
| 可观测性缺口 | `utils/tracing.py` `business_span()` 完整实现但**全仓零调用**；`/health` 不检查 Redis/AI provider/broker 网关 | 🟠 175 §5 OTel 业务 span 承诺未兑现 |
| portfolio N+1 | `api/portfolio/api.py:1041-1063` `_portfolio_sources` 循环内每次 `_persist_source_asset_specs` 独立开 session+查询 | 🟠 热路径 N+1 |
| 仓库卫生 | `MagicMock/`（72B，测试泄漏）、`lost_codes.pkl`（295B）被 tracked；`reports/` **133MB** tracked；根目录 `AKSHARE_TASK_TODO.md` 320KB / `BACKTRADER_WEB_STRESS_MONITORING.md` 411KB / `UI_OPTIMIZATION_TODO.md` 88KB；`src/frontend/artifacts/` 33MB untracked 未忽略 | 🟠 仓库膨胀与误入库 |
| i18n 硬编码 | `.vue` 中 **649 处**硬编码中文未走 `t()`，`DataPage.vue` 最严重（table label 全硬编码） | 🟠 en-US 下显示中文 |
| a11y | 354 个 `el-icon` 中 159 个缺 `aria-hidden`/`aria-label`（45%） | 🟡 可访问性 |
| 分层违规 | `workspace_service.py:98` lazy import `app.api.analytics._resolve_log_dir`（service→api 反向）；`ai_observability/budget.py:40` `AIBudgetExceededError(HTTPException)`；API 层直接 `db.commit()`（stock_analysis/airflow_callback/ai_observability/portfolio） | 🟠 架构债 |
| e2e flaky | `src/frontend/e2e/` 24 处 `waitForTimeout`、69 处中文 text selector；`tests/e2e/`（Python）大量 `has-text("登录")` 在 en-US 下全失配；两套 e2e 并存且 `tests/e2e/` 无 CI 接线 | 🟠 e2e 脆弱 |

### 2.2 已确认的正向基线（本轮未回归）

- `type: ignore`：后端业务代码已从 11 降到 **1**（181-F 部分达成）。
- 生产前端 `as any` / `@ts-ignore` / 非空断言：**0**（181-D 达成）。
- `v-html`：仅 `StrategyDetailDialog.vue:75` 一处，经 `renderMarkdown`(DOMPurify)，有 XSS 回归测试（181-D 达成）。
- sync 命令执行：`f"-p{password}"` 进 argv / `MYSQL_PWD` shell 注入 / `run_exec` 错误消息均已消除，改 `--defaults-extra-file` + `redact_command`（181-B 达成）。
- i18n full strict：已 baseline-gated blocking（baseline 15076，181-E 达成）；e2e i18n `|| true` 已移除。
- `subprocess shell=True`：全仓后端**零命中**；SQL 用户值一律参数绑定；`scanner_service.py` eval 经严格 AST 白名单。
- 生产 fail-fast：`SECRET_KEY`/`JWT_SECRET_KEY`/`ADMIN_PASSWORD` 生产模式 `raise ValueError`。
- pip-audit：backend blocking 正常。

---

## 3. 范围与非范围

### 本迭代做

- 183-A：安全授权与凭据纵深收口（IDOR、凭据外泄、WS 认证、SSRF、AI 沙箱、IB SSL）。
- 183-B：后端 god 文件分解，以 `ai_strategy_research_service.py` 为主。
- 183-C：前端 god 组件分解，以 `StrategyPage.vue` / `DataPage.vue` 为主。
- 183-D：静默吞异常治理与可观测性补齐（business_span、/health 聚合）。
- 183-E：类型与大文件棘轮续拧 + mypy 版本对齐。
- 183-F：CI 门禁硬化（npm audit、monorepo-check、覆盖率盲区、大文件 ratchet、e2e flaky）。
- 183-G：仓库卫生治理（tracked 垃圾、大文件、artifacts、.gitignore 缺口）。
- 183-H：i18n 硬编码清零与 a11y 补强。
- 183-I：181 残项收口（历史凭据、session.ts localStorage、BMAD 路径）。

### 本迭代不做

- 不由 agent 伪造 provider 凭据失效/轮换证据；history rewrite/force-push 已由 owner 决定不做，183-I 以精确 fingerprint 基线和门禁 flip 收口。
- 不一次性拆完 `ai_strategy_research_service.py` / `StrategyPage.vue`，只做可回归测试、安全收益最高的切片。
- 不改变 182 的功能性 bug 修复主线，不新增产品功能。
- 不把 `monorepo-check` 直接全量 blocking，先 baseline-gated。
- 不重写两套 e2e 框架，先收敛 selector 与硬等待，`tests/e2e/` 去留单独决策。

---

## 4. 183-A - 安全授权与凭据纵深收口（P0）

### 问题

本轮新发现多个授权与凭据洞，均可在多用户部署下被利用：

1. `start_instance` / `stop_instance`（`api/live_trading/api.py:340,367`）不传 `user_id`，`LiveTradingManager` 对应方法（`manager.py:925,944`）签名无 user_id、内部无归属判断 —— 任意认证用户可启停他人实盘。
2. `get_gateway_credentials`（`api/live_trading/api.py:101`）非 admin，`credentials.py:43-321` 明文返回全部券商密码/API Key/Secret/Passphrase。
3. 三个 WebSocket 无认证：`/ws/ticks/{broker_id}`、`/ws/alerts`、`/ws/strategies/{strategy_id}`（后者还不校验 strategy 归属）。
4. 告警 webhook（`monitoring_service.py:535,569`）URL 无内网/元数据地址过滤，存在 SSRF。
5. 孤儿实例 IDOR：`instance.py:136,251,279` 的 `if user_id and inst.get("user_id") and ...` 在实例 user_id 为空时短路。
6. `auto_trading_scheduler.py:233,243` `start_all/stop_all` 不传 user_id。
7. AI 草稿校验 `sandbox.py:253,263` 在主进程 `exec`，`__base__` 未列入 `_DANGEROUS_ATTRS`，叠加 prompt injection 存在逃逸风险。
8. `IB_*_VERIFY_SSL` 默认 `False`，`validate_runtime_security_guards` 未守（`config.py:342,357,373,382,414-436`）。
9. `data/topics.py:33,40,46,109,113` peek/refresh/push/WS 仅 `get_current_user`，push 可向任意 topic 注入。

### 建议

1. `start_instance`/`stop_instance` 增加 `user_id` 参数并前置校验 `inst["user_id"] == user_id`；`auto_trading_scheduler` 的 `start_all/stop_all` 改为按用户作用域或仅 admin。
2. `get_gateway_credentials` 收紧为 `require_data_admin_user`，或返回值掩码（仅 `is_set: true` + 末四位）。
3. 三个无认证 WS 统一接入 `get_websocket_current_user`（参考 `overfitting.py:126`、`paper_trading.py:470` 的正确做法）；`/ws/strategies/{id}` 校验归属。
4. webhook URL 增加协议白名单（http/https）+ 解析后拒绝私网/链路本地/loopback（`ipaddress.ip_address(...).is_private`）。
5. 孤儿实例过滤改为 `if inst.get("user_id") != user_id: continue`（空 user_id 视为不匹配，admin 显式放行除外）。
6. AI 草稿校验迁入子进程或 `DockerSandbox`（`sandbox.py:467` 已有），主进程不直接 `exec`；`__base__` 加入 `_DANGEROUS_ATTRS`。
7. 生产环境强制 `IB_*_VERIFY_SSL=True`（localhost 自签改 CA 注入），纳入 `validate_runtime_security_guards`。
8. `data/topics` 按 topic 命名空间做用户级 ACL，push 限本用户 topic。

### 验收

- [x] `rg -n "start_instance|stop_instance" src/backend/app/api/live_trading src/backend/app/services/live_trading/manager.py` 所有路径均传 user_id 并校验归属。
- [x] `get_gateway_credentials` 非 admin 调用返回掩码或 403；新增授权单测。
- [x] 三个 WS 端点有 token 校验与归属校验单测。
- [x] webhook SSRF 单测：`169.254.169.254` / `127.0.0.1` / `10.x` 被拒。
- [x] 孤儿实例（空 user_id）对非 admin 不可见不可操作。
- [x] AI 草稿校验不在主进程 exec；`sandbox.py` 有子进程/Docker 路径单测。
- [x] 生产模式 `IB_*_VERIFY_SSL=False` 触发 `ValueError`。
- [x] 全量非 E2E 后端套件通过，覆盖 live trading、gateway 与 monitoring 路径。

---

## 5. 183-B - 后端 god 文件分解

### 问题

| 文件 | 行数 | 最差函数 |
| --- | ---: | --- |
| `services/ai_strategy_research_service.py` | 12206 | `run()` 1354 行（L526-1879）；类 3671 行 51 方法 |
| `services/trading_asset_info_service.py` | 4071 | `normalize_asset_spec()` 590 行；103 个模块级函数无 class |
| `services/gateway/manual.py` | 2711 | `query_gateway_trades` 158 行 / `cancel_gateway_open_orders` 152 行 |
| `services/sync_service.py` | 2525 | —— |
| `services/akshare/script.py` | 1822 | `_apply_safe_default_parameters()` 1152 行（L538-1689） |
| `services/position_valuation.py` | 2373 | `contract_spec_for()` 495 行 |
| `api/portfolio/api.py` | 2435 | 79 个模块级 helper |

`ai_strategy_research_service.py` 是当前最大技术债，也是 183-D 静默吞异常的集中地。

### 建议

1. `ai_strategy_research_service.py` 按 stage 拆分（优先做 `run()` 的 1354 行）：
   - `research/orchestrator.py`：`ResearchPipelineOrchestrator`（需求结构化→初稿）
   - `research/backtest_iteration.py`：`_run_backtest_loop`
   - `research/robustness.py`：`_run_robustness_stage`
   - `research/paper_handoff.py`：模拟盘 + 实盘交接
   - 每个 stage 独立可单测，`run()` 仅做编排
2. `trading_asset_info_service.py` 的 103 个模块级函数归入按资产类型的 class（futures/stock/fund/fx），`normalize_asset_spec` 按类型拆子函数。
3. `akshare/script.py` 的 `_apply_safe_default_parameters` 改数据驱动（配置表）替代 1152 行分支。
4. `position_valuation.contract_spec_for` 按 multiplier/margin/commission 拆提取函数。
5. `api/portfolio/api.py` 的 79 个 helper 下沉到 `services/portfolio_view_service.py`，API 层只做 request/response。
6. 修 `workspace_service.py:98` service→api 反向依赖：`_resolve_log_dir` 下沉到 util。
7. `AIBudgetExceededError` 改 domain exception，API 层 handler 转 HTTPException。

### 验收

- [x] `ai_strategy_research_service.py` 降到 6000 行以下，公共 `run()` 降到 200 行以下，stage 模块与 façade 回归测试齐备。
- [x] `trading_asset_info_service.py` 降到 3000 行以下；职责已迁入 `asset_info` 子模块并保持旧导入兼容。
- [x] `rg "from app.api.analytics import" src/backend/app/services` 无命中（反向依赖消除）。
- [x] 研究、资产信息与 portfolio 路径由完整非 E2E 后端套件覆盖并通过。
- [x] 切片后 `AIStrategyResearchService` 既有行为不回归（目标套件 165 项全绿）。

---

## 6. 183-C - 前端 god 组件分解

### 问题

| 文件 | 行数 |
| --- | ---: |
| `views/StrategyPage.vue` | 10471（template 2747 + script 7723，295 函数） |
| `views/DataPage.vue` | 3445 |
| `views/ScannerPage.vue` | 2292 |
| `views/QuotePage.vue` | 2032 |
| `views/PortfolioPage.vue` | 1855 |
| `views/KnowledgeBasePage.vue` | 1796（181-G：1282→1796 反向） |
| `views/GatewayStatusPage.vue` | 1730（181-G：1256→1730 反向） |
| `components/workspace/WorkspaceUnitsTab.vue` | 1498（181-G：1271→1498） |

`StrategyPage.vue` 是前端最大技术债，含 AI Research 流程 ~40 函数、Config Profile 管理、格式化工具、模板管理四块可清晰分离的逻辑。

### 建议

1. `StrategyPage.vue` 优先拆：
   - `StrategyAIResearchTab.vue`（AI Research 流程）+ `composables/useAIResearch.ts`
   - `composables/useStrategyFormatters.ts`（`formatMetric`/`formatDateTime`/`gateGapText` 等）
   - 页面只保留 tab 编排与 4 个 dialog 的壳
2. `DataPage.vue` 按子板块（覆盖矩阵 / 表格管理 / 行情）拆 3-4 个子组件，顺手把 table label 硬编码中文改 i18n（与 183-H 联动）。
3. 181-G 四个回退页面（KnowledgeBasePage / GatewayStatusPage / WorkspaceUnitsTab / WorkspaceOptimizationTab）本轮强制降至 <900：composable 承接状态/副作用，子组件承接表格/表单/状态卡。
4. `api/strategy.ts`（1249 行，30+ interface 混排）的 interface 迁至 `types/strategy.ts`。
5. 每个切片保持旧路由/旧 API 兼容，不与 182 功能改动互相踩踏。

### 验收

- [x] `StrategyPage.vue` 降到 3000 行以下，拆出的 tab/composable 有交互测试。
- [x] 181-G 四页面均 <900 行。
- [x] `npm run typecheck`、`npm run lint` 与 `npm run test -- --run` 通过。
- [x] `npm run build` 与 bundle-size 门禁通过。

---

## 7. 183-D - 静默吞异常治理与可观测性补齐

### 问题

1. `ai_strategy_research_service.py` 多处 `except Exception: return None/record/redacted`，其中 `:4401`、`:10761` 脱敏失败返回**未脱敏** record；`task_manager.py:73,106,113,161` 4 处静默吞。
2. `trading_workspace_service.py:1244` `except Exception: pass`（`persist_asset_specs` 失败无日志）+ `:592,993,1215,1261,1454,1462,1470,1499,1520` 9 处网关查询失败静默降级。
3. `utils/tracing.py` `business_span()` 完整实现但**全仓零调用** —— 175 §5 OTel 业务 span 覆盖承诺未兑现。
4. `/health`（`main_routes.py:97-160`）不检查 Redis、AI provider、broker 网关，K8s readiness 探针无法发现 broker 断线。
5. `research_pipeline_event_service.py:64` 失败仅 DEBUG 日志，生产默认不可见。

### 建议

1. 静默吞异常分类治理：
   - 脱敏 fallback（`:4401`/`:10761`）改为失败时返回安全占位 + `logger.exception`，绝不返回未脱敏对象。
   - 其余 `except Exception: return None/False/[]` 至少补 `logger.warning`/`logger.exception` 并带 task_id 上下文。
2. 在 trust 评估、live gate 决策、网关 connect/place_order、研究 pipeline 各 stage 加 `business_span`（属性用 `bt.*` 前缀）。
3. `/health` 拆 liveness + readiness；readiness 聚合 DB + Redis + AI provider + broker 网关关键状态（可降级为 advisory 字段，不直接 500）。
4. `research_pipeline_event_service` 持久化失败提升到 WARNING。
5. portfolio N+1（`api/portfolio/api.py:1041-1063`）：批量收集后单次 upsert 或 `asyncio.gather` 并发。

### 验收

- [x] 目标吞异常扫描无命中，且无"返回未脱敏对象"路径。
- [x] `business_span` 已覆盖 trust/live gate/gateway/research 路径。
- [x] `/ready` 端点聚合多依赖状态，并有单测。
- [x] portfolio 热路径已由批量化实现及回归测试覆盖。

---

## 8. 183-E - 类型与大文件棘轮续拧 + mypy 版本对齐

### 问题

1. mypy 版本**三向错配**：`requirements-dev.lock` pin `mypy==2.1.0`、`ci.yml:219` pin `1.20.2`、本地 `1.14.1`；`mypy_ratchet.py:103-108` 版本错配仅 `::warning::` 不 fail。开发者本地结果与 CI 不可比，棘轮失效。
2. `mypy_app_baseline.json` 仍 958（181-F 目标 <900 未达），一个月未降。
3. 181-G 大文件目标全部反向恶化（见 183-B/C 表）。
4. 无大文件 ratchet：`analyze_code_lines.py` / `analyze_project.py` 存在但未接 CI。
5. 前端测试 `as any` 572-601（181-F 目标下降，仅降 ~11%）。

### 建议

1. **先修版本对齐**：统一 `requirements-dev.lock` 与 `ci.yml` 到同一 mypy 版本（推荐 lock 降到与 CI 一致，或 baseline 用新版本重新生成）；`mypy_ratchet.py` 版本错配改为 fail（advisory 一个迭代后转 blocking）。
2. 用对齐后的版本跑一次取准确 baseline，再定 958 → <900 路径，优先包 `app/services/sync`、`app/services/ai_strategy_research*`、`app/db`、`app/middleware`。
3. 引入大文件 ratchet：写 `scripts/ci/large_file_baseline.json` 记录当前 top-N 文件行数，CI 检查不允许新增超阈值文件、既有文件不允许增长（与 183-B/C 切片联动下调）。
4. 前端测试引入 typed mount helper（`defineExpose` 暴露最小 VM interface，`findComponent`/DOM 断言替代 `wrapper.vm as any`），设 baseline 601 只降不升。
5. `ci.yml:226` 注释 "~1055 legacy errors" 更新为 958。

### 验收

- [x] mypy 版本在 lock / CI / 文档一致；`mypy_ratchet.py` 版本错配 fail。
- [x] `mypy_app_baseline.json` 低于 900。
- [x] `large_file_baseline.json` 接入 CI，新增超阈值文件被拒。
- [x] 前端测试 `as any` 为 574，低于 601。
- [x] `python scripts/ci/mypy_ratchet.py` 通过。

---

## 9. 183-F - CI 门禁硬化

### 问题

1. `ci.yml:645` `npm audit --audit-level=high` 在 npm 11 下即便 11 high+2 critical 也 exit 0 —— 门禁失效。
2. `monorepo-check` job（`ci.yml:1100`）+ step（`:1118`）双层 `continue-on-error: true`，且不在 `ci-summary` fail-if（181-E 残项）。
3. `src/backend/.coveragerc` omit `app/services/workspace/*`，但 workspace 有单测（`test_workspace_service.py`）—— 覆盖率盲区。
4. 后端覆盖率仅平阈值 70%，无 ratchet；前端 `functions:52` 偏低无 ratchet。
5. `check_all.sh` 的 `MEMBERS` 不含 `src/frontend`；`scripts/ci/run_tests.py:18` 硬编码 macOS 绝对路径 `/Users/yunjinqi/...`。
6. `tests/e2e/test_optimization.py` 整文件 skip 未删（路由已移除）。
7. e2e flaky：`src/frontend/e2e/` 24 处 `waitForTimeout`、69 处中文 text selector；`tests/e2e/`（Python）中文 selector 在 en-US 下全失配，且无 CI 接线。

### 建议

1. npm audit 改 `audit-ci` 或 `better-npm-audit` 显式 exit code，或 `npm audit --audit-level=high --omit=dev` 后解析 JSON 判定；先 baseline-gated（记录当前 24 漏洞，不允许增加），逐步修复 rollup/ws/postcss。
2. `monorepo-check` 至少把 `check_all.sh` 失败 step 在 PR comment 显式标注（脚本已支持 `::error::failed step`），设解锁条件（连续 2 周 green 后转 blocking）；`check_all.sh` 补 `src/frontend` member。
3. 从 `.coveragerc` omit 移除 `app/services/workspace/*`，单独看其覆盖率；后端覆盖率引入 ratchet（baseline json 只升不降）。
4. 删除 `tests/e2e/test_optimization.py`、`scripts/ci/run_tests.py`（或改相对路径）。
5. e2e 收敛：`waitForTimeout` 全改 `expect(...).toBeVisible()`/`waitForResponse`；中文 selector 迁 `data-testid`/`getByRole`（与 183-C 联动在视图补 testid）；决策 `tests/e2e/`（Python）去留——保留则接 CI 并修 selector，否则归档。
6. `pr-check.yml` smoke-tests 只留 `pull_request`，label/summary 类留 `pull_request_target`，去双触发冗余。

### 验收

- [x] npm audit 为 baseline-gated，且 baseline 有记录。
- [x] `monorepo-check` 失败可在 PR 可见，`check_all.sh` 含 frontend。
- [x] `app/services/workspace/*` 已纳入覆盖率统计。
- [x] e2e `waitForTimeout` 降为 0，中文 text selector 已收敛。
- [x] `rg "waitForTimeout" src/frontend/e2e` 无命中。

---

## 10. 183-G - 仓库卫生治理

### 问题

| 路径 | 体量 | tracked | 问题 |
| --- | ---: | --- | --- |
| `MagicMock/` | 72B | 是 | 测试 mock 泄漏产物（commit `1d4b43cc` 误提交） |
| `lost_codes.pkl` | 295B | 是 | 不明 pickle 二进制 |
| `reports/` | **133MB** / 260 文件 | 是 | akshare 数据完整性审计 JSON/MD，使仓库膨胀 |
| `AKSHARE_TASK_TODO.md` | 320KB | 是 | 根目录大 TODO |
| `BACKTRADER_WEB_STRESS_MONITORING.md` | 411KB | 是 | 根目录大文档 |
| `UI_OPTIMIZATION_TODO.md` | 88KB | 是 | 根目录大 TODO |
| `src/frontend/artifacts/` | **33MB** / 156 PNG | 否 | 设计截图未忽略 |
| `data/datas/*/`（8 目录） | ~3MB | 否 | 回测样本数据未忽略 |
| `tests/e2e/explore_report.json` | 8KB | 否 | 测试产物未忽略 |
| `.slowapi.env` | - | 否 | 限流覆盖配置未在 `.gitignore` |

### 建议

1. `git rm -r MagicMock/` + `git rm lost_codes.pkl`，加 `.gitignore`。
2. `reports/` 移出仓库到对象存储，或仅保留索引 README；至少 Git LFS。三个根目录大 `.md` 移至 `docs/` 子目录或精简。
3. `.gitignore` 补：`src/frontend/artifacts/`、`data/datas/*/`（保留 `.gitkeep`）、`tests/e2e/explore_report.json`、`tests/e2e/*_report.json`、`.slowapi.env`、`MagicMock/`、`lost_codes.pkl`。
4. `src/frontend/artifacts/` 若确为设计资产需保留，迁 Git LFS 并加 README 说明用途。
5. 在 CI 加轻量检查：`git ls-files` 命中 cookie/key/jks/env/db/zip/pkl 等模式必须出现在 allowlist 并附解释（181-A 已建议，本轮落地）。

### 验收

- [x] `git ls-files | rg "MagicMock|lost_codes.pkl"` 无命中。
- [x] `reports/` 不在仓库主树（或 LFS）；根目录无 >100KB 的 `.md`。
- [x] `.gitignore` 覆盖上述未跟踪目录/文件。
- [x] CI tracked-sensitive 检查存在且通过。

---

## 11. 183-H - i18n 硬编码清零与 a11y 补强

### 问题

1. `.vue` 中 **649 处**硬编码中文未走 `t()`，`DataPage.vue` 最严重（table `label="状态"/"标的"/"资产"/"周期"/"来源"/"区间"/"行数"/"缺口"/"最新 Bar"`、`ElMessage.success('覆盖矩阵已刷新')`、状态映射 `pass:'通过'` 等）。
2. 354 个 `el-icon` 中 159 个缺 `aria-hidden`/`aria-label`（`WorkspaceUnitsTab.vue` 28 个全无、`WorkspaceOptimizationTab.vue` 15 个全无）。
3. `utils/exportUtils.ts` ~40 行中文注释。
4. `utils/session.ts:51-54` `setAccessToken()` 已是 no-op shim（181-D 残留）。

### 建议

1. `DataPage.vue` 硬编码中文批量提取为 i18n key（与 183-C 拆分联动），脚本辅助扫描其余 648 处分批清零，en-US/zh-CN 同步。
2. 纯装饰 `el-icon` 统一 `aria-hidden="true"`，可交互图标加 `aria-label`；加 ESLint 自定义规则或 `vue/no-unescaped-text` 强制。
3. `exportUtils.ts` 注释改英文。
4. 确认 `setAccessToken()` 无调用方后删除 shim 并修 import（181-D 收尾）。

### 验收

- [x] 硬编码中文显著下降，DataPage 及其 composable 的用户可见中文为 0。
- [x] `en-US.ts` / `zh-CN.ts` key 对齐由 locale-completeness 测试守护。
- [x] `el-icon` 由专用 a11y 检查守护。
- [x] `utils/session.ts` 无 legacy localStorage fallback。

---

## 12. 183-I - 181 残项收口

### 问题

181 仍开放项实测：

| 项 | 181 目标 | 当前实测 | 状态 |
| --- | --- | --- | --- |
| 181-A 历史凭据 | owner 确认旧值失效，再启用阻断 | owner 已确认全部历史凭据均已作废；114 条 finding 已按审计结果写入精确 fingerprint 基线，metadata 为 114/0/ready；全史复扫 0 finding，CI 将由 metadata 自动 blocking；无需改写历史 | 🟡 等待发布 CI |
| 181-D session.ts | 删 legacy localStorage | `session.ts:13,45` 仍有 `LEGACY_TOKEN_KEY` + `localStorage.getItem` | 🔴 仍开放 |
| 181-H BMAD 路径 | 统一 | `config.toml` 指向不存在的 `_bmad-output`；实际在 `.kiro/bmad/output/`；`docs/reports/archive/CODE_QUALITY_REPORT.md:44`、`docs/iterations/archived/迭代130...md:9` 仍引用错误路径 | 🔴 仍开放 |

### 建议

1. 181-A：当前树已完成 `ibkr_cookies.json` 移除、`.example` 占位符和 vendored 文件分类；owner 已确认全部历史凭据作废。114 条 finding 已纳入精确 fingerprint 基线，全史复扫为 0，`blocking_ready=true` 自动启用硬门禁。仅待发布 CI 证据，历史 purge/force-push 不需要执行。
2. 181-D：删除 `session.ts` legacy localStorage fallback（确认无调用方）。
3. 181-H：在 `docs/reference/project-context.md` 或新 BMAD 使用说明明确本仓库实际 BMAD 路径（`.kiro/bmad/output/`）；修正 `config.toml` `output_folder` 或建兼容说明；修两处历史文档错误引用。

### 验收

- [x] 当前树的 `ibkr_cookies.json` 已移除并 ignore，仅保留经 CI 校验的占位符 `.example`。
- [x] owner 已确认 IBKR 仅用于模拟交易并接受历史暴露风险；全史扫描未将其识别为 secret finding。
- [x] 103 条测试/公开值/误报告警已使用精确 fingerprint 建立基线，新增 finding 仍会失败。
- [x] 手工网关、MySQL 同步和 AI provider 凭据文件使用原子 `0600` 写入且不跟随目标 symlink；本机现存手工网关文件已收紧为 `0600`。
- [x] owner 已确认六套非 IBKR 历史凭据均已作废；11 条 finding 已完成精确 fingerprint 风险记录。
- [x] gitleaks 8.30.1 全史复扫退出 0、finding 为 0；`blocking_ready=true` 已使 CI 逻辑自动硬阻断。
- [ ] 变更发布后有一次 full-history blocking CI 通过记录；仓库变量仅为可选 override。
- [x] `session.ts` 无 legacy localStorage 路径。
- [x] BMAD 路径说明不再矛盾，新文档引用一致。

---

## 13. 执行顺序

建议按风险收益排序：

1. **183-A**（P0 安全）：实盘越权与凭据外泄先堵，最高风险。
2. **183-G**（仓库卫生）：`git rm` 垃圾、`.gitignore` 补全，低风险快速清场。
3. **183-E**（mypy 版本对齐）：先修棘轮失效，否则后续质量度量都不可信。
4. **183-D**（吞异常 + 可观测性）：与 183-B 同源，先补观测再拆。
5. **183-B**（后端 god 文件）：`ai_strategy_research_service.py` 切片。
6. **183-C**（前端 god 组件）：`StrategyPage.vue` / `DataPage.vue` 切片。
7. **183-F**（CI 门禁）：npm audit、monorepo-check、覆盖率、e2e flaky。
8. **183-H**（i18n + a11y）：与 183-C 拆 DataPage 联动。
9. **183-I**（181 残项）：精确基线与自动 blocking 已完成，发布后保留一次 CI 通过证据。

---

## 14. 总体验收标准

- [x] **安全**：`start_instance`/`stop_instance`/`get_gateway_credentials`/三个 WS/SSRF/孤儿实例/AI exec/IB SSL 均有授权或边界校验与单测。
- [x] **安全（当前树）**：`ibkr_cookies.json` 已移除/ignore，`.example` 仅含受 CI 校验的占位符；vendored `vertx.jks`/`demo.zip` 已分类。
- [ ] **安全（CI 外部证据）**：114 条精确基线全史复扫为 0，自动 blocking 逻辑已有一次发布后 CI 通过证据；无需改写历史。
- [x] **可维护性**：`ai_strategy_research_service.py` <6000 行且 `run()` <200 行；`StrategyPage.vue` <3000 行；181-G 四页面 <900 行。
- [x] **质量**：mypy 版本一致且 baseline <900；大文件 ratchet 接入 CI；npm audit 门禁有效。
- [x] **可观测性**：`business_span` 在关键业务路径有调用；`/ready` 聚合多依赖；无"返回未脱敏对象"的吞异常路径。
- [x] **仓库卫生**：`MagicMock/`/`lost_codes.pkl` 移除；`reports/`/`artifacts/` 不膨胀主树；`.gitignore` 完备。
- [x] **i18n/a11y**：硬编码中文显著下降（DataPage 为 0）；`el-icon` aria 守护。
- [ ] **181-A 外部收口**：仅待发布后的 blocking CI 证据；rotation inventory、181-D/H 已收口。
- [x] **文档**：BMAD 路径、183 发现、执行记录与剩余风险在 docs 闭环。

---

## 15. 验证命令建议

```bash
# 安全自检
rg -n "start_instance|stop_instance|get_gateway_credentials" src/backend/app/api/live_trading src/backend/app/services/live_trading
rg -n "websocket|@router.websocket" src/backend/app/api | rg -i "auth|token"
rg -n "urlopen|requests\.(get|post)" src/backend/app/services/monitoring_service.py
git ls-files | rg "(MagicMock|lost_codes\.pkl|\.env$|.*cookies.*|.*\.jks|.*\.zip)$"

# 后端质量
cd src/backend
ruff check .
ruff format --check .
python ../../scripts/ci/mypy_ratchet.py   # 先确认版本对齐
pytest -m "not e2e" -q
pytest tests/test_live_trading* tests/test_*gateway* tests/test_monitoring* tests/test_ai_strategy_research_service.py -q

# 前端质量
cd src/frontend
npm run typecheck && npm run lint && npm run test -- --run
npm run build
rg -c "waitForTimeout" e2e/            # 目标 0
rg -c "as any" src/__tests__/          # 目标 <601

# CI 门禁
rg -n "continue-on-error|\|\| true|SECRET_SCAN_HISTORY_BLOCKING" .github/workflows scripts
npm audit --audit-level=high --omit=dev; echo "exit=$?"   # 验证 exit code

# 大文件 ratchet
wc -l src/backend/app/services/ai_strategy_research_service.py src/frontend/src/views/StrategyPage.vue
python scripts/dev/analyze_code_lines.py

# 仓库卫生
du -sh reports/ src/frontend/artifacts/ 2>/dev/null
git ls-files | wc -l
```

---

## 16. 主要风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 183-A 授权改动影响既有实盘调用方 | 高 | 先加单测覆盖现有行为，灰度到本地实盘 case；保留 admin 旁路一个迭代 |
| `ai_strategy_research_service.py` 拆分破坏研究流水线 | 高 | 只切 stage 边界、保持公共 API；用既有 157 个测试做回归；切片后跑 e2e |
| `StrategyPage.vue` 拆分影响 182 功能改动 | 中高 | 与 182 协调顺序；先拆 composable/formatter（低风险），AI Research tab 后拆 |
| mypy 版本对齐引入新报错 | 中 | 对齐后先重新生成 baseline（不要求一次降），再定下降路径 |
| npm audit flip blocking 阻断 CI | 中 | 先 baseline-gated，rollup/ws/postcss 修复后再 blocking |
| e2e selector 迁移工作量大 | 中 | 与 183-C 拆分联动补 testid，分页面迁移 |
| 历史 finding 被过宽 allowlist 掩盖 | 高 | 只允许 commit+path+rule+line 精确 fingerprint；新增 finding 保持 blocking |
| `reports/` 移出影响既有引用 | 中 | 先建索引 README，确认无代码依赖再移出/LFS |

---

## 17. 实施前优化与可判定门槛（2026-07-18）

本计划保留第 3 节的全部范围，但以下调整是实施前置条件，避免将“看起来做了”误判为完成：

1. **安全控制采用 fail-closed 语义。** 实盘实例的拥有者比较必须同时在 API 和
   manager/service 边界执行；空 `user_id` 的历史实例一律仅限显式管理员修复/迁移，
   不得作为普通用户可操作的兼容路径。WebSocket 必须在 `accept()` 前完成认证，失败以
   1008 关闭；涉及 `strategy_id` 和 `broker_id` 的端点还必须验证对象归属，不能只验证
   token 有效。
2. **凭据 API 不返回密钥材料。** 即使管理员调用也只返回 provider、配置状态和稳定的
   脱敏展示值；连接所需明文仍仅从服务端环境读取。验收需覆盖普通用户 403、管理员响应
   不含 password/token/secret/api-key 原值两类断言。
3. **SSRF 防护不能仅使用 `is_private`。** 仅允许 `http`/`https`，拒绝 credentials-in-URL、
   localhost、所有非 global 的解析地址和重定向；连接时重新解析目标以避免 DNS rebinding。
   单测除 IPv4 私网外还须覆盖 IPv6 loopback/link-local、域名解析到内网和 redirect。
4. **AI 执行隔离的验收改为可证明的边界。** 生产配置必须 fail closed：未启用可用的
   Docker 隔离执行器时不执行 AI 草稿；开发/测试使用独立子进程且有超时和资源上限。不得
   用“仅补 `__base__` 黑名单”替代进程/容器隔离。新增测试要证明调用进程不执行用户代码、
   Docker 不可用时生产拒绝执行。
5. **大文件目标拆成连续交付门槛。** 每个切片先保持公共 API 和测试绿，再更新
   `large_file_baseline.json`；最终才以第 5/6 节行数为验收。中间阶段的“切出模块”不能
   用空壳转发或复制代码计数。所有“显著下降”统一改为：`DataPage.vue` 用户可见文本硬编码
   为 0、前端 e2e `waitForTimeout` 为 0、列出的例外处理全部带日志或显式安全 fallback、
   `el-icon` 由静态检查保证缺失数为 0。
6. **质量门禁先基线后阻断。** 在统一的 mypy 版本下生成一次可复现 baseline；版本不匹配
   立即失败。npm audit 使用 JSON 解析的已提交 baseline（含 lockfile hash），新增
   high/critical 漏洞失败；不能依赖 npm 的退出码。`monorepo-check` 在 summary 中明确标为
   advisory，连续两周可复现全绿后才改 blocking。
7. **外部所有者操作单列，不伪造验收。** owner 已接受模拟 IBKR 的历史暴露，故 history
   rewrite/force-push 不再是 DoD。owner 已确认全部历史凭据作废，所有 finding 仅按精确
   fingerprint 建基线；`blocking_ready=true` 自动启用门禁。总体验收仍须保留 owner 判定
   和一次发布后的 blocking CI 通过证据。

### 优化后的阶段门

| 阶段 | 进入条件 | 退出证据 |
| --- | --- | --- |
| A0 | 记录当前基线、确认 dirty worktree 不与本迭代文件重叠 | 基线命令与文件所有权记录 |
| A1 | 183-A 的授权、凭据、WS、SSRF、AI/SSL 改动完成 | 定向安全测试和拒绝路径测试全绿 |
| A2 | A1 全绿 | 183-D/E/F/G/I 可独立验证的代码与 CI 改动完成 |
| A3 | A2 全绿、为切片补回归测试 | 183-B/C/H 分批切片，large-file ratchet 不回升 |
| A4 | 全部本地门禁通过 | 第 14 节逐项以命令输出、测试结果和 owner 证据审计 |

## 18. 实施记录（2026-07-18）

本轮已完成并保留回归证据的代码交付：183-A 的实盘实例归属校验、凭据脱敏与管理员
边界、WebSocket 认证/归属、topic ACL、SSRF 重解析防护、AI 草稿隔离及 IB TLS 生产守卫；
183-B 的研究流水线和资产规格服务切片；183-D 的 readiness 聚合、业务 span、任务快照
异常日志和预算领域异常；以及 183-E/F/G/I 的版本对齐、npm/大文件/敏感文件门禁、仓库
清理、session 与凭据 example 化。

切片已完成第 6/14 节的行数门槛：`ai_strategy_research_service.py` 为 4,034 行，
`trading_asset_info_service.py` 为 2,210 行；`StrategyPage.vue` 为 2,997 行，
`DataPage.vue` 为 735 行。181-G 的 `GatewayStatusPage.vue`、`KnowledgeBasePage.vue`、
`WorkspaceUnitsTab.vue` 和 `WorkspaceOptimizationTab.vue` 分别为 514、872、806 和 662 行。
策略 API 合同也已从 `api/strategy.ts`（439 行）拆至 `types/strategy.ts`（929 行），保留
兼容导出。

183-H 的可判定门槛已落实：`DataPage.vue` 及其 composable 的用户可见中文为 0；所有
`el-icon` 已补充 `aria-hidden` 或标签，并由 `scripts/ci/check_frontend_icon_a11y.py` 和 CI
步骤持续守护；前端 e2e 中的 `waitForTimeout` 为 0。前端已通过 `vue-tsc`、无 error 的
lint（692 条既有 warning）、生产构建，以及全量 Vitest（135 个文件、1,215 项测试）；
Strategy、Data、Gateway、Knowledge Base 和 Workspace 的针对性页面测试亦已覆盖拆分边界。

最终验证已完成：后端完整非 E2E 套件为 **4,162 passed、135 skipped**（15m21s）；AI 研究
服务目标回归为 **165 passed**；前端 Vitest 为 **135 files / 1,215 passed**。Ruff、依赖
一致性检查、敏感跟踪文件检查、图标 a11y 检查和大文件棘轮均通过；`npm_audit_ratchet`
通过（high=4、critical=0）。CI 固定的 mypy 1.20.2 已在 lock、CI 与基线对齐，
`mypy_ratchet` 为 **714 errors / baseline 714 / delta +0**，满足 <900 目标。

owner 已确认 IBKR 仅用于模拟交易并接受其历史暴露，因此不再要求 history rewrite 或
force-push；同时确认其他凭据可能用于实盘，故必须按有效凭据轮换。使用 CI 固定的
gitleaks 8.30.1 复扫 485 个提交：原 114 条 finding 中，103 条
测试值、公开 Supabase `anon` JWT、清单哈希及误报已写入 `.gitleaksignore` 的精确 fingerprint
基线；首轮基线复扫只余 11 条、4 个文件、4 个提交，均来自旧 Binance/OKX、手工网关或 MySQL 同步
配置，IBKR cookie 为 0 条。脱敏去重得到 Binance、OKX、CTP、MT5、本地 MySQL 和远程
MySQL 各一套待轮换凭据；旧 Binance/OKX 配置显示 `testnet=False`。完成 provider 轮换并
验证旧值失效后已追加 11 条精确 fingerprint；gitleaks 8.30.1 全史复扫退出 0、finding 为 0，
`blocking_ready=true` 会自动硬阻断后续 finding。仅待发布后一次 blocking CI 通过即可收口，
无需改写仓库历史。

本机现存 `src/backend/data/manual_gateways.json` 原为 `0664`，已立即收紧为 `0600`。新增
`write_private_text()` 统一为手工网关、MySQL 同步和 AI provider 配置执行 `0600` 临时文件、
`fsync` 与原子替换，避免权限窗口及 symlink 重定向；相关受影响域回归为 **158 passed**。
