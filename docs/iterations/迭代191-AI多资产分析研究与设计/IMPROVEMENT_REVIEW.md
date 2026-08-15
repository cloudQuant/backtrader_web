# 迭代 191 改进建议评审决议

> 评审基线 HEAD：`e7fd2d5151c86ba62173b8d19736983a0a379909`
>
> 评审日期：2026-08-01
>
> 评审对象：当前工作区的迭代 191 计划文档及
> [`IMPROVEMENT_SUGGESTIONS.md`](./IMPROVEMENT_SUGGESTIONS.md)
>
> 结论：`IMPROVEMENT_SUGGESTIONS.md` 仅作为历史审查输入，不是需求、架构、实施或
> 验收的权威来源。实施权威按主题分工：范围/阶段使用 `README.md`，领域/API 契约使用
> `ARCHITECTURE.md`，交付责任和变更使用 `DELIVERY_GOVERNANCE.md`，数据库使用
> `MIGRATION_PLAN.md`，运行基线使用 `NON_FUNCTIONAL_REQUIREMENTS.md`，总体判定使用
> `ACCEPTANCE.md`，资产专属语义使用六个子迭代的
> REQUIREMENTS/DESIGN/PLAN/ACCEPTANCE；冲突处理遵循交付治理的权威矩阵。

## 1. 评审口径

本决议使用四类结论：

| 结论 | 含义 |
| --- | --- |
| `采纳` | 确认存在实质缺口，进入计划或实施前置工作 |
| `部分采纳` | 方向成立，但原建议的事实、参数或实现方式需要修正 |
| `已有覆盖` | 当前权威文档已经形成足够合同，不重复增加第二套描述 |
| `不采纳` | 事实不成立、会制造错误验收，或不适合作为架构约束 |

评审遵循以下原则：

1. 文档行数、文件大小和会议数量不是质量门槛；以需求—设计—计划—验收可追踪性为准。
2. 时间、人力、SLO、保留期、告警阈值和成本数字在负责人确认或实测前只能是基线假设。
3. 现有代码可作为适配器或参考实现，但不能因“可复用”而绕过 point-in-time、来源许可、
   动作权威、模型晋级和用户隔离合同。
4. 新旧系统语义不同，不以哈希相等、LLM 文本逐字相同或旧动作字段直接复制证明兼容。
5. 任何事实性结论都绑定上述 HEAD；代码或迁移链变化后必须重新核对。

## 2. 基线事实纠正

以下事实已经在指定 HEAD 上核验，替代历史审查输入中的旧表述：

| 主题 | 基线事实 | 评审影响 |
| --- | --- | --- |
| Alembic head | 唯一 head 是 `20260806_asset_research_direct_run_prediction`；历史 foundation 的 `down_revision` 是 `20260801_stock_signal_predictions`，且新增链条均为线性 `depends_on=None` | 后续 revision 必须以当时唯一真实 head 为父；无独立分支依赖时不新增 `depends_on` |
| 新表数量 | 最终 `ARCHITECTURE.md` 定义 14 张 `asset_*` 表；历史 foundation 的第 15 张 run-prediction 关联表已在 `20260806` 迁移为 run 的直接字段并删除 | 迁移、验收和回滚必须以 14 张最终表及历史转换链为准 |
| 股票分析 pipeline | `StockAnalysisPipeline.run()` 已是 `async def` | 不采纳“把同步 pipeline 整体改成异步”的任务；仍需通过适配器隔离阻塞型提供方和拆分决定/报告职责 |
| 前端任务 composable | 公共架构定义 `useAssetAnalysisTask`，由现有 `useStockAnalysisTask` 泛化 | 复用既有轮询和终态停止基础，补取消、重试和 stale-response 防护；不再新增 `useAssetAnalysis.ts` 作为第二套任务生命周期 |
| 资产专属详情 | 公共架构已为债券、基金、期货、外汇和数字货币补齐强类型最小骨架，并与期权组成 discriminator union | 子 DESIGN 只扩展版本化资产字段，不再把五类详情描述为完全缺失 |
| 旧股票动作 | `SignalAction`/Schema/数据库列使用 `BUY/SELL/WATCH`；旧 prediction 直接持有可空 `run_id` | 需要显式语义映射及新 run 的 `prediction_id/prediction_link_role` 直接关系适配，不能复制字段 |
| 新旧幂等哈希 | 旧 `prediction_key` 与新 `decision_input_hash/prediction_key` 的输入域不同 | 二者不应、也不会逐字相等；只做结构化语义对账 |
| 报告一致性 | 新架构允许结构化模板回退，LLM 文本并非确定性协议 | 对账比较发布决定、结构化章节、证据 ID 和数值，不比较渲染文本逐字相同 |
| 数据生命周期 | 已有来源 `retention_policy`、去标识化、tombstone 和受审计 retention job | 缺口是保留矩阵、执行参数和验收，不是从零设计 |
| 集成和回归 | 总计划已要求集成测试、在线冒烟和旧股票测试套件 | 仅补迁移路径、插件一致性和真实数据库矩阵，不重复建立第二套测试总纲 |

完整迁移决议见 [`MIGRATION_PLAN.md`](./MIGRATION_PLAN.md)。

## 3. 逐项评审

### 3.1 现有代码库对照分析

| 原建议 | 决议 | 理由与落点 |
| --- | --- | --- |
| 0.1 复用 `MarketInstrumentService` 并补足多资产数据 | `部分采纳` | 接受“适配器复用”和债券、开放式基金、可执行外汇、数字货币及通用期权数据缺口；不直接承诺修改通用缓存表。来源、四类时点和许可进入 `asset_source_snapshots`，数据源可用性成为各子迭代阻断 Gate |
| 0.2 用现有股票信号系统作为预测闭环起点 | `部分采纳` | 保留幂等、owner scope、质量门控和成绩单经验；动作、run 关系、多 head、晋级及哈希全部按新合同实现。旧动作映射和兼容读写由迁移计划统一定义 |
| 0.3 将同步股票流水线改成异步 | `不采纳` | 基线入口已经是 `async def run`。真正任务是识别并隔离内部阻塞调用、使用新 orchestrator 适配，并保持“先结构化决定、后报告解释”的职责边界 |
| 0.4 拆分前端壳、API 和状态 | `部分采纳` | 工作台壳、`assetResearch.ts`、由现有 `useStockAnalysisTask` 泛化的 `useAssetAnalysisTask` 和旧路由兼容已进入架构；任务状态机、轮询取消、过期响应丢弃和跨资产状态清理已有公共合同。是否拆成多个 Pinia store 由详细设计决定，不作为公共架构硬约束 |
| 0.5 迁移必须依赖股票预测迁移并验证外键 | `部分采纳` | 接受线性迁移、现存库验证和外键审计；纠正为新 revision 的 `down_revision=20260801_stock_signal_predictions`，而不是额外 `depends_on`。详细方案见迁移计划 |
| 0.6 现有模块直接复用清单 | `部分采纳` | 清单降级为“适配候选”。每个候选必须通过来源、许可、时点、错误语义、权限和不可变性契约测试后才能复用，不以函数存在证明可直接接入 |

### 3.2 项目风险与资源

| 原建议 | 决议 | 理由与落点 |
| --- | --- | --- |
| 1.1 新增风险管理 | `采纳` | `RESEARCH.md` 的反方证据是风险识别，不是活跃风险登记。实施前建立风险表，至少含 owner、概率、影响、触发器、缓解、应急、状态和复审日期；数据许可/覆盖、外部提供方、关键人员、LLM、时间和跨数据库迁移列为首批风险 |
| 1.2 明确资源与人力 | `部分采纳` | 需要后端、前端、量化/领域、数据、DB/DevOps、QA、安全合规及 primary/backup 角色；人数和 FTE 在团队确认前标为容量假设，不能由本文替业务负责人承诺 |

风险与资源建议已落在 [交付治理](./DELIVERY_GOVERNANCE.md) 和 `README.md`，
不把运行时模型治理与项目管理治理混为一谈。

### 3.3 时间线与阶段

| 原建议 | 决议 | 理由与落点 |
| --- | --- | --- |
| 2.1 将 P0 拆为 P0a/P0b | `部分采纳` | 接受拆成“领域/数据库/协议”与“API/前端壳/调度”两个可验收 Gate；`1.5–2 周`和各项天数仅为估算输入，需按确认的人力、技术 spike 和真实迁移演练重估 |
| 2.2 设置公共底座稳定期和接口冻结 | `部分采纳` | 接受 P0 合同冻结点、兼容性规则和公共层变更评审；不采纳“191A/191B 必须串行或由同一人负责”。共享适配边界应指定单一 owner，资产插件仍可并行 |
| 2.3 为影子阶段指定 owner 和终止条件 | `部分采纳` | 接受 P6 运营 owner、监控职责、复审节奏和关闭/继续条件；不采用统一 90 天。当前门槛已经是一般资产至少 60 个交易日、数字货币至少 90 个自然日，并同时受成熟样本和晋级门槛约束 |

### 3.4 子迭代质量与依赖

| 原建议 | 决议 | 理由与落点 |
| --- | --- | --- |
| 3.1 按文档体量拉齐深度 | `不采纳` | KB/行数不能证明边界覆盖。继续使用身份、PIT、质量、动作、结果、调度、权限、晋级的合同检查表，以及每项需求到验收的追踪表 |
| 3.2 为每个 PLAN 增加依赖图 | `部分采纳` | 总计划维护唯一跨子迭代依赖矩阵；六个 PLAN 已按任务补入“最小前置产物、可并行条件、开始前必须冻结”的实施门槛，并明确这些不是数据库、API 或任务模型中的 `depends_on` 字段。Mermaid 不是验收条件 |

### 3.5 非功能性要求

| 原建议 | 决议 | 理由与落点 |
| --- | --- | --- |
| 4.1 增加性能/SLA | `部分采纳` | 增加任务排队/完成 P50/P95/P99、报告超时与模板回退、调度最大 lateness、API/worker 吞吐和前端交互基线；实测和容量评审前称 SLO 基线，不对外承诺 SLA |
| 4.2 增加数据生命周期 | `部分采纳` | 已有 retention policy、tombstone 和清理 job。补充 raw payload、结构化快照、预测、outcome、报告/导出、审计事件的保留矩阵；期限按许可、地区、诉讼保全和用户删除规则配置，不设置一个全局天数 |
| 4.3 增加可观测性 | `部分采纳` | 已有 trace ID、来源延迟、缓存命中、原因码、版本和 token 成本。补任务成功率/耗时、队列积压、来源可用率、调度 lateness、不可评分率、LLM 回退率、迁移对账差异、告警和 dashboard；告警数值先作为基线 |

非功能合同进入 [非功能需求](./NON_FUNCTIONAL_REQUIREMENTS.md)，并由
`ARCHITECTURE.md` 和 `ACCEPTANCE.md` 分别引用其架构边界与验收证据。

### 3.6 技术细节

| 原建议 | 决议 | 理由与落点 |
| --- | --- | --- |
| 5.1 估算 LLM 成本 | `部分采纳` | 已有 token 成本记录和结构化模板回退。补单报告 token/金额预算、模型层级、缓存键、超限行为和月度预算告警；供应商单价、调用量和“每条影子预测是否生成报告”均为配置假设 |
| 5.2 详细数据库迁移策略 | `采纳` | 新增独立迁移计划，覆盖唯一 head、15 表、expand-migrate-contract、三类数据库、现存库、downgrade、失败恢复、锁、批次、可选双写和语义对账 |
| 5.3 明确前端状态管理 | `部分采纳` | 补任务状态机、轮询/取消/重试、路由切换和 stale response 防护；不把三个具体 Pinia store 名称写成不可更改的领域合同 |
| 5.4 补齐资产专属 `ResearchDetails` | `采纳` | 公共架构已补入债券、基金、期货、外汇和数字货币带 discriminator 的强类型最小骨架，并与期权组成公共 union；五个子 DESIGN 已在该骨架上扩展版本化字段，且禁止重复 recommendation、direction、概率或 actionability |
| 5.5 分阶段迁移旧股票能力 | `部分采纳` | 接受兼容适配、可选双写、证据对账和独立 Contract 评审；不比较新旧哈希或 LLM 文本逐字相等，不默认批量改写旧记录，不在本迭代删除旧表 |

### 3.7 验收与质量保障

| 原建议 | 决议 | 理由与落点 |
| --- | --- | --- |
| 6.1 增加集成测试层 | `已有覆盖` | 总计划已要求固定 PIT 夹具、集成测试、数据库约束、幂等/并发、API/权限和旧测试套件。增量只补：从当前 head 升级、六插件参数化协议一致性和真实 MySQL 迁移合同；SQLite 只保留快速回归 |
| 6.2 在线冒烟增加外部源替代 | `部分采纳` | 固定 fixture/VCR 属于离线可重复测试，不能冒充在线证据。在线源不可用时记录 `BLOCKED`、来源、时间窗口、重试次数和最终证据，不把方向值写成固定断言 |
| 6.3 增加股票兼容回归 | `已有覆盖` | 总体验收已要求旧接口/表无破坏性变更，并运行 `test_stock_analysis_*`、`test_stock_signal_*`、market instrument 和 option chain 测试。CI 中保持独立必过 lane 即可 |

### 3.8 沟通与治理

| 原建议 | 决议 | 理由与落点 |
| --- | --- | --- |
| 7.1 增加阶段评审与 go/no-go | `采纳` | 为 P0 合同冻结、每个子迭代 T1、P6 运营接管和 T2 晋级设置 owner、输入证据、结论、例外和后续动作；会议形式不作为合同 |
| 7.2 增加变更管理 | `采纳` | 公共 Schema/API/枚举/哈希/评分合同变更必须做影响分析、ADR、版本提升、子计划同步和回归；紧急变更保留事后补审与不可变记录 |

模型 `DRAFT/SHADOW/PROMOTED/SUSPENDED/RETIRED` 的运行治理已由架构定义，以上仅补项目
交付治理，不能用项目评审替代模型、合规、数据许可或安全审批。

## 4. 采纳优先级

### 实施前阻断项

1. 完成数据源可用性与许可 Gate，特别是债券、开放式基金、可执行外汇、完整期权链和
   多场所数字货币。
2. 确认资源/owner 和 P0a/P0b 容量假设。
3. 完成 [`MIGRATION_PLAN.md`](./MIGRATION_PLAN.md) 的 MySQL 发布演练及回滚证据。
4. 由五个子 DESIGN 在公共 `ResearchDetails` 最小骨架上完成版本化扩展和验收映射。
5. 建立风险登记、公共合同冻结和变更管理。

### 可在 P0/P1 持续收敛

1. 性能 SLO、容量、告警和 dashboard 基线。
2. 数据保留矩阵及清理 job 验收。
3. LLM token/金额预算和降级门槛。
4. 前端状态机和插件一致性测试。

## 5. 维护规则

- 本文记录对历史建议的处置，不成为新的领域规范；领域语义仍回写权威需求/架构/验收。
- `IMPROVEMENT_SUGGESTIONS.md` 不再直接驱动实现任务；后续建议先在本决议或对应 ADR
  中评审，再进入权威计划。
- 基线 HEAD、Alembic head、表数量、代码路径或现有行为变化后，相关事实必须重新验证。
- 已采纳建议完成后在权威文档和验收证据中闭环，不通过修改历史建议制造“已完成”表象。

## 6. 本次实现闭环（2026-08-01）

在本决议之后，以下“采纳/部分采纳”项已形成代码和自动化证据，而非仅保留在计划中：

| 主题 | 实施结论 | 证据 |
| --- | --- | --- |
| 资产特征、日历与结果口径 | 已落实 v2 资产专属特征、冻结来源日历、期权标的/IV 评分以及债券/数字货币可执行报价边；不再将通用价格动量或工作日猜测混入新 cohort | `test_plugin_outcome_contracts.py`、`test_outcome_evaluator.py` |
| 可观测性 | 已复用现有 Prometheus registry 和 `/metrics`，接入 task/source/schedule/reuse/outcome/lifecycle 十个低基数 series；未注册来源固定记为 `UNREGISTERED`，不会把 URL、用户、标的或任务 ID 作为标签 | `test_metrics.py`、`test_orchestrator.py`、`test_outcome_scheduler.py` |
| 生命周期 | 已提供有界、只读的 retention dry-run，覆盖全部 15 张 `asset_*` 表（含审批 manifest），分类到期、legal hold 与既有 tombstone；没有自动删除或篡改事实 | `test_retention.py` |
| MySQL 真实迁移 | 一次性 MySQL 9.4.0 完成空库 upgrade、最终 15 张 `asset_*` 表/零资产 run trigger 核验、真实非法状态拒绝、降级至父 revision 与 re-upgrade；共享 MySQL 已升级到 `20260808` 并通过回滚式合同 | `test_mysql_contract.py`（显式确认已迁移 schema 才执行） |
| MySQL 迁移可用性 | run-prediction 不变量改为 FK + 行级 CHECK，不依赖 binary-log trigger 或全局 `SUPER`；迁移不改变服务器变量且不以 `stamp` 绕过目录核验 | `test_migration.py`、`test_mysql_contract.py` 和共享库目录核验 |
| 前端可恢复轮询 | 临时请求错误只按 2.5/5/10/20 秒退避；成功后恢复配置轮询，404 等确定性客户端错误保持可见失败且不产生后台重试 | `useAssetAnalysisTask.test.ts` |
| 浏览器研究边界 | 静态 fixture 下必须先搜索候选、显式确认期货合约、再创建任务；任务完成到报告渲染只显示已发布 `HOLD/RESEARCH_ONLY` 决定和“不能直接下单”边界，不展示候选 head | `e2e/a11y/asset_analysis.spec.ts` |

当前测试计数以 [`IMPLEMENTATION_STATUS.md`](./IMPLEMENTATION_STATUS.md) 为准；前端
typecheck、1,283 项测试和生产构建通过。上述结果不关闭真实数据许可、真实交易/NAV 日历、
目标 MySQL 发布演练、dashboard/告警演练、实际清理或 T2 模型晋级 Gate。

## 7. 后续实现闭环（2026-08-02）

第 2 节和第 6 节中的 `20260806` / 14 表描述是 2026-08-01 的评审基线，保留以使
建议—决议—实现的时间线可追溯；它们不再是当前实现事实。本轮新增并验证以下受采纳建议
直接要求的控制面，而不是用运行时 selector 或市场扫描临时生成系统任务：

| 主题 | 当前实现结论 | 验证证据 |
| --- | --- | --- |
| 静态系统调度清单 | `20260807_asset_research_schedule_manifests` 新增版本化、可退役的审批清单；管理员以 approval reference、非空 evidence URI/hash 和精确资产条目创建 `PUBLIC_SHADOW/ADMIN_EVAL` schedule。每条 system schedule 绑定 manifest entry/hash 和唯一 active target，worker 与 retry 会复核该绑定 | `test_schedule_manifests.py`、`test_schedule_runner.py`、`test_api.py`、`test_migration.py` |
| 证据不可绕过 | `20260808_asset_research_manifest_evidence_required` 将 evidence URI/hash 收紧为数据库非空字段；若历史清单缺证据，迁移停止并要求人工补齐，绝不伪造回填 | SQLite migration 合同和 MySQL rollback-only 合同 |
| 成熟原因不可绕过 | `20260809_asset_research_maturity_reason_contract` 把架构定义的 `MaturityReason` 落实为 `asset_signal_outcomes` 的 CHECK；历史未定义值会停止升级而非被静默改写，`MATURED` 等非法值被 API 和 MySQL 同时拒绝 | `test_models.py`、`test_migration.py`、`test_mysql_contract.py` |
| 交互任务可恢复 | `20260811_asset_research_task_leases` 将交互 task 的 lease token、过期时间、心跳和尝试次数持久化；API 只唤醒合并 runner，长任务续租，进程中断后由过期租约恢复为可审计失败，而非永久卡在 `RUNNING` | `test_task_runner.py`、`test_task_lifecycle.py`、`test_api.py`、`test_main_startup.py`；MySQL 9.4.0 真实 claim/释放合同 |
| 当前迁移终态 | 代码唯一 Alembic head 为 `20260811_asset_research_task_leases`，最终仍为 15 张 `asset_*` 表；本机共享开发 MySQL 9.4.0 已经 0 行运行事实 preflight 升级至该 head，并通过 postflight 目录和 rollback-only 合同。一次性同版本库也已通过含 `20260811` 的 full round-trip。仍没有获批来源、主数据或系统清单行 | `test_migration.py`、`test_orchestrator.py` 覆盖 context 绑定；一次性 MySQL 的 `test_mysql_contract.py` 覆盖既有 run/context 拒绝合同及新的 task lease DDL/claim 合同；本机共享 MySQL 也执行了 rollback-only 合同，CI 将强制 round-trip 后重跑 |
| 资产级身份与降级 | 期货产品、资产级外汇/数字货币、永续/专门模型资产不会被晋级绕成方向建议；完整期货合约、基金份额类别、外汇远期/NDF 的条件身份字段均在 Schema 层 fail-closed。二级证据不足、参考汇率和官方估值缺执行价时可保留研究，但统一降为 `HOLD + RESEARCH_ONLY + NONE` | `test_identity.py`、`test_plugin_outcome_contracts.py`、`test_data_adapter.py` |
| 服务端地区门禁 | FX/数字货币地区限制不接受客户端参数：中国大陆必为 `REGION_RESTRICTED + AVOID + NONE`；其他地区也需操作开关和来源注册表 jurisdiction 同时允许。冻结的合规上下文参与 prediction 输入哈希 | `test_compliance_policy.py`、`test_orchestrator.py::test_orchestrator_applies_server_owned_mainland_fx_restriction`、`test_source_registry.py` |
| 当前回归 | 资产研究回归、当前 MySQL 回滚式契约、后端全量、前端回归和生产构建均通过；真实数据许可、主数据、日历、生产运维和 T2 晋级仍保持 Gate 关闭 | 后端全量 `4711 passed, 128 skipped`；当前本机共享 MySQL rollback-only 合同 `1 passed`；前端 `1,283 passed`、typecheck、build 和含 Axe/键盘/320px 视口断言的浏览器 fixture `13 passed` |

当前权威事实和未关闭 Gate 以
[`IMPLEMENTATION_STATUS.md`](./IMPLEMENTATION_STATUS.md)、
[`MIGRATION_PLAN.md`](./MIGRATION_PLAN.md) 与
[`ACCEPTANCE.md`](./ACCEPTANCE.md) 为准。
