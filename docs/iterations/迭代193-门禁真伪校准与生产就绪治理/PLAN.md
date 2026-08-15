# 迭代 193：门禁真伪校准与生产就绪治理 Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不增加任何功能的前提下，按行业最佳实践对全仓做一次系统性审计，校准"名存实亡"的质量门禁、修复生产阻断级缺陷、补齐测试/安全/可观测性/文档盲区，并建立防回归机制。

**Scope:** 8 维度并行只读审计（后端架构、测试体系、安全、性能、CI/CD、前端、可观测性与数据治理、文档与 DX），全部关键结论经独立复核（含两条对审计初稿的修正，见 §5）。

**Tech Stack:** Python 3.10+、FastAPI、SQLAlchemy 2.0、Alembic、MySQL 9.4.0、pytest、Prometheus/OpenTelemetry、Vue 3 + TypeScript、Vitest、Playwright、GitHub Actions。

---

## 0. 审计结论总览

审计产出约 110 条发现：**P0 × 3、P1 × 40、P2 × 70**，全部带 `file:line` 证据，完整清单见 `evidence/audit-2026-08-13-full-findings.md`。

### 0.1 P0（阻断级）

| # | 发现 | 证据（已复核） |
| --- | --- | --- |
| P0-1 | **镜像安装的依赖锁与 CI 阻断审计的依赖锁是两份已漂移的文件**。镜像经 `COPY src/backend` 装入 `src/backend/requirements-prod.lock`（310 行，含 akshare/aiomysql/backtrader 等全部 extras）；CI 的 pip-audit 阻断门禁审计的是 `config/requirements-prod.lock`（68 行，无 extras）。两者已漂移（asgiref 3.11.1 vs 3.12.1），**线上镜像携带的核心依赖完全未被漏洞审计** | `src/backend/Dockerfile:21-26`、`.github/workflows/ci.yml:647,653` |
| P0-2 | **大文件棘轮当前红灯**：迭代 192 新增 7 个超限文件（`asset_research/orchestrator.py` 3048 行、`plugins/base.py` 1948 行、`providers/akshare.py` 1310 行、`schemas/asset_research.py` 1300 行、`AssetAnalysisPage.vue` 1504 行），另有 3 处基线回归（`gateway/manual.py` 2711>2708、`StockAnalysisPage.vue` 1613>1433、`useStrategyPage.ts` 6795>6738）。实跑 `python3 scripts/ci/large_file_ratchet.py` 退出码 1 | 实跑输出（2026-08-13） |
| P0-3 | **HTTP/DB/错误/回测/实盘 Prometheus 指标全部是"死指标"**：`record_api_request`/`record_db_query`/`record_error`/`record_backtest_*`/`record_live_*` 除 `middleware/metrics.py` 自身外**零调用点**；且 `config/alerting.yaml:8-46` 引用的 `http_request_duration_seconds` 等指标名与实际代码（`api_request_duration_seconds`）不符、全仓无代码消费该文件——运营告警 100% 静默不触发 | grep 全仓零命中；`middleware/metrics.py:64-87,424,502,523` |

### 0.2 P1 汇总（各维度前 3，完整见 evidence）

| 维度 | 关键 P1 |
| --- | --- |
| 后端 | `evaluate_due_outcomes` N+1（每批最多 ~4000 次 DB 往返，`orchestrator.py:1630-1638`）；async 端点内同步日志文件解析阻塞事件循环（`api/portfolio/api.py:2961` 等 5 处）；`_run_pipeline` 单方法 1363 行（`ai_strategy_research_service.py:486`） |
| 测试 | 时间敏感测试再次爆雷（`test_schedule_runner.py:419-542` 固定 `fire_at=2026-08-03`，已过期）；`.coveragerc` 把 5 个实盘关键模块排除出覆盖率分母（`src/backend/.coveragerc:3-20`）；本地 `run-e2e.sh` 会写入开发者真实数据库（`scripts/dev/run-e2e.sh:80-85`） |
| 安全 | 任意登录用户可断开/查询他人实盘网关（BOLA，`api/live_trading/api.py:141-216` 无归属校验）；注册用户名 `admin` 即获管理员权限（`auth_service.py:53-56` + 注册无保留名）；生产经 nginx 反代后限流键退化为全平台共享单桶（`rate_limit.py:47` + `prod.yml` 无 proxy-headers） |
| 性能 | `/data/kline` 在 async 路由内直连 akshare（`api/data/base.py:48`）；MySQL 用 NullPool 每请求新建物理连接（`db/database.py:31-35`）；回测/过拟合 WebSocket 每客户端每秒一次 DB 轮询（`api/backtest_enhanced.py:552-573`） |
| CI/CD | Lighthouse CI 是死门禁（配置路径错误 + `\|\|` 吞退出码，`ci.yml:966-968`）；monorepo-check 空转（未装任何工具，全部 skip，`ci.yml:1243-1265`）；`pull_request_target` 执行不受信任的 PR 代码（`pr-check.yml:6-7,151-181`） |
| 前端 | `useStrategyPage.ts` 6795 行、`StrategyPage.vue` 3122 行（"god 文件分解"只抽了 3 个弹窗）；i18n "CJK 清零"未完成（600+ 行硬编码中文，`StrategyPage.vue:229-365` 等）；ratchet 红灯 3 项前端违规 |
| 可观测性 | 审计清理任务从未被调度（`cleanup_old_records` 已实现但零调用方，`audit_service.py:282-330`）；生产 OTel 默认关闭且 SDK 无 shutdown（`telemetry.py` + `prod.yml`）；业务日志无 request_id/user_id 上下文（`utils/logger.py:46-70` InterceptHandler 丢弃 extra） |
| 文档/DX | `README.en.md` 16 个死链接 + 错误仓库名（`ai-for-investor.git` vs 实际 `cloudQuant/backtrader_web`）；`CONTRIBUTING.md:21` 克隆命令指向不存在的仓库；uv workspace 仍声明已空壳化的 `src/bt_api_py` 为成员 → `make check-all` 必然失败（根 `pyproject.toml:13-14`） |

### 0.3 已做好的地方（审计确认，避免重复治理）

统一错误 envelope 与全局异常处理器、Session 生命周期封装（`session_provider.py` 含 unit_of_work）、Alembic 三层迁移防护（alembic check + ORM schema drift 硬门禁 + migration-safety lint，实跑 "OK: schema aligned"）、全 app 0 处裸 except、SQL 全参数化、SSRF DNS-rebinding 抗性（`utils/safe_webhook.py`）、gitleaks 全历史+基线指纹闭环、沙箱化 AI 策略执行、前端路由 100% 懒加载 + 生产代码仅 1 处 `any`、loguru 轮转/压缩/脱敏体系、低基数指标规范（已接线的 asset_research 系列是范本）、迭代 190/192 的 PLAN+ACCEPTANCE+evidence 文档质量是仓库范本。

### 0.4 计划优化记录（2026-08-13 计划评审补充）

计划初稿经行业最佳实践复核，补充 7 项强化（不改变范围与优先级，仅收紧治理口径）：

1. **棘轮基线区分"回归"与"新增存量"（细化 D-2/Task A）**：3 项回归（`gateway/manual.py` +3 行、`StockAnalysisPage.vue` +180 行、`useStrategyPage.ts` +57 行）属于"已基线文件超长"——就地修复或回退至基线值，**不得基线吸收**；仅 5 项迭代 192 新增的 god file（orchestrator 3048、plugins/base 1948、akshare 1310、schemas 1300、AssetAnalysisPage 1504）登记进基线并排入 194 切片。理由：回归基线化与 D-2"恢复门禁信用"自相矛盾，且违反棘轮"只降不升"语义。
2. **新增 §6 回滚与应急策略**：安全 fail-closed、CI 基线刷新、锁文件合并均为生产就绪变更，须有可回滚路径与灰度验证。
3. **CODEOWNERS 显式 owner 与评审标准（细化 Task A）**：基线文件 owner 至少含 2 名 maintainer，`--update` PR 必须附"为什么不能就地修复"的评审说明，否则 CI 拒绝。
4. **async 阻塞检查脚本规格化（细化 Task H）**：落地为 `scripts/ci/async_blocking_check.py`，按 AST 识别 async 函数体内的同步 `requests`/`open`/`akshare.*`/`time.sleep` 调用（豁免清单 `scripts/ci/async_blocking_allowlist.json`），接入 ci.yml backend-test job，作为棘轮门禁（初始允许清单=当前存量，后续只降不升）。
5. **量化收口报告模板（细化 ACCEPTANCE.md）**：新增"前后对比"汇总表（覆盖率%、死门禁修复数、P0/P1 闭合数、棘轮状态、bundle 体积、CI job 数与 timeout 覆盖率），证据归档 `evidence/closing-report-2026-08-13.md`。
6. **DR/备份恢复演练（新增 Task M）**：`scripts/ops/backup_mysql.py` 存在但无恢复演练；本迭代产出 `docs/runbooks/backup-restore.md` 并在 staging 实跑一次恢复（或显式递延至 194 并记录理由）。"生产就绪"无恢复演练不完整。
7. **L 级递延作为显式交付物（细化排期 §4）**：创建 `docs/iterations/迭代194-工程债切片续作/PLAN.md` 骨架（`_run_pipeline` 拆分、`contract_spec_for` 拆分、StrategyPage 模板拆分、lazy="raise" 全量、git 历史重写），作为 Task A/I/K 的收口验收项。

---

## 1. 行业最佳实践映射

外部调研不照搬某一实现，而是把下列原则固化为 193 的验收门禁：

| 主题 | 关键原则 | 参考 |
| --- | --- | --- |
| 供应链完整性 | 审计对象必须等于交付工件（单一 lockfile SSOT）；action 钉完整 SHA；发布镜像带 provenance/SBOM；门禁不能被静默跳过 | [SLSA](https://slsa.dev/)；[OpenSSF Scorecard](https://securityscorecards.dev/)（Pinned-Dependencies、Token-Permissions） |
| CI 有效性 | 每个 job 设 timeout；关键步骤失败必须显式传播；门禁"看起来通过"比没有门禁更危险；配置以目录/marker 选择而非硬编码清单 | GitHub Actions 官方《Using jobs》《Using concurrency》《Keeping your GitHub Actions and workflows secure》 |
| 应用安全 | 对象级授权每资源校验（BOLA）；权限基于角色而非用户名；令牌禁用即时生效；守卫默认拒绝（fail-closed）；敏感操作服务端权威审计 | [OWASP API Top 10 (API1/API4)](https://owasp.org/API-Security/)；[ASVS V4](https://owasp.org/www-project-application-security-verification-standard/)（V4.1.1/V4.2.1/V4.3.2/V8.1.1） |
| 可观测性 | 指标必须真实反映系统行为（虚假 RED 信号使告警与容量规划全部失效）；告警必须对真实存在的指标配置；日志携带 trace/request/user 上下文 | [Google SRE Workbook](https://sre.google/workbook/table-of-contents/)（Ch.4 Monitoring、Ch.5 Alerting、Ch.14 DR）；OTel Logs Data Model |
| 性能 | async 路径禁止阻塞 I/O；ORM 关系默认 `lazy="raise"` 让隐式 N+1 在开发期暴露；连接池复用（NullPool 仅限廉价连接场景）；多租户缓存键必须含用户维度 | FastAPI/anyio 官方文档；SQLAlchemy 2.0 官方文档（Zen of Eager Loading、Connection Pooling） |
| 测试质量 | 时间必须是可注入依赖（freezegun/显式 now）；skip 是技术债需挂 ticket；覆盖率 omit 需诚实且定期复审；e2e 必须 hermetic（不碰真实 DB）；金融计算模块失败路径优先 | [Google Testing Blog](https://testing.googleblog.com/)；[freezegun](https://github.com/spulec/freezegun) |
| 前端 | 组件单一职责；所有用户可见文案走 i18n；按需引入图表库；断言不绑定 locale 文案 | [Vue 官方风格指南](https://vuejs.org/style-guide/)；[vue-i18n](https://vue-i18n.intlify.dev/)；ECharts 按需引入文档 |
| 文档治理 | 文档与证据单一事实源；入口链接可执行（"First step must work"）；CHANGELOG 按 Keep a Changelog 逆序持续更新；重要架构决策落 ADR | [Google eng-practices](https://google.github.io/eng-practices/)；[Diátaxis](https://diataxis.fr/)；[Keep a Changelog](https://keepachangelog.com/) |

---

## 2. 设计决策

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| D-1 | 不新增功能红线：所有变更限于重构、配置、测试、门禁、文档；任何"顺手加功能"的改动拆分到 194+ | 用户明确要求"在不增加功能的前提下" |
| D-2 | 棘轮信用修复优先于切片：8 项超限先经评审走基线刷新（承认存量），切片按资产类型分批排入后续迭代；同时建立"基线变更需独立 PR + CODEOWNERS 强制审阅"防刷机制 | 棘轮红灯阻塞 CI；先转绿恢复门禁信用，再防再犯 |
| D-3 | 依赖锁 SSOT 定为 `config/requirements-prod.lock`（与 CONTRIBUTING 声明一致），删除 `src/backend/requirements-prod.lock` 副本，Dockerfile 显式 `COPY config/requirements-prod.lock`；新增 CI 步骤强制两处 diff 为空 | 审计对象必须等于交付工件（SLSA L2） |
| D-4 | 可观测性"接线优先"：复用已实现的基础设施（record_* 函数、loguru `contextualize`、已写好的 `cleanup_old_records`），不新增指标语义、不改采集协议 | 死代码的修复是接线不是重写，工作量最小、收益最大 |
| D-5 | 安全守卫 fail-closed：生产判定改为"仅显式 `DEBUG=true` 才关闭守卫"；限流键改为仅信任配置的代理网段 | CWE-453/1188；默认拒绝优于默认放行 |
| D-6 | 性能修复最小侵入：`asyncio.to_thread` 包裹 + 连接池配置化 + 批量查询，不动业务逻辑 | 与仓库既有正确模式（`api/quote.py`、`live_trading/api.py`）对齐 |
| D-7 | 测试以"任意日期可复现"为验收线：所有时间敏感测试移除硬编码过去日期 | 迭代 192 已因真实时钟导致 4 个测试过期失败，同一类问题不得第三次复发 |
| D-8 | 文档门禁扩展：`check_doc_links.py` 扫描范围从 `docs/**` 扩展为全仓 `*.md`（排除 node_modules/.git/.venv），并新增"CHANGELOG/版本号一致性"检查 | 迭代 174 Diátaxis 迁移后根级入口文档漂移 16+ 处，机制上防复发 |

---

## 3. 工作包与验收

### Task A：解除 CI 红灯并恢复棘轮信用（P0-2）

**Files:**
- Update: `scripts/ci/large_file_baseline.json`
- Modify: `scripts/ci/large_file_ratchet.py`、`mypy_ratchet.py`、`npm_audit_ratchet.py`（三个脚本 `--update` 统一加 `ALLOW_BASELINE_UPDATE` 环境变量守卫，CI 不注入；无 env 时 `--update` 拒绝执行并提示评审流程）
- Create: `.github/CODEOWNERS`（4 个基线文件 owner 指定 ≥2 名 maintainer）
- Create: `scripts/ci/baseline_update_guard.py`（共享守卫逻辑：校验 env + PR 描述含"就地不可行评审说明"标记）

**Steps:**
- [ ] **回归项就地修复（不基线吸收）**：`gateway/manual.py` 2711→≤2708（删除 3 行冗余/空行或回退近期膨胀）；`StockAnalysisPage.vue` 1613→≤1433（抽 1 个展示型子组件，~180 行）；`useStrategyPage.ts` 6795→≤6738（抽 1 个 composable，~57 行）。三项均属"已基线文件超长"，棘轮只降不升
- [ ] **新增存量登记进基线**：5 项迭代 192 新增 god file（orchestrator 3048、plugins/base 1948、akshare 1310、schemas 1300、AssetAnalysisPage 1504）登记进 `large_file_baseline.json`，CI 转绿
- [ ] 三个 ratchet 脚本加 `--update` 环境变量保护（CI 不注入 `ALLOW_BASELINE_UPDATE`）
- [ ] CODEOWNERS 覆盖 4 个基线文件（`large_file_baseline.json`/`mypy_app_baseline.json`/`npm_audit_baseline.json`/`gitleaks_history_baseline.json`）
- [ ] `asset_research` 4 个 god 文件与前端 2 个页面的切片排期写入 `docs/iterations/迭代194-工程债切片续作/PLAN.md` 骨架（本迭代只登记+排期不切片，切片属 L 级工作）

**验收标准:**
- `python3 scripts/ci/large_file_ratchet.py` 退出码 0
- 无 `ALLOW_BASELINE_UPDATE` 环境变量时 `--update` 拒绝执行（exit ≠ 0）
- 3 项回归项修复后行数 ≤ 原基线值（非吸收）
- `迭代194-工程债切片续作/PLAN.md` 骨架存在且含 5 项 god file 切片计划

### Task B：依赖锁单一事实源（P0-1）

**Files:**
- Delete: `src/backend/requirements-prod.lock`、`src/backend/requirements-dev.lock`（副本）
- Modify: `src/backend/Dockerfile`（`COPY config/requirements-prod.lock` + 按锁安装 + 移除 `if [ -f ]` 回退分支，锁文件缺失应构建失败而非静默回退）
- Create: `scripts/ci/check_prod_lock_singleton.py`（两份锁 diff 必须为空）

**Steps:**
- [ ] 合并两份锁（以含 extras 的 310 行版本为基底，重新生成到 `config/`，跑通 pip-audit）
- [ ] Dockerfile 改为显式 COPY + 安装，删除回退分支
- [ ] ci.yml 新增 lock singleton 门禁；pip-audit 对象与镜像安装对象强制一致
- [ ] CONTRIBUTING.md 依赖管理一节同步

**验收标准:**
- 全仓仅一份 `requirements-prod.lock`；CI audit 对象 == Dockerfile 安装对象（grep 验证）
- `docker build` 在锁文件缺失时失败

### Task C：可观测性"接线"收口（P0-3）

**Files:**
- Modify: `src/backend/app/middleware/logging.py`（`__call__` 完成/失败路径调 `record_api_request`/`record_api_error`；`_SKIP_PATHS` 改前缀匹配并补 `/api/v1/metrics`；request_id 改 32 位 hex；XFF 仅在 `TRUST_PROXY` 显式开启时采信；`_request_logger` 绑 user_id）
- Modify: `src/backend/app/middleware/exception_handling.py`（`handle_generic_exception` 调 `record_error`；BaseAppError 日志绑 user_id）
- Modify: `src/backend/app/db/`（SQLAlchemy `before_cursor_execute` 事件统一埋 `record_db_query`）
- Modify: `src/backend/app/telemetry.py`（version 从包元数据读取；`insecure` 配置化；excluded_urls 补 `/api/v1/metrics`）
- Modify: `src/backend/app/startup/__init__.py`（lifespan shutdown 调 `trace.get_tracer_provider().shutdown()`）
- Modify: `docker/compose/prod.yml`（`OTEL_ENABLED=true` + collector 服务）
- Modify: `config/alerting.yaml`（指标名对齐 `middleware/metrics.py` 实际定义或删除，把阈值并入应用内 AlertRule 文档）
- Modify: `src/backend/app/services/audit_service.py` + `startup/orchestration.py`（`cleanup_old_records` 按 `AUDIT_CLEANUP_HOUR` 挂 apscheduler cron）
- Modify: `src/backend/app/utils/logger.py`（InterceptHandler 转发 record extra；loguru `contextualize(request_id, user_id)` 包裹请求处理）
- Modify: `src/backend/app/main.py`（slow_request_threshold 0.5 → 5.0s，与 alerting 口径一致）
- Modify: `src/backend/app/services/monitoring_service.py`（启动钩子加载 active rules 重建监控任务；上报心跳指标）
- Modify: `scripts/ops/start_app.sh`（日志改 `>>` 追加；生产 `LOG_FORMAT=json` 消除 ANSI）
- Modify: `src/backend/app/services/ai_observability/logger.py`（`log_ai_call` 装饰器挂到 `ai_strategy_research_service.py`/`kb_chat_service.py`/`rag_service.py` 的 LLM 调用点；`_record_ai_call` 补 request_id；ai_call_log 加保留清理，仿 `cleanup_old_records`）

**Steps:**
- [ ] 死指标接线（RED 三件套：HTTP 请求、DB 查询、错误）
- [ ] 日志上下文贯穿（request_id/user_id 进服务层日志）
- [ ] 死配置清理/对齐（alerting.yaml、AUDIT_CLEANUP_HOUR、log_ai_call 装饰器）
- [ ] 生产 OTel 开启 + shutdown + 告警规则重启恢复
- [ ] 运维脚本日志追加与 JSON 化

**验收标准:**
- 刮取 `/api/v1/metrics` 时 `api_request_total` 随请求递增（实测）
- `alerting.yaml` 中每个指标名都能在 `middleware/metrics.py` grep 命中
- 服务重启后存量 AlertRule 自动恢复评估（测试覆盖）
- 服务层日志含 request_id/user_id（抽样实测）

### Task D：CI 门禁真伪校准

**Files:**
- Modify: `.github/workflows/ci.yml`（Lighthouse `--config=config/lighthouserc.js` 并删除 `|| LHCI_EXIT=$?`；monorepo-check 安装 ruff/mypy/pytest/Node 或删除该 job；governance job 改 `pytest tests/asset_research/ -m "not performance"` 目录选择器；backend-test 用 `-o addopts=...` 覆盖 `--maxfail=5`；补 `permissions: contents: read`；action 钉完整 SHA；补 concurrency）
- Modify: `.github/workflows/e2e.yml`、`nightly.yml`、`pr-check.yml`（就绪探测统一 `curl -sf` + 200 校验 `/api/v1/health` 与 `/health`；补 timeout-minutes；Playwright 缓存在 4 个浏览器 job 恢复；nightly dependency-audit 失败可见化并接线 `scripts/ci/report_nightly_failure.sh`）
- Modify: `scripts/ci/security_scan.sh`（改为调用现有 ratchet/门禁脚本，与 ci.yml 内联步骤对齐）
- Delete: `scripts/ci/run_tests.py`、`run_pytest_with_timeout.py`、`run_tests.sh`（死脚本）或接入 backend-test（`--timeout=120 --reruns 1`）
- Modify: `scripts/ci/check_deps_sync.py`（改名或改实现，使其真正校验 lock↔pyproject 同步）
- Create: `.github/dependabot.yml`（pip/uv + npm + docker + github-actions 四生态 weekly）

**Steps:**
- [ ] 死门禁修复（Lighthouse、monorepo-check、就绪探测）
- [ ] 稳定性硬化（timeout、concurrency、permissions、SHA、缓存）
- [ ] 门禁脚本与 CI 对齐（security_scan.sh、死脚本、check_deps_sync）
- [ ] dependabot 接入

**验收标准:**
- ci.yml 全绿且 Lighthouse 报告真实产出（`./lighthouse-reports` 存在）
- `make check-all` 与 CI 执行同一套检查（抽查一致性）
- 每个 job 有 timeout-minutes；actions 全部钉 SHA

### Task E：供应链与发布链路加固

**Files:**
- Modify: `.github/workflows/docker-publish.yml`（发布前 `needs` 测试 job；构建产物 `docker run` + health 冒烟；build-push-action 加 `provenance: true, sbom: true`；拒绝已存在 tag 重复推送）
- Modify: `.github/workflows/pr-check.yml`（删除 `pull_request_target` 触发与 smoke-tests 中的不受信任代码执行；修复 fork PR merge-ready label 逻辑）
- Modify: `.github/workflows/deploy-preview.yml`（接入真实托管并按 PR close 清理，或删除该 workflow；修正"Preview Environment Deployed"虚构评论）
- Modify: `docker/compose/prod.yml`（MySQL 对齐 9.4.0 与 CI 契约；挂载路径修正为仓库根相对路径 `../datas` 等）
- Modify: `src/backend/Dockerfile`、`src/frontend/Dockerfile`（基础镜像钉 digest；前端镜像补 HEALTHCHECK；删除 `RUN true` 残留）
- Modify: `.github/workflows/docs.yml`（mkdocs 插件按锁安装）

**Steps:**
- [ ] 发布门禁与镜像冒烟
- [ ] pull_request_target 安全整改
- [ ] 环境一致性（MySQL 版本、compose 挂载、镜像 tag）

**验收标准:**
- docker-publish 在测试未通过时无法发布
- 全仓无 `pull_request_target` 触发
- `docker compose -f docker/compose/prod.yml config` 挂载路径全部存在（校验）

### Task F：仓库卫生（246.7MB 被跟踪数据）

**Files:**
- Modify: `.gitignore`（补 `data/` 白名单 gitkeep；`.kiro/` 决策）
- Delete（tree-level，`git rm --cached`）: `data/datas/*.csv`（246.7MB，含 69.9MB bond_merged）、`data/dev/backtrader.db.bak.*`、`data/imports/yunjinqi_articles.jsonl`、`src/clientportal.gw/root/webapps/demo/gateway.demo.js`（vendored 产物）
- Modify: `scripts/ci/check-generated-artifacts.sh`（把 `data/` 纳入检查）

**Steps:**
- [ ] 数据文件移出 git 跟踪（历史重写 `git filter-repo` 单独排期，不阻塞本迭代）
- [ ] gitignore 与门禁脚本同步

**验收标准:**
- `git ls-files data/ | grep -v gitkeep` 为空
- 每个 CI job 的 checkout 体积显著下降（对比 246.7MB 基线）

### Task G：安全纵深收口

**Files:**
- Modify: `src/backend/app/api/live_trading/api.py` + `services/live_trading/manager.py`（网关记录绑定创建者 user_id；connect/disconnect/account/positions/list 校验归属，管理员豁免）
- Modify: `src/backend/app/services/auth_service.py`（注册保留 `ADMIN_USERNAME`；`_is_admin_user` 改为 DB 角色判定或强制默认管理员创建）
- Modify: `src/backend/app/rate_limit.py` + `docker/compose/prod.yml`（uvicorn `--proxy-headers --forwarded-allow-ips=<nginx 网段>`；生产强制 Redis 限流后端）
- Modify: `src/backend/app/services/direct_order_service.py`、`manual_gateway/`、`live_trading/manager.py`（网关连接/实例启停/下单调用点写服务端审计事件，复用 `utils/logger.py` 的 audit_logger）
- Modify: `src/backend/app/api/_dependencies.py`（`get_current_user` 增加轻量 is_active 校验（短 TTL 缓存）；修复 `has_permission` 依赖 TokenPayload 无 roles 的死代码；`/audit/records` 的 is_admin 失效修复）
- Modify: `src/backend/app/config.py`（生产判定改 fail-closed；`JWT_ALGORITHM` 白名单 validator `{HS256,HS384,HS512}`）
- Modify: `src/backend/app/api/airflow_callback.py`（共享密钥 header 校验）
- Modify: `docker/nginx.prod.conf`（静态资源补 CSP/X-Frame-Options/HSTS；生产关闭 `/docs` `/redoc` `/openapi.json` 或加白名单）
- Modify: `src/backend/app/api/`（AI 对话/分析端点挂 `limiter.limit`；公开行情端点评估配额）

**Steps:**
- [ ] 授权修复（BOLA、admin、token 失效）——按 ASVS V4 逐项闭环
- [ ] 审计权威化（服务端审计事件）
- [ ] 限流与配置守卫
- [ ] 网络边界（airflow callback、nginx 头、docs 暴露面、XFF 信任链）

**验收标准:**
- 新增测试：用户 B 无法断开/查询用户 A 的网关（BOLA 回归测试）
- 注册 `admin` 被拒绝（测试覆盖）
- 安全扫描全绿，且 `security_scan.sh` 与 CI 结论一致

### Task H：事件循环与数据库性能

**Files:**
- Modify: `src/backend/app/api/data/base.py:48`（`await asyncio.to_thread(ak.stock_zh_a_hist, ...)`）
- Modify: `src/backend/app/api/analytics.py:117`（`await asyncio.to_thread(parse_value_log, ...)`）
- Modify: `src/backend/app/api/scanners.py:212-216`（`await asyncio.to_thread(get_scanner_service().run, ...)`）
- Modify: `src/backend/app/api/portfolio/api.py`（5 处 `parse_value_log`/`_valued_source_positions` 调用包 to_thread）
- Modify: `src/backend/app/db/database.py` + `akshare_data_database.py`（MySQL 改 QueuePool：`DB_POOL_SIZE`/`DB_MAX_OVERFLOW`/`pool_recycle=3600`/`pool_pre_ping=True` 配置化）
- Modify: `src/backend/app/api/backtest_enhanced.py`、`overfitting.py`（任务状态进程内 1s TTL 缓存 + `ws_manager` 状态变更广播，去掉每客户端轮询）
- Modify: `src/backend/app/api/backtest_enhanced.py:187`（响应缓存键加入 `request.state.user_id`，修复缓存命中绕过所有权校验）
- Modify: `src/backend/app/services/workspace/units.py:540-545`（重排序改单次 `IN` 查询）
- Modify: `src/backend/app/models/paper_trading.py` + 新迁移（orders/trades 加 `(account_id, created_at)` 复合索引）
- Modify: `src/backend/app/api/scanners.py:194-205`（list_runs 加 limit/offset）
- Modify: `src/backend/app/api/analytics.py:410-480`（kline 端点加 `limit` ≤5000；指标计算移 to_thread）
- Modify: `src/frontend/src/composables/useChartResize.ts` 等 5 处（echarts 改 `echarts/core` 按需注册；确认 `echarts-gl` 去留）
- Create: `scripts/ci/async_blocking_check.py`（AST 识别 async 函数体内未包裹的同步 `requests`/`open`/`akshare.*`/`time.sleep`/`subprocess` 调用）+ `scripts/ci/async_blocking_allowlist.json`（初始豁免=当前存量）
- Modify: `.github/workflows/ci.yml`（backend-test job 接入 `async_blocking_check.py` 作为棘轮门禁）

**Steps:**
- [ ] 阻塞 I/O 清零（与仓库已有正确模式对齐）
- [ ] 连接池与 N+1（含 `evaluate_due_outcomes` 批量化，见 Task I）
- [ ] 缓存键用户维度（安全+正确性）
- [ ] async 阻塞检查脚本落地 + CI 接线 + 存量豁免清单（棘轮初始=存量，后续只降不升）

**验收标准:**
- `python3 scripts/ci/async_blocking_check.py` 退出码 0（存量豁免清单内，无新增违规）
- 豁免清单条目数 = 审计基线（B5/P1/P5 的 7 处），不得新增
- MySQL 连接复用实测（`SHOW PROCESSLIST` 观察无每请求新建）
- 缓存越权复现测试：用户 B 用用户 A 的 task_id 无法命中缓存

### Task I：后端代码质量

**Files:**
- Modify: `src/backend/app/services/asset_research/orchestrator.py:1630-1638`（`evaluate_due_outcomes` 改 `in_()` + `selectinload` 批量加载；policy 检查按 source_id 去重批量查询）
- Modify: `src/backend/app/services/ai_strategy_research_service.py:486`（`_run_pipeline` 1363 行按阶段拆 pipeline 子包——L 级，分多个迭代切片，本迭代完成拆分设计并先行拆分最独立的 2-3 个阶段）
- Modify: `src/backend/app/services/position_valuation.py`（`contract_spec_for` 492 行按资产类型拆解析函数）
- Modify: `src/backend/app/api/portfolio/api.py`（87 个私有 helper 下沉 `services/portfolio_valuation/`）
- Modify: 7 处 `sys.modules[__name__]` shim（`backtest_service.py:5`、`live_trading_api.py:5`、`manual_gateway_service.py:5`、`deps.py:9`、`portfolio_api.py:5`、`strategy_service.py:5`、`live_trading_manager.py:5`）→ 显式 re-export
- Modify: `src/backend/app/models/*.py`（77 个 relationship 分批改 `lazy="raise"` + 显式 eager load，配合测试暴露隐式加载点）
- Modify: `src/backend/app/middleware/exception_handling.py:97-114`（`BaseAppError` 增加 `status_code` 字段，删除字符串映射表）
- Modify: `src/backend/app/services/market_instrument.py`（9 个 `_lookup_*` 提取表驱动分发，去 53-65% 重复）
- Modify: `src/backend/app/api/`（分页规范统一：选定 page/page_size，提供共享 `PaginatedResponse` schema，写入 api/README.md 契约）
- Modify: `src/backend/app/db/database.py:22-52`、`config.py:850-862`、`main_routes.py:26-34`（惰性单例改 import 期初始化或加锁）
- Modify: `src/backend/app/services/ai_router/ollama_adapter.py:22` 等（默认值改引用 Settings 字段）
- Modify: 文档（Alembic revision 命名规范：新迁移只用日期前缀，存量不改）

**Steps:**
- [ ] S 级快修（N+1、shim、status_code、竞态、默认值）本迭代完成
- [ ] M/L 级切片（`_run_pipeline`、`contract_spec_for`、portfolio helper 下沉、lazy="raise" 分批）排入 194+

**验收标准:**
- `evaluate_due_outcomes` 单批次 DB 往返 ≤ 5 次（测试断言或 EXPLAIN 证据）
- 7 处 shim 全部改为 re-export，`api/README.md` 兼容窗口说明同步更新
- mypy 棘轮不升；大文件棘轮不新增超限文件

### Task J：测试体系加固

**Files:**
- Modify: `src/backend/tests/asset_research/test_schedule_runner.py:419-542`（`fire_at` 改动态 `now + timedelta(days=7)`）
- Modify: `tests/asset_research/test_report_artifacts.py:224-227`、`test_schedule_manifests.py:94`（`persist_identity` 显式传 `valid_from`）
- Modify: `tests/test_datetime_utils.py:24`（2 秒墙钟容差改 freeze/固定值）
- Modify: `src/backend/tests/conftest.py`（autouse fixture 统一重置 `_shared_hub`/`_shared_gateway` 等模块级单例）
- Modify: `src/backend/.coveragerc`（omit 收缩到真正需真实 broker 的 `ctp_tunnel`/`manual_gateway_service`；`gateway_health_service`/`live_instance_service`/`process_supervisor`/`live_execution_service` 移出并受门禁约束）
- Create: `tests/test_data_connectors.py`、`tests/test_quant_tools_runtime.py`（契约测试：注册/执行/异常路径）
- Modify: `src/backend/app/services/chunk_service.py`（确认死代码后删除或补测试）
- Modify: `tests/test_portfolio_ledger.py`（补 5-8 个异常用例：重复 idempotency_key、非法 quantity、卖超持仓）
- Modify: `tests/test_akshare_scheduler.py`（复用 `test_akshare_network_proxy.py` 注入模式补 fetch 失败/超时/退避）
- Modify: `scripts/dev/run-e2e.sh:80-85`（注入隔离 `DATABASE_URL=sqlite+aiosqlite:///$(mktemp -d)/e2e.db` + `DB_AUTO_CREATE_SCHEMA=true` + trap 清理）
- Modify: `src/backend/pytest.ini` 与 ci.yml（CI 覆盖 `--maxfail=5`；performance 套件移 nightly + 相对阈值断言或删除）
- Modify: `tests/test_extracted_modules.py:2237,2738` 等（4 个"前存故障" skip 修复或删除并开 ticket；`test_extracted_modules.py` 3776 行拆分为多个文件）

**Steps:**
- [ ] 时间炸弹拆除（freezegun 引入 requirements-dev）
- [ ] 覆盖率门禁诚实化（omit 收缩 + 零测试模块补测）
- [ ] 实盘失败路径测试（manual_gateway/live_execution 注入 fake adapter）
- [ ] e2e 隔离

**验收标准:**
- 测试在任意系统日期下全绿（验收时临时改系统日期到 2027-01-01 复跑 asset_research 套件）
- skip 数减半且每个 skip 带 ticket 引用
- 本地 `run-e2e.sh` 不触碰真实数据库（脚本内断言 DATABASE_URL 被覆盖）

### Task K：前端质量收口

**Files:**
- Modify: `src/frontend/src/views/strategy/useStrategyPage.ts`（6795 行按域拆 `useStrategyManagement`/`useAIResearchConfig`/`useAIResearchRuntime`/`useLiveHandoff` 等组合式函数，页面组合）
- Modify: `src/frontend/src/views/StrategyPage.vue`（2862 行 template 按功能区拆展示型子组件，props/emit 通信）
- Modify: `src/frontend/src/views/investment/StockAnalysisPage.vue`、`AssetAnalysisPage.vue`（拆至阈值以下并更新基线）
- Modify: `src/frontend/src/views/StrategyPage.vue`（179 行硬编码中文迁 i18n）、`useStrategyPage.ts`（278 行）、`PortfolioLedgerPage.vue`（40 行）、`AssetAnalysisPage.vue`（82 行）、`asset-research/*Panel.vue`（30 行）——合计 600+ 行
- Modify: `src/frontend/src/views/StrategyPage.vue:1551-2399`（`liveReadinessChecklistForReview` 模板方法调用改 computed 预映射）
- Modify: `src/frontend/package.json`（移除 `vue-echarts`、`@monaco-editor/loader` 死依赖）
- Modify: `src/frontend/src/main.ts:66-68`（删除全局图标注册改按需导入；静态 import watch）
- Modify: `src/frontend/src/router/index.ts`（补 `:pathMatch(.*)*` 404 兜底路由）
- Modify: `src/frontend/src/stores/auth.ts:7-9`（登出重置改事件驱动，解除对 3 个业务 store 的反向依赖）
- Modify: `src/frontend/src/main.ts:49-56`（errorHandler 触发全局事件由 ErrorBoundary 渲染友好兜底）
- Modify: `src/frontend/src/__tests__/views/StrategyPage.test.ts`（8380 行按特性拆分；中文文案断言改 i18n key 或显式 locale）
- Modify: `src/frontend/src/views/GatewayConnectDialog.vue:496`（唯一 `any` 改具体类型）

**Steps:**
- [ ] god 文件续拆（本迭代完成 useStrategyPage.ts 的第一层域拆分，页面模板拆分排入 194）
- [ ] i18n CJK 清零 + CI 加回 CJK 扫描门禁
- [ ] 依赖卫生与 bundle（echarts 按需引入见 Task H）

**验收标准:**
- 前端 large_file_ratchet 全绿
- i18n CJK 扫描 0 命中
- bundle budget 不超（entry gzip ≤300KB）

### Task L：文档与 DX 一致性

**Files:**
- Modify: `README.en.md`（16 个死链接改 Diátaxis 新路径；`ai-for-investor.git` → `cloudQuant/backtrader_web.git`；docker 路径 `docker/docker-compose.yml`）
- Modify: `CONTRIBUTING.md:21`（克隆命令修正）；`CONTRIBUTING.md:142-171`（workspace 成员与 `uv.lock` 说明同步 D-3）
- Modify: 根 `pyproject.toml:13-14`、`scripts/dev/check_all.sh:24`（`src/bt_api_py` 已空壳化，移出 members 或恢复其 pyproject）
- Modify: `CHANGELOG.md`（补 176-192 摘要（按迭代归并）、版本块逆序、死链接修正、releases URL）
- Modify: `src/backend/app/main.py:104`、`src/backend/pyproject.toml:3`、`src/frontend/package.json`、`CHANGELOG.md`、`README.md:183`（版本号统一为单一事实源）
- Modify: `AGENTS.md:55,156,179,180`（ruff 规则集、pre-commit 清单、死链接——改为引用文件而非复制配置摘要）
- Modify: `docs/iterations/README.md`（174/179/180/192 四行状态刷新并补收口链接；新增 193 行）
- Modify: `scripts/ci/check_doc_links.py:16`（扫描根扩展为全仓 `*.md`，排除 node_modules/.git/.venv/archived）
- Create: `docs/adr/014-uv-workspace-adoption.md`、`015-three-tier-data-platform.md`、`016-asset-research-model-governance.md`（从对应迭代 PLAN 提炼）
- Modify: `README.md` 快速开始（补 `python scripts/dev/seed_dev_data.py` 演示数据说明）
- Delete: `.readthedocs.yml`（失效配置）
- Modify: `docs/INDEX.md`（补 explanation/tutorials/examples/architecture 四行）
- Modify: `MVP_PRELAUNCH_NOTES.md`（移入 `docs/archive/`）
- Modify: `src/backend/app/api/`（~180 个缺 summary 的 route 分批补 summary；`scripts/ci/export_openapi.py` docstring 路径修正）
- Modify: `docs/iterations/迭代185/186/187`（补最小 ACCEPTANCE.md；182 的 bug.md 转 PLAN 任务表）

**Steps:**
- [ ] 根级入口文档一致性（README.en/CONTRIBUTING/AGENTS/CHANGELOG/版本号）
- [ ] 门禁扩展（check_doc_links 根级化——修完这条才能守住 D-01 类回归）
- [ ] ADR 补录与索引刷新

**验收标准:**
- `python scripts/ci/check_doc_links.py` 覆盖根级文件且全绿
- `make check-all` 本地可执行（bt_api_py 声明与磁盘事实一致）
- 新开发者按 README 快速开始 + seed 命令跑通（对照验证）

### Task M：DR 与备份恢复演练（生产就绪补盲）

**Files:**
- Create: `docs/runbooks/backup-restore.md`（MySQL 物理备份恢复步骤、PITR、验证清单、RPO/RTO 目标）
- Modify: `scripts/ops/backup_mysql.py`（补 `--verify` 子命令：恢复到临时库 + 行数校验 + 关键表抽样）
- Modify: `scripts/dev/run-restore-drill.sh`（Create；staging/本地实跑恢复演练，trap 清理临时库）

**Steps:**
- [ ] 编写恢复 runbook（含 RPO/RTO 目标、责任人、升级路径）
- [ ] backup 脚本补 `--verify` 自检
- [ ] 本地/staging 实跑一次完整恢复演练并记录证据

**验收标准:**
- `docs/runbooks/backup-restore.md` 存在且含可执行命令
- `bash scripts/dev/run-restore-drill.sh` 退出码 0 且输出含"restore verified: row counts match"
- 若本迭代无法 staging 演练，必须在 ACCEPTANCE.md 显式记录递延理由与 194 计划条目

---

## 4. 排期与依赖

| 批次 | Tasks | 理由 |
| --- | --- | --- |
| 第 1 批（P0 清零，~3 人日） | A、B、C 的"接线"部分 | CI 转绿恢复门禁信用；供应链审计对象与交付工件一致；RED 指标有真实数据 |
| 第 2 批（P1 快修，~5 人日） | D、E、F、G 的 S 级项、H 的 to_thread 项、J 的时间炸弹与 e2e 隔离、L 的根级文档一致性 | 均为 S 级、单文件或多文件小改、互相独立 |
| 第 3 批（P1 中等，~8 人日） | G 的 BOLA/审计、H 的连接池与轮询缓存、I 的 M 级项、J 的实盘失败路径、K 的 useStrategyPage 第一层拆分、L 的 CHANGELOG/ADR、M 的 runbook | 需要测试配合与评审带宽 |
| 第 4 批（转入 194+） | I/K 的 L 级切片（`_run_pipeline`、`contract_spec_for`、StrategyPage 模板拆分、lazy="raise" 全量）、F 的 git 历史重写、M 的 staging 恢复演练（若本迭代未完成） | L 级改动单迭代消化不了，切片配合棘轮逐批推进 |

**显式交付物**：第 1 批结束创建 `docs/iterations/迭代194-工程债切片续作/PLAN.md` 骨架，登记第 4 批全部 L 级条目，作为 Task A/I/K/M 的收口验收项（避免递延遗漏）。

依赖关系：C（指标接线）→ C 的告警对齐依赖前者完成；D 的 Lighthouse 修复依赖 A 的 CI 转绿；L 的 check_doc_links 扩展必须先于其他文档修改合入（否则门禁无法守住）；M 的恢复演练依赖 backup 脚本 `--verify` 先就绪。

---

## 5. 审计复核修正记录

审计初稿经独立抽查复核，修正两条：

1. **CI/CD 初稿 F-01（容器健康检查指向不存在路由、生产栈无法启动）不成立。** 根路径 `/health` 确实存在：`src/backend/app/main_routes.py:99` 经 `main.py:129` `register_runtime_routes(app, ...)` 注册。`Dockerfile:46` 与 `docker/compose/prod.yml:110` 的探针路径有效。保留的建议仅剩 e2e/nightly 就绪探测 `curl -s` 不带 `-f`（404 时退出码仍为 0）的硬化项，已降级为 P2 并入 Task D。
2. **安全初稿 F-07（Dockerfile 锁分支永不命中）不成立。** `COPY src/backend` 会把 `src/backend/requirements-prod.lock` 复制进 WORKDIR，`if [ -f requirements-prod.lock ]` 分支命中，镜像按该锁（310 行，含全部 extras）安装。真实问题是**双锁漂移**：CI 阻断审计的是 `config/requirements-prod.lock`（68 行，无 extras）——已在 P0-1/Task B 中按此定性处理。

已实跑复核确认的关键证据：`large_file_ratchet.py` 红灯 8 项（2026-08-13 实跑）；`config/lighthouserc.js` 存在而仓库根 `lighthouserc.js` 不存在；`record_api_request` 等指标函数除 `middleware/metrics.py` 外零调用；`api/live_trading/api.py:141-216` 网关端点无 user_id 归属校验；`auth_service.py:53-56` 按用户名判定管理员且注册无保留名检查；`.coveragerc` 排除 5 个实盘服务模块。

---

## 6. 回滚与应急策略（计划优化补充）

本迭代触及生产就绪核心（安全守卫、CI 门禁、供应链、可观测性），每批变更须有可回滚路径：

| 变更域 | 回滚触发条件 | 回滚手段 | 灰度验证 |
| --- | --- | --- | --- |
| 安全 fail-closed（D-5/Task G） | 生产判定误关守卫导致合法请求 401/403 激增 | `DEBUG=true` 临时恢复（仅限事件窗口）；config 回退 commit | staging 先行 24h；上线后监控 4xx 错误率 1h |
| BOLA 网关归属校验（Task G） | 管理员跨用户操作被误拦 | `is_admin` 豁免路径已保留；紧急时临时降级到原逻辑 | 新增回归测试先行；上线后抽查 admin 操作日志 |
| 锁文件合并（Task B） | 镜像构建失败或缺 extras | 回退 `src/backend/requirements-prod.lock` 副本 + Dockerfile 原分支 | `docker build` + health 冒烟先于推送 |
| CI 基线刷新（Task A） | 棘轮误报阻塞合入 | 回退 `large_file_baseline.json` commit；`--update` 已加 env 守卫 | 本地 `large_file_ratchet.py` 先行验证 exit 0 |
| 限流键/代理头（Task G） | nginx 后限流误杀正常流量 | `TRUST_PROXY`/`--forwarded-allow-ips` 回退到不信任；Redis 后端回退 in-memory | staging 压测验证 |
| OTel 开启（Task C） | 采集器拖慢请求或 span 丢失 | `OTEL_ENABLED=false` 单环境变量关闭 | 先 dev -> staging -> prod 灰度 |
| 可观测性接线（Task C） | middleware 异常影响吞吐 | `record_*` 调用包 try/except 不影响主路径；可单独注释 | `/api/v1/metrics` 刮取验证后放量 |

**原则**：所有安全/CI 变更必须先在 dev 分支验证、staging 灰度、prod 上线后 1h 监控窗口；任何 P0 回滚须 ≤15 分钟可执行。回滚命令清单归档 `docs/runbooks/rollback-193.md`。
