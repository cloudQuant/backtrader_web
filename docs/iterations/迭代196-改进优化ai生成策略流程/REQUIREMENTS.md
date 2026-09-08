# 迭代 196 需求文档：可信 AI 策略研究流程

> 状态：独立评审后修订的目标合同基线；目标 head 为 `20260908_ai_research_approval_authority`。它的当前回归与逐项验收状态须等待 `REGRESSION_6_WORKERS_20260908.md` 生成及 [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) 同步更新；在此之前不得以 2026-09-07 数字声称当前 PASS。历史本地 resolver 不再把 URI 或由 URI/元数据导出的哈希当作对象身份，而是要求服务器 object receipt、版本、摘要和 identity hash；但该证据仍是本地受控范围，真实对象存储/IAM 的不可变性与同 key 替换防护仍须以环境证据实证。
> 2026-09-08 协议加固：在独立代码审查发现 command-wide 绑定、外部副作用恢复、授权签发和浏览器安全投影仍缺直接合同后，新增 `FR-DATA-014`、`FR-TASK-011～012`、`FR-GATE-012～015`、`FR-UI-015` 共 8 条 P0。当前基线因此由 85 条 P0 FR 增至 93 条；加上 11 条 P0 NFR 与 6 条必需 MIG，共 110 个 P0 合同项。旧评审中的 102 项数字保留为当时历史基线，不回溯改写。
> 2026-09-08 审批终审收紧：后续独立复核发现的 human principal 来源、唯一 `ISSUED` audit、同时间戳 denial fence、审批资格派生、安全 DTO/错误投影与跨语言 Unicode 规范化，均属于对上述现有 P0 的可否证性收紧，不新增 FR/MIG 编号，P0 总数保持 110。
> 文档类型：产品/业务/系统需求
> 关联设计：[DESIGN.md](DESIGN.md)
> 关联验收：[ACCEPTANCE.md](ACCEPTANCE.md)

## 1. 背景与问题定义

当前 `/investment/strategies` 已经能够把自然语言目标转成结构化投资要求，生成 Backtrader 策略并执行多轮回测、验证、稳健性检查、模拟盘与实盘准备。现阶段的瓶颈不是“能否生成代码”，而是：

- 是否能证明候选在生成时没有看到最终留出证据；
- 是否记录了所有实验，而不是只看到最佳策略；
- 是否针对大规模搜索修正了选择偏差；
- 是否能从数据、代码、模型、提示词和环境重新构造结论；
- 是否能在 worker 重启、取消、重试和页面切换后保持唯一且一致的状态；
- 是否由服务端证据门和真实身份做出晋级决定；
- 是否能向用户明确展示未知、不确定和失败，而不是压缩成单一评分。

迭代 196 将 AI 投研从“生成—回测—看最佳结果”的功能升级为“预注册—探索—冻结—独立评估—前向观察—人工决定”的可信研究流程。

## 2. 产品目标与非目标

### 2.1 产品目标

| ID | 目标 | 成功定义 |
| --- | --- | --- |
| OBJ-01 | 研究身份不可变 | 每次运行绑定已确认的假设版本、数据策略、搜索预算和规范化哈希 |
| OBJ-02 | 独立证据隔离 | 生成器无法读取密封留出；留出结果不回流改进同一候选 |
| OBJ-03 | 搜索过程完整 | 成功、失败、取消、超时均进入追加式实验账本 |
| OBJ-04 | 统计结论诚实 | 使用完整搜索计数执行 DSR；缺少必要证据时阻断晋级 |
| OBJ-05 | 过程可重放 | 数据、代码、模型、提示词、工具和环境谱系可验证、可导出 |
| OBJ-06 | 运行可恢复 | 幂等、lease、心跳和阶段游标避免重复关键副作用 |
| OBJ-07 | 决定可问责 | 自动门与人工审批分离，审批身份来自认证上下文 |
| OBJ-08 | 界面以证据为中心 | 用户能区分主张、证据、反证、未知、门禁和人工决定 |

### 2.2 非目标

- 不保证 Alpha、收益、Sharpe 或实盘盈利；
- 不允许 LLM 直接触发实盘下单或自动发布策略；
- 不以文章所述“十倍效率”“一人替代团队”作为 KPI；
- 不建设全自治、多 Agent、自我批准的研究组织；
- 不重建行情供应、Backtrader 引擎、模拟盘和实盘执行平台；
- 不把同源模型互相同意视为独立验证；
- 不把旧运行结果补录成新的密封留出或生产证据。

## 3. 用户与职责

| 角色 | 主要目标 | 权限边界 |
| --- | --- | --- |
| 研究员 | 定义假设、运行探索、理解证据、冻结候选 | 可使用发现/验证数据；不可直接读取密封留出原始数据 |
| 研究评审人 | 检查证据、反证、限制和可复现性 | 不得修改被冻结候选；不能绕过服务端硬门 |
| 风险/实盘审批人 | 批准或拒绝模拟/实盘准备 | 身份来自登录会话；需独立挑战和理由；不得由客户端伪造 |
| 研究管理员 | 管理数据策略、阈值政策、模型和密钥引用 | 可发布有版本策略；不能改写历史运行和决定 |
| Explorer Agent | 生成、解释、改进候选 | 只可访问发现/验证上下文；无密封留出和审批权限 |
| Independent Evaluator | 执行冻结候选的独立评估 | 只读候选与指定留出快照；不得改代码或调用生成器 |
| 系统审计员 | 读取不可变事件和证据 | 只读；查看脱敏后的谱系、访问和审批记录 |

### 3.1 Actor 拓扑与审批声明

系统必须区分部署中的责任主体拓扑，而不是假定所有部署都能做到人类职责分离：

- `MULTI_ACTOR_SEPARATED_DUTIES`：研究创建者、风险/实盘审批人可由不同认证主体承担；适用 policy 可强制独立审批或四眼原则；
- `SINGLE_ACTOR_SELF_ATTESTED`：同一自然人可能同时承担研究员和管理员。AI/系统仍不得自批，前端仍不得伪造 actor；服务端必须披露“未实现独立人类复核”的残余风险；
- 冷却期、逐项挑战、证据包哈希回显只能作为 single-actor 的补偿控制，不能被显示或记录为“独立审批”；
- 当 Promotion Policy 要求独立审批时，single-actor 请求必须返回 `BLOCKED_REQUIRES_INDEPENDENT_APPROVER`；只有 policy 明确允许的自托管 scope 才能产生带 `single_actor=true` 和残余风险声明的自我确认决定。
- “人类主体”必须是服务端身份事实，不得由角色名、活跃会话或客户端布尔值推断。身份分类至少为 `HUMAN/SERVICE/UNKNOWN`；`SERVICE` 与 `UNKNOWN` 在 grant manager、issuer、subject、decision actor 和历史重放中均 fail-closed。存量主体未经可审计分类时必须保持 `UNKNOWN`，不得迁移为假定人类。

## 4. 术语与语义迁移

| 术语 | 定义 |
| --- | --- |
| 发现集（Discovery） | 用于假设形成、代码生成和初步回测的数据 |
| 迭代验证集（Iteration Validation） | 可被探索流程观察并用于选择/改进的数据；不具备最终独立性 |
| 密封留出集（Sealed Holdout） | 候选冻结前 Explorer 不可访问，只有独立评估器可按授权读取的数据 |
| 前向观察（Forward Observation） | 候选冻结后随时间自然产生的新事件；运行开始时只能预注册观察政策，不能预先拥有未来 snapshot |
| 候选（Candidate） | 一个确定的代码、参数、环境、数据策略和预注册假设组合 |
| 候选冻结（Candidate Freeze） | 固化候选内容哈希；冻结后修改必须创建新候选 |
| Trial | 一次候选—数据—评估组合；一旦观察到性能结果就计入市场试验数 |
| 证据包 | 可重放候选结论所需的不可变清单、哈希、事件和报告集合 |
| Promotion Policy | 有版本的晋级规则和阈值；历史决定永久绑定当时版本 |
| 实验纪元（Experiment Epoch） | 一组共享研究问题、搜索预算与密封留出政策的候选家族；留出揭盲后按政策关闭，防止轻微变体反复窥探 |

兼容性要求：当前字段和页面中的 `out_of_sample` 在 v2 读取时必须标为 `iteration_validation` 或 `legacy_oos`，不得自动解释为 `sealed_holdout`。

## 5. 关键用户旅程

### J1：预注册研究

1. 研究员输入投资目标或选择配置档案；
2. 系统解析成结构化假设草稿，并显示解析来源与未知字段；
3. 系统执行数据可用性与敏感字段预检；
4. 研究员确认完整假设、成本、数据切分、主指标、失效条件和搜索预算；
5. 后端保存不可变假设版本、规范化请求和内容哈希；
6. 后续任何受约束字段变化都使当前确认失效，并创建新草稿版本。

### J2：探索与实验记账

1. 系统以幂等键创建持久任务；
2. Explorer 只获得发现集/迭代验证集授权；
3. 每次生成、编译/校验、回测、失败、取消、超时均追加 trial/事件；
4. 用户看到搜索预算、已用次数、失败次数、成本和关键诊断；
5. 系统可继续生成，但不得删除或覆盖早期失败。

### J3：冻结与独立评估

1. 研究员选择一个满足探索门的版本并申请冻结；
2. 服务端核对完整账本、数据快照、返回序列、代码/环境哈希和搜索预算；
3. 系统冻结候选并签发一次性、短期、候选绑定的留出授权；
4. Independent Evaluator 执行评估并写入不可变证据；
5. 评估结果只进入证据/门禁/报告，不进入 Explorer 的提示词、改进指标或工具输出；
6. 留出失败后，同一候选不能再次调参；修改必须成为新候选并进入新的数据/前向纪元策略。

### J4：前向观察与人工决定

1. 通过密封门的候选进入模拟/影子观察；
2. 系统持续记录成本偏差、风险、漂移和运行完整性；
3. 评审人查看主张、证据、反证、未知和限制；
4. 服务端确认硬门均通过；
5. 审批人使用认证身份提交批准/拒绝、理由和确认挑战；
6. 批准只允许进入现有的实盘准备流程，不自动下单。

### J5：中断、取消和恢复

1. 取消请求产生持久取消意图和审计事件；
2. worker 在可中断点停止，释放或终止 lease，不启动新阶段；
3. 页面停止旧任务轮询，任何迟到响应按 task/run ID 丢弃；
4. worker 异常退出时，新 worker 只可在 lease 到期后通过 CAS 接管；
5. 已完成的 trial、留出评估和晋级决定不得重复执行。

## 6. 功能需求

### 6.1 假设预注册与确认

| ID | 优先级 | 需求 |
| --- | --- | --- |
| FR-HYP-001 | P0 | 系统必须支持 `DRAFT` 与 `CONFIRMED` 两种持久状态；创建解析结果不得自动等同于人工确认。 |
| FR-HYP-002 | P0 | 预注册字段至少包含研究问题、经济机制、标的范围、频率、起止时间、可用信息截止、主指标、次指标、成本/滑点、容量假设、失效条件、搜索空间与最大预算。 |
| FR-HYP-003 | P0 | 确认必须保存 `confirmed_by`、`confirmed_at`、假设版本、规范化 JSON 和 `content_hash`；身份从服务端认证上下文取得。 |
| FR-HYP-004 | P0 | 规范化请求内容哈希是确认有效性的唯一权威；确认后任何导致哈希变化的字段改动都必须使旧确认失效。示例包括 prompt、标的、频率、日期、主/次指标、失效条件、成本、质量门、OOS/稳健性配置、`workflow_steps`、搜索预算、数据策略、执行模型与沙箱策略，但实现不得只依赖该枚举。 |
| FR-HYP-005 | P0 | 已确认版本不可覆盖；修改生成新版本，并保留父版本和差异。 |
| FR-HYP-006 | P0 | 事后 AI 解释必须标为 `post_hoc`，不得写回预注册机制或伪装成先验理由。 |
| FR-HYP-007 | P0 | 数据预检失败、结果过期或请求哈希不匹配时，前端禁用启动且后端必须拒绝请求。 |
| FR-HYP-008 | P1 | 系统提示与历史研究相似的假设、数据问题和拒绝原因，但不能自动阻止新研究。 |

### 6.2 数据分区、快照与密封

| ID | 优先级 | 需求 |
| --- | --- | --- |
| FR-DATA-001 | P0 | 每个运行必须绑定有版本的数据策略，明确 Discovery、Iteration Validation、Sealed Holdout 的历史边界，并预注册 Forward Observation 的来源、最小持续时间/事件数和开始条件；不得在冻结前声明未来 snapshot。 |
| FR-DATA-002 | P0 | 历史快照和冻结后追加的 forward observation snapshot 都必须记录供应商、标的身份、频率、时区、复权/连续合约规则、event-time、ingest/as-of、知识截止、vintage、内容哈希和许可标签；还必须记录由可信存储解析的不可变对象版本/ETag（仅在其语义等同不可变版本时）或字节内容摘要。预检、冻结和评估必须重新核验同一对象身份；URI 文本或由 URI/元数据导出的哈希不能替代该核验，同一 key/URI 的对象字节替换必须 fail-closed。 |
| FR-DATA-003 | P0 | 时间切分必须支持 walk-forward、purge 和 embargo，并输出可验证的 fold 清单与证据哈希。 |
| FR-DATA-004 | P0 | Explorer 的服务身份、数据 API、工具清单和运行容器不得获得密封留出读取权限。 |
| FR-DATA-005 | P0 | 留出授权必须绑定 `candidate_id + candidate_hash + dataset_snapshot_id + policy_version`，具备短期过期时间和一次性消费语义。 |
| FR-DATA-006 | P0 | 每次留出访问（成功或拒绝）必须记录主体、候选、快照、用途、时间和结果。 |
| FR-DATA-007 | P0 | 留出结果不得出现在同一候选后续生成提示、改进输入、工具调用参数或知识库写入中。 |
| FR-DATA-008 | P0 | 候选在留出访问后发生代码、参数、依赖、成本或数据策略变化时必须拒绝原授权，并产生新候选。 |
| FR-DATA-009 | P0 | 旧 `out_of_sample` 证据只能显示为 legacy/iteration validation，不具备密封门资格。 |
| FR-DATA-010 | P0 | 必须按实验纪元/候选家族/研究问题管理留出预算；留出揭盲后关闭当前纪元，轻微变体不得通过新建 candidate 反复窥探同一留出。 |
| FR-DATA-011 | P0 | 生产/晋级运行必须具备明确起止时间、完整数据覆盖、资产规格、交易日历、许可与成本证据；缺失或仅有 warning 不得进入 paper。 |
| FR-DATA-012 | P0 | 训练、验证、留出、模拟使用的执行模型必须标明滑点、成交量限制、停牌、涨跌停/价格限制、冲击与未支持项；未实现项显示 `UNKNOWN/BLOCKED`，不得静默按零成本处理。 |
| FR-DATA-013 | P0 | Independent Evaluator 必须运行在独立 worker/进程和服务身份中，使用独立数据访问 credential/role（或经拒绝测试证明等价的独立存储边界）、对象存储凭据与专用队列；Explorer/API 的凭据和网络路径不得读取密封对象或消费授权，共享应用超级凭据一律不合格。 |
| FR-DATA-014 | P0 | 一个可用于审批的成功留出结论必须由同一 `holdout command` 唯一绑定候选冻结回执、一次性授权、evaluation、execution operation、受控 artifact binding、终态访问审计和 evidence package；candidate-wide 旧清单、v1 manifest、相邻 evaluation 或仅有 PASS 指标均不具备审批权威。 |

### 6.3 追加式实验账本与统计控制

| ID | 优先级 | 需求 |
| --- | --- | --- |
| FR-LEDGER-001 | P0 | 每个提交的尝试都必须创建 trial；状态至少含 `QUEUED/RUNNING/SUCCEEDED/FAILED/CANCELLED/TIMED_OUT/INVALID`。 |
| FR-LEDGER-002 | P0 | trial 必须保存父候选、代码与参数哈希、数据快照、fold、随机种子、指标定义、成本模型、模型调用、开始/结束时间、资源消耗、输出摘要和异常。 |
| FR-LEDGER-003 | P0 | 账本只允许追加状态事件；修订必须新建纠正事件，不得删除失败或重写历史结果。 |
| FR-LEDGER-004 | P0 | `attempt_count_total` 统计所有提交；`market_trial_count` 保守统计所有已观察性能的候选—数据—评估组合，包括失败后仍已取得指标的尝试。 |
| FR-LEDGER-005 | P0 | DSR 必须使用可审计的候选返回序列、`market_trial_count` 及完整 trial 账本得出的跨试验 Sharpe 方差；缺少返回序列、试验数、试验 Sharpe 分布、频率或基准时返回 `UNKNOWN/BLOCKED`。 |
| FR-LEDGER-006 | P0 | DSR 应复用现有 `purgedcv` 依赖和 `asset_research/evaluation.py` 的统计边界，但必须修正当前 wrapper 把收益方差当作 `var_sharpe` 的语义，并对所有调用者做独立 oracle/回归验证；依赖必须进入生产 extra/锁文件和目标镜像 import smoke，不得只存在于 dev 依赖或复制未经验证的新公式。 |
| FR-LEDGER-007 | P0 | 质量门不得仅依据简单平均分晋级；每个硬门独立显示 PASS/FAIL/UNKNOWN/BLOCKED 与证据引用。 |
| FR-LEDGER-008 | P0 | Promotion Policy 必须有版本、发布时间、阈值、适用资产/频率和变更理由；历史决定绑定原版本。 |
| FR-LEDGER-009 | P1 | 增加 CSCV/PBO 与参数/路径敏感性；PBO 阈值是可配置政策，不是全市场通用真理。 |
| FR-LEDGER-010 | P1 | 可在证据充分时计算相关性调整的 `effective_trial_count`，但不得低于可证明的保守下界或替代原始试验数展示。 |

### 6.4 生成、验证与候选冻结

| ID | 优先级 | 需求 |
| --- | --- | --- |
| FR-PIPE-001 | P0 | Explorer 只能在预注册搜索空间和预算内生成/改进；越界请求必须被服务端拒绝并留痕。 |
| FR-PIPE-002 | P0 | 每次模型调用必须保存 provider、请求的模型名、配置的模型 pin、供应商回报的实际模型版本/快照（若提供）、请求 ID、采样参数、token/费用、输入输出哈希、提示模板版本、工具清单和回退原因。配置值与观察值必须分开，缺失观察值/用量/费用标为未知，不回填配置或 0 冒充证据；严格生成政策要求观察版本与 pin 匹配后才可成功。 |
| FR-PIPE-003 | P0 | 生成结果必须绑定策略代码、依赖锁/环境摘要、Backtrader/项目版本、随机性和沙箱策略。 |
| FR-PIPE-004 | P0 | 候选冻结必须验证代码/参数/环境/数据/假设哈希完整，并禁止原地修改。 |
| FR-PIPE-005 | P0 | 独立评估器不得调用生成器、修改策略、选择最佳变体或访问非授权数据。 |
| FR-PIPE-006 | P0 | 独立评估结果只能写入 evaluation、gate decision 和只读报告；系统必须有自动化泄漏断言。 |
| FR-PIPE-007 | P0 | robustness、成本、滑点、换手、容量、极端路径和执行语义检查必须是独立门，不得被较高 Sharpe 抵消。 |
| FR-PIPE-008 | P0 | AI 评审/反证输出仅标为辅助证据，不能将门禁从 FAIL/UNKNOWN 变为 PASS。 |
| FR-PIPE-009 | P1 | 支持不同方法或不同模型的挑战者，但界面必须提示相关错误风险。 |
| FR-PIPE-010 | P0 | 所有模型调用必须通过统一 Research LLM Gateway，执行原子预算预留、Prompt Registry、调用日志、重试/回退和发送前脱敏；携密字段名必须在派发 claim 前拒绝，敏感字段值不得外发，数值资源上限须按严格类型保留而非误脱敏。研究服务和 improver 不得绕过治理直连 provider，也不得把非原子的历史成本查询当作并发硬预算。 |
| FR-PIPE-011 | P0 | 每个产物必须分开记录 `origin`（user/deterministic_template/llm/rag）、`transformation_chain`（generated/repaired/optimized/manual_edit）与 `fallback_chain`；这些维度可组合，确定性模板或 fallback 不得显示为纯“AI 生成”。 |
| FR-PIPE-012 | P0 | `workflow_steps` 要么驱动受验证的服务端执行图，要么从可执行配置中删除并明确为展示选项；不得声称执行了实际未运行的步骤。 |
| FR-PIPE-013 | P0 | 验证、正式回测和模拟盘必须执行同一代码哈希、依赖锁和执行语义合同；允许使用按阶段最小权限的不同签名镜像，但每个 image digest 必须进入 artifact identity 并通过等价性契约，任何未批准的重建/替换都创建新 candidate 并重跑门禁。 |
| FR-PIPE-014 | P0 | hypothesis、task/run、candidate/evaluation、promotion/approval 必须使用各自权威状态机和单一事务 owner；跨聚合流转通过有幂等键的 command/outbox 协调，UI 生命周期不得充当持久化状态机。 |

### 6.5 持久任务与生命周期

| ID | 优先级 | 需求 |
| --- | --- | --- |
| FR-TASK-001 | P0 | AI 研究任务必须持久化到数据库，不以进程内字典作为权威状态。 |
| FR-TASK-002 | P0 | 同一用户和同一规范化请求的幂等键只能创建一个有效任务；不同请求复用同一键必须返回冲突。 |
| FR-TASK-003 | P0 | 任务领取使用 CAS lease、过期时间和心跳；同一时刻最多一个有效执行者。部署 worker 只能在完整的服务端 stage executor 图已显式注入后领取任务，缺失执行器的启动必须在首次 claim 前失败，而不能把用户任务逐个标为占位失败。 |
| FR-TASK-004 | P0 | 阶段游标、已提交副作用及其向受批准后继阶段的转换必须在同一原子事务中持久化；每个 `SUCCEEDED` 回执必须有服务端生成、内容哈希/大小可重验且绑定 owner/run/task/attempt/request hash 的输出。接管租约只能原子采纳该完整回执；无绑定/篡改/错绑回执、终态 retry 改 cursor、重放副作用、复写旧租约回执或跳过服务端执行图均必须拒绝。 |
| FR-TASK-005 | P0 | 取消具有持久状态和幂等语义；终态任务再次取消不得改变结果。 |
| FR-TASK-006 | P0 | 留出评估、策略版本落盘、晋级决定和模拟盘创建必须具备独立幂等键。 |
| FR-TASK-007 | P0 | 前端轮询必须绑定 task/run identity；取消、切换任务或组件卸载时停止旧轮询，迟到响应不得更新新任务。 |
| FR-TASK-008 | P0 | 列表、详情和事件 API 必须支持分页/游标，不能只保留“最近 20 条”作为唯一记录。 |
| FR-TASK-009 | P0 | LLM 调用与回测计算必须在接受任务/阶段前执行原子预算预留和并发硬上限；并发 worker 不得超卖同一配额，超限返回 `BLOCKED_BUDGET/QUOTA`。模型派发上界必须覆盖输入与输出总 token，金额预留绑定受审计费合同/价格版本及精确出站请求，不能仅以输出 cap 不超过预留量声称费用硬门完成。Token 与金额必须成组预留、派发、结算/恢复，不准经旧单笔接口拆分；保守记账额必须与真实供应商账单明确区分。完成、取消或超时后仅在外部/runner 结果已确认时结算或释放；外部结果不明时必须保留预留、按最大值保守结算或阻断 bucket，不能仅凭 worker lease/fencing 回收后再次消费。 |
| FR-TASK-010 | P1 | 支持队列优先级、人工暂停/恢复、公平调度和预算预测；不得通过调度优先级绕过 P0 硬上限。 |
| FR-TASK-011 | P0 | 对具有外部副作用的留出执行必须使用确定性 operation ID、规范化 command hash 与持久 journal；状态至少表达准备、派发中、结果未知、已观察和已结算。响应丢失或 commit ACK 不确定时必须先 inspect/read-back；无法证明未执行时保持 `UNKNOWN/RECONCILING`，禁止换 operation 或盲目再次 POST。 |
| FR-TASK-012 | P0 | holdout worker 必须默认关闭，只能从受限部署 factory 启动，并在首次 recover/claim 前验证完整配置、executor 能力和运行身份；运行期间支持 lease heartbeat、代际 fencing、clean stop 与 token-free UNKNOWN 恢复，公开 API 不得暴露 worker bearer 或内部 claim/finalize 权限。 |

### 6.6 服务端门禁、人工审批与实盘准备

| ID | 优先级 | 需求 |
| --- | --- | --- |
| FR-GATE-001 | P0 | 生产/晋级流程必须由服务端强制要求数据预检、时间隔离、试验账本、DSR、稳健性、安全扫描和必要审批；客户端不得关闭硬门。 |
| FR-GATE-002 | P0 | 所有门禁结果必须包含 policy 版本、输入证据哈希、执行器版本、时间、状态和原因。 |
| FR-GATE-003 | P0 | 缺证据统一视为 `UNKNOWN/BLOCKED`，不得按 PASS 处理。 |
| FR-GATE-004 | P0 | 审批请求不得接受可自由伪造的 `approver` 作为权威；后端从认证上下文读取 user/role，并通过版本化的研究领域权限把现有 RBAC 映射为 researcher/reviewer/risk-approver/auditor 等能力；默认角色名本身不自动获得高风险权限。 |
| FR-GATE-005 | P0 | 账户确认、风险限额确认和独立挑战必须是可验证记录，不得由前端固定提交 `true`。 |
| FR-GATE-006 | P0 | 批准/拒绝必须保存决定、理由、审批者、角色、被审批证据包哈希、时间和可选失效时间。 |
| FR-GATE-007 | P0 | 候选或证据包变化后旧审批自动失效；拒绝不得被后续同一证据的前端重试覆盖。 |
| FR-GATE-008 | P0 | 实盘批准仅允许进入现有 live prepare/handoff，仍不得自动启动交易或下单。 |
| FR-GATE-009 | P1 | 高风险策略支持四眼原则和审批职责分离策略。 |
| FR-GATE-010 | P0 | 审批必须记录 `approval_mode`。single-actor scope 若 policy 允许，仍须由服务端执行版本化冷却期、逐项挑战、证据包哈希回显和残余风险确认，并保存 `single_actor=true`；若 policy 要求独立审批则必须 BLOCKED，补偿控制不得冒充职责分离。 |
| FR-GATE-011 | P0 | 任何偏差决定必须追加记录目标需求/门禁、原状态、理由、风险、补偿控制、actor、scope、生效/到期/撤销时间；偏差不得把原 FAIL/BLOCKED 改写为 PASS，且不可豁免项始终阻断完整验收。 |
| FR-GATE-012 | P0 | evidence package v2 只能由 `SUCCEEDED` terminal command、同 command 的 `PASSED` evaluation、完整 13 项当前策略硬门及精确 artifact/audit 绑定生成；拒绝、失败、未知、旧 manifest、错绑或缺项均不得产生活跃证据包。并发构建只能收敛为一个 command-scoped 包。 |
| FR-GATE-013 | P0 | approval request 与 human decision 必须分步持久化；actor、approval policy/material hash、mode、数据库时间、领域权限和 grant 均由服务端解析。客户端只允许提交当前证据引用、决定、理由、挑战回答、残余风险确认和幂等键，不得提交或覆盖权威身份/策略字段。服务端必须分别派生“可提交任何决定”的 `can_decide` 与“当前可批准”的 `can_approve`；浏览器不得自行合成资格，且两个布尔值都不代替 decision 事务内的最终重验。请求、grant、profile 或 decision TTL 以数据库时钟到期后必须投影为 `EXPIRED`、稳定阻断 code 与 `can_approve=false`。 |
| FR-GATE-014 | P0 | approval grant 必须由拥有独立 `research:manage-approval-grants` 权限的活跃 `principal_kind=HUMAN` 主体通过服务端接口签发/撤销，精确绑定活跃 human subject、run/workspace、`research:approve`、数据库签发时间和受限 TTL。grant 只在恰有一条与 issuer/subject/scope/permission/policy/material/幂等材料完全一致的不可变 `ISSUED` audit 时有来源效力；缺失、重复、篡改或错绑 audit 均 fail-closed。当前资格需另行重验未过期/未撤销；历史精确重放仍必须验证原 `ISSUED` audit，且满足 `issued_at <= decided_at < expires_at` 与 `revoked_at IS NULL OR decided_at < revoked_at`。如 grant 已撤销，还必须恰有一条与 grant/revoker/scope/reason/material/revoked_at 完全匹配的 `REVOKED` audit；`decided_at == revoked_at` 无法证明决定先于撤销，必须 fail-closed。决定后的合法撤销或当前到期只使当前批准失效，不改写可验证的历史事实。默认 ADMIN/PREMIUM/USER/GUEST 不隐含该权限；零个、多个、过期、撤销、错 scope、`SERVICE/UNKNOWN` 或来源不完整的 grant 均 fail-closed。issue/revoke 响应或 commit ACK 丢失时只允许按同一幂等键和完整 audit material 读回，不得重复签发/撤销；读回自身发生 DB/解析/超时异常时必须安全收口为 `UNKNOWN`，不向 API 泄露原异常或改换 operation。 |
| FR-GATE-015 | P0 | `REJECTED` 或 `REQUESTED_CHANGES` 必须在同一事务为 candidate、command/evidence package、promotion policy 与 approval policy 的精确组合建立不可变 denial fence；同一证据换审批请求或幂等键不得再次批准。当前批准解析必须在候选锁内先查该精确 scope 的 fence；只要 fence 存在就必须返回未批准，不得依赖 `decided_at` 或 UUID/ID 排序。因此同一数据库时间戳下，旧 APPROVED 即使 ID 排在负向决定之后也不得绕过 fence。精确 20 路并发的 P0 语义固定为：1 个 `REJECTED` 与 19 个 `APPROVED` 最终只能留下一个不可变 fence、零个 current approval，预先存在的 pending request 也不得绕过；`REQUESTED_CHANGES` 必须用同型负向向量重复验证。SQLite `LOCAL_T1` 必须在单进程的 20 个调用进入 `ApprovalService` 决定操作并竞争 `_operation_lock` 前用 barrier 全部报 ready、再由同一 signal 释放，只证明进程内线性化与上述语义；PostgreSQL/MySQL/MariaDB 则各自要求 20 个独立 process/connection 在尝试数据库锁与 commit 前同步释放的真实 online lane，当前均为 `NOT_RUN_CURRENT_HEAD`，不得由 SQLite、本地锁或六 worker 绿灯替代。不得通过预先提交拒绝来伪造任一层的竞争。只有新的候选、证据包或任一影响决定的策略材料产生新 scope 后才能重新申请。 |

### 6.7 证据工作台与可用性

| ID | 优先级 | 需求 |
| --- | --- | --- |
| FR-UI-001 | P0 | 页面按“预注册主张、数据与密封、实验账本、机器证据/反证、门禁与人工决定”呈现，不以单一 AI/质量分为主要结论。 |
| FR-UI-002 | P0 | 顶部状态必须显示当前候选、数据纪元、搜索预算、试验数、是否冻结、留出访问次数和下一阻断项。 |
| FR-UI-003 | P0 | 每个 FAIL/UNKNOWN/BLOCKED 项提供原因、证据定位、责任角色和下一步；不得只显示红色分数。 |
| FR-UI-004 | P0 | 数据预检必须展示执行时间、快照、过期时间和与当前表单哈希是否匹配。 |
| FR-UI-005 | P0 | 确认按钮显示将被冻结的全部差异；参数变更后立即清除确认态。 |
| FR-UI-006 | P0 | 取消/重试/继续按钮显示作用对象，防止旧任务结果覆盖当前任务。 |
| FR-UI-007 | P0 | 配置档案只允许持久化字段白名单；gateway、token、secret、credential 等仅保存密钥引用或被排除并脱敏。 |
| FR-UI-008 | P0 | 历史运行标记 `LEGACY_UNSEALED`，允许查看但不能出现“已通过密封留出”的视觉暗示。 |
| FR-UI-009 | P0 | 关键状态不只靠颜色表达；面板、对话框、表格和错误定位满足键盘操作、焦点管理和可读标签。 |
| FR-UI-010 | P1 | 支持下载脱敏证据包和按 run/candidate/trial/model 调用检索。 |
| FR-UI-011 | P0 | 页面必须显示真实生成来源、provider/model/prompt 版本、token/成本或“未调用模型”；不得用统一“AI 初稿”掩盖确定性 fallback。 |
| FR-UI-012 | P0 | 快速切换历史 run/query 或先取消 A 再启动 B 时，迟到响应只能被丢弃；最终 timeline/version/result 必须属于当前选中对象。 |
| FR-UI-013 | P1 | AI 版本支持 `Fork Draft → 编辑 → 静态/安全检查 → smoke backtest → 保存不可变版本 → 重跑全部门禁`；未重验草稿不能晋级。 |
| FR-UI-014 | P0 | 所有 stage、研究门禁、发布 Gate、错误码、按钮和空态必须走 i18n/error catalog；未知服务端错误仍须显示稳定 code 与 trace ID，不得只显示翻译后的泛化文案。审批 API 的前后端公开错误目录必须由同一版本化权威 manifest 生成或校验，code 集合必须精确相等，不得双方手写“近似集合”。公开 `code/message/details` 必须来自该精确封闭 allowlist；带动态后缀的内部 code 只能归一为登记稳定 code，任意未登记 `APPROVAL_*`、异常文本或后缀必须投影为 `RESEARCH_APPROVAL_OPERATION_FAILED`，不得因具有名称前缀就向外透传。 |
| FR-UI-015 | P0 | 浏览器审批上下文只能接收完成判断所需的安全 service DTO：候选、command、evaluation、evidence package ID、当前哈希、13 个稳定 gate reason code、审批 mode/policy、`can_request/can_decide/can_approve` 及稳定阻断 code。grant ID、actor/permission catalog、内部 URI、原始 manifest、密封指标/输入和任意未登记异常文本不得进入前端状态、toast 或 DOM。human-text 的权威处理顺序固定为：服务端先对原始 reason/challenge/risk 做规范化并计算 `decision_intent_hash`，再按字段白名单构建公开投影，并在 service DTO 边界将任意 RFC-style `scheme://`、userinfo/凭据 URI、POSIX 绝对路径、Windows drive/UNC 路径及 sealed/raw 敏感文本拒绝或投影为稳定脱敏值；不得先脱敏再计算 intent。所有外部提交/读回的 hash 字段必须在 service 边界严格是预定长度小写十六进制字符串；bytes、number、list/object 或其他错误类型不得隐式转字符串，而必须 fail-closed 为稳定通用错误。gate reason 只允许已登记 code，其他理由统一为 `RESEARCH_GATE_REASON_REDACTED`；未登记 API 错误统一为 `RESEARCH_APPROVAL_OPERATION_FAILED`。浏览器 projector 必须做第二道封闭检查，但它不是安全或 intent 权威。正常 2xx 与异常 read-back 都必须按 run/candidate/request/evidence/policy/decision 的精确 intent 对账；只比较脱敏文本、挑战 key 或风险布尔值不合格。跨语言文本 trim 语义必须锁定为 Python `str.strip()` 的精确 Unicode 码点集，不得直接用 JavaScript `trim()` 代替。 |

### 6.8 安全与隐私

| ID | 优先级 | 需求 |
| --- | --- | --- |
| FR-SEC-001 | P0 | AI 生成代码必须在受限沙箱执行，限制文件、网络、进程、凭据、CPU、内存和时间。 |
| FR-SEC-002 | P0 | 外部网页、新闻、研报、知识库文本和策略注释一律按不可信输入处理，并与系统/工具指令分隔。 |
| FR-SEC-003 | P0 | 模型工具调用使用显式 allowlist；提示注入文本不能扩大数据、文件、网络或密封留出权限。 |
| FR-SEC-004 | P0 | 秘钥不得出现在模型输入、配置档案、日志、事件 payload、研究包和前端回显；保存前执行结构化脱敏。 |
| FR-SEC-005 | P0 | 研究对象、档案、运行、trial、证据和审批必须按 user/workspace/tenant 隔离；所有详情 API 重新校验所有权。 |
| FR-SEC-006 | P0 | 模型/数据供应商调用必须记录批准的用途和最小化字段，不得把完整账户或交易凭据发给模型。 |
| FR-SEC-007 | P0 | 哈希用于完整性而非秘密保护；敏感原文加密/引用存储，导出只含允许字段。 |
| FR-SEC-008 | P1 | 对数据投毒、模型漂移和高风险提示注入建立定期红队样例库。 |
| FR-SEC-009 | P0 | 真实研究回测必须在与预检一致的隔离容器/沙箱中运行：默认断网、只读根/数据挂载、无宿主环境变量和凭据、受限 CPU/内存/PID/时长/输出；超时必须终止完整进程组或容器。 |
| FR-SEC-010 | P0 | `continuation_context`、profile、gateway 配置和任意嵌套字段在进入 LLM/tool 前必须经过 allowlist、污点分类和深层脱敏；检测到秘密时阻断并只记录脱敏审计哈希。 |
| FR-SEC-011 | P0 | 配置档案必须改为 user/workspace scoped 存储；任何认证用户不得读取、修改或删除其他用户档案，共享必须是显式授权对象。 |

### 6.9 部署能力与 fail-closed

| ID | 优先级 | 需求 |
| --- | --- | --- |
| FR-DEP-001 | P0 | 系统必须声明并运行时检测版本化部署拓扑档案，至少区分 `dev-single-process`、`single-node-isolated-services`、`multi-service`，并输出密封授权、Evaluator 隔离、真实沙箱、租户/凭据隔离和审批模式的能力矩阵。 |
| FR-DEP-002 | P0 | 当前拓扑缺少所需能力或能力证据过期时，对应研究门禁必须返回结构化 `BLOCKED_TOPOLOGY_CAPABILITY` 与缺失项，不得静默跳过、使用前端隐藏或降级成 PASS。 |
| FR-DEP-003 | P0 | SQLite、PostgreSQL、MySQL、MariaDB 四个数据库 lane 均须通过迁移与核心功能契约；MariaDB 是独立兼容 lane，不得由 MySQL 结果代替，真实 online 验收须单独留存引擎版本、schema 反射与原始输出。密封隔离和安全能力按实际进程、服务身份、存储/DB 权限、队列和凭据边界验收。SQLite 单进程默认不具备 DB-role 隔离，除非目标拓扑证明等价隔离，否则不得签发密封授权。 |

### 6.10 隐私生命周期（P1 治理债）

| ID | 优先级 | 需求 |
| --- | --- | --- |
| FR-PRIV-001 | P1 | 删除/擦除政策必须定义最小墓碑字段、artifact 与 evidence package 失效、导出排除、密钥销毁、引用完整性和审批记录；依赖已删除证据的历史 PASS 必须转为 `WITHDRAWN/UNVERIFIABLE` 投影而非继续有效。未实施前不得声称支持不可变证据与用户擦除的完整协调。物理擦除时限由部署、法律和组织政策版本决定。 |

## 7. 数据与证据完整性需求

### 7.1 必须可追溯的关系

`user/workspace → hypothesis_version → run → candidate_version → trial → dataset_snapshot/fold → model_invocation → evaluation → gate_decision → human_decision → paper/live_handoff`

任一晋级决定必须能沿此关系回溯，且每个节点具有稳定 ID、内容哈希和创建时间。

### 7.2 证据等级

| 等级 | 含义 | 可支持的声明 |
| --- | --- | --- |
| T0 | 静态结构、schema、路由、文档和测试收集 | “接口/结构存在” |
| T1 | 确定性功能、安全、失败注入与恢复证据 | “本地功能契约成立” |
| T2 | 新鲜、不可变的真实数据统计/研究证据 | “该候选在指定证据与政策下通过研究门” |
| T3 | 前向/模拟/生产运行与外部状态证据 | “指定环境和观察窗口内运行门成立” |

T0/T1 通过不得描述成 T2/T3；旧历史产物不得填充本次新鲜证据缺口。

## 8. 非功能需求

| ID | 领域 | 优先级 | 要求 |
| --- | --- | --- | --- |
| NFR-REL-001 | 一致性 | P0 | 同一任务最多一个有效 lease；关键副作用具备幂等键；终态不可回退 |
| NFR-REL-002 | 恢复 | P0 | worker 崩溃后在 `lease_ttl + poll_interval` 内可接管；无重复 trial、留出评估或决定 |
| NFR-PERF-001 | 读取 | P0 | 在验收数据规模和 20 个并发轮询下，任务/证据摘要 API p95 ≤ 300 ms；必须记录硬件、DB 和样本量 |
| NFR-PERF-002 | 写入 | P0 | 在同一基线下，单个追加事件/账本写入 p95 ≤ 200 ms；批量指标正文可异步对象化 |
| NFR-SCALE-001 | 可扩展 | P0 | run/trial/event 使用分页与索引；不得依赖加载完整历史 JSON |
| NFR-OBS-001 | 可观测 | P0 | 日志/指标按 trace_id、run_id、candidate_id、task_id、stage 关联，且不含秘密 |
| NFR-AUD-001 | 审计 | P0 | 关键事件追加式保存；更正以新事件表达；证据包可验证内容哈希 |
| NFR-SEC-001 | 安全 | P0 | 0 个未经授权密封读取、0 个密钥回显、0 个 AI 直接审批或下单路径 |
| NFR-UX-001 | 无障碍 | P0 | 核心流程键盘可完成，错误与状态有文本语义，动态进度使用适当 live region |
| NFR-COMP-001 | 兼容 | P0 | 旧运行可读；旧写路径在灰度期可双写；旧证据不自动升级为密封证据 |
| NFR-PORT-001 | 数据库/拓扑 | P0 | SQLite、PostgreSQL、MySQL、MariaDB 四个 lane 均通过迁移与核心功能合同；MariaDB 作为独立兼容 lane 单独执行真实 online 验收，不能复用 MySQL PASS。安全隔离合同只在 `FR-DEP-*` 能力矩阵允许的目标拓扑验收，不能用 SQLite 单进程绿灯外推密封隔离 |
| NFR-UX-002 | 可用性 | P1 | 封存 v1 基线，并比较完成有效提交的用户完成率、主动操作时间、错误恢复率和必要确认负担；点击数只作诊断，不能通过隐藏必要挑战优化指标 |
| NFR-DR-001 | 灾备 | P1/G5 | 数据库、对象存储和 evidence manifest 具备一致备份/恢复路径；恢复后内容哈希、引用和失效状态校验通过 |

性能数字是拟定工程目标，必须先记录当前基线；若基线显示不合理，需通过评审调整有版本的 NFR，而不是静默降低。

## 9. 配置与策略需求

- 所有门禁阈值属于 Promotion Policy，而不是硬编码前端默认值；
- 默认候选政策可采用 `DSR probability ≥ 0.95`，但 DSR 的派生 benchmark 方法、跨 trial Sharpe 方差输入合同、频率/年化约定、估计器版本、阈值和适用资产必须共同进入 Promotion Policy；SR*/benchmark 必须由账本与版本化方法派生，不允许任意手填以改变结论；数据不足时阻断；
- P1 可采用如 `PBO ≤ 0.20` 的初始政策候选，只有经过校准和评审后才能成为硬门；
- 最大迭代数、搜索空间、计算预算、留出预算和模拟盘天数均进入预注册哈希；
- 生产配置禁止关闭密封、统计、稳健性、安全和人工审批硬门；
- model alias 必须在每次调用时解析并记录实际模型标识；解析失败不得伪造版本。

## 10. 兼容、迁移与保留

| ID | 需求 |
| --- | --- |
| MIG-001 | 新旧 API 通过 `research_protocol_version` 区分；新建研究默认 v2，旧运行保持只读。 |
| MIG-002 | 灰度期对 run/event/version 执行双写或影子核对；运行前预注册差异政策：状态、身份/证据哈希、计数、研究门禁结论及超出版本化容差的数值为 `BLOCKING`，时间戳/展示文案及允许列表内语义迁移可为 `NON_BLOCKING`；所有差异均留痕，存在 BLOCKING 时 v2 不晋级。 |
| MIG-003 | 旧 workspace JSON 快照只作为迁移源/显示源，不能成为 v2 权威账本。 |
| MIG-004 | gateway JSON 等敏感字段不迁入配置档案；只迁移白名单字段并记录丢弃项。无 owner 的旧 YAML profile 必须进入 quarantine，等待管理员或用户显式认领，禁止自动归给触发迁移的当前用户。 |
| MIG-005 | 回滚只关闭 v2 新入口和 worker，不删除新表或重写历史；已生成证据保持可读。 |
| MIG-006 | 删除旧写路径需另一个明确迭代，在读取兼容、留存与回滚窗口结束后执行。 |

作为 `FR-GATE-014` 的 schema 实现合同，目标 head 必须为用户身份增加服务端所有的 `principal_kind`：数据库值限于 `HUMAN/SERVICE/UNKNOWN`、`NOT NULL`，新的交互式应用注册可由受控应用路径明确写入 `HUMAN`，但数据库 server default 和存量回填必须是 `UNKNOWN`。迁移不得从旧 role/session 静默猜测人类身份；未受控分类的历史账户在后续明确分类前不具备审批权威。partial re-entry 的类型比较不能停在通用“字符串/时间”家族：`principal_kind` 及其他宣告定长度状态/身份列必须精确反射为 `VARCHAR`及宣告长度，不得被 `TEXT`/原生 ENUM 替代；PostgreSQL 时区时间列必须是未显式覆盖 precision 的 `TIMESTAMP WITH TIME ZONE`/`timestamptz` 默认 precision；MySQL 与 MariaDB 必须分别反射为 `DATETIME` 且 `fsp=None`；SQLite 必须从 DDL/PRAGMA 区分目标 `DATETIME`、`VARCHAR` 与大文本 `TEXT`，不得用 TEXT affinity 把它们等价。

保留周期、对象存储和隐私删除必须由部署政策确定。删除用户数据时，应保留不含个人/秘密的最小审计墓碑或按法律/组织政策执行；本迭代不自行假设统一年限。

## 11. 优先级与发布门

### P0 发布必需

- FR-HYP-001～007；
- FR-DATA-001～014；
- FR-LEDGER-001～008；
- FR-PIPE-001～008、FR-PIPE-010～014；
- FR-TASK-001～009、FR-TASK-011～012；
- FR-GATE-001～008、FR-GATE-010～015；
- FR-UI-001～009、FR-UI-011～012、FR-UI-014～015；
- FR-SEC-001～007、FR-SEC-009～011；
- FR-DEP-001～003；
- 所有 P0 NFR 与 MIG-001～006。

### P1 延后不阻塞 P0

- 相似研究提醒、候选家族留出预算增强、PBO/CSCV、有效试验数、挑战者 Agent、四眼审批、研究记忆/导出、红队库扩展、高级队列调度、隐私物理擦除协调、可用性护栏和证据灾备演练。

### 三层发布判定

- **实现验收（Implementation Acceptance）**：G0～G4 的 T0/T1 契约通过、P0 偏差为 0，可称为“迭代 196 实现候选”；此时协议仍可默认关闭，不能声称真实研究/生产已通过；
- **协议生产启用（Protocol Enablement）**：在实现验收基础上完成 G5 的代表性 T2/T3、灰度和回滚，才允许对批准的资产/频率/用户范围默认启用 v2；一条样例不能证明跨范围普适；
- **单候选晋级（Candidate Promotion）**：每个 candidate 必须独立通过自己的 sealed、forward/paper 和人工决定；某候选 PASS 不证明功能实现普遍正确，功能实现 PASS 也不自动批准任何候选；
- 外部数据源、模型供应商、模拟盘和 staging/运行环境证据必须来自本次新鲜运行和明确环境身份。

## 12. 可追踪性

需求到设计和验收的逐项映射维护在：

- [DESIGN.md](DESIGN.md) 的“组件—需求映射”和“实施切片”；
- [TRACEABILITY_MATRIX.md](TRACEABILITY_MATRIX.md) 的逐 ID 需求—设计—验收—发布切片矩阵；
- [ACCEPTANCE.md](ACCEPTANCE.md) 的具名验收场景和 Gate 判定。

任何实现 PR 若不能指向至少一个需求 ID 和一个验收场景，不进入 Iteration 196 的功能范围；任何新增需求若没有验收方法，不能标为 P0。
