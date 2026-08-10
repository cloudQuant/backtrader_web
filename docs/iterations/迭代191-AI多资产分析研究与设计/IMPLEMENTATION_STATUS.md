# 迭代 191 实施状态与验收证据

> 更新日期：2026-08-03<br>
> 状态：P0a/P0b 的代码基础、P0c 的只读股票兼容层、持久化调度可靠性、获批静态清单控制面和 MySQL 9.4.0 至 `20260811` 的 expand 迁移已完成隔离与本机共享开发库验证；固定夹具的 NFR-C03/C04 100 标的容量测量已在一次性 MySQL 9.4.0 schema 通过；`20260810` 期权持仓上下文完整性已在共享开发库和同版本隔离库完成实库合同与 round-trip 演练，新增 `20260811` 交互任务租约已在一次性 MySQL 9.4.0 完成 full round-trip、真实 runner claim/释放与取消竞争合同以及共享开发库 DDL/rollback-only 合同；身份主数据、数据源能力与 FX/数字货币地区限制均采用 fail-closed 门禁；**尚未达到全量 T1，更未达到 T2 模型晋级**。

本文是实施事实与验收证据的当前投影，不替代总体计划、子迭代需求或模型晋级门槛。
所有未完成的外部前提都保持关闭，不会被页面或 API 伪装为可交易建议。
本机共享 MySQL 的当前迁移、应用生命周期和 fail-closed 冒烟记录见
[2026-08-03 本机 MySQL 运行时证据](./evidence/2026-08-03-local-mysql-runtime-smoke.md)。
六类资产各一条真实交互任务的隔离持久化验收见
[2026-08-03 六资产交互任务夹具证据](./evidence/2026-08-03-six-asset-interactive-task-fixture.md)。

## 0. 当前验收判定（2026-08-03 复核）

| 判定范围 | 结论 | 可复现证据 / 边界 |
| --- | --- | --- |
| P0 研究框架、迁移链与前端工作台 | **GO（代码、隔离和本机共享开发 MySQL 验收）** | 一次性 MySQL 9.4.0 已完成包含 `20260811` 的 `upgrade head → downgrade 20260801 → upgrade head` 及真实 schema/interactive task-runner 合同；其中用户取消先提交、worker 晚到终态的 compare-and-set/rollback 合同也为 `3 passed`，详见 [取消竞争证据](./evidence/2026-08-03-mysql-task-cancellation-contract.md)。本轮新增的六资产隔离任务验收以 6 个实际任务走完快照、预测、18 个资产专属 outcome 与研报，详见[夹具证据](./evidence/2026-08-03-six-asset-interactive-task-fixture.md)。2026-08-03 对本机 `backtrader_web` 再做 0 行运行事实预检后，已执行 `20260810 → 20260811`，确认四个租约列和 claim 索引，且 rollback-only MySQL 合同通过；短暂启动的应用健康检查为 200，任务轮询器正常运行。登录后的 capability 仅返回六类关闭资产，创建研究被 `SOURCE_CAPABILITY_UNAVAILABLE` 拒绝且任务表仍为 0 行。SQLite migration/orchestrator、Ruff/Mypy、前端构建和浏览器夹具亦通过。 |
| T1 真实资产研究观察 | **NO-GO** | 共享 MySQL 的 `asset_data_source_registry`、`asset_instruments`、`asset_schedule_manifests`、预测、结果与模型登记表均为 0 行；没有获批来源、版本化身份、日历或真实覆盖证据。 |
| T2 方向信号晋级 | **NO-GO** | 尚无真实的 point-in-time walk-forward、至少 200 条成熟行动信号、校准/基线、前瞻影子统计或审批事件；因此公共输出继续固定为研究观察，不能成为买卖指令。 |

这里的“框架验收 GO”表示 fail-closed 契约、MySQL 9.4.0 迁移、隔离 round-trip 和页面状态已通过可重复验证；它**不等价于**任何一个资产已经具备真实可用数据，或已经验证预测准确性。

## 1. 已实现的合理改进项

| 改进项 | 实施落点 | 当前证据 |
| --- | --- | --- |
| P0 拆为可验证的公共底座 | 多资产模型、迁移、插件协议、编排器和 API 已独立于旧股票路径实现 | `tests/asset_research` 与 startup 回归、迁移契约和真实 MySQL 合同均通过（精确命令见第 2 节） |
| 数据许可先于研究输出 | `AssetDataSourceRegistry` 与 `AssetSourceRegistryPolicy` 冻结许可决定；默认 `StrictMarketDataAdapter` 明确绑定本地 `akshare_data` 仓库且固定 `refresh_online=false`，因此不会把“同资产类型的其他来源获批”误变成 AkShare 在线请求。`/capabilities`、task、schedule 和 retry 都按已安装适配器的来源 ID 预检；响应来源或字段来源与声明 ID 不同即拒绝。outcome worker 在读取前复核预测冻结来源，失效时直接将到期 head 标为 `UNSCORABLE + COMMON.SOURCE_LICENSE_BLOCKED`，不再采集失效来源。`/capabilities` 仍要求来源 capability 与有效主数据目录同时存在，缺主数据时为 `INSTRUMENT_CATALOG_UNAVAILABLE` | `test_source_registry.py`、`test_data_adapter.py`、`test_api.py`、`test_outcome_evaluator.py`、`test_master_data.py`、`AssetAnalysisPage.test.ts`、`test_task_lifecycle.py` |
| 快照、报告和日志的凭据脱敏 | 通用适配器在构造快照前递归替换 provider payload 中的敏感键和 `key=value`/`Bearer` 文本；编排器会对自定义适配器返回的预制快照再次脱敏并重算内容哈希。公开报告、导出和知识库发布对遗留行同样递归清理。通用 Loguru patcher 在所有 sink 写入前清理 message、context 和 exception，并关闭错误 sink 的局部变量诊断，避免异常文本或 `diagnose` 本地变量形成旁路 | `test_data_adapter.py`、`test_orchestrator.py`、`test_report_artifacts.py`、`test_enhanced_logger.py`：标准/自定义快照、损坏遗留报告、结构化与文本 sink 均不保留 fixture 凭据；54 条日志回归通过 |
| 严格资产身份与无回退分析 | `ApprovedInstrumentCatalog` 只从 `asset_instruments` 读取当前有效、`ACTIVE` 且列值与 `identity_json` 完整一致的版本化身份；并列最新版本、失效/未来版本或畸形 JSON 不会成为候选。候选响应显式携带服务端主数据声明的 `identity_level`；前端不再以页面默认层级筛掉基金份额、债券上市实例、外汇远期或数字货币合约，而是在用户确认后将候选的 `canonical_id`、场所和身份层级交给 `InstrumentResolver` 再核验。显示代码不得推演 issuer、到期、乘数或交易对；原始字段逐项保存 `observed/published/available/retrieved` 时点，缺少 `available_at` 的回放数据被 PIT 门禁拒绝 | `test_master_data.py`、`test_identity.py`、`test_data_adapter.py`、`test_api.py`、`AssetAnalysisPage.test.ts` |
| 条件身份与可执行边界 | `InstrumentIdentity` 按资产与层级校验 discriminated union：精确期货合约必须有到期、乘数和场所；基金份额类别必须有申赎机制与 NAV 日历；外汇现货、远期/NDF 和数字货币产品分别冻结所需条款。期货产品、资产级外汇/数字货币、永续或专门模型资产不会因模型晋级而变成可行动建议 | `test_identity.py`、`test_plugin_outcome_contracts.py` |
| 可降级研究而非伪造可交易性 | 各插件区分 `ELIGIBLE/DEGRADED/REJECTED`。二级证据不足、参考汇率或官方债券估值缺可执行 bid/ask 时保留可审计研究材料，但固定为 `HOLD + RESEARCH_ONLY + NONE`；关键合同、时点、许可或一手字段失败仍拒绝 | `test_plugin_outcome_contracts.py`、`test_data_adapter.py` |
| 服务端地区合规与预测身份 | FX/数字货币的地区判断只读服务端运行配置和来源注册表冻结的 jurisdictions；中国大陆无条件返回 `REGION_RESTRICTED + AVOID + NONE`，其他地区也同时要求显式开关和来源范围许可。该上下文进入 `decision_input_hash`，客户端参数不能绕过 | `test_compliance_policy.py`、`test_orchestrator.py::test_orchestrator_applies_server_owned_mainland_fx_restriction`、`test_source_registry.py` |
| 身份版本运行时 fail-closed | task、持仓上下文和 schedule 不再仅按排序取一条 `asset_instruments` 记录：畸形或列值不一致 JSON、并列最新版、失效/摘牌版本，以及已被较新版本取代的绑定均返回 `INSTRUMENT_VERSION_STALE`。后台任务按当前时点复核；schedule 按其冻结 `cutoff_at` 复核，避免未来运行使用旧身份，同时不把历史补跑错误地按“现在的主数据”重解释 | `test_task_lifecycle.py`、`test_schedules.py`（15 项定向回归） |
| 股票兼容只读桥接 | `StockResearchCompatibilityAdapter` 从旧 `stock_signal_predictions` 按原可见性范围读取，并通过 `/api/v1/asset-research/stock-compat/signals` 输出版本化映射；它明确标记 legacy identity/source manifest/position context/outcome head 的不可恢复项，始终 `RESEARCH_ONLY + execution_disabled=true`，不双写、不复制旧行到通用预测表 | `test_stock_compat.py`、`test_api.py`；旧股票回归集合通过 |
| 期权精确合约与可交易性 | `OptionIdentityDetails` 强制冻结合约 ID、交易所、标的/标的合约、到期/最后交易时点、交割物、乘数、报价单位、最小变动价位、自动行权、持仓限制和保证金规则；主数据缺项、身份不一致或已停止交易的合约均 fail-closed | `test_identity.py`、`option/test_plugin_analytics.py` |
| 期权 LONG 持仓上下文不可篡改绑定 | `20260810` 将 prediction 的 context ID、访问主体、冻结 instrument、position state 和 context 时间窗以组合唯一键/外键关联；期权 LONG 还要求快照在 prediction cutoff 前已可用且尚未过期。它阻止绕过服务层的跨用户、跨合约和过期 context 直写，不使用 MySQL trigger 或全局 binary-log 权限 | `test_migration.py` 的 SQLite upgrade/downgrade 与直接写入拒绝合同、`test_orchestrator.py` 的合法 LONG 上下文持久化合同，以及共享/隔离 MySQL 9.4.0 的目录核验和 rollback-only `test_mysql_contract.py`（跨主体、跨合约与过期上下文均被拒绝） |
| 采集快照、分析时点与冻结身份强匹配 | `InstrumentIdentity.matches_frozen_identity()` 在数据适配器返回后、来源授权后均要求完整身份逐字段相等，且两个阶段的 `snapshot.cutoff_at` 必须等于请求的 UTC 时点；任一条款或时点替换均以 `SNAPSHOT_IDENTITY_MISMATCH` 或 `SNAPSHOT_CUTOFF_MISMATCH` 失败且不持久化。对遗留记录，outcome evaluator 还拒绝 `entry_snapshot.cutoff_at != prediction.as_of_at` 的评分 | `test_orchestrator.py`、`test_outcome_evaluator.py`（适配器/来源授权替换条款或时点、遗留入场时点负例） |
| 期权链、IV 与合约 P&L 可重放 | 新预测统一使用 `option.iv_direction`；IV 由同一精确合约的 entry ask / exit bid 通过冻结模型输入求解，跨最后交易时间不评分。精确合约收益以 entry ask、exit bid 或最终正式结算计算，持久化完整成本快照、入/退场时点、百分比回报及按冻结乘数换算的绝对 P&L | `option/test_pricing.py`、`option/test_chain_quality.py`、`option/test_costs.py`、`test_outcome_evaluator.py`、`test_orchestrator.py` |
| 候选与公开结论隔离 | 候选 `PredictionHead` 仅用于影子记录；未晋级时公共 API、报告和页面只显示公开结论。`PROMOTED` registry 投影视图还必须在预测 cutoff 前匹配一条 `SHADOW -> PROMOTED` 不可变事件、同一 evidence URI/hash 和同一指标快照，并通过完整 T2 JSON 解析。运行时还会从冻结列/JSON 重建 `PromotionScope` 并复算 hash；`VENUE_PRODUCT` 须精确匹配身份的 quote/settlement 资产。缺字段、错误 hash、非正 Brier Skill、事件晚于 cutoff、跨 USDT/USDC 复用或 pooled 集中度超限均 fail-closed | `test_decision_policy.py`、`test_model_promotion.py`、`test_report_artifacts.py` |
| 模型治理管理员控制面 | 新增只限数据管理员的候选读取、scope 读取和状态转换接口。候选读取仅允许 `PUBLIC_SHADOW/ADMIN_EVAL` 的 `RESEARCH_ONLY` 记录，管理员不能读取 `USER` candidate；scope 响应显式标注 hash 是否可复算。转换只接收目标状态和原因码，在同一事务更新 current projection 并追加 `AssetModelStatusEvent`；不允许通过 HTTP 修改 scope、T2 指标、五方审批、evidence 或生效时间。状态严格为 `DRAFT -> SHADOW -> PROMOTED -> SUSPENDED/RETIRED`，`SUSPENDED` 必须回到 `SHADOW` 后重新验证；晋级时复用运行时 T2 门禁并要求 `COMMON.T2_GATE_PASSED` | `test_model_governance_api.py`（管理员授权、私有候选隔离、追加事件、T2 失败关闭、暂停重验证和退役终态） |
| 公共动作真值表与 long-only 例外 | `apply_publication_gate()` 统一将持仓上下文和方向映射为 `BUY/SELL/HOLD/AVOID` 与 `OPEN/CLOSE/KEEP/NONE`。债券、基金以及未冻结为永续/交割合约的数字货币的空仓/未知 `SHORT` 候选固定为 `HOLD + RESEARCH_ONLY + NONE + COMMON.SHORT_OPEN_UNSUPPORTED`；已确认多头仍可 `SELL + CLOSE`。期货、外汇和已冻结数字货币衍生品只有在服务端 short-open capability 为真时才得到 `SELL + OPEN`，否则保留 `SELL + NONE` 的研究语义；期权继续禁止裸空 | `test_decision_policy.py` 的完整线性真值表、long-only/crypto guard、capability 缺失和期权 close/naked-short 回归 |
| 每日影子运行的可靠执行 | 任务、单资产 schedule、run、不可变 prediction、outcome 和成绩单表已落地；数据库租约只允许一个 worker 抢占，失败重跑新建 run 并重放原 cutoff/配置，`SKIP/RUN_ONCE/BACKFILL` 按明确的 misfire grace 执行，prediction 唯一冲突回读既有事实。worker 也能在不伪造用户 ID 的前提下执行预先配置的 `PUBLIC_SHADOW/ADMIN_EVAL` 单资产 schedule；预测键、run 和 prediction 均保持原 owner scope。普通用户历史只读取自己的 `USER` 与公开 `PUBLIC_SHADOW` 的发布结论，永不返回 `ADMIN_EVAL` 或 candidate | `test_schedule_runner.py`、`test_schedule_policy.py`、`test_schedules.py`、`test_signal_history.py`、`test_task_lifecycle.py`、`test_orchestrator.py` |
| 交互任务可恢复执行 | `20260811` 将交互 task 的 lease token、过期、心跳和尝试次数持久化；API 创建/重试只唤醒合并后的 runner，runner 原子领取、限制批量和并发、长任务续租，进程异常或数据库不可达时由租约过期转为可审计失败。终态由 `RUNNING + lease_token` 的条件更新提交：若用户取消先提交，晚到 worker transaction 整体 rollback，不会重新写成成功、失败或留下部分运行事实。关闭 runner 开关时任务保留 `QUEUED`，不会暗中执行 | `test_task_runner.py`、`test_task_lifecycle.py`、`test_api.py`、`test_main_startup.py`；一次性 MySQL 9.4.0 的 `test_mysql_contract.py` 验证真实 claim/释放、取消竞争和 DDL，见 [取消竞争证据](./evidence/2026-08-03-mysql-task-cancellation-contract.md)。六类资产各一条真实 runner task 的端到端持久化结果见[夹具证据](./evidence/2026-08-03-six-asset-interactive-task-fixture.md)。 |
| 受控容量 C03/C04 | 默认单次批准周期由 20 修正为 100（`ASSET_RESEARCH_SCHEDULE_MAX_BATCH=100`），同时保持 worker=4、per-source=2。专用运行器只接受名称为 `codex_iter191_capacity_*` 的已迁移 MySQL schema，既不建/删表也不接受共享库；在真实 schedule 持久化路径记录 100 条完整 claim 的延迟、CPU/RSS、MySQL 连接、队列/lease/retry、评分 backlog、并发峰值与任务/研报副作用 | [容量 JSON](./evidence/2026-08-03-mysql-capacity-traceable.json)：100/100 成功，batch 1.210 s，claim p50/p95/p99 0.0444/0.0473/0.0937 s，worker/source 4/2，due/lease/retry/非终态 0，`PENDING` outcome 300、task/report 0；JSON 还冻结了相关源文件 SHA-256。该证据不替代其余 NFR 和真实 provider 验收 |
| 获批静态清单控制面 | `asset_schedule_manifests` 保存 immutable key/version、审批引用、非空 evidence URI/hash、actor、退役原因和内容 hash；管理员 API 逐条重验 capability 与 exact identity 后才展开 `PUBLIC_SHADOW/ADMIN_EVAL` schedule。系统 schedule 强制绑定 manifest entry/hash 和唯一 active target；退役时仅禁用未来 fire，worker/run retry 再次校验 manifest 未被退役或篡改 | `test_schedule_manifests.py`、`test_schedule_runner.py`、`test_api.py`、`test_migration.py`、真实 MySQL `test_mysql_contract.py` |
| 成熟结果自动评估 | outcome worker 按 prediction 取得持久化租约；先按冻结来源和适配器绑定预检，再一次收集一个授权观察快照并评分所有成熟 head。来源许可失效时不取数，直接将已到期 head 记为不可评分；其他取数失败只记录错误、释放租约并等待重试。非期权的可执行收益也必须使用入场快照中带版本的显式成本率；成本事实缺失时记为 `UNSCORABLE + COMMON.OUTCOME_COST_SNAPSHOT_MISSING`，绝不按零成本交易评分 | `test_outcome_scheduler.py`、`test_outcome_evaluator.py` |
| 资产专属特征、日历与评分口径 | `*-domain-features-v2` 以债券/基金/期货/期权/外汇/数字货币各自输入生成影子候选；session horizon 只接受冻结来源日历，期权标的/IV、债券可执行结果和数字货币 P&L 使用各自可观察量与报价边 | `test_plugin_outcome_contracts.py`、`test_outcome_evaluator.py` |
| 五类资产的冻结输入计算 | 债券从现金流、净价、应计、日计数和频率计算 YTM/修正久期/凸性/DV01；基金从官方 NAV 路径、分红、对齐基准和 ETF 市场中间价计算总回报/超额/跟踪误差/溢折价；期货只在品质、地点和税口径一致时计算基差与年化 carry；FX 先归一报价方向并保留 bid/ask 后评分；数字货币以独立 venue 的深度加权合成价并对 USDT/USDC 脱锚 fail-closed | `tests/asset_research/{bond,fund,futures,fx,crypto}/` 与通用 outcome 契约的 27 项新增/补充黄金与集成回归；未提供冻结输入或成本事实时仍保持 `null + ReasonCode`，不会退回到伪造的零值 |
| run-prediction 终态完整性 | `20260806` 将 prediction 外键和 `CREATED/REUSED` 审计角色列化到 `asset_signal_runs`；MySQL `CHECK` 要求 `SUCCEEDED` 同时具有两列，其他终态必须同时为空，外键禁止删除被引用预测。该行级约束替换历史关联表和触发器，并允许多个成功 run 合法复用同一不可变 prediction | 当前共享 MySQL 9.4.0 已升级到 `20260811`；目录核验显示直接列、CHECK、FK、索引及 manifest/context/任务租约约束存在，旧关联表和 `trg_asset_*` 触发器均为 0；回滚式真实拒绝合同通过 |
| 版本化成绩单 | 成绩单按主 `head_spec_hash` 严格分 cohort；存在多个定义时，未指定 cohort 的查询不聚合，前端再以显式 spec 请求一个口径 | `test_outcome_evaluator.py::test_scorecard_partitions_predictions_by_primary_head_spec_hash` |
| 前端多资产工作台 | 新增六类资产导航、`/investment/ai-assets/:assetType`、严格标的确认、公开研报/成绩单、Markdown/PDF 导出、仅已发布结论的知识库保存和防 stale 的任务/提交状态机；用户必须依次搜索候选、显式确认一个候选、再提交研究，页面不会自动解析或选择标的。切换资产会使旧提交代际失效，因此迟到响应不能锁住或改写新资产页面。页面先读取服务端 capability，加载失败或资产未获批时禁用提交。保存时由用户选择自己的知识库，前端不传候选决策，服务端再次校验 report 公开范围、目标归属和审计状态。报告把每个公开标量渲染为 `字段值 + 内容寻址证据 ID`，该 ID 覆盖字段值和冻结来源快照哈希；前端同时读取只含白名单来源、版本、许可和哈希的证据清单，原始载荷与候选结论均不返回。对断网、408、429、5xx 采用 2.5/5/10/20 秒上限退避，成功后恢复配置轮询；确定性 4xx 只显示错误、不反复请求。历史/成绩单的独立请求失败会显式显示失败原因而非伪装成空数据；研报渲染失败时保留已发布结构化结论并显示 `REPORT_RENDER_FAILED` 的正文不可用状态。历史记录明确标示“我的研究”或“公共影子”，不将公开影子运行误写成用户自身预测 | `AssetAnalysisPage.test.ts`、`assetResearch.test.ts`、`useAssetAnalysisTask.test.ts`、`test_report_contracts.py`、`test_api.py`、`test_report_artifacts.py` 覆盖 capability fail-closed、显式候选确认、字段级证据、公开证据清单脱敏、公开研报保存、候选内容脱敏、stale、可见性、退避、确定性错误、独立历史/成绩单失败态、研报渲染失败和数字货币无交易/账户入口；`asset_analysis.spec.ts` 额外通过真实浏览器验证旧任务的延迟响应不会覆盖切换后的新资产，并以 Axe 验证 WCAG 阻断级违规为零、键盘焦点和 320px 视口布局；前端完整回归、typecheck、生产构建及浏览器夹具旅程均通过 |

本轮没有改动旧的 `/investment/stock-analysis` API、页面或旧股票表；“AI 股票”命名相关
改动继续保留在原有兼容入口中。

## 2. 本轮自动化证据

以下命令为本轮的可复跑证据；未特别标注日期的核心命令已于 **2026-08-03** 在本工作区重新执行成功：

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q \
  -p no:sugar tests/asset_research tests/test_asset_research_capacity_script.py \
  tests/test_ci_migration_checks.py
# 298 passed, 1 skipped, 0 failed（56.66 s；既有/外部依赖 warning 不影响结果）
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q \
  -p no:sugar tests/asset_research --cov=app/services/asset_research --cov-report=term \
  --disable-warnings
# 2026-08-02 覆盖率记录（历史快照，不能替代上面的当前无覆盖率回归）：基线回归曾为 209 passed, 1 skipped；
# 当时新增/补充资产专属、成本完整性、short-open
# 语义与完整公共动作真值表、成熟原因 API/数据库契约与迁移 preflight 回归后，完整套件为
# 275 passed, 1 skipped；该次源码总覆盖率为 84%，`promotion.py` 为 81%，
# 新增的 `model_governance.py` 为 65%（状态机、授权、候选隔离和晋级负例均已覆盖）。
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q \
  -p no:sugar tests/asset_research/test_model_promotion.py
# 14 passed；覆盖错误 scope hash、畸形 JSON、缺失 quote、错误报价资产和精确匹配的 fail-closed 回归。
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q \
  -p no:sugar tests/asset_research/test_model_governance_api.py
# 3 passed；覆盖管理员授权、系统候选隔离、append-only 状态事件、T2 证据拒绝、暂停重验证和退役终态。
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q \
  tests/test_main_startup.py
# 5 passed
# MySQL 实库合同由下方显式确认命令单独执行
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m ruff check \
  app/api/asset_research.py app/models/asset_research.py \
  app/schemas/asset_research.py \
  app/services/asset_research tests/asset_research app/utils/logger.py \
  tests/test_enhanced_logger.py tests/test_structured_logging.py \
  tests/test_log_trace_correlation.py tests/test_logging_middleware.py
# All checks passed
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m mypy \
  app/api/asset_research.py app/models/asset_research.py \
  app/schemas/asset_research.py app/services/asset_research \
  app/startup/asset_research.py app/utils/logger.py
# Success: no issues found in 43 source files（本轮额外纳入 startup hook 与 `app/utils/logger.py`）
# 在一次性 SQLite 数据库 `alembic upgrade head` 后执行：
# 使用临时、一次性的 SQLite `DATABASE_URL`：
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base alembic check
# No new upgrade operations detected
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base alembic heads
# 20260811_asset_research_task_leases (head)

# `20260810` 上下文绑定的当前定向回归：
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q \
  -p no:sugar tests/asset_research/test_migration.py \
  tests/asset_research/test_orchestrator.py::test_orchestrator_persists_the_valid_option_context_binding_window \
  tests/asset_research/test_mysql_contract.py
# 13 passed；SQLite migration/orchestrator 定向回归。
# 2026-08-03 对共享开发 MySQL 9.4.0 显式确认后，`test_mysql_contract.py` 为 1 passed；
# 对同版本临时空库的 upgrade → downgrade → re-upgrade 后也再次为 1 passed。
# 用临时 SQLite `DATABASE_URL` 执行 `alembic upgrade head` 与 `alembic check`：
# No new upgrade operations detected。

# `20260811` 交互任务持久租约的当前定向回归：
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q \
  -p no:sugar tests/asset_research/test_task_runner.py \
  tests/asset_research/test_task_lifecycle.py \
  tests/asset_research/test_api.py tests/test_main_startup.py
# 39 passed；覆盖 durable claim、超时恢复、心跳续租、重复 wake 合并、runner 开关、创建/重试唤醒及 startup/shutdown。
# 2026-08-03 本轮完整后端套件：`4711 passed, 128 skipped, 3 warnings`（23m09s）；此前
# startup 隐式 wake 导致的生命周期关闭超时已由定向回归与全量套件共同覆盖。

# 六资产真实交互任务夹具验收（只接受空的、一次性 MySQL 9.4.0 schema）：
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q \
  tests/test_asset_research_six_asset_fixture_script.py \
  tests/asset_research/test_task_runner.py \
  tests/asset_research/test_plugin_outcome_contracts.py
# 49 passed；实际 MySQL 执行与逐资产结果见
# evidence/2026-08-03-six-asset-interactive-task-fixture.md。

# 快照/报告/日志脱敏与导出/发布指标的定向回归：
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q \
  -p no:sugar tests/asset_research/test_metrics.py \
  tests/asset_research/test_data_adapter.py \
  tests/asset_research/test_orchestrator.py \
  tests/asset_research/test_report_artifacts.py \
  tests/test_enhanced_logger.py tests/test_structured_logging.py \
  tests/test_log_trace_correlation.py tests/test_logging_middleware.py --disable-warnings
# 82 passed, 3 skipped, 1 warning；覆盖低基数导出/发布计数、标准和自定义快照、
# 遗留公开报告及真实 Loguru sink 的凭据脱敏。

cd ../frontend
npm run test -- --run
# 1,283 passed
npm run typecheck
# passed
npm run build
# passed
# 先以 `npm run preview -- --host 127.0.0.1 --port 4173` 启动当前 dist，再执行：
BASE_URL='http://127.0.0.1:4173' \
  npx playwright test --config=playwright.a11y.config.ts --project=chromium
# 13 passed（含 asset_analysis 两条浏览器级并发/无障碍回归）
```

本轮最终还执行了完整后端回归：`4700 passed, 127 skipped, 0 failed`（22 分 17 秒）；
前端全量 Vitest 为 `142 files / 1283 passed`，生产构建与类型检查通过。前端 lint 为
`0 errors`，但仓库仍有 1180 条既有 warning，未将其误记为零告警。

本轮新增的受控 MySQL 容量验证命令为：

```bash
# 仅对已新建、已迁移、名称符合 codex_iter191_capacity_* 的临时库执行；
# runner 拒绝共享库，不创建或删除表。
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  scripts/ci/run_asset_research_capacity.py \
  --database-url 'mysql+aiomysql://…/codex_iter191_capacity_<suffix>' \
  --confirm-disposable \
  --output docs/iterations/迭代191-AI多资产分析研究与设计/evidence/<run>.json
# 2026-08-03 的真实 MySQL 9.4.0 结果见 traceable JSON：100/100 SUCCEEDED，
# worker/source=4/2，batch=1.210 s，且无 due/lease/retry/非终态 run 或交互报告副作用。
```

浏览器夹具也显式模拟 `GET /asset-research/capabilities`：它只为期货开启研究能力，
以验证页面既能在合法 capability 下完成公开研报旅程，也会在真实接口缺失、报错或未获批时保持关闭。

2026-08-03 还重新执行了应用启动、旧股票数据采集、TradingAgents 兼容、market
instrument、期权链及股票 signal 回归：`75 passed, 1 warning`。这证明新增多资产
路由和生命周期注册没有破坏既有 `/investment/stock-analysis` 路径。

本轮新增的数据库主数据和股票兼容定向回归也已通过：

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q \
  tests/asset_research/test_identity.py \
  tests/asset_research/test_master_data.py \
  tests/asset_research/test_stock_compat.py \
  tests/asset_research/test_api.py
# 42 passed
```

身份版本运行时门禁的补充定向回归也已通过：

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q \
  tests/asset_research/test_task_lifecycle.py \
  tests/asset_research/test_schedules.py
# 15 passed
```

系统影子 owner scope 的定向回归也已通过：

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python -m pytest -q \
  tests/asset_research/test_schedule_runner.py \
  tests/asset_research/test_schedules.py \
  tests/asset_research/test_signal_history.py
# 14 passed
```

迁移测试在隔离 SQLite 中覆盖 upgrade/downgrade；本轮还使用本机同一 MySQL 9.4.0
二进制启动一次性 `codex_iter191_acceptance` 空库，完成从空库 upgrade、降级至
`20260801_stock_signal_predictions`、再 upgrade 到 head 的演练。该演练首次暴露未发布
`20260807` downgrade 的 InnoDB 顺序缺陷：先删仍被 FK 使用的
`ix_asset_schedule_manifest_enabled` 会被 MySQL 拒绝。已在提交前调整为先删 FK、再删索引，
全链 round-trip 和合同复验均通过。最终 schema 是 15 张 `asset_*` 表，旧关联表和
`trg_asset_*` 触发器均不存在；真实写入证明“无 prediction 的成功 run”、“成功 run 清空
prediction”和“删除被引用 prediction”均被拒绝。

本机共享库的 MySQL Server、`mysql` 客户端和 `mysqld` 二进制均为 **9.4.0**。受控执行
`20260809 → 20260810` 前，`asset_position_context_snapshots` 和
`asset_signal_predictions` 均为 0 行，且目标列/约束尚不存在；因此没有历史事实被回填或改写。
升级后只读目录确认 `asset_signal_runs.prediction_id/prediction_link_role`、
`ck_asset_run_prediction_terminal`、`fk_asset_signal_runs_prediction`、
`ix_asset_run_prediction_created`、`ck_asset_outcome_maturity_reason`、三个 context 时间窗列、
两个组合唯一键、两个组合 FK 和 `ck_asset_option_long_context_window` 都存在；旧关联表和资产
run 触发器计数均为 0，三个既有股票核心表仍存在。显式确认的 rollback-only 真实 MySQL
合同测试也已通过，不提交任何夹具行。

在 2026-08-03 执行 `20260811` 前的共享库预检中，`test_mysql_contract.py` 为 `1 passed`（
临时写入全部 rollback）；只读查询确认 MySQL `9.4.0`、revision
`20260810_asset_research_option_context_binding`，且
`asset_data_source_registry`、`asset_instruments`、`asset_schedule_manifests`、
`asset_signal_schedules`、`asset_signal_predictions`、`asset_signal_outcomes`、
`asset_model_registry`、`asset_model_status_events` 均为 `0` 行。全库 `alembic check` 在该共享库仍报告既有的非 Iteration 191
漂移：`ak_*` enum、聊天/知识库 `LONGTEXT` 映射，以及纸面交易非空列。其输出没有
`asset_*` 对象；因此它不能被记为本迭代通过证据，也不应通过本迭代迁移去改写这些无关表。
资产范围的真实 MySQL 约束合同和目录核验才是本次 schema 结论的依据。

本轮补充的债券、基金、期货、外汇和数字货币度量只扩展既有不可变快照、特征和研报 JSON
载荷的字段，不新增表、列、索引或约束，**因此这些度量本身不需要 Alembic 迁移**。但
`MaturityReason` 是所有资产共享且已持久化的结果事实，必须通过 `20260809` 的数据库 CHECK
阻止绕过 API 的非法值；期权 `LONG` 的同主体、同合约及有效时间窗也属于持久化的安全事实，
故 `20260810` 必须以数据库约束阻止绕过 API 的直写。两次迁移都会先预检历史行，绝不伪造
回填。已有迁移仅负责 191 所需的持久化事实表（预测、结果、来源证据、调度和审计），并始终
以当前 MySQL 9.4.0 为目标方言；它不涉及 PostgreSQL 迁移或 MySQL 版本升级。

`ci.yml` 的阻断式 `asset-research-mysql-contract` job 现启动官方 `mysql:9.4.0`，先对一次性
`codex_iter191_*` 库执行 `alembic upgrade head → downgrade 20260801 → upgrade head`，再运行
直接关系约束合同。CI 连接串保持
SQLAlchemy URL 对象，避免密码含 URL 保留字符时被二次解析而截断。当前工作区不能替代远端 CI
运行记录，因此该 job 的远端首次成功仍应在提交后归档为证据。

此前收尾复测额外以 `/opt/homebrew/opt/mysql/bin/mysqld` 启动隔离 MySQL **9.4.0**（不使用
Anaconda `PATH` 中同名的 5.7.24 二进制），在一次性
`codex_iter191_contract` 库执行 `alembic upgrade head → downgrade 20260801 → upgrade head`；
最终 `alembic current` 为 `20260810_asset_research_option_context_binding (head)`，
`tests/asset_research/test_migration.py` 与 `test_mysql_contract.py` 合计为 `13 passed`。实例停止后已
显式确认并删除临时数据目录。这是 `20260810` 的历史隔离证据；随后当前本机应用配置成功连接共享开发
MySQL 9.4.0，确认其运行事实表为 0 行（不触碰已有 8 条 `asset_specs`），并完成下述 `20260811`
受控升级和合同复测。

本轮还在一次性 SQLite 数据库执行了 `alembic upgrade head`、`alembic current`、
`alembic heads` 和 `alembic check`；最终 revision 为
`20260811_asset_research_task_leases (head)`，且未检测到未生成的 upgrade 操作。
这只补充迁移链和 ORM 元数据一致性证据，不替代上文 MySQL 9.4.0 的方言合同。

本轮新增的 `20260811` 以一次性 MySQL 9.4.0 schema 完成
`upgrade head → downgrade 20260801 → upgrade head`；最终 head 为
`20260811_asset_research_task_leases`，`test_mysql_contract.py` 的 schema/约束合同和实际 task
runner claim/释放合同为 `2 passed`。该 schema 为 `codex_iter191_*` 临时库，测试结束后已删除容器；
它不是共享开发库，也没有读写任何业务数据。

随后对本机共享开发 `backtrader_web` 执行了同一条 `20260810 → 20260811` expand migration：升级前
`asset_analysis_tasks` 与其他运行事实表均为 0 行；升级后 revision 为
`20260811_asset_research_task_leases`，任务表仍为 0 行，`lease_token`、`lease_expires_at`、
`lease_heartbeat_at`、`attempt_count` 和 `ix_asset_task_runner_claim` 均存在。真实 MySQL
rollback-only 约束合同为 `1 passed`。应用在该库上启动后 `/api/v1/health` 为 200，认证后的
`/api/v1/asset-research/capabilities` 返回 6 类资产、0 类可研究；未获批来源的任务请求返回
`SOURCE_CAPABILITY_UNAVAILABLE` 且未写入 task。该开发库验证不替代任何生产目标的备份、维护窗口、
恢复演练或发布授权。

## 3. 仍关闭的门禁（不是实现缺陷的掩盖）

| 门禁 | 当前状态 | 对产品的影响 |
| --- | --- | --- |
| 真实数据源许可、capability manifest 与主数据适配器 | 当前共享 MySQL 中 `asset_data_source_registry=0`、`asset_instruments=0`；代码已具备只读 `ApprovedInstrumentCatalog`，但未获得可导入的批准身份/来源清单 | 默认关闭页面提交并拒绝 API 入队；搜索只展示经运营方写入且仍有效的主数据，不会用示例、缓存或未授权行情冒充可用数据 |
| 本机开发 MySQL 迁移 | 共享开发库已在 MySQL 9.4.0 经 0 行运行事实预检后，从 `20260810` 升级到 `20260811`；postflight 确认租约列、claim 索引和 revision，rollback-only 真实 MySQL 合同通过，应用健康检查和空队列轮询成功 | 本机开发方言/schema 与运行时门禁已通过；生产目标仍须在独立变更单中完成备份、维护窗口、恢复和 forward-repair 演练，不能用 `stamp` 替代 |
| 全库 ORM schema 漂移 | 当前共享 MySQL 已为 `20260811`。全库 `alembic check` 仍报告既有的 `ak_*` 枚举、聊天/知识库 `LONGTEXT` 与 `paper_trading_positions` 可空性差异，均不属于 `asset_*` 表或本轮发布门代码 | 这不阻碍已完成的资产范围目录/约束合同，但不能把它写成全库 schema 已收敛；无关漂移由对应模块单独治理 |
| 资产专属到期结果与真实市场日历 | evaluator worker 与来源冻结日历合同已经接入；真实授权交易/NAV/联合日历尚未接入 | session 日历缺失、ID 不符或覆盖不足时 `maturity_at=null` 并保持 `PENDING`，成绩单不会伪造成功率 |
| T2 模型晋级 | 运行时 fail-closed 门禁已实现：除 T2 指标、不可变事件和审批外，还会从冻结列/JSON 重建 `PromotionScope`、复算 scope hash，并在 `VENUE_PRODUCT` 精确比对 quote/settlement 资产；真实实证未开始 | 不满足 200 条成熟行动信号、walk-forward、校准、前瞻影子验证和审批证据前，公开结论固定为研究观察，不开放买卖动作；仅手工写入 `PROMOTED` 状态、篡改 scope hash 或跨 USDT/USDC 复用模型都不能绕过门禁 |
| 生产调度、容量/韧性和回滚演练 | runner 已由 feature flag 接入应用生命周期；单周期上限为 100、worker=4、同一 server-declared source=2，未声明/动态来源统一进入保守 bucket。`test_schedule_runner.py` 与 `test_source_concurrency.py` 覆盖资源保护合同；一次性 MySQL 9.4.0 已完成固定 fixture 的 NFR-C03/C04 容量实测（[JSON](./evidence/2026-08-03-mysql-capacity-traceable.json)），并验证 100/100 终态、无队列残留和无交互研报。仍未完成 C01/C02/C05、真实 provider/LLM、重启、长时运行、备份恢复和生产窗口演练 | 不声明生产调度 SLA；自动运行前仍需批准数据源、日历、其余容量/韧性门禁和运维 runbook |
| 审批静态清单配置 | 管理员 manifest API、版本/证据/退役审计和数据库约束已完成，runner 只消费绑定到 active manifest 的精确单资产 schedule；当前共享库没有任何获批 manifest、来源或主数据行 | 仍不得创建或开启任何真实系统影子 schedule；先由运营方导入获批来源、精确身份、日历和审批证据，不能以 selector、主力/近月或市场扫描替代 |
| 资产专属真实研究输入 | 通用适配器、资产特征和质量门控已存在，但债券收益率曲线/信用数据、开放式基金 NAV/持仓、可执行外汇报价、完整期权链及数字货币多场所/链上数据尚无获批接入 | 不得将通用行情或示例数据包装为各资产可交易研究结论；v2 影子候选也不会公开为买卖建议 |
| 指标与生命周期预检 | 任务/来源/调度/reuse/outcome/export/publication/lifecycle 等 12 个低基数 Prometheus series 已接入 `/metrics` 与任务、worker 和工件路径；导出/发布仅在新的终态操作完成后各记一次，并将未知格式/目标收敛为 `UNKNOWN`。`AssetResearchRetentionService.plan_dry_run()` 覆盖全部 15 张 `asset_*` 表（含审批 `asset_schedule_manifests`），只读列出到期、legal hold 和既有 tombstone 的分类与候选，不执行删除 | dashboard、告警注入、trace 贯通、队列/LLM/迁移对账指标，以及经批准的去标识化、对象存储回收和真实清理演练仍关闭；T1 非功能验收保持关闭 |

### 3.1 六个子迭代的可交付边界

六个资产已共享强类型身份、质量门控、候选/公开隔离、不可变预测/结果、调度和研报
框架；`ConfiguredAssetResearchPlugin` 的资产分支和固定夹具可验证这些**研究框架**契约。
这不等同于拥有真实市场数据或已晋级模型。当前共享 MySQL 的来源和主数据行数均为 0，
所以下列每一项仍不能打开真实研究提交或方向性公开建议。

| 子迭代 | 已在仓库闭合的部分 | 仍需外部/运营输入才可做 T1 |
| --- | --- | --- |
| AI 债券 | 身份、质量/特征、可执行报价边与 outcome 合同 | 获批债券条款/现金流、曲线、官方估值或合规可执行价格、信用事件和交易日历来源，以及版本化主数据 |
| AI 基金 | 份额/上市标识、NAV 缺失拒绝、期限和结果契约 | 官方 NAV、份额类别/合并清盘、持仓披露、费率、基准和 NAV 日历来源 |
| AI 期货 | 精确合约身份、连续序列拒绝、会话截止和换月相关质量合同 | 交易所结算、合约规格、保证金、限仓、到期/交割和交易日历来源 |
| AI 期权 | 精确合约、完整链质量、IV/Greeks、bid/ask P&L 与裸卖保护 | 合法完整期权链、标的/波动率输入、乘数/结算规则、最后交易时间和行权公司行动数据 |
| AI 外汇 | 货币对身份、NY 收盘/完整 bar 规则、地区限制与报价边契约 | 可执行而非参考汇率报价、fixing/假日、点差/隔夜成本和地域合规 manifest |
| AI 数字货币 | venue-product/链上身份、UTC 日线、地区关闭和 outcome 合同 | 多场所批准行情、链上 finalized 数据、稳定币/合约风险、交易场所状态和地区法律复核 |

## 4. 明确不采纳的危险捷径

- 不为让页面“有结果”而默认批准任何行情或许可证；
- 不用当前价格、随机概率或回填数据生成“准确率”；
- 不因前端传入 `BUY/SELL`、空头能力或地区参数而绕开服务端门控；
- 不将研究结论连接到账户、订单、杠杆或数字货币交易导流。

## 5. 下一次 Go/No-Go 所需输入

1. 针对每类资产提供获批的数据源、允许用途、有效期、覆盖字段和保留约束；
2. 在每个生产目标环境按独立变更单完成备份恢复、迁移窗口、健康检查和 forward-repair 演练，并记录 revision、schema inventory 与回滚决策；
3. 接入资产交易日历与到期 evaluator，持续积累不可变的前瞻影子结果；
4. 在冻结 scope 上完成 T2 指标和五方审批后，才允许相应资产显示方向性公开信号。
