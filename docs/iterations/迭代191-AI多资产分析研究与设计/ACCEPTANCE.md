# AI 多资产分析总体验收计划

## 1. 验收结论定义

验收分三层，不能互相替代：

| 层级 | 证明内容 | 通过后的能力 |
| --- | --- | --- |
| T1 技术验收 | 身份、数据、建议、报告、存储、评分和权限按契约工作 | 可进入研究观察/影子模式 |
| T2 模型晋级 | 未见数据和前瞻样本满足质量门槛 | 可显示方向建议 |
| T3 执行批准 | 账户、适当性、风控、订单和合规独立验收 | 不在本迭代范围 |

六个子迭代独立判定。某资产 T1 通过但 T2 未通过时，页面仍可展示事实和研报，主建议必须为“持有/暂不参与”，不得显示未经验证的买卖信号。

## 2. 验收环境

| 项目 | 条件 |
| --- | --- |
| 后端 | `/Users/yunjinqi/opt/anaconda3/bin/conda run -n base`，独立 MySQL 9.4.0（InnoDB）测试数据库，可运行 Alembic |
| 前端 | Node 依赖已安装，可运行 typecheck、Vitest 和生产构建 |
| 外部数据 | 自动化测试使用固定夹具；在线验证只作为额外证据 |
| LLM | 自动化测试使用固定结构化响应；网络模型不作为可重复通过条件 |
| 配置 | 所有方向模型默认 `SHADOW`，交易执行永久关闭 |
| 身份 | 至少两个普通用户和一个管理员测试身份 |

## 3. A 组：文档和契约一致性

- [x] 总计划、调研、架构、交付治理、迁移、非功能需求和本验收文档存在且内部链接有效；
  2026-08-02 运行 `scripts/ci/check_doc_links.py` 返回 `OK`；
- [x] `IMPROVEMENT_SUGGESTIONS.md` 仅标记为历史审查输入，每条建议均在
  `IMPROVEMENT_REVIEW.md` 有处置、证据和实施落点；该决议的第 3 节逐项覆盖
  `0.1`–`7.2`，第 6、7 节记录已实现的闭环与后续变化，不将历史建议作为权威需求；
- [x] 六个资产子目录均包含 `REQUIREMENTS.md`、`DESIGN.md`、`PLAN.md`、`ACCEPTANCE.md`；
  目录清单由本验收轮次复核；
- [x] 文档中没有未决内容或引用性省略；2026-08-02 的
  `rg 'T[B]D|T[O]DO|待[定]|同[上]' docs/iterations/迭代191-AI多资产分析研究与设计`
  返回无匹配；
- [ ] 所有资产类型、建议枚举、错误码、表名和 API 在总体与子文档中一致；
- [ ] `InstrumentIdentity`、动作真值表、`PredictionHead`、`OutcomeStatus`、
  `MaturityReason` 和命名空间 `ReasonCode` 有唯一权威定义；
- [ ] `PredictionHead` 固定 target/scoreability 版本、labels、模型与校准 artifact
  哈希、训练截止时点和 baseline 版本，且非空 head 集合只能有一个主晋级 head；
- [ ] 六类 `*ResearchDetails` 均是带 `kind` discriminator 的强类型 Schema，
  资产字段与子 DESIGN 一致，且不重复公共动作、概率或 actionability；
- [ ] 插件 registry 恰好注册六个资产插件；同一参数化合同套件逐个验证
  `resolve/collect/assess/promote/features/decision/report/score` 协议、错误语义和
  无直接 DB/LLM/订单副作用，禁止按插件跳过公共断言；
- [ ] 所有外部事实有直接来源链接，开源依赖带许可证判断；
- [ ] 每个需求均可映射到至少一个验收项。

## 4. B 组：通用身份和数据层

### B1. 唯一身份

- [ ] 同一显示代码对应多个市场、份额、合约、网络或产品时返回 `INSTRUMENT_AMBIGUOUS` 和候选列表；
- [x] `/capabilities` 仅在获批来源和至少一个可验证、有效的 `asset_instruments` 主数据
  记录同时存在时打开研究提交；只具备来源许可时返回
  `INSTRUMENT_CATALOG_UNAVAILABLE`，页面保持关闭；
- [x] 默认多资产桥接只读取声明为 `akshare_data` 的本地仓库并固定关闭在线 refresh；
  capability、task、schedule、retry 和 outcome 复核均不会用“其他获批来源”授权该桥接。
  顶层或字段级来源 ID 不匹配拒绝；来源许可撤销后，到期结果直接为
  `UNSCORABLE + COMMON.SOURCE_LICENSE_BLOCKED`，不发生新采集。此项不替代真实外部
  来源的域名、超时、大小、并发和重试 T1 Gate；
- [x] 用户确认后得到稳定 `canonical_id`，任务、报告、预测和结果均引用它；搜索候选不再
  按页面预设身份层级筛掉基金份额、债券上市实例、外汇远期或数字货币合约，而是携带服务端
  主数据声明的 `identity_level` 进入显式确认；服务端仍对
  `canonical_id`/场所/身份层级完整复核，定向回归覆盖该跨层合同；
- [x] 底层行情精确 symbol 未命中时不得返回或分析“最近任意样本”；适配器检测
  asset/symbol/venue/product/contract 任一不匹配即安全拒绝；
  `test_data_adapter.py` 覆盖跨合约提供方回退拒绝和匹配资产域事实/provenance 保留；
- [x] `ASSET/PRODUCT/CONTRACT/SERIES` 层级按资产专属 discriminated union
  条件校验；开放式基金和资产级数字货币不被强制填写虚假 venue；精确期货、外汇远期/NDF、
  基金份额类别和交割型数字货币缺关键身份条款均 fail-closed，见 `test_identity.py`；
- [x] 到期合约、已清盘基金、已摘牌代币保留历史身份但不允许生成新的可交易建议；
  通用编排器在入队、worker 与 schedule 冻结时点均复核身份的生命周期、有效期、最新版
  唯一性和绑定版本；`test_task_lifecycle.py`、`test_schedules.py` 的 15 项回归覆盖
  摘牌、过期、畸形主数据、并列最新版和较新版本取代的负例。此项不解除 T1 的真实主数据/数据源门禁。
- [ ] 任一衍生品记录都能还原标的、到期、乘数和结算方式。

### B2. point-in-time

- [ ] 缺到期、NAV、基准、费用、条款或报价时，门控前 `RawAssetSnapshot` 仍以
  `null + provenance/timestamps/missing_reason` 保存，随后安全拒绝而非返回
  Pydantic `422` 或未处理 `500`；
- [ ] 只有满足资产最小字段合同的 raw snapshot 才构造 `EligibleAssetSnapshot`
  并进入估值、特征和方向模型；
- [ ] 固定夹具证明预测只读取 `available_at <= cutoff_at` 的数据；
- [ ] 发布滞后的 COT、基金持仓和宏观数据不会按观测日提前进入特征；
- [ ] 来源修订后旧预测快照和哈希不变，新分析读取新版本；
- [ ] 缓存回退显示原始时间；超过资产新鲜度阈值返回 `DATA_STALE`；
- [ ] 受限来源不能通过导出或证据 API 泄露原始数据。

## 5. C 组：公共任务、存储、调度和权限

- [x] 空库升级后存在架构定义的全部通用表、外键、CHECK、唯一约束和真实索引；同版本
  MySQL 9.4.0 空库已完成 `upgrade head → downgrade 20260801 → upgrade head`，并在 head
  执行真实约束合同；
- [x] 从当前 Alembic head 的现存数据库升级后得到同一 schema；本机共享开发 MySQL 9.4.0 已从
  `20260809` 线性升级至 `20260810`，并在 2026-08-03 经 0 行运行事实预检继续升级至
  `20260811`；迁移使用真实 `down_revision`，不以无依据的 `depends_on` 代替迁移链；
- [ ] task/report/export/publication/position context snapshot/run/prediction/outcome/
  model event 的外键及 `ON DELETE RESTRICT` 策略与架构一致；
- [ ] run 使用 `prediction_id/prediction_link_role` 直接引用 immutable prediction；首次为
  `CREATED`，两次相同输入 retry 各新增 run 并写 `REUSED` 指向同一不可变 prediction；
- [ ] `PENDING/RUNNING/FAILED/CANCELLED` run 的直接 prediction/角色均为空，`SUCCEEDED`
  run 两列均完整，`PARTIAL` run 违反状态 CHECK；prediction FK 阻止删除被成功 run 引用的
  事实，且创建/复用、写直接字段和成功状态同事务提交；
- [ ] 决定一旦与 run 在事务内提交，该 run 保持 `SUCCEEDED`；后续研报、导出或发布
  失败只更新对应资源状态，不把 run 降为 `FAILED` 或遗留失败运行关联；
- [ ] 相同 `decision_input_hash` 重复提交只产生一条预测；持仓及其不可变快照、资产参数、
  冻结合约/映射、风险情景、head spec、来源快照或任一版本变化均产生新记录；
- [ ] 两个并发 worker 对同一 key 竞争时由唯一约束和冲突恢复收敛为一条 prediction，
  两个 run 的关联均合法；顺序重复调用不能替代该并发测试；
- [ ] 同一预测、期限和评估器可以按不同 `outcome_kind` 保存多条结果且互不覆盖；
- [x] 取消只影响未完成任务，重试创建新运行且不覆盖失败证据；
  `test_task_lifecycle.py::test_cancelling_an_unfinished_task_is_idempotent` 覆盖重复取消，
  `test_task_runner.py` 覆盖取消先提交时晚到 worker 不能复活任务、真实分析在采集阶段被
  取消后会 rollback，`test_api.py::test_retry_endpoint_queues_a_new_task_and_wakes_the_durable_runner`
  断言 retry 生成新 task 并保留原 `FAILED` task；MySQL 9.4 同一竞争合同见
  [取消竞争证据](./evidence/2026-08-03-mysql-task-cancellation-contract.md)；
- [ ] position context snapshot/run/prediction 均列化 `owner_scope + user_id`；手工和
  schedule 运行能追溯 task 或 schedule，`USER` scope 不允许空 user_id；
- [ ] 用户 A 不能读取或引用用户 B 的持仓上下文、手工任务、调度、run、报告或私有
  预测，伪造 owner/user 查询参数仍返回 `403/404`；
- [x] 期权 `SELL+CLOSE` 只有在 prediction 引用同访问主体、同精确 canonical
  contract、cutoff 有效且数量证明为纯 LONG 的不可变持仓上下文时通过；跨用户、
  跨合约、过期、SHORT 和无快照在 Schema 与服务中均失败；完整的数据库跨表约束是
  后续 T1 门禁，不能以当前 P0b 的 LONG 快照存在性 CHECK 冒充完成；共享/隔离 MySQL
  9.4.0 合同、SQLite 直写负例和服务层回归已覆盖该门禁；
- [x] `PUBLIC_SHADOW/ADMIN_EVAL` 与用户结果通过访问主体区分，普通用户拿不到
  admin candidate；runner 不伪造用户 ID，`test_schedule_runner.py` 证明两个系统 scope 的
  run/prediction 均为 null `user_id`，普通用户历史仅看到 `PUBLIC_SHADOW` 的发布结论而不含
  `ADMIN_EVAL`。
- [x] 旧股票接口和表无破坏性变更，兼容回归通过；`StockResearchCompatibilityAdapter`
  对相同 legacy record 保留动作、模型版本、结果和可见性范围，同时明确不可恢复的
  身份/来源/持仓/outcome-head 语义，且始终为 `RESEARCH_ONLY`；
- [x] 日志、快照和报告不包含账户密钥、私钥或未脱敏敏感信息；
  `test_data_adapter.py`、`test_orchestrator.py` 和 `test_report_artifacts.py` 分别覆盖标准/自定义
  provider 快照、公开遗留报告和导出/知识库发布的递归脱敏及 hash 重算；
  `test_enhanced_logger.py`、`test_structured_logging.py`、`test_log_trace_correlation.py` 和
  `test_logging_middleware.py` 覆盖结构化/文本 sink、message/context/exception 脱敏、关闭
  `diagnose` 局部变量输出与真实 Loguru sink。该代码证据不替代生产密钥管理或外部 trace
  后端审计。
- [x] 审批静态清单只在配置阶段展开成版本化的单资产 schedule，运行时不扫描整个市场；
  `test_schedule_manifests.py`、`test_schedule_runner.py` 和 `test_api.py` 覆盖 source/
  identity fail-closed、管理员授权、`Idempotency-Key` 复用、退役和 worker manifest 复核；
- [ ] `schedule_version + cutoff_policy_version` 被运行冻结；租约锁使重复调度
  只生成一次运行，失败补跑沿用原 cutoff 和配置；
- [ ] 各资产 cutoff 使用专属日历；外汇/数字货币的北京时间 19:00 任务不读取
  未完成日线。

## 6. D 组：质量门控和建议权威

- [x] 每个资产都有一条 `ELIGIBLE`、一条 `DEGRADED` 和一条 `REJECTED` 固定夹具；
  `test_plugin_outcome_contracts.py` 参数化覆盖六类资产的可用、关键字段拒绝和二级证据降级；
- [x] `REJECTED` 始终得到 `AVOID/NONE`，无法被 LLM 或前端改写；
  `apply_publication_gate()` 在任何公开渲染前清空方向、置信度和 head，固定为
  `INDETERMINATE + AVOID + NONE + INSUFFICIENT_DATA`；
  `test_decision_policy.py::test_rejected_candidate_is_always_publicly_avoided` 通过。
- [x] 未晋级候选方向只对管理员/评估器可见，普通用户只收到 `INDETERMINATE + HOLD/AVOID`；
  候选方向仅留在内部 immutable prediction/评估路径，用户的 task result、研报和证据接口只取
  `published_decision`。`test_orchestrator.py::test_orchestrator_persists_raw_then_hides_unpromoted_candidate_from_public_result`
  证明内部候选为 `LONG` 时，公开结果仍为 `INDETERMINATE + HOLD + RESEARCH_ONLY` 且不含 candidate。
- [x] 地区禁止固定返回 `REGION_RESTRICTED + AVOID + NONE`，
  不误标成 `RESEARCH_ONLY`；中国大陆 FX/数字货币由服务端配置强制，
  `test_compliance_policy.py` 和真实编排夹具覆盖该公开结果；
- [ ] 关键字段缺失保持 `null` 并带原因，不能补 0 或中性；
- [ ] 注入与结构化决定相反的 LLM 文本后，API 和页面仍显示结构化决定；
- [x] 每个建议均显示期限、持仓上下文、方向、失效条件和 `execution_disabled=true`；
  页面明确展示研究周期、规范方向、持仓上下文、失效条件（缺失时显示未提供而不编造）和执行已禁用；
  `AssetAnalysisPage.test.ts` 与浏览器 fixture 回归覆盖该公开边界。
- [x] 公共动作真值表是唯一权威，资产扩展只能派生展示标签；
  `apply_publication_gate()` 是唯一将结构化方向和持仓上下文转换为 public recommendation/
  trade intent 的路径。`test_decision_policy.py` 参数化覆盖期货的空仓、多头、空头、未知
  与 `LONG/SHORT/NEUTRAL/INDETERMINATE` 全部组合；债券/基金/数字货币及期权仅在该表之前
  应用更严格的资产风险门控，不维护第二套动作枚举。
- [x] `SELL` 的资产专属语义清晰：债券/基金为减持或退出，期货/外汇/永续可为
  做空观点，期权 v1 只为卖出平多；`apply_publication_gate()` 对债券/基金的空仓或未知持仓
  `SHORT` 候选固定降为 `HOLD + RESEARCH_ONLY + NONE + COMMON.SHORT_OPEN_UNSUPPORTED`，即使
  调用者错误传入通用 short-open 开关也不会形成裸空；未冻结为永续/交割合约的数字货币也同样
  fail-closed。已确认 `LONG` 持仓时才可得到 `SELL + CLOSE`；数字货币仅在冻结的
  `PERPETUAL/DELIVERY_FUTURE` 产品且服务端 capability 明确允许时才可 `SELL + OPEN`；
  期货/外汇及已冻结数字货币衍生品若 capability 尚未允许开空，则保留 `SELL + NONE` 的
  研究语义而不伪造开仓意图；期权的裸空与未授权平仓由
  `test_decision_policy.py` 共同覆盖。

## 7. E 组：研报和前端

- [x] 六个导航和路由可访问，浏览器刷新后资产类型保持正确；
  `src/__tests__/router/index.test.ts` 参数化验证 bond、fund、futures、option、fx、crypto
  均解析为 `InvestmentAssetAnalysis` 并保留对应 `assetType`；
- [x] 搜索候选必须先确认身份，不能自动选择歧义资产；前端只有在用户确认候选并经服务端
  复核后才允许创建任务；
- [x] 切换资产或新任务时清空旧结论，不发生跨资产残留；
  `AssetAnalysisPage.test.ts` 覆盖已完成期货研究切换到期权后，决策和研报面板均被清空；
- [x] 轮询进入终态、取消或组件卸载后停止；页面隐藏时暂停、恢复时立即刷新一次；
  `useAssetAnalysisTask.test.ts` 覆盖终态停止、取消、卸载释放、页面隐藏暂停、恢复立即刷新、
  临时错误退避与确定性错误不重试；
- [x] 旧任务晚到响应不能覆盖新资产/新任务，且该路径有浏览器级并发回归。
  `asset_analysis.spec.ts::asset switch discards a delayed prior task response in the browser`
  先阻塞旧期货任务响应，再在同一 Vue 页面内切到期权并完成新任务；旧响应释放后，
  页面仍只显示新期权研报。修复同时以提交代际标识避免旧提交把新资产提交按钮永久锁在加载态；
  `AssetAnalysisPage.test.ts` 与 `useAssetAnalysisTask.test.ts` 的定向回归通过；
- [ ] 质量、来源、估值、风险、建议、反方证据、历史和成绩单均有加载/空/失败状态；
  当前页面已覆盖任务、公开证据、历史、成绩单与研报正文的加载/空/失败状态：历史和成绩单
  请求失败不会再被伪装为“暂无数据”，`REPORT_RENDER_FAILED` 会保留并解释已发布结构化结论。
  仍需在真实获批数据接入后，为资产专属报告章节的逐章来源/估值/风险失败补齐端到端证据，
  因此本项保持未通过；
- [x] 报告中的每个关键数值能追溯到证据 ID；公开标量在渲染时附带内容寻址的
  `detail:<sha256>`，其输入覆盖字段名、字段值和冻结 `source_snapshot_hash`；章节同时保留
  来源/质量/公开结论的内容寻址 ID。页面展示这些 ID，并调用
  `GET /signals/{prediction_id}/evidence` 取得只含来源、许可、版本和快照哈希的白名单清单；
  原始载荷与候选结论不在该接口或页面中暴露。`test_report_contracts.py::test_public_report_scalar_values_have_content_addressed_evidence_ids`、
  `test_api.py::test_evidence_endpoint_returns_only_the_public_whitelisted_manifest`、
  `AssetAnalysisPage.test.ts` 和 `assetResearch.test.ts` 通过；这只是结构化离线契约，
  不替代真实获批来源的在线证据。
- [x] `POST /reports/{id}/exports` 创建导出，`GET /exports/{id}` 只读取状态和文件；
  GET 请求不产生写副作用。`test_api.py::test_report_export_post_is_the_explicit_creation_route`
  断言 POST 经过创建服务并提交审计；
  `test_api.py::test_report_export_get_routes_do_not_create_or_commit` 断言两个 GET 路径
  不调用创建服务且不提交事务；
- [x] 知识库保存使用显式 POST 端点、授权和审计对象；
  `POST /reports/{id}/publications` 只接受显式目标和幂等键，服务端按报告公开范围、调用者和
  知识库 owner 二次校验并创建 `AssetReportPublication` 审计记录；`assetResearch.test.ts` 与
  `AssetAnalysisPage.test.ts` 覆盖前端调用和用户选库，`test_report_artifacts.py` 覆盖 owner scope；
- [x] Markdown/PDF/知识库保存内容与页面发布建议一致，候选决定不泄露；所有三条路径使用
  `public_report_payload()`；`test_report_artifacts.py` 注入伪造候选字段后验证 PDF、Markdown
  和实际知识库文档均不含候选内容，页面只在已有 `published_decision` 时显示保存入口；
- [x] 键盘操作、焦点、颜色对比、表格标签和移动端布局通过现有无障碍基线；
  `e2e/a11y/asset_analysis.spec.ts` 使用 Axe 的 WCAG 2 A/AA、WCAG 2.1 A/AA 规则，阻断级
  `critical/serious` 违规为 0；同时验证提交按钮键盘焦点和 320px 视口不产生横向溢出。
- [x] 中国大陆模式的数字货币页没有交易链接、账户连接、订单或营销文案；
  `AssetAnalysisPage.test.ts` 的 crypto 页面回归断言没有链接、交易/账户按钮或营销措辞，
  且始终显示“研究用途，不能直接下单”。服务端地区强制由
  `test_compliance_policy.py` 另行覆盖。

## 8. F 组：结果评分

- [ ] 每类资产使用子迭代定义的价格、基准、成本、期限和成熟规则；
- [ ] 结果状态只使用 `PENDING/PARTIAL/SCORED/UNSCORABLE`，
  到期、赎回、换月等另存 `MaturityReason`；
- [ ] 资产专属 `outcome_kind`、状态和命名空间原因码通过数据库/API 契约测试；
- [ ] 多 `PredictionHead` 的目标、标签、概率、模型/校准 artifact、训练 cutoff、
  baseline、`scoreability_rule` 和服务端计算的 `head_spec_hash` 互相隔离，
  主 head 唯一；
- [ ] `head_spec_hash` 不同的结果不能进入同一 cohort；mixed-spec 聚合和事后改标签
  被服务与查询契约拒绝；
- [ ] `HOLD/AVOID` 不进入行动信号命中率分母，但展示覆盖率和后续分布；
- [ ] 修改当前成本配置不会重算旧结果，评分读取预测快照；
- [ ] 重复评分幂等，不覆盖不同评估版本；
- [ ] 页面同时展示样本数、可评分数、覆盖率、精确率、Brier/校准、净收益和回撤；
- [x] 分母为零返回 `null + 样本不足`，不显示 `0%`；
  `get_signal_summary()` 对空 cohort 返回所有比例/评分指标 `null`，页面将这些值明确渲染为
  “样本不足”。`test_outcome_evaluator.py::test_empty_scorecard_uses_null_metrics_instead_of_zero_percent`
  和 `AssetAnalysisPage.test.ts` 通过。

## 9. G 组：模型 T2 晋级

每个冻结的 `promotion_scope_key` 分别验收：

- [ ] 时间顺序 walk-forward，训练集不包含测试期或结果期数据；
- [ ] 重叠标签已 purge，训练和测试边界有 embargo；
- [ ] 费用、点差、滑点以及资产专属成本全部计入；
- [ ] 与总计划定义的朴素基线比较，并报告所有尝试版本；
- [ ] 至少 200 条成熟行动信号；`POOLED` scope 单一品种占比不超过 40%；
- [ ] `INSTRUMENT_SPECIFIC` scope 不套 40% 规则，但覆盖至少三个市场状态，
  衍生品覆盖多个合约或到期；
- [ ] 注册主 `PredictionHead` 的 Brier Skill Score 大于 0，
  可靠性图无系统性过度自信；
- [ ] 平均净效用为正，95% bootstrap 区间下界不劣于基线；
- [ ] 至少 60 个交易日前瞻影子验证；数字货币至少 90 个自然日；
- [ ] 分状态和尾部风险无不可接受恶化；
- [ ] 注册表和不可变审批历史固定 `promotion_scope_key`、主 head、
  head spec、target/scoreability/baseline、policy/model/calibration 版本、
  artifact 哈希、训练 cutoff、状态、审批人和证据 URI；
- [ ] 暂停或回滚新增历史记录，不覆盖原晋级证据。

- [x] 运行时不把 `asset_model_registry.status=PROMOTED` 当作充分证据：必须在预测
  cutoff 以前找到指标快照、evidence URI/hash 完全匹配的 `SHADOW -> PROMOTED` 不可变事件，
  并解析完整 T2 JSON 指标；缺指标、事件、非正 Brier Skill、时点或 pooled 集中度任一项时
  均保持未晋级。`test_model_promotion.py` 覆盖缺失指标、缺失/未来/不匹配事件、Brier Skill 和
  concentration 的 fail-closed 回归。此代码门禁不等于实际 T2 实证通过。
- [x] 运行时从注册表的冻结列和 `scope_parameters_json` 重建规范化 `PromotionScope` 并
  复算 `promotion_scope_key`；哈希、JSON 或 scope 模式不一致时不发布。`VENUE_PRODUCT`
  还必须精确匹配身份的 quote/settlement 资产，防止同一 venue/product 的 USDT 与 USDC
  模型交叉复用。`test_model_promotion.py` 覆盖错误哈希、错误报价资产、精确匹配和缺失
  quote 的 fail-closed 回归；此应用层语义校验不等于真实 T2 实证通过。

任一项不通过，方向模型保持 `SHADOW/SUSPENDED`。

## 10. H 组：合规、许可证和安全

- [ ] 数据源注册表记录允许用途、归属、再分发、缓存和派生限制；
- [ ] 每个启用资产/route 有获批 capability manifest 和真实覆盖证据；债券合同/曲线/
  估值或执行代理价/信用事件、开放式基金份额/NAV/基准/费用/持仓披露分别满足子计划
  Gate，缺失 route 保持 capability 关闭；
- [ ] 原始载荷、规范化快照、预测/结果、报告、审计和 trace 按数据类别、地区、
  租户和许可证执行可配置保留策略；更严格的许可证期限优先；
- [x] 最终 15 张通用表均有实际
  `retention_class/retention_expires_at/legal_hold/tombstoned_at` 列；业务
  `expires_at` 与保留到期时点不混用，生命周期变更不改变事实内容哈希；历史中间态的
  第 15 张 `asset_signal_run_predictions` 关联表已由 `20260806` 回填为
  `asset_signal_runs` 的直接预测外键并删除；`20260807` 新增的
  `asset_schedule_manifests` 是当前最终 schema 的第 15 张表。`test_models.py`、
  `test_migration.py`、真实 MySQL `test_mysql_contract.py` 以及 `test_retention.py`
  分别验证 schema 与 dry-run 覆盖，后者不会执行删除；
- [ ] 许可未知或超出用途时返回 `SOURCE_LICENSE_BLOCKED`；
- [ ] 证券、期货和衍生品页面展示适用风险披露与研究边界；
- [ ] 期权不存在 `SHORT`、`SELL + OPEN`、`SELL_TO_OPEN` 或无限损失建议路径；
- [x] 地区限制由服务端强制，修改前端请求不能绕过；FX/数字货币只读取操作方 jurisdiction、
  运行开关和来源注册表冻结范围，且将其纳入 prediction 输入哈希；
  `test_compliance_policy.py`、`test_source_registry.py`、
  `test_orchestrator.py::test_orchestrator_applies_server_owned_mainland_fx_restriction` 通过；
- [ ] 所有外部请求设置域名白名单、超时、响应大小和并发上限；
- [x] 导出内容经过 XSS/路径穿越验证；前端 `markdown-sanitizer.test.ts` 覆盖脚本、
  事件属性和危险 URI，`test_report_artifacts.py` 覆盖 PDF HTML 转义、候选决定脱敏及
  相对/绝对路径均不能逃逸导出根目录；
- [ ] 依赖许可证清单通过法务或开源合规复核。

## 11. I 组：性能、韧性、可观测性和成本

- [ ] 在 `NON_FUNCTIONAL_REQUIREMENTS.md` 定义的 T1 环境，以固定数据和并发模型记录
  API、交互任务、批量调度和前端的 P50/P95/P99；未测值不得对外称 SLA；
- [x] 审批 schedule 的固定夹具容量测试证明队列不会无限增长，并记录 CPU、内存、数据库连接、
  外部来源并发、缓存适用性和评分积压；2026-08-03（Asia/Shanghai）在一次性 MySQL
  9.4.0、`20260810` schema 上运行 100 个获批静态期货合约，100/100 `SUCCEEDED`，
  worker/source 峰值 4/2，batch 1.210 s，claim p50/p95/p99 为
  0.0444/0.0473/0.0937 s，`Threads_connected` 1→1、RSS 165,675,008→177,651,712 bytes、
  CPU user/system +0.798/+0.064 s，due/lease/retry/非终态均为 0，评分 `PENDING` backlog 为
  300，交互 task/report 均为 0。详见
  [可追溯容量证据](./evidence/2026-08-03-mysql-capacity-traceable.json)；固定 provider 无缓存，
  因而记录为 `applicable=false`。此项只覆盖 NFR-C03/C04，不替代其他性能或故障门禁；
- [ ] 来源超时、限流、LLM 失败、worker 重启和数据库短暂断连均按 runbook 降级或恢复，
  不产生重复 prediction，也不把失败数据补成中性；
- [ ] dashboard 可按资产/来源/环境查看任务成功率与延迟、队列年龄、来源新鲜度、
  schedule lateness、评分积压/不可评分率、LLM token/回退率、迁移对账分类和
  不变量违规；对应专用指标可由 `/metrics` 查询，不能从日志临时计算；
- [ ] 每项生产告警有阈值、持续时间、owner、runbook 和恢复条件；低基数指标 label
  不含用户 ID、canonical ID 或原始查询；
- [ ] 影子批处理默认不生成完整 LLM 报告；交互报告 token 目标、硬上限、预算 80%
  告警和预算耗尽后的确定性模板回退均通过测试；
- [ ] retention job 的 dry-run、删除/去标识化、legal hold、tombstone、对象存储回收
  和审计证据通过，数据库不存在悬空引用。

## 12. J 组：迁移、兼容和交付治理

- [ ] 空库升级、从当前生产结构升级、downgrade、升级中断恢复和大数据量批次回填均
  按 `MIGRATION_PLAN.md` 演练；
- [x] MySQL 目标约束在真实方言验证；当前代码 head `20260811` 已在一次性 MySQL 9.4.0 执行
  Alembic round-trip、schema 合同、interactive task-runner claim/释放和取消竞争合同；本机共享开发库也已在 0 行
  运行事实预检后完成 `20260810 → 20260811`，并通过 postflight 和 rollback-only 合同。SQLite
  `Base.metadata.create_all()` 未被用作替代证据；
- [ ] 股票旧写、新写、旧读、新读和回退开关逐一验证；旧 `/api/v1/stock-analysis`
  与前端 `/investment/stock-analysis` 保持行为兼容；
- [ ] 旧 `BUY/SELL/WATCH` 与新字段按版本化语义映射。对账比较身份、cutoff、发布动作、
  原因、证据和结果，不要求不同哈希域相等，也不要求 LLM 报告逐字一致；
- [ ] 连续两个发布版本的可选双写对账没有未解释结构化差异；否则禁止评审旧表 contract；
- [ ] 公共契约冻结、任务依赖、RACI、风险 owner、Go/No-Go、ADR 和紧急变更流程均有
  审批证据，未关闭高风险不得绕过门禁。

## 13. 自动化验收命令

计划实施后运行：

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base alembic current
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base alembic heads
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base alembic upgrade head
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base alembic check
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/asset_research/test_plugins.py \
  tests/asset_research/test_plugin_outcome_contracts.py
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/asset_research/test_identity.py \
  tests/asset_research/test_master_data.py \
  tests/asset_research/test_stock_compat.py \
  tests/asset_research/test_api.py
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q tests/asset_research
# 仅对已由受控 CI/发布步骤迁移至 head 的非业务 MySQL schema 执行。
# 该合同测试只做回滚断言，不执行 DDL、upgrade 或 downgrade；禁止指向业务库。
ASSET_RESEARCH_MYSQL_SHARED_SCHEMA_URL='mysql+pymysql://…/codex_iter191_example' \
ASSET_RESEARCH_MYSQL_SHARED_SCHEMA_CONFIRM=yes \
  /Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/asset_research/test_mysql_contract.py
# 仅对一次性、已迁移至 head 的 codex_iter191_* MySQL schema 追加 runner 夹具合同。
ASSET_RESEARCH_MYSQL_TASK_RUNNER_DISPOSABLE_URL='mysql+aiomysql://…/codex_iter191_example' \
ASSET_RESEARCH_MYSQL_TASK_RUNNER_DISPOSABLE_CONFIRM=yes \
  /Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/asset_research/test_mysql_contract.py
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q -m integration
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/test_stock_analysis_*.py \
  tests/test_stock_signal_*.py \
  tests/test_market_instrument*.py \
  tests/test_options_chain*.py
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m mypy \
  app/api/asset_research.py app/schemas/asset_research.py app/services/asset_research
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base ruff check app tests

cd ../../src/frontend
npm run typecheck
npm run test -- --run
npm run test:e2e
npm run build

cd ../..
git diff --check
```

文档专项检查：

```bash
rg -n 'T[B]D|T[O]DO|待[定]|同[上]' docs/iterations/迭代191-AI多资产分析研究与设计
rg -n 'BUY|SELL|HOLD|AVOID|LONG|SHORT|FLAT' \
  docs/iterations/迭代191-AI多资产分析研究与设计
```

第一条命令预期无输出。内部 Markdown 链接检查器应对本目录返回零错误。

上述本地命令之外，CI 的 `asset-research-mysql-contract` job 使用官方 `mysql:9.4.0` 一次性
数据库，先执行迁移再执行 run-prediction 直接关系合同，并作为 `ci-summary` 的阻断门禁；普通 pytest 的内存 SQLite
fixture 不能作为该发布证据。旧接口回归仍由现有 backend/frontend jobs 覆盖。API 集成测试沿用项目的
`httpx.AsyncClient + ASGITransport` 约定。

## 14. 在线冒烟证据

每类资产选一个稳定样例，在不依赖其价格方向的前提下验证：

1. 搜索和身份解析响应；
2. 来源清单、观测/发布/获取时间；
3. 完整分析任务和报告；
4. 一个故意过期或缺字段的降级任务；
5. API、页面和导出建议一致；
6. 数据提供方失败时的明确错误；
7. 全流程没有账户或订单副作用。

在线数据会随时间变化，因此只验结构、来源、新鲜度和一致性，不将某个具体买卖结论写成固定断言。

2026-08-03 的本机共享 MySQL 运行时冒烟已完成：`20260810 → 20260811` 升级、真实 MySQL
rollback-only 合同、应用健康检查、认证 capability 和未获批来源的拒绝路径均通过；任务表没有遗留
行或租约。完整记录见
[本机 MySQL 运行时冒烟证据](./evidence/2026-08-03-local-mysql-runtime-smoke.md)。该记录证明
fail-closed 运行时，不替代下列六类资产真实在线成功项。

录制响应或固定 fixture 只证明离线契约，不能冒充在线通过。提供方不可用时，该资产
在线项记录 `BLOCKED`、错误、首次发生时间、下一重试时间和 provider 状态；在两个
独立重试窗口内复验。离线套件可以继续通过，但在线证据在真实成功前不得标绿。

## 15. 验收证据包

- [ ] Alembic 表、约束、run-prediction 单 run 基数/复用、持仓上下文和访问主体
  幂等断言；
- [ ] 六类资产调度清单、cutoff、重复触发和原时点补跑断言；
- [ ] 六类资产共 18 个质量样例；
- [ ] 六条成功报告及页面截图；
- [ ] 六条从预测到成熟结果的响应链；
- [ ] 时间泄漏、LLM 越权、用户隔离和无订单副作用测试；
- [ ] 离线评估、基线、全部试验版本和置信区间；
- [ ] 前瞻影子运行统计；
- [ ] 数据许可和合规审批记录；
- [x] 后端、前端、构建、静态检查完整输出；见
  [`IMPLEMENTATION_STATUS.md`](./IMPLEMENTATION_STATUS.md) 第 2 节的可复跑命令和本轮结果。
- [ ] T1 性能容量报告、运行 dashboard/告警演练、生命周期 dry-run 和 LLM 预算证据；
- [ ] 迁移矩阵、股票兼容对账、回滚演练、风险登记册和 Go/No-Go 记录。

## 16. 验收边界

T1 或 T2 通过均不表示可以自动交易，也不表示任何资产建议保证盈利。真实/模拟执行、持仓读取、仓位规模和订单风控必须在独立迭代中重新设计和验收。
