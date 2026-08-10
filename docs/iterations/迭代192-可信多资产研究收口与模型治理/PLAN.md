# 迭代 192：可信多资产研究收口与模型治理 Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在迭代 191 的多资产研究框架基础上，把“框架层通过”推进到“真实资产 T1、模型治理、可观测性和 LLM 可信度都可验收”，并形成可复制的资产接入和生产发布门禁。

**Architecture:** 192 不重写 191 的领域模型、编排器、插件协议和不可变预测链，而是补四类断点：真实数据源与主数据、模型验证与晋级、生产运行与生命周期、LLM 引用可信与安全。先以期货和债券两个资产作为真实 T1 试点，其余四类资产按同一门禁迁移，避免把六类插件“有骨架”误当成六类研究已可用。

**Tech Stack:** Python 3.10+、FastAPI、SQLAlchemy 2.0、Alembic、MySQL 9.4.0、pytest、Prometheus/OpenTelemetry、Vue 3 + TypeScript、Vitest、Playwright；候选新增 `purgedcv`/`deflated-sharpe` 作为模型验证实现参考。

---

## 0. 191 验收结论（2026-08-07 复核）

| 范围 | 当前结论 | 依据 |
| --- | --- | --- |
| P0 公共底座、Schema、迁移、编排、前端工作台 | 部分通过 | `IMPLEMENTATION_STATUS.md` 记录 P0a/P0b/P0c 的代码与 MySQL 9.4.0 隔离验收通过；但当前工作树复跑 `tests/asset_research` 为 **301 passed / 3 skipped / 4 failed**，不能按“已全部通过”归档 |
| T1 真实资产研究观察 | 试点通过 | 2026-08-07 已新增真实 AkShare provider、获批 manifest 和可复现 T1 脚本；一次性 SQLite 中期货/债券均达到 `ELIGIBLE`。生产 MySQL 和共享库仍待正式导入 |
| T2 方向信号晋级 | NO-GO | 没有真实 walk-forward、200 条成熟行动信号、校准、前瞻影子验证和审批证据 |
| 迁移与发布 | CONDITIONAL | MySQL 9.4.0 隔离迁移和本机共享库升级有证据；生产备份恢复、升级中断恢复、双写对账和 contract 未完成 |
| 运行非功能 | NO-GO | 只实测了 NFR-C03/C04；L01-L08、C01/C02/C05、故障注入、dashboard/告警、生命周期执行和 LLM 预算仍缺 |
| 行业可信度 | 待提升 | 当前 `PredictionHead` 使用确定性 shadow rule，T2 门禁虽 fail-closed，但缺少模型卡、漂移、CPCV/DSR、引用级事实校验等生产级治理 |

### 0.1 当前自动化失败

在本机 Anaconda base 环境执行：

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q -p no:sugar tests/asset_research
```

结果：`4 failed, 301 passed, 3 skipped, 20 warnings`。

失败项：

- `test_runner_executes_public_shadow_schedule_without_a_user`
- `test_visible_history_includes_public_shadow_but_excludes_admin_evaluation`
- `test_runner_retries_with_original_cutoff_and_preserves_failed_run`
- `test_schedule_freezes_one_identity_version_and_creates_a_schedule_sourced_run`

根因：测试固定 `fire_at=2026-08-03`，但 `persist_identity()` 用真实当前时间 `_now()` 写 `valid_from`；当测试在 2026-08-07 或之后运行时，运行时身份检查得到 `INSTRUMENT_VERSION_STALE`，调度无法生成 prediction。这说明 191 的时间敏感测试不是可复现的时间旅行夹具，计划文档中的“全部通过”不能被视为可在任意日期复现的验收证据。

## 1. 191 尚未实现的关键清单

| 类别 | 缺口 |
| --- | --- |
| 真实数据 | 期货/债券已新增获批 AkShare provider；其余四类仍没有获批 provider adapter。默认 `StrictMarketDataAdapter` 仍只读本地 `akshare_data`，AkShare provider 仅在环境开关显式开启时启用 |
| 主数据 | `asset_instruments` 没有真实债券条款、基金份额/NAV、期货合约规格、期权链、外汇报价边和数字货币场所/链上数据 |
| 身份 | 部分验收要求仍未通过：跨市场歧义候选、衍生品可还原标的/到期/乘数/结算、缺失 raw snapshot 的持久化路径 |
| 结果闭环 | 结果只在固定夹具下可评分；真实日历、费用、基准、成本、修订数据、到期/换月/NAV lag 未形成生产证据 |
| T2 模型 | 没有离线 walk-forward、purge/embargo、CPCV、DSR/PBO、校准、bootstrap、模型卡和影子 cohort |
| 非功能 | NFR-L01 至 L08、C01/C02/C05、来源超时/断路、worker 重启、数据库断连、前端性能基线均未完成 |
| 指标 | 已接入 12 个低基数 series，但缺少 `asset_research_queue_depth`、`asset_research_llm_*`、`asset_research_migration_reconciliation_*` |
| 生命周期 | `AssetResearchRetentionService` 只有 dry-run，没有授权执行器、删除/去标识化、对象存储回收、legal hold 审批和审计墓碑 |
| LLM | 缺少 token/金额预算、四级降级实测、引用级事实校验、原子 claim 验证和 prompt injection 防护 |
| 股票兼容 | 只读兼容桥已实现，OFF/SHADOW/ENFORCE 双写、结构化对账、两个发布版本无 `DEFECT`、contract 和恢复演练未完成 |
| 前端 | 多资产工作台壳已实现，但债券/基金/期权/外汇/数字货币专属面板、真实空态/失败态和历史成绩单未完成 |
| 治理 | 191 的 P0a-P0c 门禁、ADR、RACI、风险 owner、Go/No-Go 签署记录和紧急变更流程尚未形成可审计证据 |
| 测试可复现性 | 时间敏感 fixture 未冻结时钟，已导致 4 个测试在当前日期失败 |

## 2. 行业最佳实践调研结论

外部调研不是照搬某一家实现，而是把下面几类原则固化为 192 的验收门禁。

| 主题 | 关键原则 | 参考 |
| --- | --- | --- |
| 模型风险管理 | 模型治理应覆盖设计、数据、解释、监控、事故响应和依赖关系；独立挑战、持续监控、结果分析是核心 | [Fiddler: Achieving Responsible AI in Finance](https://www.fiddler.ai/blog/achieving-responsible-ai-in-finance)；[VerifyWise: SR 11-7, SS1/23, OSFI E-23](https://verifywise.ai/blog/model-risk-management-ai-ml) |
| Point-in-time | 特征必须区分事件时间 `event_timestamp` 和写入时间 `created_timestamp`；训练/回测查询只能取事件时点前已存在的数据，否则静默泄漏未来信息 | [The Neural Base: Point-in-time correctness](http://theneuralbase.com/feature-store/learn/advanced/point-in-time-correctness/) |
| 金融时间序列验证 | 标签重叠必须 purge，测试后必须 embargo；walk-forward、CPCV、Deflated Sharpe、PBO、MinTRL 用于控制过拟合和多重测试偏差 | [purgedcv](https://github.com/eslazarev/purged-cross-validation)；Bailey & Lopez de Prado, 2014 |
| 数据治理与血缘 | 风险数据和报告需要可审计的列级血缘、时点重建、依赖清单和数据所有权；BCBS 239 把 lineage 作为合规支柱 | [Bigeye: Lineage for Financial Services](https://www.bigeye.com/blog/introducing-lineage-for-financial-services)；[Moody’s: BCBS 239 in the Agentic AI Era](https://www.moodys.com/web/en/us/kyc/resources/insights/bcbs-239-in-the-agentic-ai-era-from-compliance-to-command-center-data-lineage-and-governance.html) |
| 市场数据许可 | 许可应区分显示、派生、再分发、缓存和用途；授权状态必须在采集、存储、报告、导出和删除各层一致执行 | [W3C Market Data ODRL Profile](https://w3c.github.io/market-data-odrl-profile/patterns_temp.html) |
| LLM 可信 | 金融报告应做原子 claim 验证、字段级引用、事实数值与来源绑定；不能只靠 prompt 禁止幻觉 | [FinGround: Detecting and Grounding Financial Hallucinations via Atomic Claim Verification](https://arxiv.org/abs/2604.23588)；[Bigdata.com: The content layer problem in Financial AI agents](https://bigdata.com/blog/the-content-layer-problem-in-financial-ai-agents) |
| AI 安全 | LLM/agent 必须独立鉴权、最小权限、输出白名单、prompt 隔离、敏感数据脱敏；不能让提示词或工具权限放大用户权限 | [Coalition for Secure AI: Who’s Minding the Agent?](https://www.coalitionforsecureai.org/whos-minding-the-agent-a-new-framework-for-ai-identity-and-access-control/)；[FinGuard](https://github.com/suryanshgupta9933/FinGuard) |
| 可观测性 | 生产模型必须监控数据漂移、预测漂移、性能衰减、失败率和预算；告警必须有 owner、runbook 和恢复条件 | [Fiddler](https://www.fiddler.ai/blog/achieving-responsible-ai-in-finance) 的 monitoring/incident response 结论 |

## 3. 192 设计决策

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| D-1 | 先完成期货、债券两个真实资产 T1，其余四类按同一门禁后续接入 | 六类资产同时真实接入超出单迭代合理容量；期货已有合约/期权链基础，债券能证明非价格型研究链路 |
| D-2 | 模型验证优先复用 `purgedcv`/`deflated-sharpe` 方法论，再实现内部接口 | 行业已有成熟、开源的 purge/embargo/CPCV/DSR 实现，避免手写统计门槛后再返工 |
| D-3 | PIT 层不立即引入 Feast，而是扩展现有 `asset_source_snapshots` 与观测时点验证器 | 当前规模没有在线 feature store 需求；先固化时间语义、验证器和血缘，后续规模需要时再迁移 |
| D-4 | LLM 只能解释结构化事实，且必须输出字段级证据 ID；引用校验作为阻断门禁 | 191 已把 LLM 排除在决策权威之外，192 补报告可信闭环 |
| D-5 | 数据许可采用 ODRL 风格注册表语义，授权决定在采集前和导出/保留时各执行一次 | 防止“研究类型已授权”被误当作“允许导出/再分发/长期缓存” |
| D-6 | 所有时间敏感测试使用可注入时钟 | 当前 4 个失败已证明真实 `now` 会破坏历史 fire/cutoff 测试 |

## 4. 工作包与验收

### Task P0: 修复 191 当前回归并建立时间旅行测试基线

**Files:**
- Modify: `src/backend/app/services/asset_research/orchestrator.py:299`
- Modify: `src/backend/tests/asset_research/test_schedule_runner.py`
- Modify: `src/backend/tests/asset_research/test_schedules.py`
- Create: `src/backend/tests/asset_research/conftest.py`
- Modify: `docs/iterations/迭代191-AI多资产分析研究与设计/IMPLEMENTATION_STATUS.md`

**Steps:**

1. 为 `persist_identity()` 增加可注入 `valid_from`，并把 `_now()` 改为可替换 clock，避免真实当前时间污染历史 fixture。
2. 在 `tests/asset_research/conftest.py` 增加固定 UTC clock fixture，覆盖所有 schedule/task/identity/outcome 时间测试。
3. 复跑 4 个失败测试，确认原因从 `INSTRUMENT_VERSION_STALE` 变为通过。
4. 更新 191 实施状态，明确 2026-08-07 复跑结果和修复 commit，不得继续声称当前工作树“全部通过”。

**Acceptance:**
- `pytest tests/asset_research` 在任意日期均通过。
- 任意测试若使用历史 `fire_at`，其身份 `valid_from` 必须早于或等于该时间。

### Task P1: 真实数据源、主数据和资产 T1 试点

**Files:**
- Create: `src/backend/app/services/asset_research/providers/base.py`
- Create: `src/backend/app/services/asset_research/providers/futures_cffex.py`
- Create: `src/backend/app/services/asset_research/providers/bond_cn.py`
- Create: `src/backend/app/services/asset_research/importers/approved_manifest_importer.py`
- Create: `scripts/ops/import_asset_research_manifest.py`
- Modify: `src/backend/app/services/asset_research/source_registry.py`
- Modify: `src/backend/app/services/asset_research/master_data.py`
- Modify: `src/backend/app/services/asset_research/data.py`

**Steps:**

1. 定义 `AssetDataProvider` 接口：声明来源 ID、域名/URL 白名单、超时、响应大小、并发、重试、许可范围和 capability。
2. 实现期货试点：交易所结算/合约规格、交易/夜盘日历、bid/ask、费率/保证金/限仓、到期和换月映射。
3. 实现债券试点：条款/现金流、官方估值/收益率曲线、信用事件、净价/全价、可执行报价边和披露新鲜度。
4. 实现审批清单导入器：只接受带 evidence URI/hash 的来源、主数据、日历和 manifest；dry-run 后写入。
5. 用真实获批清单打开 capability，但保留 `execution_disabled=true`。

**Acceptance:**
- `asset_data_source_registry`、`asset_instruments`、`asset_schedule_manifests` 有可追溯真实行。
- 期货和债券的 `/capabilities` 返回 `research_enabled=true`，且六类资产仍无下单路径。
- 六类资产至少各保留一个 `ELIGIBLE/DEGRADED/REJECTED` 固定夹具，并新增在线冒烟证据。

**2026-08-07 落地证据：**

- 新增 `config/asset_research_approved_manifest.json` 和
  `scripts/ops/import_asset_research_manifest.py`；
- 新增 `AkShareFuturesProvider`/`AkShareBondProvider`，真实字段映射见
  [AkShare 文档镜像](../../reference/akshare/README.md)；
- 新增 `scripts/ci/run_asset_research_akshare_t1.py`，真实 T1 证据见
  `evidence/2026-08-07-akshare-real-t1.json`；
- 期货 `IF2609` 与债券 `sh110085` 在获批来源/主数据下均达到 `ELIGIBLE`。

### Task P2: 非功能、韧性、可观测性和生命周期执行

**Files:**
- Modify: `src/backend/app/config.py`
- Modify: `src/backend/app/middleware/metrics.py`
- Modify: `src/backend/app/api/metrics.py`
- Modify: `src/backend/app/startup/asset_research.py`
- Create: `src/backend/app/services/asset_research/load_testing.py`
- Create: `src/backend/app/services/asset_research/lifecycle_executor.py`
- Create: `docs/iterations/迭代192-可信多资产研究收口与模型治理/RUNBOOKS/NFR.md`
- Create: `docs/iterations/迭代192-可信多资产研究收口与模型治理/RUNBOOKS/FAILOVER.md`

**Steps:**

1. 建立 `FIXTURE/CAPACITY/FAILURE/FRONTEND` 四类测试剖面，执行并归档 NFR-L01 至 L08、C01/C02/C05 的 p50/p95/p99。
2. 补齐 `asset_research_queue_depth`、LLM tokens/cost/fallback 和迁移对账指标；保持低基数标签约束。
3. 增加来源域名白名单、连接/读取/总超时、响应大小、断路器、429/5xx 重试和故障注入测试。
4. 实现 `AssetResearchRetentionExecutor`：先 dry-run，再按来源许可、地区、legal hold、tombstone、对象存储依赖顺序执行；所有删除/去标识化写审计墓碑。
5. 增加 dashboard 和告警 runbook，完成至少一次告警触发/恢复演练。

**Acceptance:**
- NFR 报告包含提交号、数据库方言、fixture 版本、并发配置和原始结果位置。
- 生命周期执行器不会删除 legal hold 记录，且每个动作都有 actor、reason、evidence URI 和可回滚证据。
- 来源/LLM/worker/数据库故障注入不产生重复 prediction，也不会把失败数据补成中性。

### Task P3: 模型验证、模型卡和 T2 晋级治理

**Files:**
- Modify: `src/backend/pyproject.toml`
- Create: `src/backend/app/services/asset_research/evaluation.py`
- Create: `src/backend/app/services/asset_research/model_cards.py`
- Create: `src/backend/app/services/asset_research/drift.py`
- Modify: `src/backend/app/services/asset_research/promotion.py`
- Modify: `src/backend/app/api/asset_research.py`
- Create: `src/backend/tests/asset_research/test_evaluation.py`
- Create: `src/backend/tests/asset_research/test_model_cards.py`

**Steps:**

1. 在隔离数据集上实现并验证 purge/embargo、walk-forward、CPCV、PBO、Deflated Sharpe 和 MinTRL。
2. 增加模型卡 Schema/API：模型目标、标签、训练窗口、embargo、基线、成本、artifact hash、限制、失败模式和 owner。
3. 增加影子 cohort 评分流水线和漂移检测（数据漂移、预测漂移、校准漂移、concept drift 代理）。
4. 将 T2 晋级门禁改为必须引用 evaluation artifact hash、model card、drift 报告和五方审批事件。
5. 对期货和债券试点至少积累满足当前 T2 门槛的前瞻影子记录；未达到前保持 `SHADOW`。

**Acceptance:**
- 任何 `PROMOTED` 状态都可通过不可变审批历史追溯到完整评估证据。
- `head_spec_hash`、scope、基线、成本、artifact 和 drift 任一项不一致都不能发布方向建议。
- 离线评估结果与影子运行统计分开展示，不把回测/离线验证冒充真实前瞻。

### Task P4: LLM 引用可信、预算和安全边界

**Files:**
- Create: `src/backend/app/services/asset_research/llm_guardrails.py`
- Create: `src/backend/app/services/asset_research/citation_verifier.py`
- Modify: `src/backend/app/services/asset_research/reports.py`
- Modify: `src/backend/app/services/asset_research/artifacts.py`
- Modify: `src/backend/app/schemas/asset_research.py`
- Modify: `src/frontend/src/views/investment/AssetAnalysisPage.vue`
- Create: `src/backend/tests/asset_research/test_llm_guardrails.py`
- Create: `src/backend/tests/asset_research/test_citation_verifier.py`

**Steps:**

1. 强制 LLM 输出结构化报告章节，所有数值/结论字段必须引用 evidence ID 或声明 `REPORT_RENDER_FAILED`。
2. 实现原子 claim 验证：从冻结快照重建可验证事实，检测数字、单位、日期、来源归属和动作语义被改写。
3. 实现 prompt injection 防护：LLM 不接收用户自由文本指令、工具权限白名单、无数据库/订单/导出副作用。
4. 实现每任务、每日、每月 token/金额预算，80% 告警、100% 停止新调用，四级降级到确定性模板。
5. 前端对证据缺失、引用校验失败和降级模板显示明确状态，不显示无证据文本。

**Acceptance:**
- 注入与结构化事实冲突的文本后，页面/API/PDF 仍等于发布决定。
- 每个公开标量都有可点击/可导出的证据来源或明确不可用原因。
- LLM 不可用、预算耗尽、输出超限时，确定性结果和风险披露仍可用。

### Task P5: 股票兼容双写、结构化对账和 contract 准备

**Files:**
- Create: `src/backend/app/services/asset_research/stock_dual_write.py`
- Create: `src/backend/app/services/asset_research/stock_reconciliation.py`
- Modify: `src/backend/app/services/asset_research/stock_compat.py`
- Modify: `src/backend/alembic/versions/` 新 revision（如需要持久化 cohort/switch 审计）
- Create: `src/backend/tests/asset_research/test_stock_dual_write.py`
- Create: `src/backend/tests/asset_research/test_stock_reconciliation.py`

**Steps:**

1. 实现 OFF/SHADOW/ENFORCE 三种模式，SHADOW 新写失败必须告警且不改变旧响应。
2. 实现结构化对账：身份、cutoff、质量、发布动作、原因、证据、outcome 和成本；差异分类为 `EXPECTED_MAPPING`、`NONDETERMINISTIC_PRESENTATION`、`SOURCE_OR_TIMING`、`DEFECT`。
3. 对两个发布版本进行 cohort 对账，`DEFECT=0` 且所有差异有 owner/reason/evidence。
4. 演练备份恢复、downgrade/forward-repair、中断恢复和回退开关。
5. 只有对账和恢复证据齐备后，才评审旧表 contract；192 不默认执行 contract。

**Acceptance:**
- 旧 `/api/v1/stock-analysis` 和 `/investment/stock-analysis` 保持兼容。
- SHADOW 双写失败不会污染旧响应，且新写差异可查询。
- 没有未解释 `DEFECT` 前，禁止旧表 contract 或删除旧表。

### Task P6: 资产专属页面、报告和浏览器验收

**Files:**
- Modify: `src/frontend/src/views/investment/AssetAnalysisPage.vue`
- Modify: `src/frontend/src/api/assetResearch.ts`
- Modify: `src/frontend/src/composables/useAssetAnalysisTask.ts`
- Create: `src/frontend/src/components/asset-research/FuturesPanel.vue`
- Create: `src/frontend/src/components/asset-research/BondPanel.vue`
- Create: `src/frontend/src/components/asset-research/ModelCardPanel.vue`
- Modify: `src/frontend/src/i18n/locales/zh-CN.ts`
- Modify: `src/frontend/src/i18n/locales/en-US.ts`

**Steps:**

1. 为期货和债券实现专属展示：期货合约规格/换月/日历/保证金，债券条款/现金流/久期/曲线/信用状态。
2. 增加加载、空、失败、不可用和 `RESEARCH_ONLY` 状态，不能把未获批资产伪装成可用。
3. 增加模型卡、历史成绩单和引用证据面板。
4. 用真实浏览器验证资产切换、stale response、网络恢复、键盘和无障碍。

**Acceptance:**
- 页面只显示服务端 capability 允许的内容，前端参数不能开启资产或方向。
- `npm run typecheck`、`npm run test -- --run`、`npm run build` 和 Playwright 关键路径通过。

### Task P7: 治理、CI 和 192 验收证据

**Files:**
- Create: `docs/adr/011-asset-research-model-validation.md`
- Create: `docs/adr/012-market-data-license-registry.md`
- Create: `docs/adr/013-llm-report-citation-and-prompt-isolation.md`
- Create: `docs/iterations/迭代192-可信多资产研究收口与模型治理/ACCEPTANCE.md`
- Modify: `docs/iterations/README.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/ci/run_asset_research_capacity.py`

**Steps:**

1. 为 provider、模型评估、许可、LLM 引用、双写和生命周期执行建立 ADR 和变更单模板。
2. CI 增加固定时钟回归、MySQL 9.4.0 迁移合同、容量/韧性、浏览器和依赖许可证检查。
3. 将 192 验收拆成 Gate 0 决策、P0-P7 工作包证据、T1/T2 判定，并把 191 验收文档中的未完成项映射到 192。
4. 更新 `docs/iterations/README.md`，补充 185-192 状态，避免索引继续停在 184。
5. 记录每次 Go/No-Go 的提交号、命令、原始输出、owner、approver 和已知偏差。

**Acceptance:**
- 文档链接检查通过，`alembic heads` 只有一个 head。
- 后端 pytest、Ruff、Mypy、前端 typecheck/test/build、Playwright 均通过。
- 所有验收结论都有可复现证据，不以文件勾选代替证据。

## 5. 192 验收门禁

| Gate | 必须通过 |
| --- | --- |
| G0 | 191 当前 4 个失败修复；所有时间敏感测试在任意日期可复现 |
| G1 | 期货、债券真实 T1：试点已通过；生产 MySQL 导入、真实浏览器和故障注入仍为发布门禁 |
| G2 | NFR-L01 至 L08、C01/C02/C05 和故障注入全部有归档报告 |
| G3 | 指标、dashboard、告警、trace、LLM 预算和生命周期执行器有触发/恢复证据 |
| G4 | T2 晋级必须有 model card、purge/embargo/CPCV/DSR 证据、drift 报告和五方审批；真实影子观察自 2026-08-07 开始，至少 60 个交易日后才能验收；未满足保持 SHADOW |
| G5 | LLM 引用校验、prompt injection、导出和页面一致性通过对抗测试 |
| G6 | 股票双写/对账 `DEFECT=0`，旧接口回归通过，contract 不默认执行 |
| G7 | 192 文档、ADR、CI、MySQL 9.4.0 迁移和证据包完整 |

## 6. 非目标

- 不在 192 接入真实账户、持仓、订单、券商、CTP、模拟盘执行或杠杆建议。
- 不把“六类插件存在”当作“六类资产可用”。
- 不立即引入在线 feature store、分布式训练集群或全市场扫描。
- 不删除旧股票表、不做无审批 contract。
- 不修改已批准的历史预测/outcome 事实。
- 不把离线回测、在线冒烟或单次成功样本当作 T2 晋级证据。

## 7. 执行建议

建议使用 `subagent-driven-development` 分波执行，每个工作包独立 PR、独立证据；P0 必须在任何新业务开发前关闭。P1-P6 可并行，但 P1 的期货/债券数据接入必须完成 Gate 0 决策和 provider 合同冻结。P7 在 P0-P6 有证据后统一收口。

## 8. 外部参考资料

- Fiddler: [Achieving Responsible AI in Finance](https://www.fiddler.ai/blog/achieving-responsible-ai-in-finance)
- VerifyWise: [Model risk management for AI and ML](https://verifywise.ai/blog/model-risk-management-ai-ml)
- The Neural Base: [Point-in-time correctness](http://theneuralbase.com/feature-store/learn/advanced/point-in-time-correctness/)
- purgedcv: [Purged and combinatorial cross-validation](https://github.com/eslazarev/purged-cross-validation)
- Bigeye: [Lineage for Financial Services](https://www.bigeye.com/blog/introducing-lineage-for-financial-services)
- Moody’s: [BCBS 239 in the Agentic AI Era](https://www.moodys.com/web/en/us/kyc/resources/insights/bcbs-239-in-the-agentic-ai-era-from-compliance-to-command-center-data-lineage-and-governance.html)
- W3C: [Market Data ODRL Profile](https://w3c.github.io/market-data-odrl-profile/patterns_temp.html)
- FinGround: [Detecting and Grounding Financial Hallucinations via Atomic Claim Verification](https://arxiv.org/abs/2604.23588)
- Coalition for Secure AI: [Who’s Minding the Agent?](https://www.coalitionforsecureai.org/whos-minding-the-agent-a-new-framework-for-ai-identity-and-access-control/)
- FinGuard: [Open-source LLM safety orchestration for financial AI](https://github.com/suryanshgupta9933/FinGuard)
